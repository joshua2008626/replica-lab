import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

# Ensure backend root is in Python sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.mcp_client import ReaMcpClient


async def run_live_rea_integration():
    print("=" * 65)
    print("REPLICA LAB — Live REA Service Integration Test")
    print("=" * 65)

    rea_dir = "C:/Users/joshu/OneDrive/Desktop/rea-main"
    node_exe = "node"

    print("Launching actual REA MCP Streamable HTTP service...")
    cmd = [node_exe, "scripts/rea.mjs", "mcp", "--http", "--port", "0"]
    proc = subprocess.Popen(
        cmd,
        cwd=rea_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    mcp_url = None
    try:
        # Wait up to 10 seconds for listening line on stderr
        for _ in range(50):
            line = proc.stderr.readline()
            if line:
                print(f"[REA STDERR] {line.strip()}")
                match = re.search(r'"url":"(http://127\.0\.0\.1:\d+/mcp)"', line)
                if match:
                    mcp_url = match.group(1)
                    break
            await asyncio.sleep(0.2)

        assert mcp_url is not None, "Failed to capture listening URL from REA process"
        print(f"\n[LIVE TEST 1/3] Real REA bound successfully to: {mcp_url}")

        # Connect with our Python ReaMcpClient
        async with ReaMcpClient(base_url=mcp_url) as client:
            session_id = client.session_id
            assert session_id is not None
            print(f"[LIVE TEST 2/3] Live session handshake established: {session_id}")

            # Invoke a benign, pure built-in tool that requires no external engines
            # 'binary_session' target-free probe as used by REA's internal doctor
            tool_resp = await client.call_tool("binary_session", {})
            assert tool_resp["tool"] == "binary_session"
            print("[LIVE TEST 3/3] Live 'binary_session' query returned verified response!")
            print("Server Identity Response:", json.dumps(tool_resp.get("parsed") or tool_resp.get("raw_text"))[:120], "...")

        print("\nAll live REA integration checks passed cleanly!")
    finally:
        proc.terminate()
        proc.wait(timeout=5)
        print("Live REA process terminated cleanly.")


if __name__ == "__main__":
    asyncio.run(run_live_rea_integration())
