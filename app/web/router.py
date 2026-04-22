"""Top-level web router."""

from fastapi import APIRouter

from app.web import admin, auth, coordinator, volunteer

web_router = APIRouter()
web_router.include_router(auth.router)
web_router.include_router(volunteer.router, prefix="/v", tags=["web-volunteer"])
web_router.include_router(coordinator.router, prefix="/c", tags=["web-coordinator"])
web_router.include_router(admin.router, prefix="/a", tags=["web-admin"])
