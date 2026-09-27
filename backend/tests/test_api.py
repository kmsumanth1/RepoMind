import shutil
import time

import pytest
from fastapi.testclient import TestClient

from tests.conftest import FIXTURE


@pytest.fixture(scope="module")
def client():
    from api.main import app
    import api.indexing_service as svc

    def fake_clone(ref, dest, timeout=600):          # no network in tests
        shutil.copytree(FIXTURE, dest)
        return "deadbeef"
    orig, svc.clone_repo = svc.clone_repo, fake_clone
    with TestClient(app) as c:
        yield c
    svc.clone_repo = orig


def _signup(client, email, name="Irfan", password="correct-horse"):
    r = client.post("/auth/signup", json={"name": name, "email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _wait_ready(client, token, repo_id, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        r = client.get(f"/repos/{repo_id}", headers=_h(token)).json()
        if r["status"] in ("ready", "failed"):
            return r
        time.sleep(0.1)
    raise AssertionError("indexing did not finish")


# ------------------------------------------------------------------ auth
def test_signup_login_me_and_password_storage(client):
    from api.db import SessionLocal
    from api.models import User
    body = client.post("/auth/signup", json={"name": "Irfan", "email": "Irfan@Example.com", "password": "correct-horse"})
    assert body.status_code == 201 and body.json()["user"]["name"] == "Irfan"
    assert "password" not in str(body.json()["user"])

    with SessionLocal() as db:                                    # stored hashed, email normalised
        u = db.query(User).filter_by(email="irfan@example.com").one()
        assert u.password_hash.startswith("$2") and "correct-horse" not in u.password_hash

    ok = client.post("/auth/login", json={"email": "irfan@example.com", "password": "correct-horse"})
    assert ok.status_code == 200
    me = client.get("/auth/me", headers=_h(ok.json()["access_token"]))
    assert me.status_code == 200 and me.json()["email"] == "irfan@example.com"


def test_auth_failures(client):
    _signup(client, "dup@example.com")
    assert client.post("/auth/signup", json={"name": "x", "email": "dup@example.com", "password": "correct-horse"}).status_code == 409
    assert client.post("/auth/signup", json={"name": "x", "email": "weak@example.com", "password": "short"}).status_code == 422
    assert client.post("/auth/login", json={"email": "dup@example.com", "password": "wrong-password"}).status_code == 401
    assert client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever123"}).status_code == 401
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers=_h("garbage")).status_code == 401
    assert client.get("/repos").status_code == 401


def test_login_rate_limit(client):
    _signup(client, "brute@example.com")
    codes = [client.post("/auth/login", json={"email": "brute@example.com", "password": f"bad-guess-{i}"}).status_code
             for i in range(10)]
    assert 429 in codes and codes[0] == 401


# ------------------------------------------------------------------ repos + chat + history
def test_full_flow_index_query_history(client):
    t = _signup(client, "flow@example.com")
    assert client.post("/repos", json={"url": "https://example.com/x/y"}, headers=_h(t)).status_code == 422

    r = client.post("/repos", json={"url": "https://github.com/Acme/Service"}, headers=_h(t))
    assert r.status_code == 200
    repo_id = r.json()["id"]
    repo = _wait_ready(client, t, repo_id)
    assert repo["status"] == "ready" and repo["file_count"] == 6 and repo["commit_sha"] == "deadbeef"

    tree = client.get(f"/repos/{repo_id}/tree", headers=_h(t)).json()
    assert [n["name"] for n in tree] == ["app", "web", "README.md"]           # dirs first
    assert {c["name"] for c in tree[0]["children"]} >= {"auth.py", "ratelimit.py"}

    f = client.get(f"/repos/{repo_id}/file", params={"path": "app/ratelimit.py", "start": 18, "end": 20, "context": 1},
                   headers=_h(t)).json()
    assert f["highlight_start"] == 18 and f["start_line"] == 17 and f["end_line"] == 21
    assert client.get(f"/repos/{repo_id}/file", params={"path": "../../../etc/passwd"}, headers=_h(t)).status_code == 404
    assert client.get(f"/repos/{repo_id}/file", params={"path": "app/../../secrets"}, headers=_h(t)).status_code == 404

    q1 = client.post(f"/repos/{repo_id}/query", json={"question": "How does the rate limiter work?"}, headers=_h(t))
    assert q1.status_code == 200, q1.text
    a1 = q1.json()
    assert a1["grounded"] and any(c["file"] == "app/ratelimit.py" for c in a1["citations"])
    q2 = client.post(f"/repos/{repo_id}/query", json={"question": "and what about its window?", "session_id": a1["session_id"]},
                     headers=_h(t))
    assert q2.status_code == 200 and q2.json()["session_id"] == a1["session_id"]
    q3 = client.post(f"/repos/{repo_id}/query", json={"question": "How do I bake sourdough bread?"}, headers=_h(t)).json()
    assert q3["refused"] and q3["citations"] == []

    sessions = client.get(f"/repos/{repo_id}/sessions", headers=_h(t)).json()
    assert len(sessions) == 2 and {s["title"] for s in sessions} == {"How does the rate limiter work?", "How do I bake sourdough bread?"}
    detail = client.get(f"/sessions/{a1['session_id']}", headers=_h(t)).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]
    assert detail["messages"][1]["citations"][0]["file"]

    history = client.get("/repos", headers=_h(t)).json()
    assert history[0]["full_name"] == "Acme/Service" and history[0]["question_count"] == 3 and history[0]["last_opened_at"]


def test_repo_reuse_isolation_and_forget(client):
    a, b = _signup(client, "a@example.com"), _signup(client, "b@example.com")
    ra = client.post("/repos", json={"url": "acme/service"}, headers=_h(a)).json()
    _wait_ready(client, a, ra["id"])
    rb = client.post("/repos", json={"url": "https://github.com/acme/service.git"}, headers=_h(b)).json()
    assert rb["id"] == ra["id"] and rb["status"] == "ready"               # same shared index, instantly ready

    sess = client.post(f"/repos/{ra['id']}/query", json={"question": "token verification"}, headers=_h(a)).json()["session_id"]
    assert client.get(f"/sessions/{sess}", headers=_h(b)).status_code == 404          # chats are private
    c = _signup(client, "c@example.com")
    assert client.get(f"/repos/{ra['id']}", headers=_h(c)).status_code == 404         # no access without adding it
    assert client.post(f"/repos/{ra['id']}/query", json={"question": "x y z"}, headers=_h(c)).status_code == 404

    assert client.delete(f"/repos/{ra['id']}", headers=_h(a)).status_code == 204       # forget only for user a
    assert client.get("/repos", headers=_h(a)).json() == []
    assert client.get(f"/sessions/{sess}", headers=_h(a)).status_code == 404
    assert client.get(f"/repos/{ra['id']}", headers=_h(b)).status_code == 200


def test_failed_indexing_is_reported_and_retryable(client):
    import api.indexing_service as svc
    t = _signup(client, "fail@example.com")
    good = svc.clone_repo
    svc.clone_repo = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Could not clone: repository not found"))
    try:
        rid = client.post("/repos", json={"url": "acme/missing"}, headers=_h(t)).json()["id"]
        r = _wait_ready(client, t, rid)
        assert r["status"] == "failed" and "not found" in r["error"]
        assert client.post(f"/repos/{rid}/query", json={"question": "anything"}, headers=_h(t)).status_code == 409
    finally:
        svc.clone_repo = good
    again = client.post("/repos", json={"url": "acme/missing"}, headers=_h(t)).json()          # retry re-queues
    assert again["id"] == rid and _wait_ready(client, t, rid)["status"] == "ready"
