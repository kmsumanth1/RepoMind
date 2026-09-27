"""Token based authentication helpers."""
import base64
import hmac
import hashlib
import json


class TokenError(Exception):
    """Raised when a token is malformed or has a bad signature."""


def decode_payload(token):
    """Decode the payload part of a signed token."""
    body, _, _sig = token.partition(".")
    return json.loads(base64.urlsafe_b64decode(body + "=="))


def create_token(user_id, secret):
    """Create a signed authentication token for a user."""
    body = base64.urlsafe_b64encode(json.dumps({"uid": user_id}).encode()).decode().rstrip("=")
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_token(token, secret):
    """Verify a token signature and return the user id it belongs to."""
    try:
        payload = decode_payload(token)
    except ValueError as exc:
        raise TokenError("malformed token") from exc
    expected = create_token(payload["uid"], secret)
    if not hmac.compare_digest(expected, token):
        raise TokenError("bad signature")
    return payload["uid"]
