from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.core.config import settings
from app.db.database import engine, init_db
from app.routers.health import router as health_router
from app.routers.projects import router as projects_router
from app.routers.uploads import router as uploads_router
from app.routers.jobs import router as jobs_router
from app.services.job_manager import job_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager to safely initialize and teardown resources."""
    # Startup: initialize database tables, directories, and recover interrupted jobs
    await init_db()
    await job_manager.recover_interrupted_jobs()
    yield
    # Shutdown: cancel in-flight jobs and gracefully close database connection pool
    await job_manager.shutdown()
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="AI-Powered Software Intelligence & Reverse Engineering Studio",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration for React frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(health_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(uploads_router, prefix="/api")
app.include_router(jobs_router)


@app.get("/", tags=["Root"])
async def root():
    """Root entrypoint returning basic platform metadata."""
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "description": "AI-Powered Software Intelligence & Reverse Engineering Studio",
        "documentation": "/docs",
        "health_check": "/api/health",
        "endpoints": {
            "projects": "/api/projects",
            "uploads": "/api/uploads",
            "jobs": "/api/jobs",
        },
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
