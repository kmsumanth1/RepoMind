"""RAG orchestration: (condense) -> hybrid retrieve -> rerank -> guard -> graph expand -> generate -> cite."""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from core.config import get_config, repos_dir
from core.embedder import Embedder, embedder_from_spec
from core.index_store import RepoIndex
from generation.llm_client import LLMClient, get_llm
from generation.prompt_templates import CONDENSE_SYSTEM, NO_ANSWER_PREFIX, Source, build_prompt
from retrieval.graph_expansion import expand, graph_directions
from retrieval.hybrid_search import Hit, HybridSearcher
from retrieval.reranker import Reranker, get_reranker, rerank

log = logging.getLogger("repomind.rag")
_CITE = re.compile(r"\[(\d+)\]")
_PRONOUNS = re.compile(r"\b(it|its|this|that|these|those|they|them|there|same|above|previous|again)\b", re.I)

REFUSAL = ("I couldn't find code in this repository that answers that. Try naming a file, function or class, "
           "or rephrasing the question.")


@dataclass
class Citation:
    id: int
    file: str
    start_line: int
    end_line: int
    name: str
    kind: str
    relation: str = ""


@dataclass
class Answer:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    grounded: bool = False
    refused: bool = False
    llm: str = ""
    standalone_question: str = ""
    retrieved: int = 0
    latency_ms: int = 0


class RagEngine:
    MODES = ("dense", "bm25", "hybrid", "hybrid+rerank", "full")

    def __init__(self, index: RepoIndex, embedder: Embedder, reranker: Reranker, llm: LLMClient, cfg: dict):
        self.index, self.reranker, self.llm, self.cfg = index, reranker, llm, cfg
        self.searcher = HybridSearcher(index, embedder, cfg)

    # ---------------------------------------------------------------- retrieval
    def retrieve(self, question: str, mode: str = "full", top_k: int | None = None) -> list[Hit]:
        """Ranked hits. `mode` exists so evaluation can ablate each stage."""
        r = self.cfg["retrieval"]
        top_k = top_k or int(r["rerank_top_k"])
        base = {"dense": "dense", "bm25": "bm25"}.get(mode, "hybrid")
        hits = self.searcher.search(question, base)
        if mode in ("hybrid+rerank", "full") and r.get("rerank", True):
            hits = rerank(self.reranker, question, hits, top_k, r.get("min_relevance"))
        else:
            hits = hits[:top_k]
        if mode == "full" and r.get("graph_expansion", True):
            hits = hits + expand(self.index, hits, question, int(r.get("graph_max_added", 6)))
        return hits

    # ---------------------------------------------------------------- follow-ups
    def condense(self, question: str, history: list[dict]) -> str:
        if not history:
            return question
        if self.llm.can_chat:
            try:
                convo = "\n".join(f"{m['role']}: {m['content'][:500]}" for m in history[-6:])
                out = self.llm.chat(CONDENSE_SYSTEM, [{"role": "user", "content": f"{convo}\n\nLatest: {question}"}], 150)
                return out.strip().strip('"') or question
            except Exception as exc:
                log.warning("Question condensing failed (%s); using raw question", exc)
        last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
        return f"{last_user} {question}" if (last_user and (len(question.split()) < 7 or _PRONOUNS.search(question))) else question

    # ---------------------------------------------------------------- answering
    def answer(self, question: str, history: list[dict] | None = None) -> Answer:
        t0 = time.time()
        history = history or []
        standalone = self.condense(question, history)
        hits = self.retrieve(standalone, "full")
        core_hits = [h for h in hits if not h.relation]
        if not core_hits:
            return Answer(REFUSAL, refused=True, llm=self.llm.name, standalone_question=standalone,
                          latency_ms=int((time.time() - t0) * 1000))

        sources = [Source(n=i, path=h.chunk.path, start_line=h.chunk.start_line, end_line=h.chunk.end_line,
                          name=h.chunk.name, kind=h.chunk.kind, language=h.chunk.language, text=h.chunk.text,
                          docstring=h.chunk.docstring, relation=h.relation) for i, h in enumerate(hits, 1)]
        g = self.cfg["generation"]
        turns = int(g.get("history_turns", 6))
        prompt = build_prompt(question, sources, history[-turns:], int(g["max_context_chars"]))
        text = self.llm.answer(prompt, int(g["max_tokens"]))

        by_n = {s.n: s for s in prompt.sources}
        used = []
        for m in _CITE.finditer(text):
            n = int(m.group(1))
            if n in by_n and n not in used:
                used.append(n)
        refused = text.strip().startswith(NO_ANSWER_PREFIX)
        cites = [] if refused else [Citation(n, by_n[n].path, by_n[n].start_line, by_n[n].end_line,
                                             by_n[n].name, by_n[n].kind, by_n[n].relation) for n in used]
        return Answer(text, cites, grounded=bool(cites), refused=refused, llm=self.llm.name,
                      standalone_question=standalone, retrieved=len(prompt.sources),
                      latency_ms=int((time.time() - t0) * 1000))


# -------------------------------------------------------------------- process-wide cache
_lock = threading.Lock()
_engines: "OrderedDict[str, tuple[float, RagEngine]]" = OrderedDict()
_shared: dict = {}
MAX_LOADED = 4


def _shared_components(cfg: dict):
    with _lock:
        if "reranker" not in _shared:
            _shared["reranker"] = get_reranker(cfg)
            _shared["llm"] = get_llm(cfg)
        return _shared["reranker"], _shared["llm"]


def get_engine(repo_id: str) -> RagEngine:
    cfg = get_config()
    index_dir = repos_dir(cfg) / repo_id / "index"
    stamp = (index_dir / "meta.json").stat().st_mtime      # re-index => new mtime => reload
    with _lock:
        hit = _engines.get(repo_id)
        if hit and hit[0] == stamp:
            _engines.move_to_end(repo_id)
            return hit[1]
    index = RepoIndex.load(index_dir)
    reranker, llm = _shared_components(cfg)
    engine = RagEngine(index, embedder_from_spec(index.meta["embedder"], cfg), reranker, llm, cfg)
    with _lock:
        _engines[repo_id] = (stamp, engine)
        while len(_engines) > MAX_LOADED:
            _engines.popitem(last=False)
    return engine


def drop_engine(repo_id: str) -> None:
    with _lock:
        _engines.pop(repo_id, None)
