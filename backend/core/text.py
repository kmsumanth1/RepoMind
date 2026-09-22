"""Code-aware tokenisation shared by BM25, the hashing embedder and the lexical reranker."""
from __future__ import annotations

import re

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PARTS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")

CODE_STOP = {
    "self", "cls", "the", "and", "for", "return", "import", "from", "def", "class", "none", "true",
    "false", "in", "is", "not", "if", "else", "elif", "with", "as", "pass", "or", "to", "of", "a",
    "an", "async", "await", "var", "let", "const", "new", "this", "then", "try", "except", "raise",
}
QUERY_STOP = CODE_STOP | {
    "how", "does", "do", "did", "what", "where", "which", "who", "why", "when", "are", "can", "could",
    "would", "should", "i", "me", "my", "we", "it", "its", "this", "that", "these", "those", "there",
    "implemented", "implement", "work", "works", "working", "used", "use", "uses", "using", "code",
    "codebase", "repo", "repository", "project", "function", "file", "explain", "show", "tell", "about",
    "define", "defined", "handle", "handled", "handles", "happen", "happens", "on", "at", "by", "be",
    "was", "were", "has", "have", "there", "any", "all", "get", "gets", "find", "into", "out", "up",
}


_SUFFIXES = ("ations", "ation", "ingly", "ing", "ers", "ed", "es", "er")


def stem(w: str) -> str:
    """Tiny suffix-stripper so verify/verified/verifier, limit/limiter, handle/handlers collide."""
    if len(w) <= 4:
        return w
    r = w
    if w.endswith("ies") and len(w) > 5:
        r = w[:-3] + "y"
    else:
        for suf in _SUFFIXES:
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                r = w[: -len(suf)]
                if r.endswith("i"):
                    r = r[:-1] + "y"
                break
        else:
            if w.endswith("s") and not w.endswith("ss"):
                r = w[:-1]
    if len(r) > 4 and r.endswith("e"):
        r = r[:-1]
    return r


def split_identifier(tok: str) -> list[str]:
    return [p.lower() for p in _PARTS.findall(tok.replace("_", " "))]


def tokenize(text: str, query: bool = False) -> list[str]:
    """Lower-cased tokens. Compound identifiers yield the exact identifier AND its sub-words,
    so both `add_middleware` and `middleware` match."""
    stop = QUERY_STOP if query else CODE_STOP
    out: list[str] = []
    for m in _IDENT.finditer(text):
        tok = m.group(0)
        low = tok.lower()
        parts = split_identifier(tok)
        if len(parts) > 1:
            if low not in stop and len(low) > 1:
                out.append(low)
            out.extend(stem(p) for p in parts if p not in stop and len(p) > 1)
        elif low not in stop and len(low) > 1:
            out.append(stem(low))
    return out
