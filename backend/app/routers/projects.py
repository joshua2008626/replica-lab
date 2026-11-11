from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.db.models import Project
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["Projects"])


def to_project_response(project: Project) -> ProjectResponse:
    """Helper to convert a Project ORM instance into ProjectResponse with computed counts."""
    artifacts_list = project.artifacts or []
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        updated_at=project.updated_at,
        artifact_count=len(artifacts_list),
        artifacts=artifacts_list,
    )


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project workspace",
)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new project container for managing software artifacts."""
    new_project = Project(
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
    )
    db.add(new_project)
    await db.commit()
    await db.refresh(new_project)
    return to_project_response(new_project)


@router.get(
    "",
    response_model=List[ProjectResponse],
    summary="List all project workspaces",
)
async def list_projects(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=100, description="Limit of projects to retrieve"),
    search: Optional[str] = Query(None, description="Optional case-insensitive substring search by name"),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all projects ordered by newest first, with optional pagination and search."""
    stmt = (
        select(Project)
        .options(selectinload(Project.artifacts))
        .order_by(Project.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    if search and search.strip():
        stmt = stmt.where(Project.name.ilike(f"%{search.strip()}%"))

    result = await db.execute(stmt)
    projects = result.scalars().all()
    return [to_project_response(p) for p in projects]


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get project details by ID",
)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve details, timestamps, and artifacts for a single project workspace."""
    stmt = (
        select(Project)
        .options(selectinload(Project.artifacts))
        .where(Project.id == project_id)
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    return to_project_response(project)


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update an existing project workspace",
)
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a project's name or description."""
    stmt = (
        select(Project)
        .options(selectinload(Project.artifacts))
        .where(Project.id == project_id)
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    if payload.name is not None:
        project.name = payload.name.strip()
    if payload.description is not None:
        project.description = payload.description.strip() if payload.description else None

    await db.commit()
    await db.refresh(project)
    return to_project_response(project)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a project workspace",
)
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a project workspace and cascade-delete all associated database records."""
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    await db.delete(project)
    await db.commit()

    return {
        "ok": True,
        "message": f"Project '{project_id}' deleted successfully",
    }
