import os
import shutil
import tempfile
from pathlib import Path

# Configure BEFORE anything imports the app: lightweight, offline components only.
_tmp = tempfile.mkdtemp(prefix="repomind-test-")
os.environ["REPOMIND__data_dir"] = _tmp
os.environ["REPOMIND__embedding__backend"] = "hashing"
os.environ["REPOMIND__retrieval__reranker_backend"] = "lexical"
os.environ["REPOMIND__generation__provider"] = "extractive"
os.environ["REPOMIND_JWT_SECRET"] = "test-secret-that-is-at-least-32-bytes-long"

import pytest  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


@pytest.fixture(scope="session")
def cfg():
    from core.config import get_config
    return get_config()


@pytest.fixture(scope="session")
def built_index(cfg, tmp_path_factory):
    from core.index_store import RepoIndex
    from ingestion.embed_and_index import build_index
    base = tmp_path_factory.mktemp("repo")
    shutil.copytree(FIXTURE, base / "source")
    build_index(base / "source", base / "index", cfg, repo_name="sample/service", commit="abc")
    return RepoIndex.load(base / "index")


@pytest.fixture(scope="session")
def engine(cfg, built_index):
    from core.embedder import embedder_from_spec
    from generation.llm_client import ExtractiveClient
    from rag.engine import RagEngine
    from retrieval.reranker import LexicalReranker
    return RagEngine(built_index, embedder_from_spec(built_index.meta["embedder"], cfg), LexicalReranker(),
                     ExtractiveClient(), cfg)
