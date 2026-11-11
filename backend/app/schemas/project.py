from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ProjectBase(BaseModel):
    """Shared properties for a Project."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="User-friendly name of the project workspace",
        examples=["My Windows Tool Analysis"],
    )
    description: Optional[str] = Field(
        None,
        max_length=2000,
        description="Optional project overview or notes",
        examples=["Investigating native binary imports and security flags"],
    )


class ProjectCreate(ProjectBase):
    """Payload for creating a new project workspace."""
    pass


class ProjectUpdate(BaseModel):
    """Payload for modifying an existing project workspace."""
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Updated project name",
    )
    description: Optional[str] = Field(
        None,
        max_length=2000,
        description="Updated project description",
    )


class ArtifactSummary(BaseModel):
    """Brief metadata summary of an associated software artifact."""
    id: str
    original_filename: str
    file_size_bytes: int
    sha256_hash: str
    detected_format: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectResponse(ProjectBase):
    """Complete project representation returned by API endpoints."""
    id: str
    created_at: datetime
    updated_at: datetime
    artifact_count: int = 0
    artifacts: List[ArtifactSummary] = []

    model_config = ConfigDict(from_attributes=True)
