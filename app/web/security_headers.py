"""HTTP security headers middleware helpers."""

from fastapi import Response

from app.core.config import settings

_DEPLOYED_ENVS = {"prod", "production", "staging"}

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://unpkg.com",
        "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://unpkg.com",
        "img-src 'self' data: https:",
        "font-src 'self' data: https:",
        "connect-src 'self' https:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)


def add_security_headers(response: Response) -> None:
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"

    if settings.APP_ENV.lower() in _DEPLOYED_ENVS:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"