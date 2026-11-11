import hashlib
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import detect_format_from_bytes, sanitize_filename
from app.db.database import get_db
from app.db.models import Artifact, Project
from app.schemas.upload import ArtifactResponse

router = APIRouter(prefix="/uploads", tags=["Uploads & Artifacts"])

# Bounded chunk size for streaming upload to disk (64 KiB)
CHUNK_SIZE = 64 * 1024


@router.post(
    "",
    response_model=ArtifactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and quarantine a software artifact",
)
async def upload_artifact(
    project_id: str = Form(..., description="ID of the destination project workspace"),
    file: UploadFile = File(..., description="The software artifact binary or archive"),
    db: AsyncSession = Depends(get_db),
):
    """Securely stream an uploaded software artifact to quarantined storage.
    
    Security controls:
    1. Validates that the target project exists (404 if missing).
    2. Streams bytes in bounded chunks (never buffers entire file in memory).
    3. Calculates cryptographic SHA-256 digest on the fly.
    4. Enforces hard file-size ceiling (HTTP 413 if exceeded).
    5. Stores file with random UUID filename (never client filename).
    6. Performs magic-byte format detection without executing code.
    7. Cleans up incomplete/failed files from disk immediately.
    """
    # 1. Verify project exists
    stmt = select(Project).where(Project.id == project_id)
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    # 2. Allocate UUID-based storage path
    artifact_id = str(uuid.uuid4())
    storage_filename = f"{artifact_id}.bin"
    target_path = settings.absolute_upload_dir / storage_filename

    hasher = hashlib.sha256()
    total_bytes = 0
    header_sample = bytearray()
    MAX_HEADER_SAMPLE = 8192

    try:
        with open(target_path, "wb") as out_file:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break

                total_bytes += len(chunk)
                if total_bytes > settings.MAX_UPLOAD_SIZE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=(
                            f"Uploaded file exceeds maximum permitted size of "
                            f"{settings.MAX_UPLOAD_SIZE_BYTES} bytes (100 MiB)."
                        ),
                    )

                hasher.update(chunk)
                out_file.write(chunk)

                # Retain header sample for structural magic-byte detection
                if len(header_sample) < MAX_HEADER_SAMPLE:
                    slice_needed = MAX_HEADER_SAMPLE - len(header_sample)
                    header_sample.extend(chunk[:slice_needed])

        if total_bytes == 0:
            if target_path.exists():
                target_path.unlink()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty (0 bytes).",
            )

        # 3. Detect format using magic bytes and structural inspection
        detected_format = detect_format_from_bytes(bytes(header_sample), target_path)

        # 4. Save metadata record to database
        artifact = Artifact(
            id=artifact_id,
            project_id=project_id,
            original_filename=sanitize_filename(file.filename),
            storage_path=str(target_path),
            file_size_bytes=total_bytes,
            sha256_hash=hasher.hexdigest(),
            detected_format=detected_format,
        )
        db.add(artifact)
        await db.commit()
        await db.refresh(artifact)

        return ArtifactResponse.model_validate(artifact)

    except Exception:
        # Guarantee partial files are purged on any streaming or database error
        if target_path.exists():
            try:
                target_path.unlink()
            except Exception:
                pass
        raise
    finally:
        await file.close()
