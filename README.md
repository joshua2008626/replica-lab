# REPLICA LAB — AI Software Intelligence Studio

> **A modern, security-hardened developer studio for static binary inspection, architecture reverse-engineering, and cryptographic evidence collection.**

---

## 1. Executive Summary

**REPLICA LAB** is a high-assurance software intelligence studio that empowers security analysts, software architects, and reverse engineers to introspect compiled executables, neural models, databases, and application packages without dynamic execution risks.

Operating as an orchestration studio atop the **REA (Reverse Engineering Assistant)** daemon, REPLICA LAB combines an asynchronous FastAPI backend, a persistent SQLite evidence ledger, and a modern React 19 / TypeScript / Tailwind CSS studio interface.

```
+-------------------------------------------------------------------------------+
|                               REPLICA LAB STUDIO                              |
|                       React 19 + TypeScript + Vite + Tailwind                 |
|            (Workspaces, Quarantined Uploads, Live Jobs, Architecture Visuals) |
+---------------------------------------+---------------------------------------+
                                        |  REST API / HTTP Streaming
                                        v
+-------------------------------------------------------------------------------+
|                            FASTAPI BACKEND ENGINE                             |
|  - Cryptographic Provenance (SHA-256)   - Symlink & Path Traversal Guards     |
|  - Magic Byte MIME Validation           - Asynchronous Job Runner Pool        |
|  - REA Tool Analysis Dispatcher         - SQLite WAL Ledger & Schema Locks    |
+---------------------------------------+---------------------------------------+
                                        |  HTTP Streaming MCP Protocol
                                        v
+-------------------------------------------------------------------------------+
|                       REA MCP ENGINE (rea-main daemon)                        |
|  - inspect_pe_imports                  - inspect_sqlite_database             |
|  - inspect_pe_resources                - inspect_model_artifact (GGUF)       |
|  - inspect_pe_certificates             - analyze_javascript_application      |
+-------------------------------------------------------------------------------+
```

---

## 2. Key Architecture Pillars

### 2.1 Static-Only Inspection Guarantee
REPLICA LAB strictly inspects binary artifacts through static AST introspection, structural header parsing, and static metadata extraction. **Untrusted uploaded binaries are never executed on the host system.**

### 2.2 Quarantined Storage & Cryptographic Provenance
- **Chunked SHA-256 Hashing**: Every uploaded artifact is ingested in 64 KiB streams and cryptographically fingerprinted before disk commitment.
- **Magic Byte Verification**: True binary MIME types are verified using `python-magic-bin` to prevent extension-spoofing attacks (e.g. renaming an executable to `.txt`).
- **Symlink & Path Traversal Guards**: Artifact storage enforces UUID-based isolation. Any file path attempting to resolve outside the configured upload directory or across symbolic links is immediately rejected with HTTP 400.

### 2.3 Memory-Safe MCP Streaming Transport
Tool responses from the REA MCP engine are ingested through an incremental chunked HTTP reader. A running byte counter enforces a strict memory ceiling (`REA_MAX_RESPONSE_BYTES`, default 10 MiB) before memory allocation can expand, preventing denial-of-service (OOM) attacks from malicious or oversized tool outputs.

### 2.4 Race-Free Asynchronous Job Processing
- Background analysis jobs transition through atomic states: `queued` → `running` → `completed` | `partial` | `failed` | `cancelled`.
- **Database-Level Duplicate Protection**: A partial unique SQLite index (`uq_active_artifact_job`) ensures concurrent requests for the same artifact cannot create competing active worker tasks.
- **SQLite Lock Isolation**: Tool dispatches are decoupled from active database sessions, preventing database locks during multi-second tool runs.
- **Cancellation & Shutdown Safety**: Cancelled jobs discard pending tool calls immediately without leaving orphan jobs or corrupting terminal states.

---

## 3. Verified REA Tool Catalog & Dispatch Mappings

The REA Analysis Dispatcher (`backend/app/services/dispatcher.py`) maps validated file types to precise REA MCP tools:

| Artifact Type | File Extensions / Signatures | REA MCP Tool(s) | Key Arguments | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Windows PE** | `.exe`, `.dll`, `MZ` header | `inspect_pe_imports`<br>`inspect_pe_resources`<br>`inspect_pe_certificates` | `path` (string) | Extracts imported DLLs/functions, Win32 dialogs/icons, and authenticode digital signatures. |
| **SQLite Database** | `.db`, `.sqlite`, `SQLite format 3` | `inspect_sqlite_database` | `path` (string) | Dumps schema tables, triggers, indices, and row counts. |
| **GGUF Neural Model** | `.gguf`, `GGUF` magic header | `inspect_model_artifact` | `path` (string) | Extracts neural architecture, tensor counts, and quantization flags. |
| **JavaScript App** | `.js` | `analyze_javascript_application` | `input_path` (string) | AST parse of modules, dependencies, and native bridge invocations. |
| **Electron ASAR** | `.asar`, ASAR header | `analyze_javascript_application` | `input_path` (string) | Inspects bundled desktop application packages. |
| **Go Binaries** | Go build info section | *(Heuristic Detection)* | — | Flags Go runtime versions, module paths, and compiler flags. |
| **Rust Binaries** | Rust cargo-auditable | *(Heuristic Detection)* | — | Identifies embedded Cargo dependency dependency manifests. |

---

## 4. Frontend Studio Overview

The frontend is built with **React 19**, **TypeScript** (in `verbatimModuleSyntax` strict mode), and **Tailwind CSS v4**:

- **Overview Dashboard**: High-level telemetry, backend health monitoring, recent workspace activity, and system resource counters.
- **Workspace & Project Detail View**:
  - Secure drag-and-drop artifact quarantine uploader with live upload progress.
  - Artifact inventory displaying SHA-256 hashes, verified MIME types, and file sizes.
  - Single-click analysis runner triggering asynchronous background jobs.
  - Live job status queue with real-time cancellation buttons.
- **Evidence Explorer & Audit Trail**:
  - Full-text search and filtering across captured REA MCP evidence records.
  - Formatted JSON inspector with one-click clipboard copying.
  - Detailed findings modal categorizing imported libraries, resources, certificates, and compiler markers.
- **System Architecture Visualizer**:
  - Interactive topology map rendered using `@xyflow/react` (React Flow) illustrating data flow between Studio, Backend, SQLite Ledger, and REA MCP Daemon.
- **Settings & Telemetry**:
  - Live component status indicators for the FastAPI core, SQLite database, and REA MCP socket.

---

## 5. Getting Started

### Prerequisites
- **Python 3.10+** (Python 3.13 recommended)
- **Node.js 18+** (Node.js 20+ / npm 10+ recommended)
- **PowerShell** or **Command Prompt** (Windows)

---

### Quick Launch (One-Click)

From the project root:

- **Using Command Prompt / Explorer**:
  Double-click `run_dev.bat`
- **Using PowerShell**:
  ```powershell
  .\run_dev.ps1
  ```

This automatically spins up both the FastAPI backend (`http://127.0.0.1:8000`) and the Vite React frontend (`http://localhost:5173`).

---

### Manual Setup & Execution

#### 1. Backend Setup
```powershell
cd backend

# Create virtual environment (if not already created)
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run backend test suite (43 tests)
python -m pytest -v

# Start development server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

#### 2. Frontend Setup
```powershell
cd frontend

# Install node dependencies
npm.cmd install

# Run static linter (0 errors, 0 warnings)
npm.cmd run lint

# Build production bundle
npm.cmd run build

# Start development dev server
npm.cmd run dev
```

---

## 6. API Reference

All backend endpoints are documented interactively via OpenAPI Swagger at `http://127.0.0.1:8000/docs`:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Comprehensive system health and REA MCP engine connectivity. |
| `GET` | `/api/projects` | List all registered workspaces/projects. |
| `POST` | `/api/projects` | Create a new project workspace. |
| `GET` | `/api/projects/{id}` | Get project metadata along with its uploaded artifacts. |
| `DELETE` | `/api/projects/{id}` | Delete a project and its associated database records. |
| `POST` | `/api/uploads` | Upload and quarantine an artifact with SHA-256 calculation & MIME detection. |
| `POST` | `/api/projects/{id}/artifacts/{aid}/analyze` | Trigger asynchronous REA analysis job. |
| `GET` | `/api/projects/{id}/jobs` | List all analysis jobs for a given project. |
| `GET` | `/api/jobs/{id}` | Get comprehensive job status, timestamps, and normalized findings. |
| `POST` | `/api/jobs/{id}/cancel` | Abort a queued or running analysis job. |

---

## 7. Verification & Test Metrics

- **Backend Test Suite**: **43 / 43 tests passing** (`pytest -v`).
  - Covers dispatcher format routing, path symlink security, memory ceilings, partial tool isolation, background job concurrency, cancellation races, SQLite lock prevention, and shutdown recovery.
- **Frontend Code Quality**:
  - `oxlint`: **0 errors, 0 warnings** across all 27 TypeScript/React components.
  - Production build: Compiles cleanly with `tsc -b && vite build` in **< 1.0 second**.
- **External Dependency Integrity**:
  - Zero modifications to `rea-main`. `rea-main` remains 100% pristine and untouched.

---

## 8. License & Academic Attribution
Developed as part of the **REPLICA LAB** Software Intelligence Initiative. Designed with enterprise-grade security rigor for academic and professional reverse engineering research.
