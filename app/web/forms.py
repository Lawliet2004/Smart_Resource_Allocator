"""Small form parsing helpers for URL-encoded HTML forms."""

import math
from urllib.parse import parse_qs

from fastapi import HTTPException, Request, status

from app.core.config import settings


async def parse_urlencoded_form(request: Request) -> dict[str, list[str]]:
    body_bytes = await request.body()
    if len(body_bytes) > settings.MAX_FORM_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Form payload is too large.",
        )

    try:
        body = body_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Form payload must be valid UTF-8.",
        ) from exc

    try:
        return parse_qs(
            body,
            keep_blank_values=True,
            max_num_fields=settings.MAX_FORM_FIELDS,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many form fields.",
        ) from exc


def form_value(form: dict[str, list[str]], key: str, default: str = "") -> str:
    values = form.get(key)
    if not values:
        return default
    return values[0].strip()


def form_list(form: dict[str, list[str]], key: str) -> list[str]:
    return [value.strip() for value in form.get(key, []) if value.strip()]


def form_bool(form: dict[str, list[str]], key: str) -> bool:
    values = form.get(key)
    if not values:
        return False
    value = values[0].strip().lower()
    if not value:
        return True
    return value in {"1", "true", "on", "yes"}


def form_float(
    form: dict[str, list[str]],
    key: str,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float | None:
    value = form_value(form, key)
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    if min_value is not None and parsed < min_value:
        return None
    if max_value is not None and parsed > max_value:
        return None
    return parsed
