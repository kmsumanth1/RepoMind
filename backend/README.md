# RepoMind backend

FastAPI + SQLAlchemy backend and RAG engine for RepoMind: accounts, per-user repository/question history,
and grounded, cited answers about any public GitHub repo.

## Run it

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt            # heavy: pulls torch via sentence-transformers

export REPOMIND_JWT_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(48))")
export ANTHROPIC_API_KEY=sk-ant-...        # or: export REPOMIND__generation__provider=ollama
uvicorn api.main:app --reload --port 8000  # docs at http://localhost:8000/docs
```

No GPU / no API key / no model downloads? Lightweight dev mode (still exercises the whole pipeline):

```bash
export REPOMIND__embedding__backend=hashing REPOMIND__retrieval__reranker_backend=lexical \
       REPOMIND__generation__provider=extractive
```

Any `config.yaml` value can be overridden with `REPOMIND__<section>__<key>`.

## Layout

```
api/         FastAPI app: main.py (routes), models.py (tables), schemas.py, security.py, indexing_service.py, db.py
core/        config, shared types, tokenizer, embedders, RepoIndex (on-disk index + FAISS/BM25 search)
ingestion/   clone_repo.py, ast_chunker.py, graph_builder.py, embed_and_index.py, cli.py
retrieval/   hybrid_search.py (dense+BM25+symbol, RRF), reranker.py, graph_expansion.py
generation/  prompt_templates.py, llm_client.py (anthropic | ollama | extractive)
rag/         engine.py - the query pipeline + per-repo engine cache
evaluation/  eval_dataset.json, retrieval_metrics.py (ablation), ragas_eval.py
tests/       22 tests (chunking, graph, retrieval, guardrail, auth, full API flow)
```

## What is stored (database)

| Table | Holds |
|---|---|
| `users` | name, email (unique, lower-cased), **bcrypt hash** (never the password), optional GitHub id/login/avatar, timestamps |
| `repos` | one row per GitHub repo, shared by everyone: status, progress, commit, file/chunk counts |
| `user_repos` | each user's **repository history**: which repos they added/opened and when |
| `chat_sessions` / `chat_messages` | each user's **question history**: questions, answers, citations, grounded/refused flags |

SQLite by default (`data/repomind.db`); set `database_url` to Postgres for production. Tables are created on startup
(use Alembic once the schema starts changing). Indexes live on disk in `data/indexed_repos/<repo_id>/{source,index}`.

## API

Auth: `Authorization: Bearer <token>` from signup/login.

| Endpoint | Purpose |
|---|---|
| `POST /auth/signup` `{name,email,password}` | create account, returns token + user (`user.name` -> "Hi builder ...") |
| `POST /auth/login` `{email,password}` | log in (rate-limited per IP+email) |
| `POST /auth/github` `{code}` | exchange a GitHub OAuth code for a session (needs `GITHUB_CLIENT_ID/SECRET`) |
| `GET /auth/me` | current user |
| `POST /repos` `{url, force?}` | add a repo; already-indexed repos are reused instantly, new ones index in the background |
| `GET /repos` | **my repository history**, most recent first (the "Continue where you left off" chips) |
| `GET /repos/{id}` | poll for live progress: `status` (cloning/parsing/graph/embedding/ready/failed), `progress` 0-100 |
| `GET /repos/{id}/tree` | nested file tree for the sidebar |
| `GET /repos/{id}/file?path=&start=&end=&context=` | code for the citation viewer, with highlight range |
| `POST /repos/{id}/query` `{question, session_id?}` | grounded answer + citations `[{file,start_line,end_line,name}]` |
| `GET /repos/{id}/sessions`, `GET /sessions/{id}`, `DELETE /sessions/{id}` | recent questions / full chat / delete |
| `DELETE /repos/{id}` | remove from *my* history (shared index stays) |

Frontend GitHub login flow: send the user to
`https://github.com/login/oauth/authorize?client_id=...&scope=read:user user:email`, then POST the returned `code` to `/auth/github`.

## How a question is answered

1. (follow-ups) rewrite the question into a standalone one using recent chat history
2. **hybrid retrieval**: FAISS dense + BM25 + exact identifier/filename lookup, fused with weighted Reciprocal Rank Fusion
3. **re-rank** with a cross-encoder (`bge-reranker-base`); scores are normalised to 0-1
4. **guardrail**: nothing above the relevance threshold -> "I couldn't find..." with *no LLM call*
5. **graph expansion** for relationship questions ("what calls X", "what would break if...") - adds callers/callees/subclasses
6. LLM answers from numbered excerpts only, citing `[n]`; only citations that map to real excerpts are returned

Chunking is AST-based for Python (functions/methods/classes with decorators + docstrings kept whole; big classes split per
method); JS/TS/Go/Rust/Java/etc. use declaration-boundary heuristics (swap in tree-sitter behind `chunk_file`); Markdown splits by heading.
Translated docs trees (`docs/en` + `docs/zh` + ...) are skipped automatically.

## Evaluation

```bash
python -m ingestion.cli tiangolo/fastapi                                   # index without the API
python -m evaluation.retrieval_metrics --repo-dir data/indexed_repos/tiangolo__fastapi
```
Prints Recall@1/3/5/10, MRR and context recall for dense -> bm25 -> hybrid -> +rerank -> +graph, plus guardrail
false/true refusal rates. `eval_dataset.json` is a 12-question **starter** set: grow it to 30+ before quoting numbers.
`ragas_eval.py` (faithfulness / answer relevancy) is an untested adapter - see its docstring.

## Notes & limits

* Public GitHub repos only, by design: the server never holds GitHub credentials, so one user can't reach another's private code.
* The login rate limiter is in-memory (per process). Use Redis if you run multiple workers.
* Indexing jobs run in a thread pool inside the API process; jobs interrupted by a restart are marked failed and can be re-submitted.
* Swap `bge-small` for `BAAI/bge-large-en-v1.5` (config) for better recall at higher CPU cost; re-index after changing the embedder.
