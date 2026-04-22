"""Rate limiting helpers and 429 responses."""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.security import decode_access_token
from app.web.deps import SESSION_COOKIE
from app.web.options import ROLE_OPTIONS
from app.web.templates import context, templates


def get_client_ip_key(request: Request) -> str:
    # X-Forwarded-For is client-controlled and can be freely spoofed unless
    # the app is deployed behind a trusted reverse proxy that overwrites it.
    # Only honor it when TRUST_FORWARDED_HEADERS is enabled; otherwise fall
    # back to the direct peer address so rate-limit buckets can't be rotated.
    if settings.TRUST_FORWARDED_HEADERS:
        forwarded_for = (
            request.headers.get("x-forwarded-for", "").split(",", maxsplit=1)[0].strip()
        )
        if forwarded_for:
            return f"ip:{forwarded_for}"
    client = request.client.host if request.client is not None else "unknown"
    return f"ip:{client}"


def user_or_ip_key(request: Request) -> str:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        user_id = decode_access_token(token)
        if user_id is not None:
            return f"user:{user_id}"
    return get_client_ip_key(request)


limiter = Limiter(key_func=get_client_ip_key)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    message = "Too many requests. Please wait a moment and try again."
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": message},
        )

    template_name = "auth/register.html" if request.url.path == "/register" else "auth/login.html"
    template_context = context(request, error=message)
    if template_name == "auth/register.html":
        template_context["roles"] = ROLE_OPTIONS
    return templates.TemplateResponse(
        template_name,
        template_context,
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
    )