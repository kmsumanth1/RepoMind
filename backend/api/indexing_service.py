"""Background repo indexing: clone -> chunk -> graph -> embed -> swap into place, reporting progress
to the `repos` row so the frontend can poll GET /repos/{id}."""
from __future__ import annotations

import logging
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from core.config import get_config, repos_dir
from ingestion.clone_repo import clone_repo, parse_repo_url
from ingestion.embed_and_index import build_index
from rag.engine import drop_engine

from .db import SessionLocal
from .models import Repo

log = logging.getLogger("repomind.indexing")
_executor: ThreadPoolExecutor | None = None
IN_PROGRESS = ("queued", "cloning", "parsing", "graph", "embedding", "saving")


def _pool() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=int(get_config()["indexing"]["max_workers"]),
                                       thread_name_prefix="indexer")
    return _executor


def _update(repo_id: str, **fields) -> None:
    with SessionLocal() as db:
        repo = db.get(Repo, repo_id)
        if repo:
            for k, v in fields.items():
                setattr(repo, k, v)
            db.commit()


def submit(repo_id: str) -> None:
    _pool().submit(_run, repo_id)


def _run(repo_id: str) -> None:
    cfg = get_config()
    with SessionLocal() as db:
        repo = db.get(Repo, repo_id)
        if not repo:
            return
        url, name = repo.url, repo.display_name
    base = repos_dir(cfg) / repo_id
    work = base / "work"
    try:
        _update(repo_id, status="cloning", progress=5, message="Cloning repository", error=None)
        if work.exists():
            shutil.rmtree(work)
        sha = clone_repo(parse_repo_url(url), work / "source", int(cfg["indexing"]["clone_timeout_seconds"]))
        _update(repo_id, progress=15, message="Cloned")

        last = {"stage": "", "pct": -1}

        def progress(stage: str, pct: int, msg: str) -> None:      # only write to the DB when something visible changed
            if stage != "ready" and (stage != last["stage"] or pct != last["pct"]):
                last.update(stage=stage, pct=pct)
                _update(repo_id, status=stage, progress=min(pct, 99), message=msg)

        meta = build_index(work / "source", work / "index", cfg, repo_name=name, commit=sha, progress=progress)

        for part in ("source", "index"):                  # swap the fresh copy in
            if (base / part).exists():
                shutil.rmtree(base / part)
            (work / part).rename(base / part)
        shutil.rmtree(work, ignore_errors=True)
        drop_engine(repo_id)
        _update(repo_id, status="ready", progress=100, message="Ready", commit_sha=sha,
                file_count=meta["num_files"], chunk_count=meta["num_chunks"],
                indexed_at=datetime.now(timezone.utc))
    except Exception as exc:  # noqa: BLE001 - surface any failure to the user
        log.exception("Indexing %s failed", repo_id)
        shutil.rmtree(work, ignore_errors=True)
        had_index = (base / "index" / "meta.json").exists()
        # if an older index is still intact, keep serving it and just report the failed refresh
        _update(repo_id, status="ready" if had_index else "failed", progress=100 if had_index else 0,
                message="Re-index failed; serving previous index" if had_index else "Failed",
                error=str(exc)[:500])


def recover_interrupted() -> None:
    """Jobs that were running when the server stopped will never finish; mark them failed."""
    with SessionLocal() as db:
        for repo in db.query(Repo).filter(Repo.status.in_(IN_PROGRESS)).all():
            repo.status, repo.message, repo.error = "failed", "Interrupted", "Indexing was interrupted by a server restart"
        db.commit()
