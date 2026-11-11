import asyncio
import hashlib
import io
import re
import struct
import sys
import uuid
import zipfile
from pathlib import Path

# Ensure backend root is in Python sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import select
from main import app
from app.core.config import settings
from app.core.security import detect_format_from_bytes, sanitize_filename
from app.db.database import async_session_maker, init_db
from app.db.models import Artifact, Project


def create_synthetic_pe() -> bytes:
    """Generate a minimal synthetic Windows PE header structure for safe static testing."""
    dos_header = bytearray(b"MZ" + b"\x00" * 58)
    e_lfanew = 128
    dos_header[0x3C : 0x3C + 4] = struct.pack("<I", e_lfanew)
    padding = b"\x00" * (e_lfanew - len(dos_header))
    pe_signature = b"PE\x00\x00"
    pe_header = b"\x00" * 64
    return bytes(dos_header + padding + pe_signature + pe_header)


def create_synthetic_apk() -> bytes:
    """Generate a minimal valid in-memory zip archive containing AndroidManifest.xml."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("AndroidManifest.xml", b"<manifest></manifest>")
        zf.writestr("classes.dex", b"DEX\n035\x00")
    return buf.getvalue()


def create_synthetic_zip() -> bytes:
    """Generate a standard non-APK zip archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("notes.txt", b"Standard text document")
    return buf.getvalue()


async def run_all_upload_tests():
    print("=" * 65)
    print("REPLICA LAB — Secure Upload & Format Detection Test Suite")
    print("=" * 65)

    # Clean existing test .bin artifacts before running test run
    for old_file in settings.absolute_upload_dir.glob("*.bin"):
        try:
            old_file.unlink()
        except Exception:
            pass

    await init_db()

    # -------------------------------------------------------------
    # 1. Pure Security & Format Detection Unit Tests (Tasks 1 - 6)
    # -------------------------------------------------------------
    # Test 1: PE Detection
    pe_bytes = create_synthetic_pe()
    assert detect_format_from_bytes(pe_bytes) == "pe", "Failed to detect synthetic PE"
    print("[1/12] Synthetic PE signature detection: PASSED")

    # Test 2: ELF Detection
    elf_bytes = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 56
    assert detect_format_from_bytes(elf_bytes) == "elf", "Failed to detect synthetic ELF"
    print("[2/12] Synthetic ELF signature detection: PASSED")

    # Test 3: SQLite Detection
    sqlite_bytes = b"SQLite format 3\x00" + b"\x00" * 84
    assert detect_format_from_bytes(sqlite_bytes) == "sqlite", "Failed to detect SQLite"
    print("[3/12] Synthetic SQLite database signature detection: PASSED")

    # Test 4: ZIP and APK Container Detection
    zip_bytes = create_synthetic_zip()
    apk_bytes = create_synthetic_apk()
    temp_zip = settings.absolute_upload_dir / "temp_test.zip"
    temp_apk = settings.absolute_upload_dir / "temp_test.apk"
    temp_zip.write_bytes(zip_bytes)
    temp_apk.write_bytes(apk_bytes)
    try:
        assert detect_format_from_bytes(zip_bytes[:512], temp_zip) == "zip", "Failed to identify ZIP"
        assert detect_format_from_bytes(apk_bytes[:512], temp_apk) == "apk", "Failed to identify APK"
    finally:
        if temp_zip.exists(): temp_zip.unlink()
        if temp_apk.exists(): temp_apk.unlink()
    print("[4/12] ZIP vs APK container differentiation: PASSED")

    # Test 5: GGUF Header Detection
    gguf_bytes = b"GGUF\x03\x00\x00\x00" + b"\x00" * 24
    assert detect_format_from_bytes(gguf_bytes) == "gguf", "Failed to detect GGUF model"
    print("[5/12] Synthetic GGUF model header detection: PASSED")

    # Test 6: Unknown Format Classification
    unknown_bytes = b"\x00\xff\xaa\x55\x12\x34\x56\x78\x99" * 10
    assert detect_format_from_bytes(unknown_bytes) == "unknown", "Failed to classify unknown"
    print("[6/12] Unknown / unclassified binary detection: PASSED")

    # -------------------------------------------------------------
    # 2. Upload API Integration Tests (Tasks 7 - 12)
    # -------------------------------------------------------------
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create a fresh project to associate uploads with
        proj_resp = await client.post("/api/projects", json={"name": "Upload Test Workspace"})
        assert proj_resp.status_code == 201
        project_id = proj_resp.json()["id"]

        # Test 7: Successful Upload and Database Record Creation
        test_content = b"SQLite format 3\x00" + b"\x01" * 128
        files = {"file": ("my_database.db", test_content, "application/octet-stream")}
        data = {"project_id": project_id}

        upload_resp = await client.post("/api/uploads", files=files, data=data)
        assert upload_resp.status_code == 201, f"Upload failed: {upload_resp.text}"
        artifact_data = upload_resp.json()

        assert artifact_data["project_id"] == project_id
        assert artifact_data["original_filename"] == "my_database.db"
        assert artifact_data["detected_format"] == "sqlite"
        assert artifact_data["file_size_bytes"] == len(test_content)
        # Verify internal storage path is NOT leaked to the client
        assert "storage_path" not in artifact_data, "SECURITY FLAW: storage_path leaked in response!"
        artifact_id = artifact_data["id"]
        print(f"[7/12] Successful upload & DB creation: PASSED (Artifact ID: {artifact_id})")

        # Test 8: Nonexistent Project Rejection (404)
        fake_proj = "00000000-0000-0000-0000-000000000000"
        bad_proj_resp = await client.post(
            "/api/uploads",
            files={"file": ("test.bin", b"data", "application/octet-stream")},
            data={"project_id": fake_proj},
        )
        assert bad_proj_resp.status_code == 404
        assert f"Project with ID '{fake_proj}' not found" in bad_proj_resp.json()["detail"]
        print("[8/12] Rejection of nonexistent project with 404: PASSED")

        # Test 9: Oversized Upload Rejection (413)
        original_limit = settings.MAX_UPLOAD_SIZE_BYTES
        try:
            settings.MAX_UPLOAD_SIZE_BYTES = 512  # Set small temporary limit of 512 bytes
            oversized_content = b"A" * 2048
            large_resp = await client.post(
                "/api/uploads",
                files={"file": ("giant_file.bin", oversized_content, "application/octet-stream")},
                data={"project_id": project_id},
            )
            assert large_resp.status_code == 413, f"Expected 413, got {large_resp.status_code}"
            assert "exceeds maximum permitted size" in large_resp.json()["detail"]
            print("[9/12] Oversized upload rejection with HTTP 413: PASSED")
        finally:
            settings.MAX_UPLOAD_SIZE_BYTES = original_limit

        # Test 10: Cryptographic SHA-256 Verification
        independent_sha256 = hashlib.sha256(test_content).hexdigest()
        assert artifact_data["sha256_hash"] == independent_sha256, "SHA-256 digest mismatch"
        print(f"[10/12] Cryptographic SHA-256 digest match: PASSED ({independent_sha256[:16]}...)")

        # Test 11: Partial Upload Cleanup (No orphaned files left on disk)
        upload_dir_files = list(settings.absolute_upload_dir.glob("*.bin"))
        # Only the successful upload should exist (oversized file was deleted)
        assert len(upload_dir_files) == 1, f"Expected 1 file, found {len(upload_dir_files)}"
        assert upload_dir_files[0].name == f"{artifact_id}.bin"
        print("[11/12] Partial / rejected upload disk cleanup: PASSED")

        # Test 12: Storage Filename UUID Isolation
        stored_file_path = upload_dir_files[0]
        uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.bin$"
        assert re.match(uuid_pattern, stored_file_path.name), "Stored filename is not a safe UUID"
        assert "my_database.db" not in stored_file_path.name, "Original filename leaked onto filesystem"
        print(f"[12/12] UUID filename isolation: PASSED ({stored_file_path.name})")

        # -------------------------------------------------------------
        # 3. UTC Timestamp Persistence Verification
        # -------------------------------------------------------------
        async with async_session_maker() as session:
            stmt = select(Artifact).where(Artifact.id == artifact_id)
            persisted_artifact = (await session.execute(stmt)).scalar_one()
            assert persisted_artifact.created_at.tzinfo is not None, "Timestamp is not timezone-aware"
            print("[BONUS] UTC timestamp persistence: PASSED (Timezone-aware UTC confirmed)")

    print("=" * 65)
    print("ALL 12 UPLOAD & SECURITY CONTROLS VERIFIED SUCCESSFULLY!")
    print("=" * 65)


async def test_upload_and_security_lifecycle():
    """Pytest entrypoint for upload and format detection tests."""
    await run_all_upload_tests()


if __name__ == "__main__":
    asyncio.run(run_all_upload_tests())
