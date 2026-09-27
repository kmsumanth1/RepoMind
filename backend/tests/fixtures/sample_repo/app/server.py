"""HTTP entry points."""
from .auth import TokenError, verify_token
from .base import BaseHandler
from .ratelimit import rate_limit

SECRET = "dev-secret"


@rate_limit(limit=100)
def handle_request(request):
    """Authenticate the caller and dispatch the request."""
    try:
        user = verify_token(request["token"], SECRET)
    except TokenError:
        return {"status": 401, "body": "unauthorized"}
    return {"status": 200, "body": f"hello {user}"}


class AdminHandler(BaseHandler):
    """Handler for admin-only endpoints."""

    def handle(self, request):
        """Only allow admin users."""
        response = handle_request(request)
        if response["status"] == 200 and request.get("role") != "admin":
            return {"status": 403, "body": "forbidden"}
        return response
