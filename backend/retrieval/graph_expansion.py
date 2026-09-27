"""Pull in structurally-related code (callers / callees / subclasses / bases) when the question is
about relationships rather than about a single piece of code."""
from __future__ import annotations

import re

from core.index_store import RepoIndex

from .hybrid_search import Hit

_CALLERS = re.compile(r"\b(what|who|which)\b.*\b(calls?|uses?|invokes?|depends? on|references?)\b|used by|called by|\bcallers?\b|"
                      r"where (is|are) .*\b(used|called)\b|\b(breaks?|impact|affected)\b|"
                      r"\bif i (change|rename|remove|delete|modify|refactor)\b", re.I)
_CALLEES = re.compile(r"\bwhat does .* (call|use|depend)|\bcalls? what\b|\bdepends? on what\b|\bdependenc(y|ies)\b|\bcall (graph|chain|flow)\b", re.I)
_INHERIT = re.compile(r"\b(inherit\w*|subclass\w*|extends?|derived|parent class|base class|children of)\b", re.I)


def graph_directions(question: str) -> list[str]:
    dirs = []
    if _CALLERS.search(question):
        dirs += ["callers", "subclasses"]
    if _CALLEES.search(question):
        dirs += ["callees"]
    if _INHERIT.search(question):
        dirs += ["subclasses", "bases"]
    return list(dict.fromkeys(dirs))


def expand(index: RepoIndex, hits: list[Hit], question: str, max_added: int = 6, seeds: int = 3) -> list[Hit]:
    dirs = graph_directions(question)
    if not dirs or not hits:
        return []
    have = {h.pos for h in hits}
    added: list[Hit] = []
    for seed in hits[:seeds]:
        sym = seed.chunk.symbol
        for d in dirs:
            for other in index.graph.get(d, {}).get(sym, []):
                positions = index.by_symbol.get(other)
                if not positions or positions[0] in have:
                    continue
                pos = positions[0]
                have.add(pos)
                verb = {"callers": "calls", "callees": "is called by", "subclasses": "inherits from", "bases": "is inherited by"}[d]
                added.append(Hit(pos=pos, chunk=index.chunks[pos], score=0.0, relevance=seed.relevance * 0.5,
                                 relation=f"{verb} {seed.chunk.name}"))
                if len(added) >= max_added:
                    return added
    return added
