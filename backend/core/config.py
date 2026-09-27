"""Config loader: config.yaml + REPOMIND__section__key env overrides."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _deep_merge(base: dict, over: dict) -> dict:
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    path = Path(os.getenv("REPOMIND_CONFIG", ROOT / "config.yaml"))
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    cfg: dict[str, Any] = yaml.safe_load(path.read_text()) or {}

    for key, raw in os.environ.items():
        if not key.startswith("REPOMIND__"):
            continue
        parts = key[len("REPOMIND__"):].lower().split("__")
        try:
            value = yaml.safe_load(raw)
        except yaml.YAMLError:
            value = raw
        node = cfg
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value

    data_dir = Path(cfg.get("data_dir", "data"))
    if not data_dir.is_absolute():
        data_dir = ROOT / data_dir
    cfg["data_dir"] = str(data_dir)
    return cfg


def repos_dir(cfg: dict | None = None) -> Path:
    cfg = cfg or get_config()
    p = Path(cfg["data_dir"]) / "indexed_repos"
    p.mkdir(parents=True, exist_ok=True)
    return p
