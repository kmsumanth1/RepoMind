"""Lightweight code graph: who-calls-whom and who-inherits-from-whom.

Nodes are symbols (`path::Qualified.name`). Resolution is name-based and deliberately conservative:
a call resolves to a same-file definition if one exists, otherwise to a repo-wide definition only
when the name is (nearly) unique. This trades recall for precision - wrong edges would poison
"what would break" answers.
"""
from __future__ import annotations

from collections import defaultdict

from core.types import Chunk

MAX_AMBIGUITY = 3
GRAPH_KINDS = ("function", "method", "class")


def build_graph(chunks: list[Chunk]) -> dict[str, dict[str, list[str]]]:
    defs: dict[str, list[Chunk]] = defaultdict(list)
    class_defs: dict[str, list[Chunk]] = defaultdict(list)
    for c in chunks:
        if c.kind in GRAPH_KINDS and c.part == 0:
            simple = c.name.split(".")[-1]
            defs[simple].append(c)
            if c.kind == "class":
                class_defs[simple].append(c)

    def resolve(name: str, table: dict[str, list[Chunk]], here: Chunk) -> list[Chunk]:
        if name.startswith("__") and name.endswith("__"):
            return []
        targets = table.get(name, [])
        same = [t for t in targets if t.path == here.path]
        return same or (targets if len(targets) <= MAX_AMBIGUITY else [])

    callees, callers = defaultdict(set), defaultdict(set)
    bases, subclasses = defaultdict(set), defaultdict(set)
    for c in chunks:
        if c.kind not in GRAPH_KINDS or c.part != 0:
            continue
        for name in c.calls:
            for t in resolve(name, defs, c):
                if t.symbol != c.symbol:
                    callees[c.symbol].add(t.symbol)
                    callers[t.symbol].add(c.symbol)
        for name in c.bases:
            for t in resolve(name, class_defs, c):
                if t.symbol != c.symbol:
                    bases[c.symbol].add(t.symbol)
                    subclasses[t.symbol].add(c.symbol)
    to_json = lambda d: {k: sorted(v) for k, v in d.items()}  # noqa: E731
    return {"callees": to_json(callees), "callers": to_json(callers),
            "bases": to_json(bases), "subclasses": to_json(subclasses)}
