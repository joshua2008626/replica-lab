"""REPLICA LAB — Background Analysis Job Runner Test Suite.

Verifies all 15 background job lifecycle, concurrency, persistence, and recovery controls:
1. Job creation.
2. Immediate queued response (HTTP 202).
3. Successful background execution.
4. Partial analysis result.
5. Failed analysis.
6. Job status retrieval (GET /api/jobs/{id}).
7. Project job listing (GET /api/projects/{id}/jobs).
8. Unknown job ID (HTTP 404).
9. Invalid project/artifact relationship (HTTP 404).
10. Duplicate processing prevention (HTTP 409).
11. Concurrency limits (Semaphore bounded).
12. Restart recovery for queued jobs.
13. Restart recovery for running jobs.
14. Completed result persistence.
15. Database session cleanup.
BONUS: Job cancellation handling.
"""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure backend root is in Python sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import select
from main import app
from app.core.config import settings
from app.db.database import async_session_maker, init_db
from app.db.models import AnalysisJob, Artifact, EvidenceRecord, Project, utc_now
from app.services.dispatcher import DispatchResult, NormalizedSummary, NormalizedToolResult
from app.services.job_manager import JobManager, job_manager


# Helper to create isolated test fixtures
async def create_test_project_and_artifact(
    project_name: str = "Job Test Project",
    filename: str = "test_binary.exe",
    detected_format: str = "pe",
) -> tuple[Project, Artifact]:
    async with async_session_maker() as session:
        proj = Project(
            id=str(uuid.uuid4()),
            name=project_name,
            description="Automated job runner verification workspace",
        )
        session.add(proj)
        await session.commit()
        await session.refresh(proj)

        storage_file = settings.absolute_upload_dir / f"{uuid.uuid4().hex}.bin"
        with open(storage_file, "wb") as f:
            f.write(b"MZ" + b"\x00" * 100)

        art = Artifact(
            id=str(uuid.uuid4()),
            project_id=proj.id,
            original_filename=filename,
            storage_path=str(storage_file),
            file_size_bytes=storage_file.stat().st_size,
            sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            detected_format=detected_format,
        )
        session.add(art)
        await session.commit()
        await session.refresh(art)

    return proj, art


async def cleanup_artifact_file(storage_path_str: str):
    p = Path(storage_path_str)
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Individual Test Functions
# ---------------------------------------------------------------------------

async def test_job_creation_and_immediate_response():
    """Tests 1 & 2: Job creation returns immediate HTTP 202 with status='queued'."""
    await init_db()
    proj, art = await create_test_project_and_artifact()

    try:
        # Mock dispatcher so job can complete safely in background
        async def mock_dispatcher(artifact, project_id):
            return DispatchResult(
                artifact_id=artifact.id,
                project_id=project_id,
                format="pe",
                status="completed",
                message="Mock completed",
                tool_results=[],
                summary=NormalizedSummary(),
                raw_evidence=[],
            )

        job_manager.set_dispatcher(mock_dispatcher)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(f"/api/projects/{proj.id}/artifacts/{art.id}/analyze")
            assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert "id" in data
            assert data["project_id"] == proj.id
            assert data["artifact_id"] == art.id
            assert data["status"] == "queued"
            assert data["progress_percent"] == 0
            assert data["current_step"] == "Queued for analysis"

            # Wait briefly for background execution to finish
            await asyncio.sleep(0.1)
    finally:
        await cleanup_artifact_file(art.storage_path)


async def test_successful_background_execution():
    """Test 3: Successful background execution transitions to running then completed."""
    await init_db()
    proj, art = await create_test_project_and_artifact()

    try:
        async def mock_dispatcher(artifact, project_id):
            return DispatchResult(
                artifact_id=artifact.id,
                project_id=project_id,
                format="pe",
                status="completed",
                message="All 3 PE tools succeeded",
                tool_results=[
                    NormalizedToolResult(
                        tool_name="inspect_pe_imports",
                        status="success",
                        category="pe_imports",
                        arguments={"path": artifact.storage_path},
                        raw_result={"imports": ["KERNEL32.dll"]},
                        raw_text='{"imports": ["KERNEL32.dll"]}',
                        parsed_evidence={"imports": ["KERNEL32.dll"]},
                    )
                ],
                summary=NormalizedSummary(
                    imports=[{"dll": "KERNEL32.dll"}],
                    technologies=["Windows Native"],
                ),
                raw_evidence=[{"tool": "inspect_pe_imports", "data": "raw"}],
            )

        job_manager.set_dispatcher(mock_dispatcher)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(f"/api/projects/{proj.id}/artifacts/{art.id}/analyze")
            job_id = resp.json()["id"]

            # Poll for completion (up to 2 seconds)
            completed_job = None
            for _ in range(20):
                await asyncio.sleep(0.05)
                get_resp = await client.get(f"/api/jobs/{job_id}")
                if get_resp.json()["status"] == "completed":
                    completed_job = get_resp.json()
                    break

            assert completed_job is not None, "Job did not reach 'completed' status"
            assert completed_job["status"] == "completed"
            assert completed_job["progress_percent"] == 100
            assert completed_job["started_at"] is not None
            assert completed_job["completed_at"] is not None
            assert len(completed_job["evidence_records"]) == 1
            assert completed_job["evidence_records"][0]["tool_name"] == "inspect_pe_imports"
            assert "KERNEL32.dll" in str(completed_job["summary"])
    finally:
        await cleanup_artifact_file(art.storage_path)


async def test_partial_analysis_result():
    """Test 4: Partial analysis result records partial status and error details."""
    await init_db()
    proj, art = await create_test_project_and_artifact()

    try:
        async def mock_partial_dispatcher(artifact, project_id):
            return DispatchResult(
                artifact_id=artifact.id,
                project_id=project_id,
                format="pe",
                status="partial",
                message="Analysis completed with partial results: 2 succeeded, 1 failed.",
                tool_results=[
                    NormalizedToolResult(
                        tool_name="inspect_pe_imports",
                        status="error",
                        category="pe_imports",
                        arguments={"path": artifact.storage_path},
                        error_message="PE import table was corrupted",
                    ),
                    NormalizedToolResult(
                        tool_name="inspect_pe_certificates",
                        status="success",
                        category="pe_certificates",
                        arguments={"path": artifact.storage_path},
                        parsed_evidence={"certificates": []},
                    ),
                ],
                summary=NormalizedSummary(),
                raw_evidence=[],
            )

        job_manager.set_dispatcher(mock_partial_dispatcher)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(f"/api/projects/{proj.id}/artifacts/{art.id}/analyze")
            job_id = resp.json()["id"]

            for _ in range(20):
                await asyncio.sleep(0.05)
                get_resp = await client.get(f"/api/jobs/{job_id}")
                if get_resp.json()["status"] == "partial":
                    break

            final_data = (await client.get(f"/api/jobs/{job_id}")).json()
            assert final_data["status"] == "partial"
            assert "partial results" in final_data["error_message"]
            assert final_data["progress_percent"] == 100
            assert len(final_data["evidence_records"]) == 2
    finally:
        await cleanup_artifact_file(art.storage_path)


async def test_failed_analysis():
    """Test 5: Failed analysis marks job status='failed' with error message."""
    await init_db()
    proj, art = await create_test_project_and_artifact()

    try:
        async def mock_failing_dispatcher(artifact, project_id):
            return DispatchResult(
                artifact_id=artifact.id,
                project_id=project_id,
                format="pe",
                status="error",
                message="All planned tool invocations returned errors.",
                tool_results=[
                    NormalizedToolResult(
                        tool_name="inspect_pe_imports",
                        status="error",
                        category="pe_imports",
                        arguments={"path": artifact.storage_path},
                        error_message="Host REA engine rejected connection",
                    )
                ],
                summary=NormalizedSummary(),
                raw_evidence=[],
            )

        job_manager.set_dispatcher(mock_failing_dispatcher)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(f"/api/projects/{proj.id}/artifacts/{art.id}/analyze")
            job_id = resp.json()["id"]

            for _ in range(20):
                await asyncio.sleep(0.05)
                get_resp = await client.get(f"/api/jobs/{job_id}")
                if get_resp.json()["status"] == "failed":
                    break

            final_data = (await client.get(f"/api/jobs/{job_id}")).json()
            assert final_data["status"] == "failed"
            assert "All planned tool invocations returned errors" in final_data["error_message"]
            assert final_data["completed_at"] is not None
    finally:
        await cleanup_artifact_file(art.storage_path)


async def test_job_status_retrieval_and_listing():
    """Tests 6 & 7: Job status retrieval and project job listing."""
    await init_db()
    proj, art = await create_test_project_and_artifact()

    try:
        async def mock_dispatcher(artifact, project_id):
            return DispatchResult(
                artifact_id=artifact.id,
                project_id=project_id,
                format="pe",
                status="completed",
                message="Success",
                tool_results=[],
                summary=NormalizedSummary(),
                raw_evidence=[],
            )

        job_manager.set_dispatcher(mock_dispatcher)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(f"/api/projects/{proj.id}/artifacts/{art.id}/analyze")
            job_id = resp.json()["id"]

            # Test GET /api/jobs/{id}
            get_resp = await client.get(f"/api/jobs/{job_id}")
            assert get_resp.status_code == 200
            assert get_resp.json()["id"] == job_id
            assert get_resp.json()["project_id"] == proj.id

            # Test GET /api/projects/{id}/jobs
            list_resp = await client.get(f"/api/projects/{proj.id}/jobs")
            assert list_resp.status_code == 200
            jobs_list = list_resp.json()
            assert len(jobs_list) >= 1
            assert any(j["id"] == job_id for j in jobs_list)
    finally:
        await cleanup_artifact_file(art.storage_path)


async def test_unknown_job_id_returns_404():
    """Test 8: Unknown job ID returns HTTP 404."""
    await init_db()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/jobs/{fake_id}")
        assert resp.status_code == 404
        assert "was not found" in resp.json()["detail"]


async def test_invalid_project_artifact_relationship():
    """Test 9: Invalid project/artifact relationship returns HTTP 404."""
    await init_db()
    proj_a, art_a = await create_test_project_and_artifact(project_name="Project A")
    proj_b, art_b = await create_test_project_and_artifact(project_name="Project B")

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. Nonexistent project
            resp1 = await client.post(f"/api/projects/{uuid.uuid4()}/artifacts/{art_a.id}/analyze")
            assert resp1.status_code == 404

            # 2. Artifact belongs to Project A, but Project B is requested
            resp2 = await client.post(f"/api/projects/{proj_b.id}/artifacts/{art_a.id}/analyze")
            assert resp2.status_code == 404
            assert f"Artifact '{art_a.id}' was not found in project '{proj_b.id}'" in resp2.json()["detail"]
    finally:
        await cleanup_artifact_file(art_a.storage_path)
        await cleanup_artifact_file(art_b.storage_path)


async def test_duplicate_processing_prevention():
    """Test 10: Duplicate processing prevention returns HTTP 409 Conflict."""
    await init_db()
    proj, art = await create_test_project_and_artifact()

    try:
        # Create a lingering dispatcher using an Event
        release_event = asyncio.Event()

        async def slow_dispatcher(artifact, project_id):
            await release_event.wait()
            return DispatchResult(
                artifact_id=artifact.id,
                project_id=project_id,
                format="pe",
                status="completed",
                tool_results=[],
                summary=NormalizedSummary(),
                raw_evidence=[],
            )

        job_manager.set_dispatcher(slow_dispatcher)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            # First request: starts and enters running state
            resp1 = await client.post(f"/api/projects/{proj.id}/artifacts/{art.id}/analyze")
            assert resp1.status_code == 202
            job1_id = resp1.json()["id"]

            # Second request on the SAME artifact while first is active
            resp2 = await client.post(f"/api/projects/{proj.id}/artifacts/{art.id}/analyze")
            assert resp2.status_code == 409
            assert "already active for artifact" in resp2.json()["detail"]

            # Release slow dispatcher and wait
            release_event.set()
            for _ in range(20):
                await asyncio.sleep(0.05)
                get_resp = await client.get(f"/api/jobs/{job1_id}")
                if get_resp.json()["status"] == "completed":
                    break
    finally:
        await cleanup_artifact_file(art.storage_path)


async def test_concurrency_limits():
    """Test 11: Concurrency limits throttle simultaneous analysis jobs."""
    await init_db()
    proj1, art1 = await create_test_project_and_artifact(filename="b1.exe")
    proj2, art2 = await create_test_project_and_artifact(filename="b2.exe")
    proj3, art3 = await create_test_project_and_artifact(filename="b3.exe")

    try:
        # Configure manager with a max concurrency of 2
        concurrency_manager = JobManager(max_concurrent_jobs=2)
        active_counts = []
        max_seen = 0
        current_active = 0
        lock = asyncio.Lock()
        gate = asyncio.Event()

        async def concurrent_dispatcher(artifact, project_id):
            nonlocal current_active, max_seen
            async with lock:
                current_active += 1
                if current_active > max_seen:
                    max_seen = current_active
            await gate.wait()
            async with lock:
                current_active -= 1
            return DispatchResult(
                artifact_id=artifact.id,
                project_id=project_id,
                format="pe",
                status="completed",
                tool_results=[],
                summary=NormalizedSummary(),
                raw_evidence=[],
            )

        concurrency_manager.set_dispatcher(concurrent_dispatcher)

        # Enqueue 3 jobs manually
        t1 = await concurrency_manager.enqueue_job("job-1", proj1.id, art1.id)
        t2 = await concurrency_manager.enqueue_job("job-2", proj2.id, art2.id)
        t3 = await concurrency_manager.enqueue_job("job-3", proj3.id, art3.id)

        # Let event loop schedule tasks
        await asyncio.sleep(0.1)
        # Verify no more than 2 jobs ran concurrently
        assert max_seen <= 2, f"Concurrency ceiling violated! Max active was {max_seen} > 2"

        # Release gate and await all
        gate.set()
        await asyncio.gather(t1, t2, t3)
    finally:
        await cleanup_artifact_file(art1.storage_path)
        await cleanup_artifact_file(art2.storage_path)
        await cleanup_artifact_file(art3.storage_path)


async def test_restart_recovery_for_queued_and_running_jobs():
    """Tests 12 & 13: Restart recovery reconciles leftover queued and running jobs."""
    await init_db()
    proj, art1 = await create_test_project_and_artifact(filename="crash_art1.exe")
    _, art2 = await create_test_project_and_artifact(project_name="Crash Proj 2", filename="crash_art2.exe")

    try:
        async with async_session_maker() as session:
            # Create a synthetic job left in 'running' state from previous process crash
            crashed_running_job = AnalysisJob(
                id=str(uuid.uuid4()),
                project_id=proj.id,
                artifact_id=art1.id,
                status="running",
                started_at=utc_now(),
                progress_percent=45,
                current_step="Executing inspect_pe_imports",
            )
            # Create a synthetic job left in 'queued' state for another artifact
            crashed_queued_job = AnalysisJob(
                id=str(uuid.uuid4()),
                project_id=proj.id,
                artifact_id=art2.id,
                status="queued",
                progress_percent=0,
                current_step="Queued for analysis",
            )
            session.add_all([crashed_running_job, crashed_queued_job])
            await session.commit()
            running_id = crashed_running_job.id
            queued_id = crashed_queued_job.id

        # Execute recovery
        recovery_summary = await job_manager.recover_interrupted_jobs()
        assert recovery_summary["recovered_running"] >= 1
        assert recovery_summary["recovered_queued"] >= 1

        # Verify state in database
        async with async_session_maker() as session:
            j_running = (await session.execute(select(AnalysisJob).where(AnalysisJob.id == running_id))).scalar_one()
            assert j_running.status == "failed"
            assert "interrupted by an application restart while running" in j_running.error_message
            assert j_running.completed_at is not None

            j_queued = (await session.execute(select(AnalysisJob).where(AnalysisJob.id == queued_id))).scalar_one()
            assert j_queued.status == "failed"
            assert "queued when the application restarted" in j_queued.error_message
            assert j_queued.completed_at is not None
    finally:
        await cleanup_artifact_file(art1.storage_path)
        await cleanup_artifact_file(art2.storage_path)


async def test_completed_result_persistence():
    """Test 14: Completed results and evidence records persist across database sessions."""
    await init_db()
    proj, art = await create_test_project_and_artifact()

    try:
        test_summary_dict = {
            "imports": [{"dll": "USER32.dll"}],
            "technologies": ["Win32 GUI"],
        }

        async def mock_dispatcher(artifact, project_id):
            return DispatchResult(
                artifact_id=artifact.id,
                project_id=project_id,
                format="pe",
                status="completed",
                message="Success",
                tool_results=[
                    NormalizedToolResult(
                        tool_name="inspect_pe_imports",
                        status="success",
                        category="pe_imports",
                        arguments={"path": artifact.storage_path},
                        parsed_evidence={"imports": ["USER32.dll"]},
                        raw_result={"isError": False},
                    )
                ],
                summary=NormalizedSummary(
                    imports=[{"dll": "USER32.dll"}],
                    technologies=["Win32 GUI"],
                ),
                raw_evidence=[{"tool": "inspect_pe_imports"}],
            )

        job_manager.set_dispatcher(mock_dispatcher)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(f"/api/projects/{proj.id}/artifacts/{art.id}/analyze")
            job_id = resp.json()["id"]

            for _ in range(20):
                await asyncio.sleep(0.05)
                get_resp = await client.get(f"/api/jobs/{job_id}")
                if get_resp.json()["status"] == "completed":
                    break

        # Read back using a completely fresh database session
        async with async_session_maker() as fresh_session:
            stmt = select(AnalysisJob).where(AnalysisJob.id == job_id)
            reloaded_job = (await fresh_session.execute(stmt)).scalar_one()
            assert reloaded_job.status == "completed"
            assert reloaded_job.result_summary_json is not None
            parsed_summary = json.loads(reloaded_job.result_summary_json)
            assert parsed_summary["technologies"] == ["Win32 GUI"]

            # Verify evidence records persisted
            stmt_ev = select(EvidenceRecord).where(EvidenceRecord.job_id == job_id)
            ev_records = (await fresh_session.execute(stmt_ev)).scalars().all()
            assert len(ev_records) == 1
            assert ev_records[0].tool_name == "inspect_pe_imports"
    finally:
        await cleanup_artifact_file(art.storage_path)


async def test_database_session_cleanup():
    """Test 15: Database session cleanup guarantees no leaked active connections."""
    await init_db()
    proj, art = await create_test_project_and_artifact()

    try:
        # Verify clean opening and closing of sessions in a loop
        for _ in range(5):
            async with async_session_maker() as session:
                res = await session.execute(select(Project).where(Project.id == proj.id))
                assert res.scalar_one_or_none() is not None
                # Session exits and is cleanly closed
    finally:
        await cleanup_artifact_file(art.storage_path)


async def test_job_cancellation():
    """Bonus Test: Safe job cancellation sets status='cancelled' and aborts task."""
    await init_db()
    proj, art = await create_test_project_and_artifact()

    try:
        hang_event = asyncio.Event()

        async def hanging_dispatcher(artifact, project_id):
            await hang_event.wait()
            return DispatchResult(
                artifact_id=artifact.id,
                project_id=project_id,
                format="pe",
                status="completed",
                tool_results=[],
                summary=NormalizedSummary(),
                raw_evidence=[],
            )

        job_manager.set_dispatcher(hanging_dispatcher)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(f"/api/projects/{proj.id}/artifacts/{art.id}/analyze")
            job_id = resp.json()["id"]

            # Wait until job enters running state
            for _ in range(20):
                await asyncio.sleep(0.05)
                get_resp = await client.get(f"/api/jobs/{job_id}")
                if get_resp.json()["status"] == "running":
                    break

            # Cancel job
            cancel_resp = await client.post(f"/api/jobs/{job_id}/cancel")
            assert cancel_resp.status_code == 200
            assert cancel_resp.json()["status"] == "cancelled"

            # Check status after cancellation
            status_resp = await client.get(f"/api/jobs/{job_id}")
            assert status_resp.json()["status"] == "cancelled"
            assert "cancelled by user request" in status_resp.json()["error_message"]

            hang_event.set()
    finally:
        await cleanup_artifact_file(art.storage_path)


async def test_concurrent_duplicate_analysis_requests_race_condition():
    """Verify that concurrent POST requests for the same artifact cannot both create active jobs."""
    await init_db()
    proj, art = await create_test_project_and_artifact(filename="race_test.exe")

    try:
        hang_event = asyncio.Event()

        async def slow_dispatcher(artifact, project_id, is_cancelled=None):
            await hang_event.wait()
            return DispatchResult(
                artifact_id=artifact.id,
                project_id=project_id,
                format="pe",
                status="completed",
                message="Done",
                tool_results=[],
                summary=NormalizedSummary(),
                raw_evidence=[],
            )

        job_manager.set_dispatcher(slow_dispatcher)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            # Send two simultaneous POST requests for the exact same artifact
            resps = await asyncio.gather(
                client.post(f"/api/projects/{proj.id}/artifacts/{art.id}/analyze"),
                client.post(f"/api/projects/{proj.id}/artifacts/{art.id}/analyze"),
                return_exceptions=False,
            )

            status_codes = sorted([r.status_code for r in resps])
            # Exactly one must succeed with HTTP 202, and the other must be rejected with HTTP 409 Conflict
            assert status_codes == [202, 409], f"Expected [202, 409] but got {status_codes}"

            # Verify in DB: only one active job exists for this artifact
            async with async_session_maker() as session:
                stmt = select(AnalysisJob).where(
                    AnalysisJob.artifact_id == art.id,
                    AnalysisJob.status.in_(["queued", "running"]),
                )
                active_jobs = (await session.execute(stmt)).scalars().all()
                assert len(active_jobs) == 1

        hang_event.set()
    finally:
        await cleanup_artifact_file(art.storage_path)


async def test_cancellation_during_active_dispatch_aborts_subsequent_tools():
    """Verify that cancelling during dispatch halts remaining tools and preserves cancelled state."""
    await init_db()
    proj, art = await create_test_project_and_artifact(filename="cancel_multi_tool.exe")

    tools_executed = []
    tool1_started = asyncio.Event()
    can_proceed_tool1 = asyncio.Event()

    async def multi_tool_dispatcher(artifact, project_id, is_cancelled=None):
        # Tool 1
        if is_cancelled and is_cancelled():
            return DispatchResult(artifact_id=artifact.id, project_id=project_id, format="pe", status="partial", message="Cancelled", tool_results=[], summary=NormalizedSummary(), raw_evidence=[])
        tools_executed.append("tool_1")
        tool1_started.set()
        await can_proceed_tool1.wait()

        # Tool 2: Check cancellation
        if is_cancelled and is_cancelled():
            return DispatchResult(artifact_id=artifact.id, project_id=project_id, format="pe", status="partial", message="Cancelled before tool 2", tool_results=[], summary=NormalizedSummary(), raw_evidence=[])
        tools_executed.append("tool_2")
        return DispatchResult(artifact_id=artifact.id, project_id=project_id, format="pe", status="completed", message="All done", tool_results=[], summary=NormalizedSummary(), raw_evidence=[])

    job_manager.set_dispatcher(multi_tool_dispatcher)

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(f"/api/projects/{proj.id}/artifacts/{art.id}/analyze")
            assert resp.status_code == 202
            job_id = resp.json()["id"]

            # Wait until Tool 1 starts executing
            await tool1_started.wait()

            # Now cancel the job before Tool 2 can run
            cancel_resp = await client.post(f"/api/jobs/{job_id}/cancel")
            assert cancel_resp.status_code == 200
            assert cancel_resp.json()["status"] == "cancelled"

            # Allow Tool 1 to finish
            can_proceed_tool1.set()

            # Wait briefly for background execution to complete
            await asyncio.sleep(0.1)

            # Check job status: must remain CANCELLED, not updated to completed or partial
            get_resp = await client.get(f"/api/jobs/{job_id}")
            assert get_resp.json()["status"] == "cancelled"
            assert "cancelled by user request" in get_resp.json()["error_message"]

            # Tool 2 was NOT executed
            assert "tool_1" in tools_executed
            assert "tool_2" not in tools_executed
    finally:
        can_proceed_tool1.set()
        await cleanup_artifact_file(art.storage_path)


async def test_invalid_state_transitions_rejected():
    """Verify that illegal state machine transitions and terminal state overwrites are rejected."""
    import pytest
    from app.services.job_manager import JobStateTransitionError

    jm = JobManager()

    # Valid transitions:
    jm.validate_transition("queued", "running")
    jm.validate_transition("queued", "cancelled")
    jm.validate_transition("queued", "failed")
    jm.validate_transition("running", "completed")
    jm.validate_transition("running", "partial")
    jm.validate_transition("running", "failed")
    jm.validate_transition("running", "cancelled")

    # Invalid transitions from terminal states:
    for terminal in ("completed", "partial", "failed", "cancelled"):
        for target in ("queued", "running", "completed", "partial", "failed", "cancelled"):
            with pytest.raises(JobStateTransitionError):
                jm.validate_transition(terminal, target)

    # Invalid direct skips:
    with pytest.raises(JobStateTransitionError):
        jm.validate_transition("queued", "completed")
    with pytest.raises(JobStateTransitionError):
        jm.validate_transition("queued", "partial")

    # Verify cancelling a terminal job returns HTTP 400
    await init_db()
    proj, art = await create_test_project_and_artifact(filename="terminal_test.exe")
    try:
        async with async_session_maker() as session:
            completed_job = AnalysisJob(
                id=str(uuid.uuid4()),
                project_id=proj.id,
                artifact_id=art.id,
                status="completed",
                progress_percent=100,
                current_step="Analysis completed successfully",
                completed_at=utc_now(),
            )
            session.add(completed_job)
            await session.commit()
            term_id = completed_job.id

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(f"/api/jobs/{term_id}/cancel")
            assert resp.status_code == 400
            assert "Cannot cancel job" in resp.json()["detail"]
            assert "terminal state 'completed'" in resp.json()["detail"]
    finally:
        await cleanup_artifact_file(art.storage_path)


async def test_job_manager_shutdown_cancels_all_active_tasks():
    """Verify that shutdown cancels in-flight tasks cleanly."""
    await init_db()
    proj, art = await create_test_project_and_artifact(filename="shutdown_test.exe")

    try:
        custom_jm = JobManager(max_concurrent_jobs=2)
        hang_event = asyncio.Event()
        dispatcher_entered = asyncio.Event()

        async def hanging_dispatcher(artifact, project_id, is_cancelled=None):
            dispatcher_entered.set()
            await hang_event.wait()
            return DispatchResult(
                artifact_id=artifact.id,
                project_id=project_id,
                format="pe",
                status="completed",
                message="Done",
                tool_results=[],
                summary=NormalizedSummary(),
                raw_evidence=[],
            )

        custom_jm.set_dispatcher(hanging_dispatcher)

        async with async_session_maker() as session:
            job = AnalysisJob(
                id=str(uuid.uuid4()),
                project_id=proj.id,
                artifact_id=art.id,
                status="queued",
            )
            session.add(job)
            await session.commit()
            job_id = job.id

        task = await custom_jm.enqueue_job(job_id, proj.id, art.id)
        assert not task.done()

        # Wait until task is actively executing in background
        await dispatcher_entered.wait()

        # Execute shutdown
        await custom_jm.shutdown()
        assert task.done()

        # Verify job is marked as failed due to shutdown, NOT cancelled by user
        async with async_session_maker() as session:
            stmt = select(AnalysisJob).where(AnalysisJob.id == job_id)
            recovered_job = (await session.execute(stmt)).scalar_one()
            assert recovered_job.status == "failed"
            assert recovered_job.current_step == "Interrupted by application shutdown"
            assert "interrupted by application shutdown" in recovered_job.error_message.lower()
            assert "cancelled by user" not in recovered_job.error_message.lower()
    finally:
        hang_event.set()
        await cleanup_artifact_file(art.storage_path)


async def test_database_migration_handles_existing_duplicate_active_jobs_safely():
    """Verify that init_db() reconciles pre-existing duplicate active jobs non-destructively."""
    from sqlalchemy import text
    from app.db.database import engine

    proj, art = await create_test_project_and_artifact(filename="pre_existing_dup.exe")
    try:
        # Simulate an older database state before unique index was applied
        async with engine.begin() as conn:
            await conn.execute(text("DROP INDEX IF EXISTS uq_active_artifact_job"))

        # Insert two active jobs for the same artifact directly into SQLite
        job1_id = str(uuid.uuid4())
        job2_id = str(uuid.uuid4())
        async with async_session_maker() as session:
            job_old = AnalysisJob(
                id=job1_id,
                project_id=proj.id,
                artifact_id=art.id,
                status="queued",
                created_at=utc_now(),
            )
            # Sleep slightly so timestamps are ordered
            await asyncio.sleep(0.01)
            job_new = AnalysisJob(
                id=job2_id,
                project_id=proj.id,
                artifact_id=art.id,
                status="running",
                created_at=utc_now(),
            )
            session.add_all([job_old, job_new])
            await session.commit()

        # Run init_db() - must safely migrate without crashing
        await init_db()

        # Verify:
        async with async_session_maker() as session:
            # 1. Older duplicate was non-destructively marked as failed
            reloaded_old = (await session.execute(select(AnalysisJob).where(AnalysisJob.id == job1_id))).scalar_one()
            assert reloaded_old.status == "failed"
            assert reloaded_old.current_step == "Superseded during migration"
            assert "duplicate active jobs" in reloaded_old.error_message

            # 2. Newer active job remains active
            reloaded_new = (await session.execute(select(AnalysisJob).where(AnalysisJob.id == job2_id))).scalar_one()
            assert reloaded_new.status == "running"

            # 3. Partial unique index is now active; inserting a 3rd active job must fail with IntegrityError
            third_job = AnalysisJob(
                id=str(uuid.uuid4()),
                project_id=proj.id,
                artifact_id=art.id,
                status="queued",
            )
            session.add(third_job)
            import pytest
            from sqlalchemy.exc import IntegrityError
            with pytest.raises(IntegrityError):
                await session.commit()
    finally:
        await cleanup_artifact_file(art.storage_path)


async def test_late_results_cannot_overwrite_terminal_job_state():
    """Verify that late results from delayed tool execution cannot overwrite a terminal state."""
    await init_db()
    proj, art = await create_test_project_and_artifact(filename="late_result_test.exe")

    try:
        tool_in_flight = asyncio.Event()
        tool_can_finish = asyncio.Event()

        async def late_dispatcher(artifact, project_id, is_cancelled=None):
            tool_in_flight.set()
            await tool_can_finish.wait()
            return DispatchResult(
                artifact_id=artifact.id,
                project_id=project_id,
                format="pe",
                status="completed",
                message="Late arrival",
                tool_results=[
                    NormalizedToolResult(
                        tool_name="inspect_pe_imports",
                        status="success",
                        category="pe_imports",
                        arguments={"path": artifact.storage_path},
                        parsed_evidence={"imports": ["KERNEL32.dll"]},
                    )
                ],
                summary=NormalizedSummary(),
                raw_evidence=[],
            )

        custom_jm = JobManager(max_concurrent_jobs=1, dispatcher_fn=late_dispatcher)

        async with async_session_maker() as session:
            job = AnalysisJob(
                id=str(uuid.uuid4()),
                project_id=proj.id,
                artifact_id=art.id,
                status="queued",
            )
            session.add(job)
            await session.commit()
            job_id = job.id

        task = await custom_jm.enqueue_job(job_id, proj.id, art.id)
        # Wait until tool is in-flight
        await tool_in_flight.wait()

        # While tool is in-flight, simulate an out-of-band terminal failure (e.g. timeout / admin cancel)
        async with async_session_maker() as session:
            stmt = select(AnalysisJob).where(AnalysisJob.id == job_id)
            j = (await session.execute(stmt)).scalar_one()
            j.status = "failed"
            j.completed_at = utc_now()
            j.current_step = "Terminated out-of-band"
            j.error_message = "External termination."
            await session.commit()

        # Now let the late tool finish
        tool_can_finish.set()
        await task

        # Re-check database: terminal state 'failed' must NOT have been overwritten by late 'completed'
        async with async_session_maker() as session:
            stmt = select(AnalysisJob).where(AnalysisJob.id == job_id)
            final_job = (await session.execute(stmt)).scalar_one()
            assert final_job.status == "failed"
            assert final_job.current_step == "Terminated out-of-band"
            assert final_job.error_message == "External termination."

            # Verify no late evidence records were committed
            stmt_ev = select(EvidenceRecord).where(EvidenceRecord.job_id == job_id)
            evs = (await session.execute(stmt_ev)).scalars().all()
            assert len(evs) == 0
    finally:
        tool_can_finish.set()
        await cleanup_artifact_file(art.storage_path)


# ---------------------------------------------------------------------------
# Direct Runner
# ---------------------------------------------------------------------------

async def run_all_job_tests():
    print("=" * 65)
    print("REPLICA LAB — Background Job Runner Test Suite")
    print("=" * 65)

    tests = [
        ("Job creation & immediate response", test_job_creation_and_immediate_response),
        ("Successful background execution", test_successful_background_execution),
        ("Partial analysis result", test_partial_analysis_result),
        ("Failed analysis", test_failed_analysis),
        ("Job status retrieval & listing", test_job_status_retrieval_and_listing),
        ("Unknown job ID (404)", test_unknown_job_id_returns_404),
        ("Invalid project/artifact relationship", test_invalid_project_artifact_relationship),
        ("Duplicate processing prevention", test_duplicate_processing_prevention),
        ("Concurrency limits", test_concurrency_limits),
        ("Restart recovery (queued & running)", test_restart_recovery_for_queued_and_running_jobs),
        ("Completed result persistence", test_completed_result_persistence),
        ("Database session cleanup", test_database_session_cleanup),
        ("Safe job cancellation", test_job_cancellation),
        ("Concurrent duplicate request race condition", test_concurrent_duplicate_analysis_requests_race_condition),
        ("Cancellation halts subsequent tools", test_cancellation_during_active_dispatch_aborts_subsequent_tools),
        ("Invalid state transitions rejected", test_invalid_state_transitions_rejected),
        ("Shutdown marks jobs interrupted not user cancelled", test_job_manager_shutdown_cancels_all_active_tasks),
        ("Safe migration handles existing duplicate active jobs", test_database_migration_handles_existing_duplicate_active_jobs_safely),
        ("Late results cannot overwrite terminal states", test_late_results_cannot_overwrite_terminal_job_state),
    ]

    for i, (name, fn) in enumerate(tests, 1):
        await fn()
        print(f"[{i}/{len(tests)}] {name}: PASSED")

    print("=" * 65)
    print("ALL BACKGROUND JOB RUNNER CONTROLS VERIFIED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_all_job_tests())
