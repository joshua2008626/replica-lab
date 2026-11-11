from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base backend directory: C:\Users\joshu\OneDrive\Desktop\replica-lab\backend
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Global Application Settings loaded from environment or .env."""

    # Project metadata
    PROJECT_NAME: str = "REPLICA LAB"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Server binding
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # CORS Allowed Origins
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Storage paths relative to backend root
    STORAGE_DIR: str = "storage"
    UPLOAD_DIR: str = "storage/uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 104_857_600  # 100 MiB limit

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///storage/replica_lab.db"

    # REA MCP Engine Service Settings
    REA_MCP_URL: str = "http://127.0.0.1:8080/mcp"
    REA_CONNECT_TIMEOUT_SECONDS: float = 5.0
    REA_READ_TIMEOUT_SECONDS: float = 60.0
    REA_MAX_RESPONSE_BYTES: int = 10_485_760  # 10 MiB limit for tool response payload

    # Background Job Engine Settings
    MAX_CONCURRENT_JOBS: int = 2  # Concurrency limit for background analysis tasks
    RESTART_RECOVERY_POLICY: str = "fail"  # Fail interrupted jobs on startup

    # Optional AI Keys (Leave empty for offline mode)
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    AI_MODEL_NAME: str = "gemini-2.5-flash"

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def absolute_storage_dir(self) -> Path:
        """Absolute Path to storage directory."""
        path = BACKEND_DIR / self.STORAGE_DIR
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def absolute_upload_dir(self) -> Path:
        """Absolute Path to upload directory."""
        path = BACKEND_DIR / self.UPLOAD_DIR
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
