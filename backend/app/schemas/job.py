"""Pydantic schemas for Analysis Jobs and Evidence Records."""

import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EvidenceRecordResponse(BaseModel):
    """Public representation of an immutable raw evidence record."""

    id: str
    job_id: str
    tool_name: str
    category: str
    raw_evidence: Optional[Any] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobResponse(BaseModel):
    """Immediate and summary representation of an asynchronous analysis job."""

    id: str
    project_id: str
    artifact_id: str
    status: str
    progress_percent: int
    current_step: str
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobDetailResponse(JobResponse):
    """Detailed job status including aggregated findings summary and evidence records."""

    summary: Optional[Dict[str, Any]] = None
    evidence_records: List[EvidenceRecordResponse] = Field(default_factory=list)

    @classmethod
    def from_orm_with_summary(cls, job: Any) -> "JobDetailResponse":
        parsed_summary = None
        if getattr(job, "result_summary_json", None):
            try:
                parsed_summary = json.loads(job.result_summary_json)
            except Exception:
                parsed_summary = {"raw": job.result_summary_json}

        records = []
        if getattr(job, "evidence_records", None):
            for er in job.evidence_records:
                parsed_ev = None
                if getattr(er, "raw_evidence_json", None):
                    try:
                        parsed_ev = json.loads(er.raw_evidence_json)
                    except Exception:
                        parsed_ev = er.raw_evidence_json
                records.append(
                    EvidenceRecordResponse(
                        id=er.id,
                        job_id=er.job_id,
                        tool_name=er.tool_name,
                        category=er.category,
                        raw_evidence=parsed_ev,
                        created_at=er.created_at,
                    )
                )

        return cls(
            id=job.id,
            project_id=job.project_id or "",
            artifact_id=job.artifact_id,
            status=job.status,
            progress_percent=job.progress_percent,
            current_step=job.current_step,
            error_message=job.error_message,
            started_at=job.started_at,
            completed_at=job.completed_at,
            created_at=job.created_at,
            summary=parsed_summary,
            evidence_records=records,
        )
