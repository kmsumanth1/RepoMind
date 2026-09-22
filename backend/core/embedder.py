"""Embedding backends.

* SentenceTransformerEmbedder - real semantic embeddings (bge / e5 / code models).
* HashingEmbedder            - deterministic feature-hashing vectors. Not semantic, but needs no
                               download, so tests / offline dev / CI work. Recorded per repo so a
                               repo is always queried with the same embedder it was indexed with.
"""
from __future__ import annotations

import logging
import math
import zlib
from functools import lru_cache

import numpy as np

from .text import tokenize

log = logging.getLogger("repomind.embedder")

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder:
    dim: int
    spec: dict

    def encode(self, texts: list[str], is_query: bool = False) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError


class HashingEmbedder(Embedder):
    def __init__(self, dim: int = 768):
        self.dim = dim
        self.spec = {"backend": "hashing", "dim": dim}
        self._cache: dict[str, tuple[int, float]] = {}

    def _slot(self, tok: str) -> tuple[int, float]:
        hit = self._cache.get(tok)
        if hit is None:
            h = zlib.crc32(tok.encode())
            hit = (h % self.dim, 1.0 if (h >> 31) & 1 else -1.0)
            self._cache[tok] = hit
        return hit

    def encode(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            toks = tokenize(text, query=is_query)
            counts: dict[str, int] = {}
            for t in toks:
                counts[t] = counts.get(t, 0) + 1
            for t, c in counts.items():
                idx, sign = self._slot(t)
                out[i, idx] += sign * (1.0 + math.log(c))
            for a, b in zip(toks, toks[1:]):          # light phrase signal
                idx, sign = self._slot(a + "_" + b)
                out[i, idx] += 0.5 * sign
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return out / norms


class SentenceTransformerEmbedder(Embedder):
    def __init__(self, model: str, batch_size: int = 32):
        from sentence_transformers import SentenceTransformer  # heavy import, keep lazy

        self.model_name = model
        self.batch_size = batch_size
        self.model = SentenceTransformer(model)
        self.dim = int(self.model.get_sentence_embedding_dimension())
        self.query_prefix = BGE_QUERY_PREFIX if "bge" in model.lower() and "-en" in model.lower() else ""
        self.spec = {"backend": "sentence-transformers", "model": model, "dim": self.dim}

    def encode(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        if is_query and self.query_prefix:
            texts = [self.query_prefix + t for t in texts]
        vecs = self.model.encode(
            texts, batch_size=self.batch_size, normalize_embeddings=True,
            show_progress_bar=False, convert_to_numpy=True,
        )
        return vecs.astype(np.float32)


@lru_cache(maxsize=8)
def _cached(backend: str, model: str, dim: int, batch_size: int) -> Embedder:
    if backend == "hashing":
        return HashingEmbedder(dim)
    if backend == "sentence-transformers":
        return SentenceTransformerEmbedder(model, batch_size)
    raise ValueError(f"Unknown embedding backend: {backend}")


def embedder_for_indexing(cfg: dict) -> Embedder:
    """Embedder used when building a new index (may fall back to hashing, and says so)."""
    e = cfg["embedding"]
    try:
        return _cached(e["backend"], e.get("model", ""), int(e.get("hashing_dim", 768)), int(e.get("batch_size", 32)))
    except Exception as exc:  # missing package, model download blocked, ...
        if e.get("fallback_to_hashing", True) and e["backend"] != "hashing":
            log.warning("Embedding backend %r unavailable (%s); falling back to hashing embedder. "
                        "Retrieval quality will be much lower.", e["backend"], exc)
            return _cached("hashing", "", int(e.get("hashing_dim", 768)), 0)
        raise


def embedder_from_spec(spec: dict, cfg: dict) -> Embedder:
    """Embedder matching an existing index (no silent fallback: dimensions must agree)."""
    e = cfg["embedding"]
    return _cached(spec["backend"], spec.get("model", ""), int(spec.get("dim", e.get("hashing_dim", 768))),
                   int(e.get("batch_size", 32)))
