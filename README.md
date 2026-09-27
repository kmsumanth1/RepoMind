# RepoMind

**Ask questions about any GitHub repository in plain English — get answers grounded in the actual code, with every claim linked back to the exact lines it came from.**

RepoMind is a Retrieval-Augmented Generation (RAG) assistant for codebases. Point it at a public GitHub repo, and it clones, parses, and indexes the code, then answers natural-language questions about it — how something works, where it's defined, what calls it, what would break if you changed it — citing real files and line ranges instead of guessing.

## What it does

- **Index any public GitHub repo** by pasting its URL. RepoMind clones it, chunks the code by function/class (not arbitrary line windows), and builds a searchable index.
- **Ask questions in plain English** — "How does middleware work here?", "What calls `get_openapi`?", "What would break if I changed the `Request` class?"
- **Every answer is grounded and cited.** Answers reference numbered source excerpts `[1]`, `[2]`, ... and each citation opens the real file at the real line range in a source viewer. If nothing relevant is found, it says so instead of making something up.
- **Understands code relationships**, not just keyword matches — it follows a call graph, so it can answer "what depends on this" or "what would this change affect" questions, not just "where is X defined."
- **Per-user accounts and history** — sign up, and your indexed repos and past questions/answers are saved and searchable later.

## How it works

1. **Clone & chunk** — the repo is cloned and parsed. Python is chunked using the real `ast` module (functions, methods, classes — decorators and docstrings kept intact); other languages (JS/TS/Go/Rust/Java/etc.) use declaration-boundary parsing; Markdown splits by heading.
2. **Build a call graph** — function calls and class inheritance are resolved into a graph, so the system knows what calls what.
3. **Embed & index** — chunks are embedded and indexed for both semantic (dense vector) and keyword (BM25) search, plus exact symbol/filename lookup.
4. **Retrieve** — a question is answered by combining all three search types (dense + BM25 + symbol), fused together, then re-ranked for relevance.
5. **Guardrail** — if nothing retrieved is actually relevant, the system refuses rather than hallucinating an answer.
6. **Graph expansion** — for relationship questions ("what calls X", "what breaks if I change Y"), related code is pulled in via the call graph.
7. **Generate** — an LLM (or a citation-only fallback if none is configured) writes the final answer strictly from the retrieved excerpts, with citations checked against what was actually retrieved.

## Architecture

```
repomind/
├── frontend/     Next.js + React + Tailwind — landing page, auth, dashboard, chat UI
└── backend/      FastAPI + SQLAlchemy — accounts, repo indexing, RAG pipeline, chat history
```

**Frontend** — Next.js (App Router), React 19, Tailwind CSS v4. Handles sign-up/login, the repo dashboard, the indexing-progress screen, the chat interface, and the source-code viewer with citation highlighting.

**Backend** — Python/FastAPI, SQLAlchemy (SQLite by default), FAISS + BM25 for retrieval, a cross-encoder reranker, and a pluggable LLM layer that supports:
- **Anthropic (Claude)** — paid API, highest quality
- **Ollama** — free, runs a local open-source model (e.g. Llama 3.1) on your own machine, no API key needed
- **Extractive fallback** — no LLM at all; returns the top relevant code chunks directly, useful for offline testing or a zero-cost demo

## Getting started

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # add ANTHROPIC_API_KEY here if you're using Claude
uvicorn api.main:app --reload    # runs on http://localhost:8000
```

No API key? Use the free local option — install [Ollama](https://ollama.com), run `ollama pull llama3.1`, and leave `config.yaml`'s `generation.provider` set to `ollama` (the default). Full backend details, API reference, and evaluation instructions are in [`backend/README.md`](backend/README.md).

### 2. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # point NEXT_PUBLIC_API_URL at your backend
npm run dev                        # runs on http://localhost:3000
```

### 3. Try it

Open `http://localhost:3000`, sign up, paste a public GitHub repo URL (e.g. `https://github.com/pallets/flask`), wait for indexing to finish, and start asking questions.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| Backend API | FastAPI, SQLAlchemy, Pydantic |
| Auth | JWT (HS256), bcrypt password hashing |
| Retrieval | FAISS (dense vectors), BM25 (keyword), custom symbol index |
| Embeddings | sentence-transformers (`bge-small-en-v1.5`) or an offline hashing fallback |
| Reranking | cross-encoder (`bge-reranker-base`) or a lexical fallback |
| Generation | Claude (Anthropic API), Ollama (local models), or a citation-only extractive fallback |
| Database | SQLite (default), swappable for Postgres |

## Evaluation

Retrieval quality is measured with Recall@k, MRR, and context recall across an ablation (dense-only → BM25 → hybrid → hybrid+rerank → full pipeline with graph expansion), plus false/correct refusal rates for the guardrail. See [`backend/README.md`](backend/README.md#evaluation) for how to run it.

## Project status

Built by **KM Sumanth**, B.Tech CSE (AI & ML), Mohan Babu University.

- [x] Backend: accounts, repo indexing, RAG pipeline, chat history (22 automated tests passing)
- [x] Frontend: landing, auth, dashboard, indexing progress, chat with citations
- [x] Frontend wired to the live backend
- [ ] Production-grade embeddings (currently defaults to the offline fallback unless `sentence-transformers` is installed)
- [ ] Deployment (Docker + hosting)

## License

Add a license of your choice (MIT is a common default for student/portfolio projects) before making this repo public.