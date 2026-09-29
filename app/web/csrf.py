"""CSRF protection for cookie-authenticated form submissions.

Strategy: signed double-submit cookie.

* Every HTML response carries a ``sra_csrf`` cookie holding ``<random>.<hmac>``,
  signed with ``JWT_SECRET`` so a same-site attacker cannot inject a cookie
  value they also know how to put in a form field.
* Every unsafe request (POST/PUT/PATCH/DELETE) must echo that exact value back
  in a ``csrf_token`` form field or an ``X-CSRF-Token`` header.
* Unsafe requests additionally have their ``Origin`` / ``Referer`` checked
  against the request host, which blocks cross-site submissions even before the
  token is examined.

The check lives in ASGI middleware rather than in each route so a new form
cannot forget it. JSON endpoints under ``/api/`` are exempt from the token
requirement — a cross-origin ``application/json`` POST triggers a CORS preflight
that no CORS middleware answers, so the browser never sends it — but they are
still subject to the origin check.
"""

import hashlib
import hmac
import secrets
from http.cookies import SimpleCookie
from urllib.parse import parse_qsl, urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

CSRF_COOKIE = "sra_csrf"
CSRF_FIELD = "csrf_token"
CSRF_HEADER = "x-csrf-token"

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"

# Requests whose body we are willing to buffer for token extraction. Anything
# larger is rejected by the form parser anyway.
_MAX_BUFFERED_BODY = 1_000_000


def _sign(raw: str) -> str:
    return hmac.new(
        settings.JWT_SECRET.encode("utf-8"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def generate_csrf_token() -> str:
    raw = secrets.token_urlsafe(32)
    return f"{raw}.{_sign(raw)}"


def is_valid_csrf_token(token: str | None) -> bool:
    if not token or token.count(".") != 1:
        return False
    raw, signature = token.split(".", 1)
    if not raw or not signature:
        return False
    return hmac.compare_digest(signature, _sign(raw))


def tokens_match(cookie_token: str | None, submitted_token: str | None) -> bool:
    if not is_valid_csrf_token(cookie_token) or not submitted_token:
        return False
    return hmac.compare_digest(cookie_token or "", submitted_token)


def _cookie_token(headers: Headers) -> str | None:
    cookie_header = headers.get("cookie")
    if not cookie_header:
        return None
    jar: SimpleCookie = SimpleCookie()
    try:
        jar.load(cookie_header)
    except Exception:
        return None
    morsel = jar.get(CSRF_COOKIE)
    return morsel.value if morsel is not None else None


def _origin_is_same_site(headers: Headers) -> bool:
    """Reject unsafe requests that declare a foreign origin.

    A missing Origin *and* Referer is allowed: non-browser clients (curl, the
    test client, server-to-server calls) omit both, and those are not subject to
    CSRF. Browsers always send Origin on cross-origin unsafe requests.
    """
    source = headers.get("origin") or headers.get("referer")
    if not source:
        return True

    host = headers.get("host")
    if not host:
        return False

    parsed = urlsplit(source)
    if not parsed.netloc:
        return False
    return parsed.netloc.casefold() == host.casefold()


class CSRFMiddleware:
    """Issues CSRF cookies and validates them on unsafe requests."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        cookie_token = _cookie_token(headers)

        # Reuse a valid existing token so a user with several tabs open keeps a
        # single stable token; otherwise mint one and set it on the way out.
        if is_valid_csrf_token(cookie_token):
            token = cookie_token or ""
            set_cookie = False
        else:
            token = generate_csrf_token()
            set_cookie = True

        scope.setdefault("state", {})
        scope["state"]["csrf_token"] = token

        method: str = scope["method"]
        if method not in SAFE_METHODS:
            if not _origin_is_same_site(headers):
                await self._reject(scope, receive, send, "Cross-site request blocked.")
                return

            path: str = scope.get("path", "")
            if not path.startswith("/api/"):
                receive, submitted = await self._extract_token(headers, receive)
                if not tokens_match(cookie_token, submitted):
                    await self._reject(
                        scope,
                        receive,
                        send,
                        "Your session expired or the form was stale. Please reload and try again.",
                    )
                    return

        await self.app(scope, receive, self._wrap_send(send, token, set_cookie))

    async def _extract_token(
        self, headers: Headers, receive: Receive
    ) -> tuple[Receive, str | None]:
        """Return a replayable receive plus the submitted token, if any."""
        header_token = headers.get(CSRF_HEADER)
        content_type = (headers.get("content-type") or "").split(";", 1)[0].strip().casefold()
        if header_token or content_type != FORM_CONTENT_TYPE:
            return receive, header_token

        messages: list[Message] = []
        body = b""
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] != "http.request":
                break
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break
            if len(body) > _MAX_BUFFERED_BODY:
                break

        async def replay() -> Message:
            if messages:
                return messages.pop(0)
            return await receive()

        try:
            fields = dict(parse_qsl(body.decode("utf-8"), keep_blank_values=True))
        except UnicodeDecodeError:
            return replay, None
        return replay, fields.get(CSRF_FIELD)

    def _wrap_send(self, send: Send, token: str, set_cookie: bool) -> Send:
        if not set_cookie:
            return send

        async def wrapped(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append(
                    "set-cookie",
                    (
                        f"{CSRF_COOKIE}={token}; Path=/; SameSite=Lax; HttpOnly"
                        f"{'; Secure' if settings.session_cookie_secure else ''}"
                    ),
                )
            await send(message)

        return wrapped

    async def _reject(self, scope: Scope, receive: Receive, send: Send, detail: str) -> None:
        response = PlainTextResponse(detail, status_code=403)
        await response(scope, receive, send)
