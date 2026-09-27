"""Password hashing, JWTs, auth dependency and a small login rate limiter."""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from core.config import get_config

from .db import get_db
from .models import User

log = logging.getLogger("repomind.auth")
_bearer = HTTPBearer(auto_error=False)
ALGO = "HS256"


# ---- passwords -------------------------------------------------------------
def _prehash(pw: str) -> bytes:
    # bcrypt only looks at the first 72 bytes (and newer versions reject longer input);
    # SHA-256 + base64 first makes every password length safe.
    return base64.b64encode(hashlib.sha256(pw.encode("utf-8")).digest())


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(_prehash(pw), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str | None) -> bool:
    # Always do a bcrypt comparison so unknown emails cost the same time as wrong passwords.
    return bcrypt.checkpw(_prehash(pw), (hashed or DUMMY_HASH).encode()) and hashed is not None


DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt()).decode()


def check_password_policy(pw: str) -> None:
    n = int(get_config()["auth"]["min_password_length"])
    if len(pw) < n:
        raise HTTPException(422, f"Password must be at least {n} characters")


# ---- JWT -------------------------------------------------------------------
_secret_cache: str | None = None


def _secret() -> str:
    global _secret_cache
    if _secret_cache:
        return _secret_cache
    env = os.getenv("REPOMIND_JWT_SECRET")
    if env:
        if len(env) < 32:
            log.warning("REPOMIND_JWT_SECRET is shorter than 32 characters; use a long random value.")
        _secret_cache = env
    else:  # dev convenience: persist a random secret so tokens survive restarts
        p = Path(get_config()["data_dir"]) / ".jwt_secret"
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text(secrets.token_urlsafe(48))
            p.chmod(0o600)
            log.warning("REPOMIND_JWT_SECRET not set; generated a dev secret at %s. Set the env var in production.", p)
        _secret_cache = p.read_text().strip()
    return _secret_cache


def create_access_token(user_id: str) -> str:
    minutes = int(get_config()["auth"]["access_token_minutes"])
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + timedelta(minutes=minutes)}, _secret(), algorithm=ALGO)


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                     db: Session = Depends(get_db)) -> User:
    err = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    if not creds:
        raise err
    try:
        payload = jwt.decode(creds.credentials, _secret(), algorithms=[ALGO])
    except jwt.PyJWTError:
        raise err
    user = db.get(User, payload.get("sub"))
    if not user:
        raise err
    return user


# ---- brute-force protection (in-memory; use Redis if you run several workers) ----
class RateLimiter:
    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, window: float) -> deque:
        q, now = self._hits[key], time.time()
        while q and now - q[0] > window:
            q.popleft()
        return q

    def check(self, key: str, limit: int, window: float) -> None:
        with self._lock:
            if len(self._prune(key, window)) >= limit:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Try again later.")

    def fail(self, key: str, window: float) -> None:
        with self._lock:
            self._prune(key, window).append(time.time())

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


login_limiter = RateLimiter()
