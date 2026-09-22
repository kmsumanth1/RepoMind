"""Hybrid retrieval: dense (FAISS) + sparse (BM25) + exact-identifier lookup, fused with
weighted Reciprocal Rank Fusion."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.embedder import Embedder
from core.index_store import RepoIndex
from core.types import Chunk

_FILE_TOKEN = re.compile(r"[\w./-]+\.(?:py|js|jsx|ts|tsx|go|rs|java|kt|rb|php|cs|md|toml|ya?ml|json|sh)\b")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_KIND_RANK = {"module": 0, "class": 1, "doc": 1, "function": 2, "method": 3, "text": 4}


@dataclass
class Hit:
    pos: int
    chunk: Chunk
    score: float = 0.0
    ranks: dict[str, int] = field(default_factory=dict)   # channel -> 1-based rank
    relevance: float = 0.0                                 # set by the reranker, in [0, 1]
    relation: str = ""                                     # set by graph expansion


def extract_symbols(question: str) -> list[str]:
    """Identifier-looking tokens: `backticked`, snake_case, dotted.names, CamelCase, or Capitalised
    words that are not sentence-initial. Plain English words are ignored to avoid false matches."""
    found: list[str] = []
    for m in re.findall(r"`([^`]+)`", question):
        found.append(m.strip().rstrip("()"))
    for i, m in enumerate(_WORD.finditer(question)):
        tok = m.group(0).strip(".")
        if len(tok) < 3:
            continue
        internal_cap = any(ch.isupper() for ch in tok[1:])
        if "_" in tok or "." in tok or internal_cap or (tok[0].isupper() and i > 0):
            found.append(tok)
    seen, out = set(), []
    for f in found:
        k = f.lower()
        if k and k not in seen:
            seen.add(k)
            out.append(f)
    return out


class HybridSearcher:
    def __init__(self, index: RepoIndex, embedder: Embedder, cfg: dict):
        self.index, self.embedder = index, embedder
        r = cfg["retrieval"]
        self.dense_k, self.sparse_k = int(r["dense_k"]), int(r["sparse_k"])
        self.fused_k, self.rrf_k = int(r["fused_k"]), int(r["rrf_k"])
        self.symbol_weight = float(r.get("symbol_weight", 2.0))

    # ---- channels ----
    def dense(self, query: str, k: int | None = None) -> list[int]:
        q = self.embedder.encode([query], is_query=True)[0]
        return [p for p, _ in self.index.dense_search(q, k or self.dense_k)]

    def sparse(self, query: str, k: int | None = None) -> list[int]:
        return [p for p, _ in self.index.bm25_search(query, k or self.sparse_k)]

    def symbols(self, query: str) -> list[int]:
        out: list[int] = []
        for tok in extract_symbols(query):
            out.extend(self.index.name_index.get(tok.lower(), []))
            out.extend(self.index.name_index.get(tok.lower().split(".")[-1], []))
        for m in _FILE_TOKEN.findall(query):
            hits = [p for path, ps in self.index.file_index.items() if path == m or path.endswith("/" + m) for p in ps]
            hits.sort(key=lambda p: (_KIND_RANK.get(self.index.chunks[p].kind, 5), self.index.chunks[p].start_line))
            out.extend(hits[:8])
        return list(dict.fromkeys(out))

    # ---- fusion ----
    def search(self, query: str, mode: str = "hybrid") -> list[Hit]:
        """mode: dense | bm25 | hybrid"""
        channels: dict[str, tuple[list[int], float]] = {}
        if mode in ("dense", "hybrid"):
            channels["dense"] = (self.dense(query), 1.0)
        if mode in ("bm25", "hybrid"):
            channels["bm25"] = (self.sparse(query), 1.0)
        if mode == "hybrid":
            sym = self.symbols(query)
            if sym:
                channels["symbol"] = (sym, self.symbol_weight)
        scores: dict[int, float] = {}
        ranks: dict[int, dict[str, int]] = {}
        for name, (ids, weight) in channels.items():
            for rank, pos in enumerate(ids, 1):
                scores[pos] = scores.get(pos, 0.0) + weight / (self.rrf_k + rank)
                ranks.setdefault(pos, {})[name] = rank
        top = sorted(scores, key=lambda p: -scores[p])[: self.fused_k]
        return [Hit(pos=p, chunk=self.index.chunks[p], score=scores[p], ranks=ranks[p]) for p in top]
