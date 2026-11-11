"""REPLICA LAB — REA Analysis Dispatcher.

Deterministic, security-hardened tool dispatcher connecting database-backed
Artifact records to verified REA MCP tools.

Enforces:
1. Database-backed Artifact verification and project ownership.
2. Strict storage directory boundary confinement (path traversal mitigation).
3. Existence and regular file checks.
4. Deterministic format-to-tool routing using verified REA MCP schemas.
5. Strict evidence normalization and raw output preservation.
6. Zero code execution on host (authorized static inspection only).
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from app.core.config import settings
from app.db.models import Artifact
from app.services.mcp_client import (
    ReaMcpClient,
    ReaMcpError,
    ReaOperationTimeoutError,
    ReaResponseTooLargeError,
    ReaToolExecutionError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class DispatchError(Exception):
    """Base exception for all dispatcher errors."""
    pass


class DispatchSecurityError(DispatchError):
    """Raised when security boundaries (path traversal, project mismatch, non-regular files) are violated."""
    pass


class DispatchFileNotFoundError(DispatchError):
    """Raised when an artifact file does not exist on disk."""
    pass


# ---------------------------------------------------------------------------
# Evidence Normalization Models
# ---------------------------------------------------------------------------

class NormalizedToolResult(BaseModel):
    """Normalized evidence record from a single REA MCP tool invocation."""

    tool_name: str
    status: str  # "success" | "error" | "unsupported"
    category: str
    arguments: Dict[str, Any]
    raw_result: Optional[Dict[str, Any]] = None
    raw_text: Optional[str] = None
    parsed_evidence: Optional[Any] = None
    error_message: Optional[str] = None


class NormalizedSummary(BaseModel):
    """Aggregated, unembellished summary of verified technical findings."""

    imports: List[Dict[str, Any]] = Field(default_factory=list)
    resources: List[Dict[str, Any]] = Field(default_factory=list)
    certificates: List[Dict[str, Any]] = Field(default_factory=list)
    database_tables: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    model_metadata: Dict[str, Any] = Field(default_factory=dict)
    modules: List[str] = Field(default_factory=list)
    compiler_info: Dict[str, Any] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)


class DispatchResult(BaseModel):
    """Top-level dispatch execution result returned to caller / job runner."""

    artifact_id: str
    project_id: str
    format: str
    status: str  # "completed" | "unsupported" | "inconclusive" | "error"
    message: Optional[str] = None
    tool_results: List[NormalizedToolResult] = Field(default_factory=list)
    summary: NormalizedSummary = Field(default_factory=NormalizedSummary)
    raw_evidence: List[Dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Static Binary Language Identification (Go / Rust)
# ---------------------------------------------------------------------------

def detect_binary_language(file_path: Path) -> Optional[str]:
    """Inspect binary content for reliable, format-specific language indicators.

    Safe read-only static analysis without binary execution.
    - Go: Identifies Go buildinfo magic (b"\\xff Go buildinf:") or .go.buildinfo section header
    - Rust: Identifies cargo-auditable section (b".dep-v0") or rustc panic markers
    Returns: 'go', 'rust', or None if inconclusive.
    """
    try:
        file_size = file_path.stat().st_size
        with open(file_path, "rb") as f:
            # Read first 64 KiB
            head = f.read(min(file_size, 65536))
            if b"\xff Go buildinf:" in head or b".go.buildinfo" in head or b"Go build ID:" in head:
                return "go"
            if b".dep-v0" in head or b"cargo-auditable" in head or b"/rustc/" in head:
                return "rust"

            # Read last 64 KiB (section tables / string tables often at file end in PE/ELF)
            if file_size > 65536:
                f.seek(max(0, file_size - 65536))
                tail = f.read(65536)
                if b"\xff Go buildinf:" in tail or b".go.buildinfo" in tail or b"Go build ID:" in tail:
                    return "go"
                if b".dep-v0" in tail or b"cargo-auditable" in tail or b"/rustc/" in tail:
                    return "rust"
    except Exception as exc:
        logger.warning("Error inspecting binary for language markers: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Security Validation
# ---------------------------------------------------------------------------

def validate_artifact_security(artifact: Artifact, project_id: str) -> Path:
    """Validate DB artifact record, project ownership, path traversal confinement, and file existence.

    Returns the resolved, trusted filesystem Path.
    Raises DispatchSecurityError or DispatchFileNotFoundError on violations.
    """
    if not isinstance(artifact, Artifact) or not getattr(artifact, "id", None):
        raise DispatchSecurityError("Invalid artifact: must be a database-backed Artifact instance.")

    if artifact.project_id != project_id:
        raise DispatchSecurityError(
            f"Security violation: Artifact '{artifact.id}' belongs to project '{artifact.project_id}', "
            f"not requested project '{project_id}'."
        )

    if not artifact.storage_path:
        raise DispatchSecurityError("Artifact has no storage_path recorded.")

    raw_path = Path(artifact.storage_path)
    if not raw_path.is_absolute():
        raw_path = settings.BACKEND_DIR / raw_path

    resolved_path = raw_path.resolve()
    upload_dir = settings.absolute_upload_dir.resolve()

    # Enforce upload directory containment (Path Traversal & Symlink Guard)
    try:
        resolved_path.relative_to(upload_dir)
    except ValueError:
        raise DispatchSecurityError(
            f"Security violation: Storage path '{artifact.storage_path}' resolves outside "
            f"upload directory '{upload_dir}'."
        )

    # Check symlink target explicitly if the file path is a symbolic link
    if raw_path.is_symlink():
        try:
            resolved_path.relative_to(upload_dir)
        except ValueError:
            raise DispatchSecurityError(
                f"Security violation: Symbolic link '{raw_path}' escapes upload directory to '{resolved_path}'."
            )

    # Check file exists
    if not resolved_path.exists():
        raise DispatchFileNotFoundError(f"Artifact file not found on disk at: {resolved_path}")

    # Check if target is a directory
    if resolved_path.is_dir():
        raise DispatchSecurityError(f"Artifact storage target is a directory, not a regular file: {resolved_path}")

    # Check regular file
    if not resolved_path.is_file():
        raise DispatchSecurityError(f"Artifact storage target is not a regular file: {resolved_path}")

    return resolved_path


# ---------------------------------------------------------------------------
# Tool Planning (Format & Language to Tool Mapping)
# ---------------------------------------------------------------------------

def plan_tools_for_artifact(
    artifact: Artifact,
    resolved_path: Path,
) -> Tuple[str, List[Tuple[str, str, Dict[str, Any]]], Optional[str]]:
    """Determine the list of REA tools to invoke based on detected format and verified language evidence.

    Verified Tool Schemas:
    - PE: inspect_pe_imports (path), inspect_pe_resources (path), inspect_pe_certificates (path)
    - SQLite: inspect_sqlite_database (path)
    - GGUF: inspect_model_artifact (path)
    - JavaScript: analyze_javascript_application (input_path)  <- CRITICAL: input_path, not path
    - ASAR: analyze_javascript_application (input_path)  <- verified in electronToolContracts.ts
    - Go: inspect_go_binary (path)  <- requires reliable Go indicators
    - Rust: inspect_rust_binary (path)  <- requires reliable Rust indicators
    - ZIP/APK: unsupported  <- no verified general analyzers, never route APK to JS

    Returns:
        (dispatch_status, tool_plans, explanation_message)
        where each tool_plan is a tuple of (tool_name, category, tool_arguments)
    """
    fmt = (artifact.detected_format or "unknown").lower()
    path_str = str(resolved_path)

    # 1. Windows Portable Executable (PE)
    if fmt == "pe":
        tool_plans = [
            ("inspect_pe_imports", "pe_imports", {"path": path_str}),
            ("inspect_pe_resources", "pe_resources", {"path": path_str}),
            ("inspect_pe_certificates", "pe_certificates", {"path": path_str}),
        ]
        # Check for specialized language runtime within PE
        lang = detect_binary_language(resolved_path)
        if lang == "go":
            tool_plans.append(("inspect_go_binary", "go_metadata", {"path": path_str}))
        elif lang == "rust":
            tool_plans.append(("inspect_rust_binary", "rust_metadata", {"path": path_str}))
        return "ready", tool_plans, None

    # 2. SQLite 3 Database
    if fmt == "sqlite":
        return "ready", [("inspect_sqlite_database", "sqlite_database", {"path": path_str})], None

    # 3. GGUF AI Model Artifact
    if fmt == "gguf":
        return "ready", [("inspect_model_artifact", "model_artifact", {"path": path_str})], None

    # 4. JavaScript Source / Bundle
    if fmt == "javascript":
        # CRITICAL: REA's analyze_javascript_application schema strictly expects 'input_path'
        return "ready", [("analyze_javascript_application", "javascript_application", {"input_path": path_str})], None

    # 5. Electron ASAR Archive
    if fmt == "asar":
        # Verified: analyze_javascript_application explicitly supports ASAR archives via input_path
        return "ready", [("analyze_javascript_application", "javascript_application", {"input_path": path_str})], None

    # 6. Explicit Go Binary
    if fmt == "go":
        lang = detect_binary_language(resolved_path)
        if lang == "go":
            return "ready", [("inspect_go_binary", "go_metadata", {"path": path_str})], None
        return (
            "inconclusive",
            [],
            "Artifact format is specified as Go, but reliable Go compiler signatures or buildinfo were not detected in the binary.",
        )

    # 7. Explicit Rust Binary
    if fmt == "rust":
        lang = detect_binary_language(resolved_path)
        if lang == "rust":
            return "ready", [("inspect_rust_binary", "rust_metadata", {"path": path_str})], None
        return (
            "inconclusive",
            [],
            "Artifact format is specified as Rust, but reliable Rust or cargo-auditable signatures were not detected in the binary.",
        )

    # 8. Linux Executable and Linkable Format (ELF)
    if fmt == "elf":
        lang = detect_binary_language(resolved_path)
        if lang == "go":
            return "ready", [("inspect_go_binary", "go_metadata", {"path": path_str})], None
        if lang == "rust":
            return "ready", [("inspect_rust_binary", "rust_metadata", {"path": path_str})], None
        return (
            "inconclusive",
            [],
            "ELF binary language is inconclusive. Generic ELF analyzers are not currently enabled to avoid guessing language runtimes.",
        )

    # 9. ZIP Archive Container
    if fmt == "zip":
        return (
            "unsupported",
            [],
            "ZIP archive analysis is not supported: no verified REA archive analyzer is currently configured.",
        )

    # 10. Android Application Package (APK)
    if fmt == "apk":
        return (
            "unsupported",
            [],
            "Android APK analysis is not supported: APK containers must not be routed to the JavaScript analyzer.",
        )

    # 11. Unknown / Other unsupported formats
    return (
        "unsupported",
        [],
        f"Artifact format '{fmt}' has no verified REA analyzer.",
    )


# ---------------------------------------------------------------------------
# Evidence Normalization
# ---------------------------------------------------------------------------

def normalize_evidence_summary(tool_results: List[NormalizedToolResult]) -> NormalizedSummary:
    """Extract and aggregate verified findings from tool results into a structured summary.

    Strict rules:
    - Never invent missing findings.
    - Only record observations directly extracted from parsed tool evidence.
    - Preserve categories cleanly.
    """
    summary = NormalizedSummary()

    for tr in tool_results:
        if tr.status != "success" or not tr.parsed_evidence:
            continue

        data = tr.parsed_evidence
        if not isinstance(data, dict):
            continue

        # PE Imports extraction
        if tr.tool_name == "inspect_pe_imports":
            imports_data = data.get("imports") or data.get("dlls") or data.get("descriptors") or []
            if isinstance(imports_data, list):
                for item in imports_data:
                    if isinstance(item, dict):
                        summary.imports.append(item)
                    elif isinstance(item, str):
                        summary.imports.append({"dll": item})

        # PE Resources extraction
        elif tr.tool_name == "inspect_pe_resources":
            resources_data = data.get("resources") or data.get("entries") or []
            if isinstance(resources_data, list):
                for res in resources_data:
                    if isinstance(res, dict):
                        summary.resources.append(res)
                    elif isinstance(res, str):
                        summary.resources.append({"name": res})

        # PE Certificates extraction
        elif tr.tool_name == "inspect_pe_certificates":
            certs_data = data.get("certificates") or data.get("entries") or data.get("signatures") or []
            if isinstance(certs_data, list):
                for cert in certs_data:
                    if isinstance(cert, dict):
                        summary.certificates.append(cert)

        # SQLite Database extraction
        elif tr.tool_name == "inspect_sqlite_database":
            tables_data = data.get("tables") or data.get("schema") or []
            if isinstance(tables_data, list):
                for tbl in tables_data:
                    if isinstance(tbl, dict) and "name" in tbl:
                        summary.database_tables.append(tbl["name"])
                    elif isinstance(tbl, str):
                        summary.database_tables.append(tbl)
            elif isinstance(tables_data, dict):
                summary.database_tables.extend(tables_data.keys())

        # GGUF Model extraction
        elif tr.tool_name == "inspect_model_artifact":
            for k in ("architecture", "model_type", "tensor_count", "alignment", "header", "metadata"):
                if k in data:
                    summary.model_metadata[k] = data[k]

        # JavaScript / ASAR Application extraction
        elif tr.tool_name == "analyze_javascript_application":
            modules_data = data.get("modules") or data.get("packages") or data.get("files") or []
            if isinstance(modules_data, list):
                for m in modules_data:
                    if isinstance(m, str):
                        summary.modules.append(m)
                    elif isinstance(m, dict) and "name" in m:
                        summary.modules.append(m["name"])
            tech_data = data.get("technologies") or data.get("frameworks") or []
            if isinstance(tech_data, list):
                for t in tech_data:
                    if isinstance(t, str) and t not in summary.technologies:
                        summary.technologies.append(t)

        # Go Binary extraction
        elif tr.tool_name == "inspect_go_binary":
            for k in ("go_version", "main_module", "dependencies", "build_settings"):
                if k in data:
                    summary.compiler_info[k] = data[k]

        # Rust Binary extraction
        elif tr.tool_name == "inspect_rust_binary":
            for k in ("packages", "dep_v0", "rustc_version", "cargo_auditable"):
                if k in data:
                    summary.compiler_info[k] = data[k]

    return summary


# ---------------------------------------------------------------------------
# Main Dispatch Execution Function
# ---------------------------------------------------------------------------

async def dispatch_analysis(
    artifact: Artifact,
    project_id: str,
    mcp_client: Optional[ReaMcpClient] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
) -> DispatchResult:
    """Execute static analysis dispatch for a verified Artifact record.

    Lifecycle:
    1. Validate artifact database record, project ownership, upload dir containment, and file existence.
    2. Determine verified REA MCP tools and argument schemas.
    3. Return clean inconclusive / unsupported result immediately if no verified analyzer exists.
    4. Call ReaMcpClient for each planned tool.
    5. Collect, normalize, and preserve raw evidence.
    6. Return structured DispatchResult.
    """
    # 1. Security validation
    resolved_path = validate_artifact_security(artifact, project_id)

    # 2. Tool planning
    status_kind, tool_plans, explanation = plan_tools_for_artifact(artifact, resolved_path)

    if status_kind in ("unsupported", "inconclusive"):
        return DispatchResult(
            artifact_id=artifact.id,
            project_id=project_id,
            format=artifact.detected_format,
            status=status_kind,
            message=explanation,
            tool_results=[],
            summary=NormalizedSummary(),
            raw_evidence=[],
        )

    # 3. Execution via ReaMcpClient
    tool_results: List[NormalizedToolResult] = []
    raw_evidence: List[Dict[str, Any]] = []

    async def _run_tools(client: ReaMcpClient) -> None:
        for tool_name, category, args in tool_plans:
            # Check cancellation before dispatching each individual tool
            if is_cancelled and is_cancelled():
                logger.info("Cancellation detected in dispatcher; aborting before '%s'", tool_name)
                break
            try:
                res = await client.call_tool(tool_name, arguments=args)
                parsed = res.get("parsed")
                raw_txt = res.get("raw_text")
                raw_res = res.get("raw_result")

                tool_results.append(
                    NormalizedToolResult(
                        tool_name=tool_name,
                        status="success",
                        category=category,
                        arguments=args,
                        raw_result=raw_res,
                        raw_text=raw_txt,
                        parsed_evidence=parsed,
                    )
                )
                raw_evidence.append(
                    {
                        "tool": tool_name,
                        "category": category,
                        "raw_result": raw_res,
                        "raw_text": raw_txt,
                    }
                )
            except ReaOperationTimeoutError as err:
                logger.error("Operation timeout for tool '%s': %s", tool_name, err)
                tool_results.append(
                    NormalizedToolResult(
                        tool_name=tool_name,
                        status="error",
                        category=category,
                        arguments=args,
                        error_message=f"Operation timed out: {err}",
                    )
                )
            except ReaResponseTooLargeError as err:
                logger.error("Response size limit exceeded for tool '%s': %s", tool_name, err)
                tool_results.append(
                    NormalizedToolResult(
                        tool_name=tool_name,
                        status="error",
                        category=category,
                        arguments=args,
                        error_message=f"Response size exceeded limit: {err}",
                    )
                )
            except ReaToolExecutionError as err:
                logger.warning("Tool '%s' returned execution error: %s", tool_name, err)
                tool_results.append(
                    NormalizedToolResult(
                        tool_name=tool_name,
                        status="error",
                        category=category,
                        arguments=args,
                        raw_result=getattr(err, "raw_result", None),
                        error_message=str(err),
                    )
                )
            except ReaMcpError as err:
                logger.error("MCP transport failure invoking tool '%s': %s", tool_name, err)
                tool_results.append(
                    NormalizedToolResult(
                        tool_name=tool_name,
                        status="error",
                        category=category,
                        arguments=args,
                        error_message=str(err),
                    )
                )

    if mcp_client is not None:
        await _run_tools(mcp_client)
    else:
        async with ReaMcpClient() as client:
            await _run_tools(client)

    # 4. Normalize summary
    summary = normalize_evidence_summary(tool_results)

    # 5. Determine overall dispatch status (distinguishing partial results)
    has_success = any(tr.status == "success" for tr in tool_results)
    has_error = any(tr.status == "error" for tr in tool_results)
    success_count = sum(1 for tr in tool_results if tr.status == "success")
    error_count = sum(1 for tr in tool_results if tr.status == "error")

    if has_success and not has_error:
        overall_status = "completed"
        message = f"Analysis completed successfully with {len(tool_results)} tool(s) executed."
    elif has_success and has_error:
        overall_status = "partial"
        message = f"Analysis completed with partial results: {success_count} tool(s) succeeded, {error_count} tool(s) failed."
    elif tool_results:
        overall_status = "error"
        message = "All planned tool invocations returned errors."
    else:
        overall_status = "unsupported"
        message = "No tools could be executed."

    return DispatchResult(
        artifact_id=artifact.id,
        project_id=project_id,
        format=artifact.detected_format,
        status=overall_status,
        message=message,
        tool_results=tool_results,
        summary=summary,
        raw_evidence=raw_evidence,
    )
