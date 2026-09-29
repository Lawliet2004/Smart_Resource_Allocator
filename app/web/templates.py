"""Jinja template setup and shared render helpers."""

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.models.user import User
from app.services.skills import skill_label

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"


class WebTemplates(Jinja2Templates):
    """Accept the older FastAPI template call shape used by this web layer."""

    def TemplateResponse(self, name: str, template_context: dict[str, Any], **kwargs: Any):
        return super().TemplateResponse(
            template_context["request"],
            name,
            template_context,
            **kwargs,
        )


templates = WebTemplates(directory=str(TEMPLATE_DIR))


templates.env.filters["skill_label"] = skill_label


def context(
    request: Request,
    user: User | None = None,
    **extra: Any,
) -> dict[str, Any]:
    message = extra.pop("message", None) or request.query_params.get("message")
    error = extra.pop("error", None) or request.query_params.get("error")
    return {
        "request": request,
        "user": user,
        "message": message,
        "error": error,
        # Injected by CSRFMiddleware; every <form> must render it as a hidden
        # input, and HTMX requests may send it as the X-CSRF-Token header.
        "csrf_token": getattr(request.state, "csrf_token", ""),
        **extra,
    }
