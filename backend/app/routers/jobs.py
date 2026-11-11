"""FastAPI router for background analysis jobs."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.db.models import AnalysisJob, Artifact, Project, utc_now
from app.schemas.job import JobDetailResponse, JobResponse
from app.services.job_manager import job_manager

router = APIRouter(tags=["Analysis Jobs"])


@router.post(
    "/api/projects/{project_id}/artifacts/{artifact_id}/analyze",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger asynchronous background analysis for an uploaded artifact",
)
async def start_artifact_analysis(
    project_id: str,
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    """Validate project and artifact, create a persistent queued job, and launch asynchronous processing."""
    # 1. Validate project existence
    proj_stmt = select(Project).where(Project.id == project_id)
    project = (await db.execute(proj_stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' was not found.",
        )

    # 2. Validate artifact existence and project ownership
    art_stmt = select(Artifact).where(Artifact.id == artifact_id)
    artifact = (await db.execute(art_stmt)).scalar_one_or_none()
    if not artifact or artifact.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' was not found in project '{project_id}'.",
        )

    # 3. Prevent duplicate concurrent processing of the same artifact
    active_stmt = select(AnalysisJob).where(
        AnalysisJob.artifact_id == artifact_id,
        AnalysisJob.status.in_(["queued", "running"]),
    )
    existing_active = (await db.execute(active_stmt)).scalars().first()
    if existing_active or job_manager.is_artifact_active(artifact_id):
        active_id = existing_active.id if existing_active else "active"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An analysis job ({active_id}) is already active for artifact '{artifact_id}'.",
        )

    # 4. Create and persist the queued job record with database-level race protection
    new_job = AnalysisJob(
        project_id=project_id,
        artifact_id=artifact_id,
        status="queued",
        progress_percent=0,
        current_step="Queued for analysis",
        created_at=utc_now(),
    )
    db.add(new_job)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An analysis job is already active for artifact '{artifact_id}'.",
        )
    await db.refresh(new_job)

    # 5. Enqueue with background manager
    await job_manager.enqueue_job(new_job.id, project_id, artifact_id)

    return JobResponse.model_validate(new_job)


@router.get(
    "/api/jobs/{job_id}",
    response_model=JobDetailResponse,
    summary="Retrieve current job telemetry, progress, findings summary, and evidence records",
)
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobDetailResponse:
    """Fetch persistent job state, progress, and immutable evidence from SQLite."""
    stmt = (
        select(AnalysisJob)
        .options(selectinload(AnalysisJob.evidence_records))
        .where(AnalysisJob.id == job_id)
    )
    job = (await db.execute(stmt)).scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis job '{job_id}' was not found.",
        )

    return JobDetailResponse.from_orm_with_summary(job)


@router.get(
    "/api/projects/{project_id}/jobs",
    response_model=List[JobResponse],
    summary="List all historical and active analysis jobs for a given project",
)
async def list_project_jobs(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> List[JobResponse]:
    """Retrieve all analysis jobs belonging to a project, ordered by creation date."""
    # Verify project exists
    proj_stmt = select(Project).where(Project.id == project_id)
    project = (await db.execute(proj_stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' was not found.",
        )

    stmt = (
        select(AnalysisJob)
        .where(AnalysisJob.project_id == project_id)
        .order_by(AnalysisJob.created_at.desc())
    )
    jobs = (await db.execute(stmt)).scalars().all()
    return [JobResponse.model_validate(j) for j in jobs]


@router.post(
    "/api/jobs/{job_id}/cancel",
    response_model=JobResponse,
    summary="Safely cancel a queued or running analysis job",
)
async def cancel_job_endpoint(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    """Transition a non-terminal job to 'cancelled' and abort subsequent tool dispatches."""
    stmt = select(AnalysisJob).where(AnalysisJob.id == job_id)
    job = (await db.execute(stmt)).scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis job '{job_id}' was not found.",
        )

    if job.status in ("completed", "partial", "failed", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job '{job_id}' in terminal state '{job.status}'.",
        )

    success = await job_manager.cancel_job(job_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job '{job_id}' could not be cancelled.",
        )

    # Reload updated job
    await db.refresh(job)
    return JobResponse.model_validate(job)
