"""API router endpoints."""

from app.routers.health import router as health_router
from app.routers.projects import router as projects_router
from app.routers.uploads import router as uploads_router
from app.routers.jobs import router as jobs_router

__all__ = [
    "health_router",
    "projects_router",
    "uploads_router",
    "jobs_router",
]
