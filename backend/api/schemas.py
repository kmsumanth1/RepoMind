from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth ----
class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class GithubAuthRequest(BaseModel):
    code: str = Field(min_length=1, max_length=200)


class UserOut(ORM):
    id: str
    name: str
    email: str | None = None
    github_login: str | None = None
    avatar_url: str | None = None
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---- repos ----
class RepoCreate(BaseModel):
    url: str = Field(min_length=3, max_length=300)
    force: bool = False           # re-clone + re-index even if already indexed


class RepoOut(BaseModel):
    id: str
    full_name: str
    url: str
    status: str
    progress: int
    message: str
    error: str | None = None
    file_count: int = 0
    chunk_count: int = 0
    commit_sha: str | None = None
    indexed_at: datetime | None = None
    last_opened_at: datetime | None = None
    question_count: int = 0


class TreeNode(BaseModel):
    name: str
    path: str
    type: str                     # dir | file
    children: list["TreeNode"] | None = None


class FileOut(BaseModel):
    path: str
    language: str
    start_line: int
    end_line: int
    total_lines: int
    highlight_start: int | None = None
    highlight_end: int | None = None
    content: str


# ---- chat ----
class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class CitationOut(BaseModel):
    id: int
    file: str
    start_line: int
    end_line: int
    name: str
    kind: str
    relation: str = ""


class QueryResponse(BaseModel):
    session_id: str
    message_id: int
    answer: str
    citations: list[CitationOut]
    grounded: bool
    refused: bool
    llm: str
    latency_ms: int


class MessageOut(ORM):
    id: int
    role: str
    content: str
    citations: list[CitationOut] | None = None
    meta: dict | None = None
    created_at: datetime


class SessionOut(ORM):
    id: str
    repo_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class SessionDetail(SessionOut):
    messages: list[MessageOut]
