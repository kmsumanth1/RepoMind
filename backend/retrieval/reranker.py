"""Second-stage relevance scoring. Scores are normalised to [0, 1] so one threshold can drive the
"no relevant code found" guardrail regardless of backend."""
from __future__ import annotations

import logging
import math

from core.text import tokenize

from .hybrid_search import Hit, extract_symbols

log = logging.getLogger("repomind.reranker")


class Reranker:
    name = "base"
    default_min_relevance = 0.1

    def score(self, query: str, hits: list[Hit]) -> list[float]:  # pragma: no cover
        raise NotImplementedError


class CrossEncoderReranker(Reranker):
    name = "cross-encoder"
    default_min_relevance = 0.05

    def __init__(self, model: str):
        from sentence_transformers import CrossEncoder  # lazy, heavy

        self.model = CrossEncoder(model, max_length=512)

    def score(self, query: str, hits: list[Hit]) -> list[float]:
        pairs = [(query, h.chunk.embedding_text()[:2000]) for h in hits]
        raw = self.model.predict(pairs, show_progress_bar=False)
        return [1.0 / (1.0 + math.exp(-float(x))) for x in raw]


class LexicalReranker(Reranker):
    """Cheap fallback: weighted query-term coverage (name > path > body) + exact-symbol bonus."""
    name = "lexical"
    default_min_relevance = 0.15

    def score(self, query: str, hits: list[Hit]) -> list[float]:
        q = set(tokenize(query, query=True))
        syms = {s.lower() for s in extract_symbols(query)}
        if not q:
            return [0.0] * len(hits)
        out = []
        for h in hits:
            c = h.chunk
            name_t, path_t, body_t = set(tokenize(c.name)), set(tokenize(c.path)), set(tokenize(c.text))
            got = sum(2.0 if t in name_t else 1.5 if t in path_t else 1.0 if t in body_t else 0.0 for t in q)
            s = got / (2.0 * len(q))
            if c.name.lower() in syms or c.name.split(".")[-1].lower() in syms:
                s += 0.5
            out.append(min(1.0, s))
        return out


def get_reranker(cfg: dict) -> Reranker:
    r = cfg["retrieval"]
    if r.get("reranker_backend") == "cross-encoder":
        try:
            return CrossEncoderReranker(r["reranker_model"])
        except Exception as exc:
            log.warning("Cross-encoder reranker unavailable (%s); using lexical reranker.", exc)
    return LexicalReranker()


def rerank(reranker: Reranker, query: str, hits: list[Hit], top_k: int, min_relevance: float | None = None) -> list[Hit]:
    """Score, sort, drop weak matches, keep top_k."""
    if not hits:
        return []
    for h, s in zip(hits, reranker.score(query, hits)):
        h.relevance = s
    threshold = reranker.default_min_relevance if min_relevance is None else min_relevance
    ranked = sorted(hits, key=lambda h: -h.relevance)
    return [h for h in ranked if h.relevance >= threshold][:top_k]
