"""REPLICA LAB — REA Analysis Dispatcher Test Suite.

Verifies all 15 deterministic dispatching and security controls, plus focused audit tests:
1. PE dispatches to the three correct tools (inspect_pe_imports, inspect_pe_resources, inspect_pe_certificates).
2. SQLite dispatch (inspect_sqlite_database with path).
3. GGUF dispatch (inspect_model_artifact with path).
4. JavaScript uses input_path (analyze_javascript_application).
5. Go requires reliable language identification.
6. Rust requires reliable language identification.
7. Inconclusive formats do not trigger guessed analysis.
8. ZIP is unsupported without a verified analyzer.
9. APK is not incorrectly routed to JavaScript.
10. ASAR is routed only if verified as supported.
11. Missing file rejection.
12. Path outside upload directory rejection.
13. Project ownership mismatch rejection.
14. MCP errors are represented correctly.
15. Raw evidence is preserved.

AUDIT SECURITY EXTENSIONS:
16. Directory target rejection (directories rejected as non-regular files).
17. Symlink escape rejection (symlink resolving outside upload dir blocked).
18. Oversized MCP response protection (memory exhaustion guard with ReaResponseTooLargeError).
19. Tool timeout isolation & partial status (independent execution of PE tools despite timeout).
20. Distinguishable partial vs complete results.
"""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.db.models import Artifact
from app.services.dispatcher import (
    DispatchFileNotFoundError,
    DispatchResult,
    DispatchSecurityError,
    detect_binary_language,
    dispatch_analysis,
    plan_tools_for_artifact,
    validate_artifact_security,
)
from app.services.mcp_client import (
    ReaConnectionError,
    ReaMcpClient,
    ReaOperationTimeoutError,
    ReaResponseTooLargeError,
    ReaToolExecutionError,
)


class MockReaMcpClient(ReaMcpClient):
    """Mock REA MCP Client simulating verified REA tool execution."""

    def __init__(
        self,
        responses: Optional[Dict[str, Any]] = None,
        errors: Optional[Dict[str, Exception]] = None,
        max_response_bytes: Optional[int] = None,
    ):
        super().__init__(
            base_url="http://mock-rea:8080/mcp",
            max_response_bytes=max_response_bytes or settings.REA_MAX_RESPONSE_BYTES,
        )
        self.calls: List[Tuple[str, Dict[str, Any]]] = []
        self.responses = responses or {}
        self.errors = errors or {}

    async def call_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        args = arguments or {}
        self.calls.append((tool_name, args))

        if tool_name in self.errors:
            raise self.errors[tool_name]

        if tool_name in self.responses:
            resp = self.responses[tool_name]
            raw_txt = resp.get("raw_text", "")
            if len(raw_txt.encode("utf-8")) > self.max_response_bytes:
                raise ReaResponseTooLargeError(
                    f"REA tool '{tool_name}' content text size ({len(raw_txt.encode('utf-8'))} bytes) "
                    f"exceeds maximum permitted size of {self.max_response_bytes} bytes."
                )
            return resp

        # Standard simulated response
        simulated_parsed = {"status": "ok", "tool": tool_name}
        return {
            "tool": tool_name,
            "parsed": simulated_parsed,
            "raw_text": json.dumps(simulated_parsed),
            "raw_result": {
                "isError": False,
                "content": [{"type": "text", "text": json.dumps(simulated_parsed)}],
            },
        }


# Helper to create temporary test files safely inside settings.absolute_upload_dir
def create_test_file(filename: str, content: bytes) -> Path:
    dest = settings.absolute_upload_dir / filename
    with open(dest, "wb") as f:
        f.write(content)
    return dest


def make_mock_artifact(
    storage_path: Path,
    detected_format: str,
    project_id: str = "project-alpha",
    artifact_id: Optional[str] = None,
) -> Artifact:
    return Artifact(
        id=artifact_id or str(uuid.uuid4()),
        project_id=project_id,
        original_filename=storage_path.name,
        storage_path=str(storage_path),
        file_size_bytes=storage_path.stat().st_size if storage_path.exists() and storage_path.is_file() else 0,
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        detected_format=detected_format,
    )


# ---------------------------------------------------------------------------
# Individual Test Functions for Pytest & Direct Execution
# ---------------------------------------------------------------------------

async def test_pe_dispatch_selects_three_tools():
    """Test 1: PE dispatches to inspect_pe_imports, inspect_pe_resources, inspect_pe_certificates."""
    f = create_test_file(f"test_pe_{uuid.uuid4().hex[:6]}.exe", b"MZ" + b"\x00" * 200)
    try:
        art = make_mock_artifact(f, "pe", project_id="proj-pe")
        mock_client = MockReaMcpClient(
            responses={
                "inspect_pe_imports": {
                    "tool": "inspect_pe_imports",
                    "parsed": {"imports": [{"dll": "KERNEL32.dll", "functions": ["ExitProcess"]}]},
                    "raw_text": '{"imports":[{"dll":"KERNEL32.dll"}]}',
                    "raw_result": {"isError": False},
                },
                "inspect_pe_resources": {
                    "tool": "inspect_pe_resources",
                    "parsed": {"resources": [{"name": "RT_MANIFEST"}]},
                    "raw_text": '{"resources":[{"name":"RT_MANIFEST"}]}',
                    "raw_result": {"isError": False},
                },
                "inspect_pe_certificates": {
                    "tool": "inspect_pe_certificates",
                    "parsed": {"certificates": [{"type": "authenticode"}]},
                    "raw_text": '{"certificates":[{"type":"authenticode"}]}',
                    "raw_result": {"isError": False},
                },
            }
        )
        res = await dispatch_analysis(art, "proj-pe", mock_client)
        assert res.status == "completed"
        assert len(mock_client.calls) == 3
        called_tools = [c[0] for c in mock_client.calls]
        assert called_tools == ["inspect_pe_imports", "inspect_pe_resources", "inspect_pe_certificates"]
        for tool_name, args in mock_client.calls:
            assert "path" in args
            assert args["path"] == str(f.resolve())
        assert len(res.summary.imports) == 1
        assert res.summary.imports[0]["dll"] == "KERNEL32.dll"
        assert len(res.summary.resources) == 1
        assert len(res.summary.certificates) == 1
    finally:
        if f.exists():
            f.unlink()


async def test_sqlite_dispatch():
    """Test 2: SQLite dispatch uses inspect_sqlite_database."""
    f = create_test_file(f"test_sql_{uuid.uuid4().hex[:6]}.db", b"SQLite format 3\x00" + b"\x00" * 100)
    try:
        art = make_mock_artifact(f, "sqlite", project_id="proj-sql")
        mock_client = MockReaMcpClient(
            responses={
                "inspect_sqlite_database": {
                    "tool": "inspect_sqlite_database",
                    "parsed": {"tables": [{"name": "users"}, {"name": "sessions"}]},
                    "raw_text": '{"tables":[{"name":"users"},{"name":"sessions"}]}',
                    "raw_result": {"isError": False},
                }
            }
        )
        res = await dispatch_analysis(art, "proj-sql", mock_client)
        assert res.status == "completed"
        assert len(mock_client.calls) == 1
        assert mock_client.calls[0][0] == "inspect_sqlite_database"
        assert mock_client.calls[0][1] == {"path": str(f.resolve())}
        assert "users" in res.summary.database_tables
        assert "sessions" in res.summary.database_tables
    finally:
        if f.exists():
            f.unlink()


async def test_gguf_dispatch():
    """Test 3: GGUF dispatch uses inspect_model_artifact."""
    f = create_test_file(f"test_model_{uuid.uuid4().hex[:6]}.gguf", b"GGUF" + b"\x00" * 100)
    try:
        art = make_mock_artifact(f, "gguf", project_id="proj-gguf")
        mock_client = MockReaMcpClient(
            responses={
                "inspect_model_artifact": {
                    "tool": "inspect_model_artifact",
                    "parsed": {"architecture": "llama", "tensor_count": 291},
                    "raw_text": '{"architecture":"llama","tensor_count":291}',
                    "raw_result": {"isError": False},
                }
            }
        )
        res = await dispatch_analysis(art, "proj-gguf", mock_client)
        assert res.status == "completed"
        assert len(mock_client.calls) == 1
        assert mock_client.calls[0][0] == "inspect_model_artifact"
        assert mock_client.calls[0][1] == {"path": str(f.resolve())}
        assert res.summary.model_metadata.get("architecture") == "llama"
        assert res.summary.model_metadata.get("tensor_count") == 291
    finally:
        if f.exists():
            f.unlink()


async def test_javascript_uses_input_path():
    """Test 4: JavaScript uses input_path (CRITICAL: not path)."""
    f = create_test_file(f"test_script_{uuid.uuid4().hex[:6]}.js", b"console.log('hello');")
    try:
        art = make_mock_artifact(f, "javascript", project_id="proj-js")
        mock_client = MockReaMcpClient(
            responses={
                "analyze_javascript_application": {
                    "tool": "analyze_javascript_application",
                    "parsed": {"modules": ["index.js"], "technologies": ["Node.js"]},
                    "raw_text": '{"modules":["index.js"],"technologies":["Node.js"]}',
                    "raw_result": {"isError": False},
                }
            }
        )
        res = await dispatch_analysis(art, "proj-js", mock_client)
        assert res.status == "completed"
        assert len(mock_client.calls) == 1
        tool_name, args = mock_client.calls[0]
        assert tool_name == "analyze_javascript_application"
        assert "input_path" in args, "Must use 'input_path'!"
        assert "path" not in args, "'path' must not be sent!"
        assert args["input_path"] == str(f.resolve())
        assert "Node.js" in res.summary.technologies
    finally:
        if f.exists():
            f.unlink()


async def test_go_requires_reliable_indicators():
    """Test 5: Go requires reliable language evidence."""
    # 5A: Valid Go indicators present
    f_go = create_test_file(f"test_go_{uuid.uuid4().hex[:6]}.bin", b"\x7fELF" + b"\x00" * 16 + b"\xff Go buildinf:\x01\x02\x03" + b"\x00" * 100)
    try:
        art_go = make_mock_artifact(f_go, "go", project_id="proj-go")
        mock_go = MockReaMcpClient(
            responses={
                "inspect_go_binary": {
                    "tool": "inspect_go_binary",
                    "parsed": {"go_version": "go1.22.1", "main_module": "github.com/app"},
                    "raw_text": '{"go_version":"go1.22.1"}',
                    "raw_result": {"isError": False},
                }
            }
        )
        res_go = await dispatch_analysis(art_go, "proj-go", mock_go)
        assert res_go.status == "completed"
        assert len(mock_go.calls) == 1
        assert mock_go.calls[0][0] == "inspect_go_binary"
        assert mock_go.calls[0][1] == {"path": str(f_go.resolve())}
    finally:
        if f_go.exists():
            f_go.unlink()

    # 5B: Missing Go indicators
    f_nogo = create_test_file(f"test_nogo_{uuid.uuid4().hex[:6]}.bin", b"\x7fELF" + b"\x00" * 200)
    try:
        art_nogo = make_mock_artifact(f_nogo, "go", project_id="proj-go")
        mock_nogo = MockReaMcpClient()
        res_nogo = await dispatch_analysis(art_nogo, "proj-go", mock_nogo)
        assert res_nogo.status == "inconclusive"
        assert len(mock_nogo.calls) == 0
        assert "reliable Go compiler signatures" in res_nogo.message
    finally:
        if f_nogo.exists():
            f_nogo.unlink()


async def test_rust_requires_reliable_indicators():
    """Test 6: Rust requires reliable language evidence."""
    # 6A: Valid Rust .dep-v0 section present
    f_rust = create_test_file(f"test_rust_{uuid.uuid4().hex[:6]}.bin", b"\x7fELF" + b"\x00" * 16 + b".dep-v0" + b"\x00" * 100)
    try:
        art_rust = make_mock_artifact(f_rust, "rust", project_id="proj-rust")
        mock_rust = MockReaMcpClient(
            responses={
                "inspect_rust_binary": {
                    "tool": "inspect_rust_binary",
                    "parsed": {"packages": [{"name": "tokio", "version": "1.35.0"}]},
                    "raw_text": '{"packages":[{"name":"tokio"}]}',
                    "raw_result": {"isError": False},
                }
            }
        )
        res_rust = await dispatch_analysis(art_rust, "proj-rust", mock_rust)
        assert res_rust.status == "completed"
        assert len(mock_rust.calls) == 1
        assert mock_rust.calls[0][0] == "inspect_rust_binary"
        assert mock_rust.calls[0][1] == {"path": str(f_rust.resolve())}
    finally:
        if f_rust.exists():
            f_rust.unlink()

    # 6B: Missing Rust indicators
    f_norust = create_test_file(f"test_norust_{uuid.uuid4().hex[:6]}.bin", b"\x7fELF" + b"\x00" * 200)
    try:
        art_norust = make_mock_artifact(f_norust, "rust", project_id="proj-rust")
        mock_norust = MockReaMcpClient()
        res_norust = await dispatch_analysis(art_norust, "proj-rust", mock_norust)
        assert res_norust.status == "inconclusive"
        assert len(mock_norust.calls) == 0
    finally:
        if f_norust.exists():
            f_norust.unlink()


async def test_inconclusive_formats_do_not_guess():
    """Test 7: Inconclusive formats do not trigger guessed analysis."""
    f = create_test_file(f"test_elf_{uuid.uuid4().hex[:6]}.bin", b"\x7fELF" + b"\x01\x01\x01\x00" + b"\x00" * 100)
    try:
        art = make_mock_artifact(f, "elf", project_id="proj-elf")
        mock_client = MockReaMcpClient()
        res = await dispatch_analysis(art, "proj-elf", mock_client)
        assert res.status == "inconclusive"
        assert len(mock_client.calls) == 0
        assert "ELF binary language is inconclusive" in res.message
    finally:
        if f.exists():
            f.unlink()


async def test_zip_unsupported():
    """Test 8: ZIP receives an unsupported result without verified analyzer."""
    f = create_test_file(f"test_archive_{uuid.uuid4().hex[:6]}.zip", b"PK\x03\x04" + b"\x00" * 50)
    try:
        art = make_mock_artifact(f, "zip", project_id="proj-zip")
        mock_client = MockReaMcpClient()
        res = await dispatch_analysis(art, "proj-zip", mock_client)
        assert res.status == "unsupported"
        assert len(mock_client.calls) == 0
        assert "ZIP archive analysis is not supported" in res.message
    finally:
        if f.exists():
            f.unlink()


async def test_apk_not_routed_to_javascript():
    """Test 9: APK is not incorrectly routed to JavaScript analyzer."""
    f = create_test_file(f"test_app_{uuid.uuid4().hex[:6]}.apk", b"PK\x03\x04" + b"\x00" * 50)
    try:
        art = make_mock_artifact(f, "apk", project_id="proj-apk")
        mock_client = MockReaMcpClient()
        res = await dispatch_analysis(art, "proj-apk", mock_client)
        assert res.status == "unsupported"
        assert len(mock_client.calls) == 0
        assert "Android APK analysis is not supported" in res.message
    finally:
        if f.exists():
            f.unlink()


async def test_asar_routed_when_supported():
    """Test 10: ASAR is routed only if verified as supported."""
    f = create_test_file(f"test_app_{uuid.uuid4().hex[:6]}.asar", b"\x04\x00\x00\x00" + b"\x10\x00\x00\x00" + b'{"files":{}}')
    try:
        art = make_mock_artifact(f, "asar", project_id="proj-asar")
        mock_client = MockReaMcpClient(
            responses={
                "analyze_javascript_application": {
                    "tool": "analyze_javascript_application",
                    "parsed": {"modules": ["main.js"], "technologies": ["Electron"]},
                    "raw_text": '{"modules":["main.js"]}',
                    "raw_result": {"isError": False},
                }
            }
        )
        res = await dispatch_analysis(art, "proj-asar", mock_client)
        assert res.status == "completed"
        assert len(mock_client.calls) == 1
        assert mock_client.calls[0][0] == "analyze_javascript_application"
        assert mock_client.calls[0][1] == {"input_path": str(f.resolve())}
    finally:
        if f.exists():
            f.unlink()


async def test_missing_file_rejection():
    """Test 11: Missing artifact files are rejected."""
    missing_path = settings.absolute_upload_dir / f"missing_{uuid.uuid4().hex[:8]}.bin"
    art = make_mock_artifact(missing_path, "pe", project_id="proj-miss")
    try:
        await dispatch_analysis(art, "proj-miss", MockReaMcpClient())
        assert False, "Should raise DispatchFileNotFoundError"
    except DispatchFileNotFoundError as exc:
        assert "Artifact file not found" in str(exc)


async def test_path_outside_upload_dir_rejection():
    """Test 12: Paths outside upload directory are rejected."""
    outside = Path("C:/Windows/System32/cmd.exe") if os.name == "nt" else Path("/bin/sh")
    art = make_mock_artifact(outside, "pe", project_id="proj-out")
    try:
        await dispatch_analysis(art, "proj-out", MockReaMcpClient())
        assert False, "Should raise DispatchSecurityError"
    except DispatchSecurityError as exc:
        assert "resolves outside upload directory" in str(exc)


async def test_project_ownership_mismatch_rejection():
    """Test 13: Project ownership mismatches are rejected."""
    f = create_test_file(f"test_own_{uuid.uuid4().hex[:6]}.bin", b"SQLite format 3\x00")
    try:
        art = make_mock_artifact(f, "sqlite", project_id="proj-owner-A")
        try:
            await dispatch_analysis(art, "proj-owner-B", MockReaMcpClient())
            assert False, "Should raise DispatchSecurityError"
        except DispatchSecurityError as exc:
            assert "belongs to project 'proj-owner-A', not requested project 'proj-owner-B'" in str(exc)
    finally:
        if f.exists():
            f.unlink()


async def test_mcp_errors_represented_correctly():
    """Test 14: MCP tool errors are represented correctly without process crash."""
    f = create_test_file(f"test_err_{uuid.uuid4().hex[:6]}.exe", b"MZ" + b"\x00" * 100)
    try:
        art = make_mock_artifact(f, "pe", project_id="proj-err")
        mock_client = MockReaMcpClient(
            errors={
                "inspect_pe_imports": ReaToolExecutionError("Corrupted PE header in import table"),
                "inspect_pe_resources": ReaConnectionError("Connection lost during resource scan"),
            },
            responses={
                "inspect_pe_certificates": {
                    "tool": "inspect_pe_certificates",
                    "parsed": {"certificates": []},
                    "raw_text": '{"certificates":[]}',
                    "raw_result": {"isError": False},
                }
            },
        )
        res = await dispatch_analysis(art, "proj-err", mock_client)
        assert res.status == "partial"
        assert len(res.tool_results) == 3
        imports_res = next(tr for tr in res.tool_results if tr.tool_name == "inspect_pe_imports")
        assert imports_res.status == "error"
        assert "Corrupted PE header" in imports_res.error_message

        res_res = next(tr for tr in res.tool_results if tr.tool_name == "inspect_pe_resources")
        assert res_res.status == "error"
        assert "Connection lost" in res_res.error_message

        cert_res = next(tr for tr in res.tool_results if tr.tool_name == "inspect_pe_certificates")
        assert cert_res.status == "success"
    finally:
        if f.exists():
            f.unlink()


async def test_raw_evidence_preserved():
    """Test 15: Raw evidence is preserved during normalization."""
    f = create_test_file(f"test_raw_{uuid.uuid4().hex[:6]}.db", b"SQLite format 3\x00")
    try:
        art = make_mock_artifact(f, "sqlite", project_id="proj-raw")
        raw_dict = {"status": "ok", "db_signature": "sqlite3_verified"}
        mock_client = MockReaMcpClient(
            responses={
                "inspect_sqlite_database": {
                    "tool": "inspect_sqlite_database",
                    "parsed": raw_dict,
                    "raw_text": json.dumps(raw_dict),
                    "raw_result": {
                        "isError": False,
                        "custom_envelope_digest": "abcdef0123456789",
                        "content": [{"type": "text", "text": json.dumps(raw_dict)}],
                    },
                }
            }
        )
        res = await dispatch_analysis(art, "proj-raw", mock_client)
        assert res.status == "completed"
        assert res.tool_results[0].raw_result["custom_envelope_digest"] == "abcdef0123456789"
        assert json.loads(res.tool_results[0].raw_text) == raw_dict
        assert len(res.raw_evidence) == 1
        assert res.raw_evidence[0]["tool"] == "inspect_sqlite_database"
        assert res.raw_evidence[0]["raw_result"]["custom_envelope_digest"] == "abcdef0123456789"
    finally:
        if f.exists():
            f.unlink()


# ---------------------------------------------------------------------------
# AUDIT SECURITY EXTENSIONS
# ---------------------------------------------------------------------------

async def test_directory_artifact_rejection():
    """Audit 16: Directory targets passed as artifact storage path must be rejected."""
    dir_path = settings.absolute_upload_dir / f"test_dir_{uuid.uuid4().hex[:6]}"
    dir_path.mkdir(exist_ok=True)
    try:
        art = make_mock_artifact(dir_path, "pe", project_id="proj-dir")
        try:
            await dispatch_analysis(art, "proj-dir", MockReaMcpClient())
            assert False, "Should raise DispatchSecurityError for directory target"
        except DispatchSecurityError as exc:
            assert "directory, not a regular file" in str(exc)
    finally:
        if dir_path.exists():
            dir_path.rmdir()


async def test_symlink_escape_rejection():
    """Audit 17: Symlink resolving outside the upload directory is rejected."""
    fake_nominal = settings.absolute_upload_dir / "simulated_symlink.bin"
    art = make_mock_artifact(fake_nominal, "pe", project_id="proj-sym")
    outside_target = Path("C:/Windows/System32/notepad.exe") if os.name == "nt" else Path("/etc/passwd")

    real_resolve = Path.resolve

    def mock_resolve(self):
        if "simulated_symlink" in str(self):
            return outside_target
        return real_resolve(self)

    with patch.object(Path, "resolve", side_effect=mock_resolve, autospec=True):
        try:
            await dispatch_analysis(art, "proj-sym", MockReaMcpClient())
            assert False, "Should raise DispatchSecurityError for symlink escape"
        except DispatchSecurityError as exc:
            assert "resolves outside upload directory" in str(exc)


async def test_mcp_oversized_response_rejection():
    """Audit 18: Oversized MCP tool response is caught as ReaResponseTooLargeError and recorded as error."""
    f = create_test_file(f"test_huge_{uuid.uuid4().hex[:6]}.db", b"SQLite format 3\x00")
    try:
        art = make_mock_artifact(f, "sqlite", project_id="proj-huge")
        # Configure client with tiny 100-byte max response limit
        huge_mock = MockReaMcpClient(
            max_response_bytes=100,
            responses={
                "inspect_sqlite_database": {
                    "tool": "inspect_sqlite_database",
                    "parsed": {"status": "ok"},
                    "raw_text": "X" * 500,  # 500 bytes exceeds 100-byte limit
                    "raw_result": {"isError": False},
                }
            },
        )
        res = await dispatch_analysis(art, "proj-huge", huge_mock)
        assert res.status == "error"
        assert len(res.tool_results) == 1
        assert res.tool_results[0].status == "error"
        assert "Response size exceeded limit" in res.tool_results[0].error_message
        # Confirm incomplete/oversized evidence is NOT silently presented as success
        assert len(res.summary.database_tables) == 0
    finally:
        if f.exists():
            f.unlink()


async def test_tool_timeout_isolation():
    """Audit 19: One tool timing out does not terminate other independent PE inspections."""
    f = create_test_file(f"test_timeout_{uuid.uuid4().hex[:6]}.exe", b"MZ" + b"\x00" * 200)
    try:
        art = make_mock_artifact(f, "pe", project_id="proj-timeout")
        timeout_mock = MockReaMcpClient(
            errors={
                "inspect_pe_imports": ReaOperationTimeoutError("inspect_pe_imports timed out after 60.0s"),
            },
            responses={
                "inspect_pe_resources": {
                    "tool": "inspect_pe_resources",
                    "parsed": {"resources": [{"name": "RT_VERSION"}]},
                    "raw_text": '{"resources":[{"name":"RT_VERSION"}]}',
                    "raw_result": {"isError": False},
                },
                "inspect_pe_certificates": {
                    "tool": "inspect_pe_certificates",
                    "parsed": {"certificates": [{"type": "authenticode"}]},
                    "raw_text": '{"certificates":[{"type":"authenticode"}]}',
                    "raw_result": {"isError": False},
                },
            },
        )
        res = await dispatch_analysis(art, "proj-timeout", timeout_mock)
        # Verify status is partial
        assert res.status == "partial"
        assert "2 tool(s) succeeded, 1 tool(s) failed" in res.message
        # Verify timeout error was isolated to imports only
        imports_res = next(tr for tr in res.tool_results if tr.tool_name == "inspect_pe_imports")
        assert imports_res.status == "error"
        assert "Operation timed out" in imports_res.error_message
        # Verify subsequent tools ran and populated summary
        assert len(res.summary.resources) == 1
        assert len(res.summary.certificates) == 1
    finally:
        if f.exists():
            f.unlink()


async def test_partial_results_distinguishable_from_complete():
    """Audit 20: Partial results are distinct from complete results in status and summary."""
    f = create_test_file(f"test_comp_{uuid.uuid4().hex[:6]}.exe", b"MZ" + b"\x00" * 200)
    try:
        art = make_mock_artifact(f, "pe", project_id="proj-dist")
        # Complete run
        comp_mock = MockReaMcpClient()
        res_comp = await dispatch_analysis(art, "proj-dist", comp_mock)
        assert res_comp.status == "completed"

        # Partial run
        part_mock = MockReaMcpClient(
            errors={"inspect_pe_resources": ReaConnectionError("Connection dropped")}
        )
        res_part = await dispatch_analysis(art, "proj-dist", part_mock)
        assert res_part.status == "partial"
        assert res_comp.status != res_part.status
    finally:
        if f.exists():
            f.unlink()


# ---------------------------------------------------------------------------
# Runner function for direct script execution
# ---------------------------------------------------------------------------

async def run_all_tests():
    print("=" * 65)
    print("REPLICA LAB — REA Analysis Dispatcher Test Suite")
    print("=" * 65)

    tests = [
        ("PE dispatches to the three correct tools", test_pe_dispatch_selects_three_tools),
        ("SQLite dispatch", test_sqlite_dispatch),
        ("GGUF dispatch", test_gguf_dispatch),
        ("JavaScript uses input_path", test_javascript_uses_input_path),
        ("Go requires reliable language evidence", test_go_requires_reliable_indicators),
        ("Rust requires reliable language evidence", test_rust_requires_reliable_indicators),
        ("Inconclusive formats do not trigger guessed analysis", test_inconclusive_formats_do_not_guess),
        ("ZIP is unsupported without a verified analyzer", test_zip_unsupported),
        ("APK is not incorrectly routed to JavaScript", test_apk_not_routed_to_javascript),
        ("ASAR is routed only if verified as supported", test_asar_routed_when_supported),
        ("Missing file rejection", test_missing_file_rejection),
        ("Path outside upload directory rejection", test_path_outside_upload_dir_rejection),
        ("Project ownership mismatch rejection", test_project_ownership_mismatch_rejection),
        ("MCP errors are represented correctly", test_mcp_errors_represented_correctly),
        ("Raw evidence is preserved", test_raw_evidence_preserved),
        ("Directory artifact rejection (Audit)", test_directory_artifact_rejection),
        ("Symlink escape rejection (Audit)", test_symlink_escape_rejection),
        ("Oversized MCP response protection (Audit)", test_mcp_oversized_response_rejection),
        ("Tool timeout isolation & partial status (Audit)", test_tool_timeout_isolation),
        ("Partial vs complete result distinction (Audit)", test_partial_results_distinguishable_from_complete),
    ]

    for i, (name, fn) in enumerate(tests, 1):
        await fn()
        print(f"[{i}/{len(tests)}] {name}: PASSED")

    print("=" * 65)
    print(f"ALL {len(tests)} DISPATCHER CONTROLS & AUDIT CHECKS PASSED!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
