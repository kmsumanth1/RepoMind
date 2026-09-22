"""Turn a cloned source tree into a searchable index (chunks + vectors + BM25 inputs + graph)."""
from __future__ import annotations

import logging
import shutil
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from core.embedder import Embedder, embedder_for_indexing
from core.index_store import write_index
from core.types import Chunk

from .ast_chunker import chunk_file
from .clone_repo import collect_files
from .graph_builder import build_graph

log = logging.getLogger("repomind.index")
Progress = Callable[[str, int, str], None]


def embed_chunks(chunks: list[Chunk], embedder: Embedder, batch_size: int = 64,
                 on_batch: Callable[[int, int], None] | None = None) -> np.ndarray:
    if not chunks:
        return np.zeros((0, embedder.dim), dtype=np.float32)
    parts = []
    for i in range(0, len(chunks), batch_size):
        parts.append(embedder.encode([c.embedding_text() for c in chunks[i:i + batch_size]]))
        if on_batch:
            on_batch(min(i + batch_size, len(chunks)), len(chunks))
    return np.vstack(parts).astype(np.float32)


def build_index(source_dir: Path, index_dir: Path, cfg: dict, *, repo_name: str = "",
                commit: str = "", progress: Progress | None = None,
                embedder: Embedder | None = None) -> dict:
    """Parse -> chunk -> graph -> embed -> write. `index_dir` is replaced atomically."""
    say = progress or (lambda stage, pct, msg: None)
    t0 = time.time()

    say("parsing", 20, "Scanning files")
    files = collect_files(source_dir, cfg)
    if not files:
        raise RuntimeError("No indexable source files found in this repository")

    chunks: list[Chunk] = []
    kept: list[dict] = []
    for n, sf in enumerate(files, 1):
        try:
            text = (source_dir / sf.path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        file_chunks = chunk_file(sf.path, text, sf.language, cfg)
        if file_chunks:
            chunks.extend(file_chunks)
            kept.append({"path": sf.path, "language": sf.language, "lines": text.count("\n") + 1})
        if n % 50 == 0:
            say("parsing", 20 + int(20 * n / len(files)), f"Parsed {n}/{len(files)} files")
    if not chunks:
        raise RuntimeError("Repository contained no parseable code")

    say("graph", 42, "Building call graph")
    graph = build_graph(chunks)

    embedder = embedder or embedder_for_indexing(cfg)
    say("embedding", 45, f"Embedding {len(chunks)} chunks")
    bs = int(cfg["embedding"].get("batch_size", 32))
    vectors = embed_chunks(
        chunks, embedder, batch_size=bs,
        on_batch=lambda done, total: say("embedding", 45 + int(50 * done / total), f"Embedded {done}/{total} chunks"))

    say("saving", 96, "Writing index")
    meta = {
        "repo": repo_name, "commit": commit, "created_at": datetime.now(timezone.utc).isoformat(),
        "embedder": embedder.spec, "num_files": len(kept), "num_chunks": len(chunks),
        "languages": dict(Counter(f["language"] for f in kept)),
        "graph_edges": sum(len(v) for v in graph["callees"].values()),
        "build_seconds": round(time.time() - t0, 1),
    }
    tmp = index_dir.parent / (index_dir.name + ".building")
    if tmp.exists():
        shutil.rmtree(tmp)
    write_index(tmp, meta, chunks, vectors, graph, kept)
    if index_dir.exists():
        shutil.rmtree(index_dir)
    tmp.rename(index_dir)
    say("ready", 100, "Indexed")
    log.info("Indexed %s: %d files, %d chunks in %.1fs", repo_name, len(kept), len(chunks), meta["build_seconds"])
    return meta
