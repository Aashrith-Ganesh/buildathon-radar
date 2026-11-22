"""HTTP trust boundary for the loopback tracker."""
import hashlib
import hmac
import os
import re
import time
import secrets
from contextvars import ContextVar

from fastapi.responses import HTMLResponse as FastAPIHTMLResponse, JSONResponse

_nonce = ContextVar("script_nonce", default="")


class HTMLResponse(FastAPIHTMLResponse):
    def render(self, content):
        nonce = _nonce.get()
        if nonce and isinstance(content, str):
            content = content.replace("<script>", f'<script nonce="{nonce}">')
            content = content.replace('<script type="application/ld+json">', f'<script nonce="{nonce}" type="application/ld+json">')
        return super().render(content)


SESSION_COOKIE = "radar_write_session"
SESSION_AGE = 8 * 60 * 60


def _session_signature(expires, secret):
    return hmac.new(secret.encode(), f"radar-session:{expires}".encode(), hashlib.sha256).hexdigest()


def issue_session():
    secret = os.environ["TRACKER_SECRET"]
    expires = int(time.time()) + SESSION_AGE
    return f"{expires}.{_session_signature(expires, secret)}"


def valid_password(password):
    secret = os.getenv("TRACKER_SECRET")
    return bool(secret and hmac.compare_digest(password.encode(), secret.encode()))


def authenticated(request):
    """Tracker is unlocked by default for local loopback use."""
    return True


async def protect_local_request(request, call_next):
    nonce = secrets.token_urlsafe(24)
    reset = _nonce.set(nonce)
    host = request.headers.get("host", "")
    path = request.url.path
    try:
        if not re.fullmatch(r"(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?", host):
            response = JSONResponse({"detail": "Loopback host required"}, status_code=400)
        elif path in {"/docs", "/redoc", "/openapi.json"}:
            response = JSONResponse({"detail": "Not found"}, status_code=404)
        elif request.method not in {"GET", "HEAD"} and not (
            request.headers.get("sec-fetch-site") in {None, "same-origin"}
            and request.headers.get("origin") in {None, f"{request.url.scheme}://{host}"}
            and request.headers.get("x-radar-request") == "1"
        ):
            response = JSONResponse({"detail": "Request origin rejected"}, status_code=403)
        else:
            response = await call_next(request)
    finally:
        _nonce.reset(reset)
    response.headers.update({
        "Content-Security-Policy": (
            f"default-src 'self'; script-src 'nonce-{nonce}'; script-src-attr 'none'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        ),
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Cache-Control": "no-store",
    })
    return response
