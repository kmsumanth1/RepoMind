"""On-disk + in-memory representation of one indexed repository.

index/ layout:  meta.json  chunks.jsonl  vectors.npy  graph.json  files.json
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import numpy as np

from .text import tokenize
from .types import Chunk

try:  # FAISS is optional at runtime: falls back to a numpy dot product
    import faiss  # type: ignore
except Exception:  # pragma: no cover
    faiss = None

DEF_KINDS = ("function", "method", "class")


def write_index(index_dir: Path, meta: dict, chunks: list[Chunk], vectors: np.ndarray,
                graph: dict, files: list[dict]) -> None:
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    with (index_dir / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c.to_dict()) + "\n")
    np.save(index_dir / "vectors.npy", vectors.astype(np.float32))
    (index_dir / "graph.json").write_text(json.dumps(graph))
    (index_dir / "files.json").write_text(json.dumps(files))


class RepoIndex:
    def __init__(self, root: Path, meta: dict, chunks: list[Chunk], vectors: np.ndarray,
                 graph: dict, files: list[dict]):
        self.root = root                      # <repo_dir>/index
        self.source_dir = root.parent / "source"
        self.meta, self.chunks, self.vectors, self.graph, self.files = meta, chunks, vectors, graph, files
        self.by_id = {c.id: i for i, c in enumerate(chunks)}
        self.by_symbol: dict[str, list[int]] = {}
        self.name_index: dict[str, list[int]] = {}
        self.file_index: dict[str, list[int]] = {}
        for i, c in enumerate(chunks):
            self.by_symbol.setdefault(c.symbol, []).append(i)
            self.file_index.setdefault(c.path, []).append(i)
            if c.kind in DEF_KINDS and c.part == 0:
                for key in {c.name.lower(), c.name.split(".")[-1].lower()}:
                    self.name_index.setdefault(key, []).append(i)
        self._bm25 = None
        self._faiss = None
        self._lock = threading.Lock()

    @classmethod
    def load(cls, root: Path) -> "RepoIndex":
        meta = json.loads((root / "meta.json").read_text())
        with (root / "chunks.jsonl").open(encoding="utf-8") as f:
            chunks = [Chunk(**json.loads(line)) for line in f if line.strip()]
        vectors = np.load(root / "vectors.npy")
        graph = json.loads((root / "graph.json").read_text())
        files = json.loads((root / "files.json").read_text())
        if len(chunks) != len(vectors):
            raise ValueError("Corrupt index: chunk/vector count mismatch")
        return cls(root, meta, chunks, vectors, graph, files)

    # ---- dense ----
    def dense_search(self, qvec: np.ndarray, k: int) -> list[tuple[int, float]]:
        k = min(k, len(self.chunks))
        if k == 0:
            return []
        q = qvec.astype(np.float32).reshape(1, -1)
        if faiss is not None:
            with self._lock:
                if self._faiss is None:
                    idx = faiss.IndexFlatIP(self.vectors.shape[1])
                    idx.add(np.ascontiguousarray(self.vectors))
                    self._faiss = idx
            scores, ids = self._faiss.search(q, k)
            return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i >= 0]
        scores = self.vectors @ q[0]
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(int(i), float(scores[i])) for i in top]

    # ---- sparse ----
    def bm25_search(self, query: str, k: int) -> list[tuple[int, float]]:
        from rank_bm25 import BM25Okapi

        with self._lock:
            if self._bm25 is None:
                self._bm25 = BM25Okapi([tokenize(c.bm25_text()) or ["_"] for c in self.chunks])
        q = tokenize(query, query=True)
        if not q:
            return []
        scores = self._bm25.get_scores(q)
        k = min(k, len(scores))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(int(i), float(scores[i])) for i in top if scores[i] > 0]
