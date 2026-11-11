import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import ForeignKey, Index, Integer, String, Text, TypeDecorator, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base


def generate_uuid() -> str:
    """Generate a standard RFC 4122 UUID4 string."""
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Custom SQLAlchemy type ensuring SQLite datetimes are always timezone-aware UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Optional[datetime], dialect) -> Optional[datetime]:
        if value is not None:
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value: Optional[datetime], dialect) -> Optional[datetime]:
        if value is not None:
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        return value


class Project(Base):
    """A workspace container for one or more software artifacts and analyses."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    # 1 Project -> Many Artifacts (Cascade delete orphans in DB)
    artifacts: Mapped[List["Artifact"]] = relationship(
        "Artifact",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    analysis_jobs: Mapped[List["AnalysisJob"]] = relationship(
        "AnalysisJob",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class Artifact(Base):
    """An uploaded software file (binary, bundle, package) stored in quarantine."""

    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    storage_path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    sha256_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    detected_format: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=utc_now,
        nullable=False,
    )

    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="artifacts",
    )
    analysis_jobs: Mapped[List["AnalysisJob"]] = relationship(
        "AnalysisJob",
        back_populates="artifact",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class AnalysisJob(Base):
    """Tracks the asynchronous execution lifecycle of an analysis task."""

    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    artifact_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("artifacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="queued",
        nullable=False,
        index=True,
    )  # queued, running, completed, partial, failed, cancelled
    progress_percent: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    current_step: Mapped[str] = mapped_column(
        String(255),
        default="Queued for analysis",
        nullable=False,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    result_summary_json: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=utc_now,
        nullable=False,
    )

    project: Mapped[Optional["Project"]] = relationship(
        "Project",
        back_populates="analysis_jobs",
    )
    artifact: Mapped["Artifact"] = relationship(
        "Artifact",
        back_populates="analysis_jobs",
    )
    evidence_records: Mapped[List["EvidenceRecord"]] = relationship(
        "EvidenceRecord",
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class EvidenceRecord(Base):
    """Raw, immutable technical findings and telemetry returned by REA tools."""

    __tablename__ = "evidence_records"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    raw_evidence_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=utc_now,
        nullable=False,
    )

    job: Mapped["AnalysisJob"] = relationship(
        "AnalysisJob",
        back_populates="evidence_records",
    )
