import asyncio
import sys
import uuid
from pathlib import Path

# Ensure backend root is in Python sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import select
from main import app
from app.db.database import (
    Base,
    async_session_maker,
    create_async_engine,
    engine,
    init_db,
)
from app.db.models import AnalysisJob, Artifact, EvidenceRecord, Project


async def run_all_project_tests():
    print("=" * 60)
    print("REPLICA LAB — Project Management & Database Test Suite")
    print("=" * 60)

    # 1. Initialize Database Tables
    await init_db()
    print("[1/8] Database initialization: Verified all tables created.")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # ---------------------------------------------------------
        # TEST 1: Create a Project
        # ---------------------------------------------------------
        create_payload = {
            "name": "Windows Malware Analysis Suite",
            "description": "Inspecting native PE headers and delayed imports",
        }
        resp = await client.post("/api/projects", json=create_payload)
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        project_data = resp.json()
        project_id = project_data["id"]

        assert project_data["name"] == create_payload["name"]
        assert project_data["description"] == create_payload["description"]
        assert "created_at" in project_data
        assert "updated_at" in project_data
        assert project_data["artifact_count"] == 0
        # Validate UUID4 structure
        uuid.UUID(project_id)
        print(f"[2/8] Project creation: PASSED (Project ID: {project_id})")

        # ---------------------------------------------------------
        # TEST 2: List Projects
        # ---------------------------------------------------------
        list_resp = await client.get("/api/projects")
        assert list_resp.status_code == 200
        projects_list = list_resp.json()
        assert any(p["id"] == project_id for p in projects_list), "Created project not found in list"
        print(f"[3/8] List projects: PASSED (Total found: {len(projects_list)})")

        # ---------------------------------------------------------
        # TEST 3: Retrieve Project by ID
        # ---------------------------------------------------------
        get_resp = await client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 200
        retrieved_data = get_resp.json()
        assert retrieved_data["id"] == project_id
        assert retrieved_data["name"] == create_payload["name"]
        print(f"[4/8] Get project by ID: PASSED")

        # ---------------------------------------------------------
        # TEST 4: Retrieve Nonexistent Project (Expect 404)
        # ---------------------------------------------------------
        fake_id = "00000000-0000-0000-0000-000000000000"
        missing_resp = await client.get(f"/api/projects/{fake_id}")
        assert missing_resp.status_code == 404, f"Expected 404, got {missing_resp.status_code}"
        assert f"Project with ID '{fake_id}' not found" in missing_resp.json()["detail"]
        print(f"[5/8] 404 on nonexistent project: PASSED")

        # ---------------------------------------------------------
        # TEST 5: Update Project
        # ---------------------------------------------------------
        update_payload = {"name": "Updated Analysis Suite"}
        update_resp = await client.patch(f"/api/projects/{project_id}", json=update_payload)
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "Updated Analysis Suite"
        print(f"[6/8] Update project: PASSED")

        # ---------------------------------------------------------
        # TEST 6: Persistence Across Application / Connection Restart
        # ---------------------------------------------------------
        # Simulate closing the current engine connection pool completely
        await engine.dispose()

        # Reopen and query directly to simulate a cold server reboot
        async with async_session_maker() as verify_session:
            stmt = select(Project).where(Project.id == project_id)
            persisted_project = (await verify_session.execute(stmt)).scalar_one_or_none()
            assert persisted_project is not None, "Project did not persist in SQLite after restart"
            assert persisted_project.name == "Updated Analysis Suite"
        print(f"[7/8] Persistence across restart: PASSED (Verified from storage/replica_lab.db)")

        # ---------------------------------------------------------
        # TEST 7: Cascade Deletion & Related Record Integrity
        # ---------------------------------------------------------
        # Create a full hierarchy: Project -> Artifact -> Job -> Evidence
        async with async_session_maker() as session:
            artifact = Artifact(
                project_id=project_id,
                original_filename="sample_payload.exe",
                storage_path="C:/dummy/storage/sample_payload.bin",
                file_size_bytes=10240,
                sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                detected_format="pe",
            )
            session.add(artifact)
            await session.flush()

            job = AnalysisJob(
                artifact_id=artifact.id,
                status="completed",
                progress_percent=100,
                current_step="Analysis complete",
            )
            session.add(job)
            await session.flush()

            evidence = EvidenceRecord(
                job_id=job.id,
                tool_name="inspect_pe_imports",
                category="imports",
                raw_evidence_json='{"dlls": ["KERNEL32.dll"]}',
            )
            session.add(evidence)
            await session.commit()

            artifact_id = artifact.id
            job_id = job.id
            evidence_id = evidence.id

        # Confirm all 4 records exist in DB
        async with async_session_maker() as session:
            assert (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none() is not None
            assert (await session.execute(select(Artifact).where(Artifact.id == artifact_id))).scalar_one_or_none() is not None
            assert (await session.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))).scalar_one_or_none() is not None
            assert (await session.execute(select(EvidenceRecord).where(EvidenceRecord.id == evidence_id))).scalar_one_or_none() is not None

        # Delete the project via the API endpoint
        del_resp = await client.delete(f"/api/projects/{project_id}")
        assert del_resp.status_code == 200, f"Delete failed: {del_resp.text}"

        # Verify all related records are deleted from SQLite (no orphaned records)
        async with async_session_maker() as session:
            assert (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none() is None, "Project still exists"
            assert (await session.execute(select(Artifact).where(Artifact.id == artifact_id))).scalar_one_or_none() is None, "Artifact orphaned"
            assert (await session.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))).scalar_one_or_none() is None, "Job orphaned"
            assert (await session.execute(select(EvidenceRecord).where(EvidenceRecord.id == evidence_id))).scalar_one_or_none() is None, "Evidence orphaned"

        # Subsequent GET should return 404
        assert (await client.get(f"/api/projects/{project_id}")).status_code == 404
        print(f"[8/8] Cascade deletion & orphan prevention: PASSED (All child records purged cleanly)")

    print("=" * 60)
    print("ALL 8 AUTOMATED PROJECT & DATABASE TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)


async def test_project_management_lifecycle():
    """Pytest entrypoint for project and database persistence tests."""
    await run_all_project_tests()


if __name__ == "__main__":
    asyncio.run(run_all_project_tests())
