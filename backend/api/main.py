"""RepoMind API.   Run:  uvicorn api.main:app --reload --port 8000"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()  # populate os.environ from .env before anything below reads it

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.config import get_config, repos_dir
from generation.llm_client import LLMError
from ingestion.clone_repo import parse_repo_url
from rag.engine import get_engine

from . import indexing_service, schemas
from .db import get_db, init_db
from .models import ChatMessage, ChatSession, Repo, User, UserRepo
from .security import (check_password_policy, create_access_token, get_current_user, hash_password,
                       login_limiter, verify_password)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("repomind.api")
cfg = get_config()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    indexing_service.recover_interrupted()
    yield


app = FastAPI(title="RepoMind API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=cfg["server"]["cors_origins"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


@app.get("/health")
def health():
    return {"status": "ok"}


# =============================================================== auth
def _token_for(user: User, db: Session) -> schemas.TokenResponse:
    user.last_login_at = _now()
    db.commit()
    return schemas.TokenResponse(access_token=create_access_token(user.id), user=schemas.UserOut.model_validate(user))


@app.post("/auth/signup", response_model=schemas.TokenResponse, status_code=201)
def signup(body: schemas.SignupRequest, db: Session = Depends(get_db)):
    check_password_policy(body.password)
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(name=body.name.strip(), email=email, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    return _token_for(user, db)


@app.post("/auth/login", response_model=schemas.TokenResponse)
def login(body: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    a = cfg["auth"]
    key = f"{request.client.host if request.client else '?'}|{body.email.lower()}"
    login_limiter.check(key, int(a["login_attempts"]), float(a["login_window_seconds"]))
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not verify_password(body.password, user.password_hash if user else None):
        login_limiter.fail(key, float(a["login_window_seconds"]))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    login_limiter.reset(key)
    return _token_for(user, db)


@app.post("/auth/github", response_model=schemas.TokenResponse)
def github_login(body: schemas.GithubAuthRequest, db: Session = Depends(get_db)):
    """Exchange a GitHub OAuth `code` (from your frontend's redirect) for a RepoMind session.
    Needs GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET. Request scopes `read:user user:email`."""
    cid, secret = os.getenv("GITHUB_CLIENT_ID"), os.getenv("GITHUB_CLIENT_SECRET")
    if not (cid and secret):
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "GitHub login is not configured on this server")
    try:
        with httpx.Client(timeout=15) as c:
            r = c.post("https://github.com/login/oauth/access_token", headers={"Accept": "application/json"},
                       data={"client_id": cid, "client_secret": secret, "code": body.code})
            gh_token = r.json().get("access_token")
            if not gh_token:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "GitHub rejected the login code")
            h = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"}
            profile = c.get("https://api.github.com/user", headers=h).json()
            emails = c.get("https://api.github.com/user/emails", headers=h)
            verified = next((e["email"] for e in (emails.json() if emails.status_code == 200 else [])
                             if e.get("primary") and e.get("verified")), None)
    except httpx.HTTPError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not reach GitHub")
    gh_id = str(profile.get("id") or "")
    if not gh_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "GitHub login failed")
    verified = verified.lower() if verified else None
    # link by GitHub id, else by *verified* email, else create
    user = db.scalar(select(User).where(User.github_id == gh_id)) or \
        (db.scalar(select(User).where(User.email == verified)) if verified else None)
    if not user:
        user = User(name=profile.get("name") or profile.get("login") or "builder", email=verified)
        db.add(user)
    user.github_id, user.github_login, user.avatar_url = gh_id, profile.get("login"), profile.get("avatar_url")
    db.commit()
    return _token_for(user, db)


@app.get("/auth/me", response_model=schemas.UserOut)
def me(user: User = Depends(get_current_user)):
    return user


# =============================================================== repos
def _repo_out(repo: Repo, link: UserRepo | None = None, qcount: int = 0) -> schemas.RepoOut:
    return schemas.RepoOut(
        id=repo.id, full_name=repo.display_name, url=repo.url, status=repo.status, progress=repo.progress,
        message=repo.message, error=repo.error, file_count=repo.file_count, chunk_count=repo.chunk_count,
        commit_sha=repo.commit_sha, indexed_at=repo.indexed_at,
        last_opened_at=link.last_opened_at if link else None, question_count=qcount)


def _owned_repo(repo_id: str, user: User, db: Session) -> tuple[Repo, UserRepo]:
    row = db.execute(select(Repo, UserRepo).join(UserRepo, UserRepo.repo_id == Repo.id)
                     .where(Repo.id == repo_id, UserRepo.user_id == user.id)).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")
    return row[0], row[1]


@app.post("/repos", response_model=schemas.RepoOut)
def add_repo(body: schemas.RepoCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Submit a GitHub URL. Already-indexed repos are reused instantly; new ones index in the background."""
    try:
        ref = parse_repo_url(body.url)
    except ValueError as e:
        raise HTTPException(422, str(e))
    key = ref.full_name.lower()
    repo = db.scalar(select(Repo).where(Repo.full_name == key))
    if not repo:
        repo = Repo(full_name=key, display_name=ref.full_name, url=ref.web_url)
        db.add(repo)
        try:
            db.commit()
        except IntegrityError:            # two users submitted the same repo at once
            db.rollback()
            repo = db.scalar(select(Repo).where(Repo.full_name == key))
        else:
            indexing_service.submit(repo.id)
    elif repo.status == "failed" or (body.force and repo.status not in indexing_service.IN_PROGRESS):
        repo.status, repo.progress, repo.message, repo.error = "queued", 0, "Queued", None
        db.commit()
        indexing_service.submit(repo.id)

    link = db.scalar(select(UserRepo).where(UserRepo.user_id == user.id, UserRepo.repo_id == repo.id))
    if link:
        link.last_opened_at = _now()
    else:
        link = UserRepo(user_id=user.id, repo_id=repo.id)
        db.add(link)
    db.commit()
    return _repo_out(repo, link)


@app.get("/repos", response_model=list[schemas.RepoOut])
def list_repos(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The user's repository history, most recently opened first."""
    qcounts = dict(db.execute(
        select(ChatSession.repo_id, func.count(ChatMessage.id))
        .join(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.user_id == user.id, ChatMessage.role == "user").group_by(ChatSession.repo_id)).all())
    rows = db.execute(select(Repo, UserRepo).join(UserRepo, UserRepo.repo_id == Repo.id)
                      .where(UserRepo.user_id == user.id).order_by(UserRepo.last_opened_at.desc())).all()
    return [_repo_out(r, l, qcounts.get(r.id, 0)) for r, l in rows]


@app.get("/repos/{repo_id}", response_model=schemas.RepoOut)
def get_repo(repo_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Poll this while status is not 'ready'/'failed' to drive the live progress bar."""
    repo, link = _owned_repo(repo_id, user, db)
    link.last_opened_at = _now()
    db.commit()
    return _repo_out(repo, link)


@app.delete("/repos/{repo_id}", status_code=204)
def forget_repo(repo_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Remove from *my* history (and my chats about it). The shared index stays for other users."""
    _, link = _owned_repo(repo_id, user, db)
    for s in db.scalars(select(ChatSession).where(ChatSession.user_id == user.id, ChatSession.repo_id == repo_id)):
        db.delete(s)
    db.delete(link)
    db.commit()


def _ready_repo(repo_id: str, user: User, db: Session) -> Repo:
    repo, _ = _owned_repo(repo_id, user, db)
    if not (repos_dir(cfg) / repo.id / "index" / "meta.json").exists():
        raise HTTPException(status.HTTP_409_CONFLICT, f"Repository is not ready yet (status: {repo.status})")
    return repo


@app.get("/repos/{repo_id}/tree", response_model=list[schemas.TreeNode])
def repo_tree(repo_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repo = _ready_repo(repo_id, user, db)
    files = get_engine(repo.id).index.files
    root: dict = {}
    for f in files:
        node = root
        for part in f["path"].split("/"):
            node = node.setdefault(part, {})

    def build(d: dict, prefix: str) -> list[schemas.TreeNode]:
        out = []
        for name in sorted(d, key=lambda n: (not d[n], n.lower())):      # dirs first
            path = f"{prefix}{name}"
            out.append(schemas.TreeNode(name=name, path=path, type="dir", children=build(d[name], path + "/"))
                       if d[name] else schemas.TreeNode(name=name, path=path, type="file"))
        return out
    return build(root, "")


@app.get("/repos/{repo_id}/file", response_model=schemas.FileOut)
def repo_file(repo_id: str, path: str, start: int | None = Query(None, ge=1), end: int | None = Query(None, ge=1),
              context: int = Query(3, ge=0, le=50), user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """Source for the citation viewer. With start/end, returns that range (+context) and echoes the highlight."""
    repo = _ready_repo(repo_id, user, db)
    src = (repos_dir(cfg) / repo.id / "source").resolve()
    target = (src / path).resolve()
    if not target.is_relative_to(src) or not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    total = len(lines)
    if start is not None:
        end = min(end or start, total)
        lo, hi = max(1, start - context), min(total, end + context)
    else:
        lo, hi = 1, min(total, 2000)
    lang = next((f["language"] for f in get_engine(repo.id).index.files if f["path"] == path), "text")
    return schemas.FileOut(path=path, language=lang, start_line=lo, end_line=hi, total_lines=total,
                           highlight_start=start, highlight_end=end, content="\n".join(lines[lo - 1:hi]))


# =============================================================== chat
def _owned_session(session_id: str, user: User, db: Session) -> ChatSession:
    s = db.get(ChatSession, session_id)
    if not s or s.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")
    return s


@app.post("/repos/{repo_id}/query", response_model=schemas.QueryResponse)
def query_repo(repo_id: str, body: schemas.QueryRequest, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    repo = _ready_repo(repo_id, user, db)
    if body.session_id:
        session = _owned_session(body.session_id, user, db)
        if session.repo_id != repo.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "That chat belongs to a different repository")
    else:
        session = ChatSession(user_id=user.id, repo_id=repo.id, title=body.question.strip()[:80])
        db.add(session)
        db.flush()
    history = [{"role": m.role, "content": m.content} for m in session.messages][-int(cfg["generation"]["history_turns"]):]

    try:
        result = get_engine(repo.id).answer(body.question, history)
    except LLMError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))

    cites = [c.__dict__ for c in result.citations]
    db.add(ChatMessage(session_id=session.id, role="user", content=body.question))
    reply = ChatMessage(session_id=session.id, role="assistant", content=result.answer, citations=cites,
                        meta={"grounded": result.grounded, "refused": result.refused, "llm": result.llm,
                              "latency_ms": result.latency_ms, "standalone_question": result.standalone_question})
    db.add(reply)
    session.updated_at = _now()
    link = db.scalar(select(UserRepo).where(UserRepo.user_id == user.id, UserRepo.repo_id == repo.id))
    if link:
        link.last_opened_at = _now()
    db.commit()
    return schemas.QueryResponse(session_id=session.id, message_id=reply.id, answer=result.answer,
                                 citations=[schemas.CitationOut(**c) for c in cites], grounded=result.grounded,
                                 refused=result.refused, llm=result.llm, latency_ms=result.latency_ms)


@app.get("/repos/{repo_id}/sessions", response_model=list[schemas.SessionOut])
def list_sessions(repo_id: str, limit: int = Query(30, ge=1, le=100), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Recent chats for a repo - the titles are the first question, which powers 'Recent questions'."""
    _owned_repo(repo_id, user, db)
    return db.scalars(select(ChatSession).where(ChatSession.user_id == user.id, ChatSession.repo_id == repo_id)
                      .order_by(ChatSession.updated_at.desc()).limit(limit)).all()


@app.get("/sessions/{session_id}", response_model=schemas.SessionDetail)
def get_session(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _owned_session(session_id, user, db)


@app.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_owned_session(session_id, user, db))
    db.commit()
