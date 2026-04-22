"""FastAPI entry point."""

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.router import api_router
from app.core.database import get_db
from app.web.router import web_router

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Smart Resource Allocator",
    description="Volunteer coordination platform for NGOs.",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(web_router)
app.include_router(api_router, prefix="/api")


@app.get("/health")
def health() -> dict[str, bool | str]:
    """Liveness probe."""
    return {"ok": True, "service": "smart-resource-allocator"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict[str, bool | str | int]:
    """Readiness probe: runs SELECT 1 against Postgres."""
    try:
        result = db.execute(text("SELECT 1")).scalar()
        return {"ok": True, "db": "connected", "result": result}
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"db unavailable: {exc.__class__.__name__}",
        ) from exc
