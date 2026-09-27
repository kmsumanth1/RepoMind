"""Sliding window rate limiting."""
import time
from collections import defaultdict, deque


class RateLimiter:
    """Allow at most `limit` requests per `window` seconds for each key."""

    def __init__(self, limit, window):
        self.limit = limit
        self.window = window
        self.hits = defaultdict(deque)

    def _prune(self, key, now):
        """Drop timestamps that fell out of the window."""
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def allow(self, key):
        """Return True if this request is within the rate limit."""
        now = time.time()
        q = self._prune(key, now)
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


def rate_limit(limit, window=60):
    """Decorator factory that applies a RateLimiter to a handler function."""
    limiter = RateLimiter(limit, window)

    def wrap(fn):
        def inner(request):
            if not limiter.allow(request["client"]):
                return {"status": 429, "body": "too many requests"}
            return fn(request)
        return inner
    return wrap
