"""REPLICA LAB — Background Analysis Job Runner.

Manages the asynchronous execution lifecycle of software analysis jobs:
- Strict state machine transitions: queued -> running -> (completed | partial | failed | cancelled).
- Persistent SQLite storage for job telemetry, progress, and immutable evidence records.
- Configurable concurrency ceiling via asyncio.Semaphore.
- Duplicate execution prevention on the same artifact.
- Safe crash and restart recovery policy (no blind retries of uncertain operations).
- Controlled cancellation preventing subsequent tool execution.
"""

import asyncio
import inspect
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Set

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.database import async_session_maker
from app.db.models import AnalysisJob, Artifact, EvidenceRecord, utc_now
from app.services.dispatcher import DispatchResult, dispatch_analysis

logger = logging.getLogger(__name__)

# Valid state machine transitions
VALID_TRANSITIONS: Dict[str, Set[str]] = {
    "queued": {"running", "cancelled", "failed"},
    "running": {"completed", "partial", "failed", "cancelled"},
    "completed": set(),
    "partial": set(),
    "failed": set(),
    "cancelled": set(),
}


class JobStateTransitionError(Exception):
    """Raised when an illegal job state transition is attempted."""
    pass


class JobManager:
    """Orchestrates persistent background analysis jobs with bounded concurrency."""

    def __init__(
        self,
        max_concurrent_jobs: Optional[int] = None,
        dispatcher_fn: Optional[Callable] = None,
    ):
        self.max_concurrent_jobs = max_concurrent_jobs or settings.MAX_CONCURRENT_JOBS
        self._semaphore = asyncio.Semaphore(self.max_concurrent_jobs)
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._active_artifacts: Set[str] = set()
        self._cancelled_jobs: Set[str] = set()
        self._is_shutting_down = False
        self._dispatcher_fn = dispatcher_fn or dispatch_analysis
        self._lock = asyncio.Lock()

    def is_job_cancelled(self, job_id: str) -> bool:
        """Check if job_id has been flagged for cancellation."""
        return job_id in self._cancelled_jobs

    def set_dispatcher(self, fn: Callable) -> None:
        """Inject a custom dispatcher function (e.g. for testing)."""
        self._dispatcher_fn = fn

    # -----------------------------------------------------------------------
    # State Validation Helper
    # -----------------------------------------------------------------------

    def validate_transition(self, current_status: str, target_status: str) -> None:
        """Verify that transitioning from current_status to target_status is valid."""
        allowed = VALID_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            raise JobStateTransitionError(
                f"Invalid job state transition: '{current_status}' -> '{target_status}'. "
                f"Allowed target states: {sorted(list(allowed)) or 'None (Terminal state)'}"
            )

    # -----------------------------------------------------------------------
    # Restart Recovery Policy
    # -----------------------------------------------------------------------

    async def recover_interrupted_jobs(self) -> Dict[str, int]:
        """Detect and safely reconcile jobs left in-flight after an application restart or crash.

        Policy:
        - 'running' jobs: Mark as 'failed'. Do NOT automatically retry uncertain operations,
          as the analyzer may have already executed or state may have been modified.
        - 'queued' jobs: Mark as 'failed' with clear error notice.
        Returns counts of recovered jobs.
        """
        recovered_running = 0
        recovered_queued = 0
        now = utc_now()

        async with async_session_maker() as session:
            # 1. Recover interrupted running jobs
            stmt_running = select(AnalysisJob).where(AnalysisJob.status == "running")
            running_jobs = (await session.execute(stmt_running)).scalars().all()

            for job in running_jobs:
                job.status = "failed"
                job.completed_at = now
                job.current_step = "Interrupted by application restart"
                job.error_message = (
                    "Analysis job was interrupted by an application restart while running. "
                    "Uncertain REA operations were not automatically retried to prevent state corruption."
                )
                recovered_running += 1

            # 2. Recover abandoned queued jobs
            stmt_queued = select(AnalysisJob).where(AnalysisJob.status == "queued")
            queued_jobs = (await session.execute(stmt_queued)).scalars().all()

            for job in queued_jobs:
                job.status = "failed"
                job.completed_at = now
                job.current_step = "Interrupted before execution"
                job.error_message = (
                    "Analysis job was queued when the application restarted and was not executed. "
                    "Please submit a new analysis request."
                )
                recovered_queued += 1

            if recovered_running > 0 or recovered_queued > 0:
                await session.commit()
                logger.warning(
                    "Restart recovery complete: marked %d running jobs and %d queued jobs as failed.",
                    recovered_running,
                    recovered_queued,
                )

        return {"recovered_running": recovered_running, "recovered_queued": recovered_queued}

    # -----------------------------------------------------------------------
    # Enqueue & Launch Job
    # -----------------------------------------------------------------------

    async def enqueue_job(self, job_id: str, project_id: str, artifact_id: str) -> asyncio.Task:
        """Register the job in active tracking and schedule asynchronous execution."""
        async with self._lock:
            self._active_artifacts.add(artifact_id)
            task = asyncio.create_task(
                self._run_job_lifecycle(job_id, project_id, artifact_id),
                name=f"job-{job_id}",
            )
            self._active_tasks[job_id] = task
            return task

    def is_artifact_active(self, artifact_id: str) -> bool:
        """Check if an artifact currently has an active queued or running job."""
        return artifact_id in self._active_artifacts

    # -----------------------------------------------------------------------
    # Job Cancellation
    # -----------------------------------------------------------------------

    async def cancel_job(self, job_id: str) -> bool:
        """Safely cancel a queued or running job.

        Guarantees:
        - If still queued, transitions to 'cancelled' before execution.
        - If running, marks job as 'cancelled' and aborts subsequent tools.
        - Does NOT pretend that an already-issued remote MCP command was undone.
        - Persists 'cancelled' state in database.
        """
        async with self._lock:
            self._cancelled_jobs.add(job_id)

        async with async_session_maker() as session:
            stmt = select(AnalysisJob).where(AnalysisJob.id == job_id)
            job = (await session.execute(stmt)).scalar_one_or_none()
            if not job:
                return False

            if job.status in ("completed", "partial", "failed", "cancelled"):
                return False

            self.validate_transition(job.status, "cancelled")
            job.status = "cancelled"
            job.completed_at = utc_now()
            job.current_step = "Cancelled by user"
            job.error_message = "Analysis job was cancelled by user request."
            await session.commit()

        # Cancel active task if running in background
        async with self._lock:
            task = self._active_tasks.get(job_id)
            if task and not task.done():
                task.cancel()

        return True

    # -----------------------------------------------------------------------
    # Core Background Execution Worker
    # -----------------------------------------------------------------------

    async def _run_job_lifecycle(self, job_id: str, project_id: str, artifact_id: str) -> None:
        """Execute the job under bounded concurrency with database synchronization."""
        try:
            # 1. Acquire concurrency semaphore (limits simultaneous active analyzers)
            async with self._semaphore:
                # 2. Check if cancelled while waiting in semaphore queue
                async with async_session_maker() as session:
                    stmt = select(AnalysisJob).where(AnalysisJob.id == job_id)
                    job = (await session.execute(stmt)).scalar_one_or_none()
                    if not job or job.status in ("completed", "partial", "failed", "cancelled") or self.is_job_cancelled(job_id):
                        logger.info("Job %s was cancelled or in terminal state before execution started.", job_id)
                        return

                    # 3. Transition to 'running'
                    self.validate_transition(job.status, "running")
                    job.status = "running"
                    job.started_at = utc_now()
                    job.progress_percent = max(job.progress_percent, 10)
                    job.current_step = "Initializing analysis dispatcher"
                    await session.commit()

                # 4. Fetch artifact
                async with async_session_maker() as session:
                    stmt_art = select(Artifact).where(Artifact.id == artifact_id)
                    artifact = (await session.execute(stmt_art)).scalar_one_or_none()
                    if not artifact:
                        raise ValueError(f"Artifact '{artifact_id}' could not be loaded for job '{job_id}'.")

                # Dispatcher performs all verified REA tool calls outside any database session
                # to prevent SQLite lock contention during long-running tool dispatches.
                sig = inspect.signature(self._dispatcher_fn)
                if "is_cancelled" in sig.parameters:
                    dispatch_result: DispatchResult = await self._dispatcher_fn(
                        artifact, project_id, is_cancelled=lambda: self.is_job_cancelled(job_id)
                    )
                else:
                    dispatch_result = await self._dispatcher_fn(artifact, project_id)

                # 5. Check if cancelled during dispatcher run
                async with async_session_maker() as session:
                    stmt = select(AnalysisJob).where(AnalysisJob.id == job_id)
                    job = (await session.execute(stmt)).scalar_one_or_none()
                    if not job:
                        return
                    if job.status in ("completed", "partial", "failed", "cancelled") or self.is_job_cancelled(job_id):
                        logger.info("Job %s was cancelled or terminal during execution; discarding late completion update.", job_id)
                        return

                    # 6. Persist immutable EvidenceRecord entries
                    for tr in dispatch_result.tool_results:
                        er = EvidenceRecord(
                            job_id=job.id,
                            tool_name=tr.tool_name,
                            category=tr.category,
                            raw_evidence_json=json.dumps(
                                {
                                    "status": tr.status,
                                    "arguments": tr.arguments,
                                    "raw_result": tr.raw_result,
                                    "raw_text": tr.raw_text,
                                    "parsed": tr.parsed_evidence,
                                    "error_message": tr.error_message,
                                }
                            ),
                            created_at=utc_now(),
                        )
                        session.add(er)

                    # 7. Map final status and persist summary
                    if dispatch_result.status == "completed":
                        self.validate_transition(job.status, "completed")
                        job.status = "completed"
                        job.progress_percent = 100
                        job.current_step = "Analysis completed successfully"
                        job.error_message = None
                    elif dispatch_result.status == "partial":
                        self.validate_transition(job.status, "partial")
                        job.status = "partial"
                        job.progress_percent = 100
                        job.current_step = "Analysis completed with partial tool results"
                        job.error_message = dispatch_result.message
                    elif dispatch_result.status in ("unsupported", "inconclusive"):
                        self.validate_transition(job.status, "partial")
                        job.status = "partial"
                        job.progress_percent = 100
                        job.current_step = f"Format {dispatch_result.status}"
                        job.error_message = dispatch_result.message
                    else:
                        self.validate_transition(job.status, "failed")
                        job.status = "failed"
                        job.progress_percent = 100
                        job.current_step = "Analysis failed"
                        job.error_message = dispatch_result.message or "All tool invocations failed."

                    job.completed_at = utc_now()
                    job.result_summary_json = json.dumps(dispatch_result.summary.model_dump())
                    await session.commit()
                    logger.info("Job %s completed with status '%s'", job_id, job.status)

        except asyncio.CancelledError:
            logger.info("Job %s received asyncio cancellation signal.", job_id)
            async with async_session_maker() as session:
                stmt = select(AnalysisJob).where(AnalysisJob.id == job_id)
                job = (await session.execute(stmt)).scalar_one_or_none()
                if job and job.status not in ("completed", "partial", "failed", "cancelled"):
                    if self.is_job_cancelled(job_id):
                        job.status = "cancelled"
                        job.completed_at = utc_now()
                        job.current_step = "Cancelled by user"
                        job.error_message = "Analysis job was cancelled by user request."
                    else:
                        job.status = "failed"
                        job.completed_at = utc_now()
                        job.current_step = "Interrupted by application shutdown"
                        job.error_message = (
                            "Analysis job was interrupted by application shutdown while in progress. "
                            "Uncertain REA operations were not automatically retried to prevent state corruption."
                        )
                    await session.commit()
        except Exception as exc:
            logger.exception("Unexpected error in background job %s: %s", job_id, exc)
            async with async_session_maker() as session:
                stmt = select(AnalysisJob).where(AnalysisJob.id == job_id)
                job = (await session.execute(stmt)).scalar_one_or_none()
                if job and job.status not in ("completed", "partial", "failed", "cancelled"):
                    job.status = "failed"
                    job.completed_at = utc_now()
                    job.current_step = "Failed due to internal error"
                    job.error_message = f"Execution error: {str(exc)}"
                    await session.commit()
        finally:
            # Always clean up active tracking
            async with self._lock:
                self._active_tasks.pop(job_id, None)
                self._active_artifacts.discard(artifact_id)
                self._cancelled_jobs.discard(job_id)

    async def shutdown(self) -> None:
        """Cancel and await all in-flight jobs during graceful server shutdown."""
        self._is_shutting_down = True
        async with self._lock:
            tasks = list(self._active_tasks.values())
        for t in tasks:
            if not t.done():
                t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


# Global job manager instance
job_manager = JobManager()
