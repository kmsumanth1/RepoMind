"""Clone a public GitHub repository and collect indexable source files."""
from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?:/.*)?$")
_SHORT_RE = re.compile(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?$")

LANGUAGES = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".java": "java", ".kt": "kotlin", ".go": "go",
    ".rs": "rust", ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp", ".cs": "csharp",
    ".rb": "ruby", ".php": "php", ".swift": "swift", ".scala": "scala", ".sh": "shell",
    ".md": "markdown", ".rst": "rst", ".txt": "text", ".toml": "toml", ".yaml": "yaml", ".yml": "yaml",
    ".json": "json", ".cfg": "ini", ".ini": "ini", ".sql": "sql", ".proto": "proto",
}
SPECIAL_NAMES = {"Dockerfile": "dockerfile", "Makefile": "makefile"}
_LOCALE_DIR = re.compile(r"^[a-z]{2}(?:[-_][A-Za-z]{2,4})?$")


def _drop_translation_dirs(dirnames: list[str]) -> list[str]:
    """Docs trees like docs/en, docs/zh, docs/ru, ... hold the same content in many languages and would
    drown real answers in near-duplicates. Keep `en`; drop the locale siblings (needs >=3 of them, so a
    lone `en`/`ui` pair is never touched)."""
    if "en" not in dirnames:
        return dirnames
    locales = [d for d in dirnames if d != "en" and _LOCALE_DIR.match(d)]
    return dirnames if len(locales) < 3 else [d for d in dirnames if d not in locales]


@dataclass
class RepoRef:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}.git"

    @property
    def web_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}"


def parse_repo_url(s: str) -> RepoRef:
    s = s.strip().rstrip("/")
    m = _URL_RE.match(s) or _SHORT_RE.match(s)
    if not m:
        raise ValueError("Enter a public GitHub repository URL like https://github.com/owner/name")
    owner, name = m.group(1), m.group(2)
    if set(owner) <= {"."} or set(name) <= {"."}:
        raise ValueError("Invalid repository name")
    return RepoRef(owner, name)


def clone_repo(ref: RepoRef, dest: Path, timeout: int = 600) -> str:
    """Shallow-clone into `dest` (replacing it), strip .git, return the commit SHA.
    Public repos only - we deliberately never attach credentials."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    cmd = ["git", "-c", "core.symlinks=false", "clone", "--depth", "1", "--single-branch", "--no-tags",
           "--", ref.clone_url, str(dest)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("Cloning timed out") from e
    if proc.returncode != 0:
        msg = (proc.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
        raise RuntimeError(f"Could not clone {ref.full_name}: {msg[0]}")
    sha = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    shutil.rmtree(dest / ".git", ignore_errors=True)
    return sha


@dataclass
class SourceFile:
    path: str        # posix path relative to repo root
    language: str
    size: int


def collect_files(root: Path, cfg: dict) -> list[SourceFile]:
    ing = cfg["ingestion"]
    exclude_dirs = set(ing["exclude_dirs"])
    globs = ing.get("exclude_globs", [])
    max_bytes, max_files = int(ing["max_file_bytes"]), int(ing["max_files"])
    skip_translations = bool(ing.get("skip_translations", True))
    found: list[SourceFile] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in exclude_dirs and not (Path(dirpath) / d).is_symlink())
        if skip_translations:
            dirnames[:] = _drop_translation_dirs(dirnames)
        for fn in sorted(filenames):
            full = Path(dirpath) / fn
            if full.is_symlink():
                continue
            rel = full.relative_to(root).as_posix()
            lang = SPECIAL_NAMES.get(fn) or LANGUAGES.get(full.suffix.lower())
            if not lang or any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(fn, g) for g in globs):
                continue
            try:
                size = full.stat().st_size
                if size == 0 or size > max_bytes:
                    continue
                with full.open("rb") as f:
                    if b"\x00" in f.read(2048):
                        continue
            except OSError:
                continue
            found.append(SourceFile(rel, lang, size))
            if len(found) >= max_files:
                return found
    return found
