from core.types import Chunk
from ingestion.ast_chunker import chunk_file
from ingestion.graph_builder import build_graph


def _check_ranges(text, chunks):
    lines = text.splitlines()
    for c in chunks:
        assert c.text == "\n".join(lines[c.start_line - 1:c.end_line]), c.id


def test_python_functions_classes_and_decorators(cfg):
    src = '''"""mod doc"""
import os

CONST = 1


@decorator
def alpha(x):
    """Alpha docs."""
    return beta(x)


def beta(y):
    return y + 1


class Thing(Base):
    """A thing."""

    def method(self):
        return alpha(1)
'''
    chunks = chunk_file("pkg/mod.py", src, "python", cfg)
    _check_ranges(src, chunks)
    by = {c.name: c for c in chunks}
    assert by["alpha"].kind == "function" and by["alpha"].text.lstrip().startswith("@decorator")
    assert by["alpha"].docstring == "Alpha docs."
    assert "beta" in by["alpha"].calls
    assert by["Thing"].kind == "class" and by["Thing"].bases == ["Base"]
    assert any(c.kind == "module" and "import os" in c.text for c in chunks)      # module-level code kept


def test_large_class_is_split_into_methods(cfg):
    methods = "\n".join(f"    def m{i}(self):\n        return {i}\n" for i in range(40))
    src = f"class Big:\n    \"\"\"Big class.\"\"\"\n    x = 1\n\n{methods}"
    chunks = chunk_file("big.py", src, "python", cfg)
    _check_ranges(src, chunks)
    names = {c.name for c in chunks}
    assert "Big" in names and "Big.m0" in names and "Big.m39" in names
    assert next(c for c in chunks if c.name == "Big.m3").kind == "method"


def test_long_function_becomes_overlapping_windows(cfg):
    body = "\n".join(f"    x{i} = {i}" for i in range(300))
    src = f"def huge():\n{body}\n"
    chunks = chunk_file("huge.py", src, "python", cfg)
    _check_ranges(src, chunks)
    parts = [c for c in chunks if c.name == "huge"]
    assert len(parts) >= 3 and [c.part for c in parts] == list(range(len(parts)))
    assert all(c.end_line - c.start_line + 1 <= cfg["chunking"]["max_chunk_lines"] for c in parts)


def test_syntax_error_falls_back_to_windows(cfg):
    chunks = chunk_file("old.py", "def broken(:\n    print 'x'\n" * 3, "python", cfg)
    assert chunks and all(c.kind == "text" for c in chunks)


def test_javascript_and_markdown(cfg):
    js = "export function a() {\n  return b();\n}\n\nexport class K extends Base {\n  m() {}\n}\n"
    names = {c.name: c for c in chunk_file("a.js", js, "javascript", cfg)}
    assert names["a"].kind == "function" and "b" in names["a"].calls
    assert names["K"].kind == "class" and names["K"].bases == ["Base"]
    md = "# Title\nintro text here\n\n```\n# not a heading\n```\n\n## Second\nmore text goes here\n"
    docs = chunk_file("r.md", md, "markdown", cfg)
    assert [c.name for c in docs] == ["Title", "Second"]


def test_call_graph_prefers_same_file_and_tracks_inheritance():
    def ch(path, name, kind, calls=(), bases=()):
        return Chunk(id=f"{path}:{name}", path=path, start_line=1, end_line=2, kind=kind, name=name,
                     language="python", text="x" * 30, calls=list(calls), bases=list(bases))
    chunks = [ch("a.py", "run", "function", ["helper", "__init__"]), ch("a.py", "helper", "function"),
              ch("b.py", "helper", "function"), ch("b.py", "Child", "class", bases=["Parent"]),
              ch("c.py", "Parent", "class")]
    g = build_graph(chunks)
    assert g["callees"]["a.py::run"] == ["a.py::helper"]          # same-file wins over b.py::helper
    assert g["callers"]["a.py::helper"] == ["a.py::run"]
    assert g["bases"]["b.py::Child"] == ["c.py::Parent"]
    assert g["subclasses"]["c.py::Parent"] == ["b.py::Child"]


def test_translation_dirs_are_dropped_only_when_clearly_i18n():
    from ingestion.clone_repo import _drop_translation_dirs
    assert _drop_translation_dirs(["en", "zh", "ru", "ja", "zh-hant", "img"]) == ["en", "img"]
    assert _drop_translation_dirs(["en", "ui"]) == ["en", "ui"]            # too few locale-like siblings
    assert _drop_translation_dirs(["zh", "ru", "ja", "ko"]) == ["zh", "ru", "ja", "ko"]   # no `en` sibling
