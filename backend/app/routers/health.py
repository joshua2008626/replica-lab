import time
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.database import get_db

router = APIRouter(prefix="/health", tags=["System Health"])

START_TIME = time.time()


@router.get("")
async def check_health(db: AsyncSession = Depends(get_db)):
    """Comprehensive system health check: API, SQLite Database, and REA MCP Server probe."""
    uptime_seconds = round(time.time() - START_TIME, 2)

    # 1. Probe SQLite Database
    db_status = "disconnected"
    try:
        result = await db.execute(text("SELECT 1"))
        if result.scalar() == 1:
            db_status = "connected"
    except Exception as exc:
        db_status = f"error: {str(exc)}"

    # 2. Probe REA MCP Server (non-blocking 1.5s timeout)
    rea_status = "disconnected"
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(settings.REA_MCP_URL)
            # REA HTTP listener returns 405 or 200 on basic probe
            if resp.status_code in (200, 400, 405):
                rea_status = "reachable"
            else:
                rea_status = f"unexpected_status: {resp.status_code}"
    except httpx.ConnectError:
        rea_status = "not_running"
    except Exception as exc:
        rea_status = f"offline ({type(exc).__name__})"

    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "uptime_seconds": uptime_seconds,
        "components": {
            "database": db_status,
            "rea_mcp_engine": rea_status,
            "storage_ready": settings.absolute_upload_dir.exists(),
        },
    }
