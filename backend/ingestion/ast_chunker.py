"""Structure-aware chunking.

Python  -> real AST: one chunk per function / method / class (decorators + docstring kept together).
           Big classes become a header chunk + one chunk per method. Module-level code between
           definitions (imports, constants, `app = FastAPI()`) becomes `module` chunks.
Other   -> boundary heuristics per language (function/class declarations) - a pragmatic stand-in
           for tree-sitter, which can be dropped in behind `chunk_file`.
Markdown-> one chunk per heading section.  Everything else -> overlapping line windows.
"""
from __future__ import annotations

import ast
import re
from pathlib import PurePosixPath

from core.types import Chunk

# ------------------------------------------------------------------ helpers

def _windows(start: int, end: int, max_lines: int, overlap: int) -> list[tuple[int, int]]:
    if end - start + 1 <= max_lines:
        return [(start, end)]
    out, s = [], start
    step = max(1, max_lines - overlap)
    while s <= end:
        e = min(end, s + max_lines - 1)
        out.append((s, e))
        if e == end:
            break
        s += step
    return out


class _Builder:
    def __init__(self, path: str, language: str, lines: list[str], cfg: dict):
        self.path, self.language, self.lines = path, language, lines
        c = cfg["chunking"]
        self.max_lines = int(c["max_chunk_lines"])
        self.overlap = int(c["window_overlap_lines"])
        self.min_chars = int(c["min_chunk_chars"])
        self.chunks: list[Chunk] = []
        self._seen: set[str] = set()

    def add(self, start: int, end: int, kind: str, name: str, doc: str = "",
            calls: list[str] | None = None, bases: list[str] | None = None) -> None:
        for part, (s, e) in enumerate(_windows(start, end, self.max_lines, self.overlap)):
            text = "\n".join(self.lines[s - 1:e])
            if len(text.strip()) < self.min_chars:
                continue
            cid = f"{self.path}:{s}-{e}"
            while cid in self._seen:
                cid += "#"
            self._seen.add(cid)
            self.chunks.append(Chunk(id=cid, path=self.path, start_line=s, end_line=e, kind=kind, name=name,
                                     language=self.language, text=text, docstring=doc,
                                     calls=calls or [], bases=bases or [], part=part))


# ------------------------------------------------------------------ python

_STRUCTURAL = re.compile(r"^\s*(try|else|finally|except\b.*|if\b.*|elif\b.*|with\b.*|for\b.*|while\b.*)\s*:\s*$")


def _expr_name(e: ast.AST) -> str:
    if isinstance(e, ast.Name):
        return e.id
    if isinstance(e, ast.Attribute):
        return e.attr
    if isinstance(e, ast.Subscript):
        return _expr_name(e.value)
    if isinstance(e, ast.Call):
        return _expr_name(e.func)
    return ""


def _calls(node: ast.AST) -> list[str]:
    names = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            nm = _expr_name(n.func)
            if nm:
                names.add(nm)
    return sorted(names)


def _span(node: ast.AST) -> tuple[int, int]:
    decos = getattr(node, "decorator_list", [])
    return min([node.lineno] + [d.lineno for d in decos]), node.end_lineno  # type: ignore[attr-defined]


def _has_defs(nodes: list[ast.stmt]) -> bool:
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for n in nodes)


def _sub_bodies(node: ast.stmt) -> list[list[ast.stmt]]:
    if isinstance(node, ast.If):
        return [node.body, node.orelse]
    if isinstance(node, ast.Try):
        return [node.body, *[h.body for h in node.handlers], node.orelse, node.finalbody]
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return [node.body]
    return []


def _chunk_python(path: str, text: str, cfg: dict) -> list[Chunk]:
    lines = text.splitlines()
    tree = ast.parse(text)
    b = _Builder(path, "python", lines, cfg)
    class_split = int(cfg["chunking"]["class_split_lines"])
    covered = [False] * (len(lines) + 2)

    def mark(s: int, e: int) -> None:
        for i in range(s, e + 1):
            covered[i] = True

    def function(node, prefix: str, is_method: bool) -> None:
        s, e = _span(node)
        mark(s, e)
        b.add(s, e, "method" if is_method else "function", f"{prefix}{node.name}",
              ast.get_docstring(node) or "", _calls(node))

    def klass(node: ast.ClassDef, prefix: str) -> None:
        s, e = _span(node)
        qual = f"{prefix}{node.name}"
        bases = [n for n in (_expr_name(x) for x in node.bases) if n]
        doc = ast.get_docstring(node) or ""
        mark(s, e)
        if e - s + 1 <= class_split:
            b.add(s, e, "class", qual, doc, _calls(node), bases)
            return
        members = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        header_end = (min(_span(m)[0] for m in members) - 1) if members else e
        b.add(s, max(s, header_end), "class", qual, doc, [], bases)
        for m in members:
            if isinstance(m, ast.ClassDef):
                klass(m, f"{qual}.")
            else:
                function(m, f"{qual}.", True)

    def visit(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function(node, "", False)
            elif isinstance(node, ast.ClassDef):
                klass(node, "")
            else:
                for sub in _sub_bodies(node):
                    if _has_defs(sub):
                        visit(sub)

    visit(tree.body)

    # module-level code = the uncovered gaps between definitions
    stem = PurePosixPath(path).stem
    i, n = 1, len(lines)
    while i <= n:
        if covered[i]:
            i += 1
            continue
        j = i
        while j + 1 <= n and not covered[j + 1]:
            j += 1
        seg = [ln for ln in lines[i - 1:j] if ln.strip()]
        code = [ln for ln in seg if not ln.strip().startswith("#") and not _STRUCTURAL.match(ln)]
        if code:
            s, e = i, j
            while s < e and not lines[s - 1].strip():
                s += 1
            while e > s and not lines[e - 1].strip():
                e -= 1
            b.add(s, e, "module", f"<module {stem}>", "", [])
        i = j + 1
    b.chunks.sort(key=lambda c: (c.start_line, c.part))
    return b.chunks


# ------------------------------------------------------------------ other languages

_JS = [("function", r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\*?\s+([A-Za-z_$][\w$]*)"),
       ("class", r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)"),
       ("function", r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[\w$]+)\s*(?::[^=]+)?=>"),
       ("class", r"^\s*(?:export\s+)?(?:interface|enum)\s+([A-Za-z_$][\w$]*)")]
_JAVA_MODS = r"(?:(?:public|private|protected|static|final|abstract|synchronized|override|internal|open|sealed|data)\s+)"
_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "javascript": _JS, "typescript": _JS,
    "go": [("function", r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)"),
           ("class", r"^type\s+([A-Za-z_]\w*)\s+(?:struct|interface)")],
    "rust": [("function", r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+([A-Za-z_]\w*)"),
             ("class", r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait)\s+([A-Za-z_]\w*)"),
             ("class", r"^\s*impl(?:<[^>]*>)?\s+(?:[\w:<>]+\s+for\s+)?([A-Za-z_]\w*)")],
    "java": [("class", rf"^\s*{_JAVA_MODS}*(?:class|interface|enum|record)\s+([A-Za-z_]\w*)"),
             ("function", rf"^\s*{_JAVA_MODS}+[\w<>\[\],.?]+\s+([A-Za-z_]\w*)\s*\(")],
    "kotlin": [("class", rf"^\s*{_JAVA_MODS}*(?:class|interface|object|enum class)\s+([A-Za-z_]\w*)"),
               ("function", r"^\s*(?:[a-z]+\s+)*fun\s+(?:<[^>]*>\s*)?(?:[\w.]+\.)?([A-Za-z_]\w*)")],
    "csharp": [("class", rf"^\s*{_JAVA_MODS}*(?:class|interface|struct|enum|record)\s+([A-Za-z_]\w*)"),
               ("function", rf"^\s*{_JAVA_MODS}+[\w<>\[\],.?]+\s+([A-Za-z_]\w*)\s*\(")],
    "ruby": [("function", r"^\s*def\s+(?:self\.)?([A-Za-z_]\w*[?!]?)"), ("class", r"^\s*(?:class|module)\s+([A-Za-z_]\w*)")],
    "php": [("function", r"^\s*(?:(?:public|private|protected|static)\s+)*function\s+([A-Za-z_]\w*)"),
            ("class", r"^\s*(?:abstract\s+|final\s+)?(?:class|interface|trait)\s+([A-Za-z_]\w*)")],
    "scala": [("function", r"^\s*(?:(?:override|private|protected|final)\s+)*def\s+([A-Za-z_]\w*)"),
              ("class", r"^\s*(?:case\s+|abstract\s+|sealed\s+)*(?:class|object|trait)\s+([A-Za-z_]\w*)")],
    "swift": [("function", r"^\s*(?:(?:public|private|internal|static|override)\s+)*func\s+([A-Za-z_]\w*)"),
              ("class", r"^\s*(?:(?:public|private|internal|final)\s+)*(?:class|struct|enum|protocol)\s+([A-Za-z_]\w*)")],
    "shell": [("function", r"^\s*(?:function\s+)?([A-Za-z_][\w-]*)\s*\(\)\s*\{?")],
}
_PATTERNS = {lang: [(k, re.compile(p)) for k, p in pats] for lang, pats in _PATTERNS.items()}
_COMMENT_PREFIX = ("//", "/*", "*", "#", "@", "///", "--")
_CALL_RE = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")
_NOT_CALLS = {"if", "for", "while", "switch", "catch", "function", "return", "sizeof", "typeof", "def", "fn",
              "func", "elif", "match", "with", "new", "await", "assert", "super", "print"}
_EXT_RE = re.compile(r"\b(?:extends|implements|:)\s+([A-Z][\w.]*)")


def _chunk_generic(path: str, lines: list[str], language: str, cfg: dict) -> list[Chunk]:
    pats = _PATTERNS.get(language)
    b = _Builder(path, language, lines, cfg)
    n = len(lines)
    if not pats or n == 0:
        return _chunk_text(path, lines, language, cfg)
    starts: list[tuple[int, str, str, int]] = []
    for i, line in enumerate(lines, 1):
        for kind, rx in pats:
            m = rx.match(line)
            if m:
                s = i
                while s > 1 and lines[s - 2].strip().startswith(_COMMENT_PREFIX):   # attach leading doc-comments/decorators
                    s -= 1
                starts.append((s, kind, m.group(1), i))
                break
    if not starts:
        return _chunk_text(path, lines, language, cfg)
    stem = PurePosixPath(path).stem
    if starts[0][0] > 1:
        b.add(1, starts[0][0] - 1, "module", f"<module {stem}>")
    for idx, (s, kind, name, decl) in enumerate(starts):
        e = (starts[idx + 1][0] - 1) if idx + 1 < len(starts) else n
        while e > s and not lines[e - 1].strip():
            e -= 1
        body = "\n".join(lines[s - 1:e])
        calls = sorted({c for c in _CALL_RE.findall(body) if c not in _NOT_CALLS and c != name}) if kind == "function" else []
        bases = sorted(set(_EXT_RE.findall(lines[decl - 1]))) if kind == "class" else []
        b.add(s, e, kind, name, "", calls, bases)
    return b.chunks


def _chunk_markdown(path: str, lines: list[str], cfg: dict) -> list[Chunk]:
    b = _Builder(path, "markdown", lines, cfg)
    heads, fence = [], False
    for i, line in enumerate(lines, 1):
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
        elif not fence and re.match(r"^#{1,6}\s+\S", line):
            heads.append((i, line.lstrip("# ").strip()))
    stem = PurePosixPath(path).stem
    if not heads:
        b.add(1, len(lines), "doc", stem)
        return b.chunks
    if heads[0][0] > 1:
        b.add(1, heads[0][0] - 1, "doc", stem)
    for idx, (s, title) in enumerate(heads):
        e = (heads[idx + 1][0] - 1) if idx + 1 < len(heads) else len(lines)
        b.add(s, e, "doc", title)
    return b.chunks


def _chunk_text(path: str, lines: list[str], language: str, cfg: dict) -> list[Chunk]:
    win = int(cfg["chunking"]["text_window_lines"])
    b = _Builder(path, language, lines, cfg)
    b.max_lines = win
    b.add(1, len(lines), "text", PurePosixPath(path).name)
    return b.chunks


# ------------------------------------------------------------------ entry point

def chunk_file(path: str, text: str, language: str, cfg: dict) -> list[Chunk]:
    lines = text.splitlines()
    if not lines:
        return []
    if language == "python":
        try:
            return _chunk_python(path, text, cfg)
        except (SyntaxError, ValueError, RecursionError):
            pass  # py2 files, templates, ... -> heuristic windows below
        return _chunk_text(path, lines, "python", cfg)
    if language == "markdown":
        return _chunk_markdown(path, lines, cfg)
    if language in _PATTERNS:
        return _chunk_generic(path, lines, language, cfg)
    return _chunk_text(path, lines, language, cfg)
