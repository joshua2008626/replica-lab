import hashlib
import os
import re
import struct
import zipfile
from pathlib import Path
from typing import Optional

SUPPORTED_FORMATS = {
    "pe": "Windows Portable Executable (EXE/DLL)",
    "elf": "Linux Executable and Linkable Format (ELF)",
    "sqlite": "SQLite 3 Database",
    "gguf": "GGUF AI Model Artifact",
    "zip": "ZIP Archive Container",
    "apk": "Android Application Package (APK)",
    "asar": "Electron ASAR Archive",
    "javascript": "JavaScript Source / Bundle",
    "unknown": "Unknown / Unclassified Binary",
}


def sanitize_filename(filename: Optional[str]) -> str:
    """Sanitize original client filename to prevent path traversal and control character attacks.
    
    This clean string is stored solely for human display in the database; it is never
    used as a storage path on the filesystem.
    """
    if not filename:
        return "unnamed_artifact"

    # Normalize slashes and extract base name only
    clean = os.path.basename(filename.replace("\\", "/"))
    # Remove ASCII control characters, null bytes, and non-printable characters
    clean = re.sub(r"[\x00-\x1f\x7f]", "", clean).strip(". ")

    # Disallow Windows device reservation names
    stem = clean.split(".")[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "LPT1", "LPT2"}:
        clean = f"safe_{clean}"

    return clean[:255] if clean else "sanitized_artifact"


def detect_format_from_bytes(header: bytes, file_path: Optional[Path] = None) -> str:
    """Detect file format using magic bytes, structural headers, and cautious validation.
    
    Never relies solely on client file extensions. Returns 'unknown' if the format
    cannot be reliably established.
    """
    if not header:
        return "unknown"

    header_len = len(header)

    # 1. ELF Check: \x7fELF (Bytes 0-3)
    if header_len >= 4 and header[:4] == b"\x7fELF":
        return "elf"

    # 2. SQLite 3 Check: "SQLite format 3\x00" (Bytes 0-15)
    if header_len >= 16 and header[:16] == b"SQLite format 3\x00":
        return "sqlite"

    # 3. GGUF AI Model Check: "GGUF" (Bytes 0-3: 0x47, 0x47, 0x55, 0x46)
    if header_len >= 4 and header[:4] == b"GGUF":
        return "gguf"

    # 4. Windows PE Check: Begins with "MZ" (DOS header) and offset 0x3C points to "PE\0\0"
    if header_len >= 64 and header[:2] == b"MZ":
        try:
            e_lfanew = struct.unpack_from("<I", header, 0x3C)[0]
            if 0 < e_lfanew <= header_len - 4:
                if header[e_lfanew : e_lfanew + 4] == b"PE\x00\x00":
                    return "pe"
            elif file_path and file_path.exists() and e_lfanew > 0:
                # If e_lfanew exceeds initial header slice, seek directly in the file
                with open(file_path, "rb") as f:
                    f.seek(e_lfanew)
                    if f.read(4) == b"PE\x00\x00":
                        return "pe"
        except Exception:
            pass

    # 5. Electron ASAR Check: Chromium Pickle header structure
    # Standard ASAR begins with uint32(4), then uint32 pickle_size, then json header containing '{"files"'
    if header_len >= 28 and header[:4] == b"\x04\x00\x00\x00":
        try:
            pickle_size = struct.unpack_from("<I", header, 4)[0]
            search_bound = min(header_len, 16 + pickle_size)
            if b'{"files"' in header[:search_bound]:
                return "asar"
        except Exception:
            pass

    # 6. ZIP / APK Check: PK\x03\x04 (Local file header) or PK\x05\x06 (Empty zip)
    if header_len >= 4 and (header[:4] == b"PK\x03\x04" or header[:4] == b"PK\x05\x06"):
        if file_path and file_path.exists():
            try:
                with zipfile.ZipFile(file_path, "r") as zf:
                    names = set(zf.namelist())
                    # Android APKs contain AndroidManifest.xml or Dalvik DEX files
                    if "AndroidManifest.xml" in names or any(n.endswith(".dex") for n in names):
                        return "apk"
                return "zip"
            except Exception:
                return "zip"
        return "zip"

    # 7. JavaScript Source Check: Valid text with JS tokens and no binary null bytes
    if b"\x00" not in header[:1024]:
        try:
            sample_text = header[:4096].decode("utf-8", errors="strict")
            js_keywords = [
                r"\bfunction\b",
                r"\bconst\b",
                r"\blet\b",
                r"\bvar\b",
                r"\bimport\b.*\bfrom\b",
                r"\bexport\b",
                r"\bclass\b",
                r"\bconsole\.(?:log|error|warn)\b",
                r"\brequire\s*\(",
                r"^#!\s*/usr/bin/env\s+node",
            ]
            matches = sum(1 for pattern in js_keywords if re.search(pattern, sample_text, re.MULTILINE))
            if matches >= 2 or (matches >= 1 and any(tok in sample_text for tok in [";\n", "{\n", "}\n", "=>"])):
                return "javascript"
        except UnicodeDecodeError:
            pass

    return "unknown"


def calculate_sha256(file_path: Path, chunk_size: int = 65536) -> str:
    """Calculate the hex SHA-256 digest of a file using bounded chunks."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()
