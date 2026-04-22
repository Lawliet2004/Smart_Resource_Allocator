"""Jinja template setup and shared render helpers."""

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.models.user import User
from app.web.options import SKILL_OPTIONS

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


def skill_label(value: str) -> str:
    labels = dict(SKILL_OPTIONS)
    return labels.get(value, value.replace("_", " ").title())


templates.env.filters["skill_label"] = skill_label


def context(
    request: Request,
    user: User | None = None,
    **extra: Any,
) -> dict[str, Any]:
    message = extra.pop("message", None) or request.query_params.get("message")
    error = extra.pop("error", None) or request.query_params.get("error")
    return {"request": request, "user": user, "message": message, "error": error, **extra}
