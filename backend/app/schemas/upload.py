from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ArtifactResponse(BaseModel):
    """Metadata response for an uploaded software artifact.
    
    Security note: Internal absolute filesystem storage paths are strictly withheld
    from client responses to prevent internal environment disclosure.
    """

    id: str = Field(..., description="Unique artifact identifier (UUID4)")
    project_id: str = Field(..., description="ID of the associated project workspace")
    original_filename: str = Field(..., description="Original client filename (sanitized)")
    file_size_bytes: int = Field(..., description="Exact verified size in bytes")
    sha256_hash: str = Field(..., description="Cryptographic SHA-256 digest")
    detected_format: str = Field(..., description="Detected format classification")
    created_at: datetime = Field(..., description="Upload timestamp in UTC")

    model_config = ConfigDict(from_attributes=True)
