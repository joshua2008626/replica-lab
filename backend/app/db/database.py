from collections.abc import AsyncGenerator
from pathlib import Path
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from app.core.config import BACKEND_DIR, settings


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy database models."""
    pass


# Enforce foreign key constraints and concurrency pragmas in SQLite
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Ensure SQLite enforces ON DELETE CASCADE, busy timeouts, and WAL mode."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


# Normalize database URL to ensure absolute path on Windows
db_url = settings.DATABASE_URL
if db_url.startswith("sqlite+aiosqlite:///storage/"):
    # Convert relative storage path to absolute backend path
    db_filename = db_url.replace("sqlite+aiosqlite:///storage/", "")
    abs_db_path = settings.absolute_storage_dir / db_filename
    db_url = f"sqlite+aiosqlite:///{abs_db_path.as_posix()}"

engine = create_async_engine(
    db_url,
    echo=settings.DEBUG,
    future=True,
)

async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for obtaining an isolated async database session."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables and run lightweight migrations on application startup."""
    # Ensure storage folder exists
    settings.absolute_storage_dir.mkdir(parents=True, exist_ok=True)
    # Import all models to ensure metadata is populated before creation
    import app.db.models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Lightweight schema evolution: ensure analysis_jobs has project_id and result_summary_json
        res = await conn.execute(text("PRAGMA table_info(analysis_jobs)"))
        existing_cols = {row[1] for row in res.fetchall()}
        if "project_id" not in existing_cols:
            await conn.execute(text("ALTER TABLE analysis_jobs ADD COLUMN project_id VARCHAR(36) REFERENCES projects(id) ON DELETE CASCADE"))
        if "result_summary_json" not in existing_cols:
            await conn.execute(text("ALTER TABLE analysis_jobs ADD COLUMN result_summary_json TEXT"))

        # Safe non-destructive pre-migration reconciliation:
        # Reconcile any pre-existing duplicate active jobs before creating the partial unique index
        dup_rows = await conn.execute(text(
            "SELECT artifact_id FROM analysis_jobs "
            "WHERE status IN ('queued', 'running') "
            "GROUP BY artifact_id HAVING COUNT(*) > 1"
        ))
        duplicate_artifact_ids = [row[0] for row in dup_rows.fetchall()]

        if duplicate_artifact_ids:
            from datetime import datetime, timezone
            now_iso = datetime.now(timezone.utc).isoformat()
            for art_id in duplicate_artifact_ids:
                jobs_for_art = await conn.execute(
                    text(
                        "SELECT id FROM analysis_jobs "
                        "WHERE artifact_id = :art_id AND status IN ('queued', 'running') "
                        "ORDER BY created_at DESC"
                    ),
                    {"art_id": art_id},
                )
                job_ids = [r[0] for r in jobs_for_art.fetchall()]
                for old_id in job_ids[1:]:
                    await conn.execute(
                        text(
                            "UPDATE analysis_jobs SET "
                            "status = 'failed', "
                            "completed_at = :now, "
                            "current_step = 'Superseded during migration', "
                            "error_message = 'Marked as failed during migration due to pre-existing duplicate active jobs for this artifact. Preserved for audit.' "
                            "WHERE id = :id"
                        ),
                        {"now": now_iso, "id": old_id},
                    )

        # Database-level guarantee: prevent duplicate concurrent active jobs for the same artifact
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_artifact_job "
            "ON analysis_jobs (artifact_id) "
            "WHERE status IN ('queued', 'running')"
        ))
