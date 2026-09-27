"""Shared data types."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Chunk:
    id: str
    path: str
    start_line: int
    end_line: int
    kind: str            # function | method | class | module | doc | text
    name: str            # qualified name, e.g. "FastAPI.add_middleware"
    language: str
    text: str
    docstring: str = ""
    calls: list[str] = field(default_factory=list)   # simple names of things this chunk calls
    bases: list[str] = field(default_factory=list)   # base classes (class chunks)
    part: int = 0                                     # >0 for continuation windows of long units

    @property
    def symbol(self) -> str:
        """Graph node key shared by all windows of one unit."""
        return f"{self.path}::{self.name}"

    def embedding_text(self) -> str:
        return f"{self.path} | {self.kind} {self.name}\n{self.text}"[:4000]

    def bm25_text(self) -> str:
        return f"{self.path} {self.name} {self.name} {self.text}"

    def to_dict(self) -> dict:
        return asdict(self)
