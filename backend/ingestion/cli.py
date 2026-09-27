"""Index a repo from the command line (no API / database needed) - handy for experiments and evaluation.

    python -m ingestion.cli tiangolo/fastapi            # clone + index -> data/indexed_repos/tiangolo__fastapi
    python -m ingestion.cli --local ./some/checkout --name my/project
"""
from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path

from core.config import get_config, repos_dir

from .clone_repo import clone_repo, parse_repo_url
from .embed_and_index import build_index


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo", nargs="?", help="GitHub URL or owner/name")
    ap.add_argument("--local", help="index an existing local directory instead of cloning")
    ap.add_argument("--name", help="display name for --local")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = get_config()

    if args.local:
        name = args.name or Path(args.local).resolve().name
        base = repos_dir(cfg) / name.replace("/", "__")
        src = Path(args.local).resolve()
        commit = ""
    elif args.repo:
        ref = parse_repo_url(args.repo)
        name = ref.full_name
        base = repos_dir(cfg) / name.replace("/", "__")
        src = base / "source"
        print(f"Cloning {ref.clone_url} ...")
        commit = clone_repo(ref, src)
    else:
        ap.error("give a repo or --local")

    if args.local:                       # keep the layout <base>/source + <base>/index
        if (base / "source").exists():
            shutil.rmtree(base / "source")
        shutil.copytree(src, base / "source", ignore=shutil.ignore_patterns(".git"))
        src = base / "source"
    meta = build_index(src, base / "index", cfg, repo_name=name, commit=commit,
                       progress=lambda stage, pct, msg: print(f"[{pct:3d}%] {msg}"))
    print(f"\nDone: {meta['num_files']} files, {meta['num_chunks']} chunks, {meta['graph_edges']} call edges, "
          f"embedder={meta['embedder']['backend']} -> {base}")


if __name__ == "__main__":
    main()
