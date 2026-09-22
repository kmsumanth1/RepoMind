"""Base classes shared by request handlers."""


class BaseHandler:
    """Common behaviour for every handler."""

    def handle(self, request):
        """Process a request and return a response dict."""
        return {"status": 501, "body": "not implemented"}
