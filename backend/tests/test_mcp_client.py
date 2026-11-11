import asyncio
import json
import sys
from pathlib import Path
from typing import List

# Ensure backend root is in Python sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from app.services.mcp_client import (
    ReaConnectionError,
    ReaMcpClient,
    ReaOperationTimeoutError,
    ReaProtocolError,
    ReaResponseTooLargeError,
    ReaToolExecutionError,
)


class TrackingByteStream(httpx.AsyncByteStream):
    """Custom streaming byte stream to test chunked responses and stream cleanup."""

    def __init__(self, chunks: List[bytes]):
        self.chunks = chunks
        self.closed = False
        self.chunks_yielded = 0

    async def __aiter__(self):
        for chunk in self.chunks:
            self.chunks_yielded += 1
            yield chunk

    async def aclose(self):
        self.closed = True


async def run_all_mcp_client_tests():
    print("=" * 65)
    print("REPLICA LAB — REA MCP HTTP Client Test Suite")
    print("=" * 65)

    base_url = "http://127.0.0.1:8080/mcp"
    captured_requests = []

    # -------------------------------------------------------------
    # Mock Transport implementing REA Streamable HTTP Specifications
    # -------------------------------------------------------------
    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)

        accept = request.headers.get("accept", "")
        content_type = request.headers.get("content-type", "")

        # 1. Initialize Request
        if request.method == "POST" and "mcp-session-id" not in request.headers:
            body = json.loads(request.read())
            if body.get("method") == "initialize":
                assert "application/json" in accept and "text/event-stream" in accept
                assert "application/json" in content_type
                return httpx.Response(
                    200,
                    headers={"mcp-session-id": "test-session-uuid-1234"},
                    json={
                        "jsonrpc": "2.0",
                        "id": body["id"],
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "serverInfo": {"name": "rea-mock-engine", "version": "6.8.0"},
                        },
                    },
                )

        # 2. Tool Calls & Notifications (Require mcp-session-id)
        session_id = request.headers.get("mcp-session-id")
        assert session_id == "test-session-uuid-1234", "Missing or invalid mcp-session-id"

        if request.method == "POST":
            body = json.loads(request.read())

            # Notifications (e.g. notifications/initialized)
            if body.get("method") == "notifications/initialized":
                return httpx.Response(200, json={})

            # Tool Calls
            if body.get("method") == "tools/call":
                tool_name = body["params"]["name"]

                if tool_name == "failing_tool":
                    return httpx.Response(
                        200,
                        json={
                            "jsonrpc": "2.0",
                            "id": body["id"],
                            "result": {
                                "isError": True,
                                "content": [
                                    {"type": "text", "text": "Target executable has invalid PE magic"}
                                ],
                            },
                        },
                    )

                if tool_name == "invalid_json_tool":
                    return httpx.Response(
                        200,
                        headers={"content-type": "application/json"},
                        content=b"<!DOCTYPE html><html>502 Bad Gateway</html>",
                    )

                # Successful tool call returning simulated findings
                payload = {
                    "tool": tool_name,
                    "evidence": {
                        "imports": ["KERNEL32.dll", "USER32.dll"],
                        "exports_count": 0,
                    },
                }
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": body["id"],
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(payload)}],
                        },
                    },
                )

        # 3. Session Cleanup (DELETE /mcp)
        if request.method == "DELETE":
            return httpx.Response(200, json={"status": "session_terminated"})

        return httpx.Response(404, json={"error": "Not Found"})

    mock_transport = httpx.MockTransport(mock_handler)
    client = ReaMcpClient(base_url=base_url, transport=mock_transport)

    # -------------------------------------------------------------
    # Test 1 & 2 & 3: Initialization, Session ID, Headers
    # -------------------------------------------------------------
    session_id = await client.initialize()
    assert session_id == "test-session-uuid-1234"
    assert client.session_id == "test-session-uuid-1234"
    print("[1/13] Successful initialization: PASSED")
    print(f"[2/13] Session ID extraction: PASSED ({session_id})")

    init_req = captured_requests[0]
    assert init_req.headers["accept"] == "application/json, text/event-stream"
    assert init_req.headers["content-type"] == "application/json"
    print("[3/13] Verified Accept and Content-Type headers: PASSED")

    # -------------------------------------------------------------
    # Test 4 & 5 & 6: Tool Call Execution & JSON Extraction
    # -------------------------------------------------------------
    captured_requests.clear()
    tool_resp = await client.call_tool("inspect_pe_imports", {"path": "/fake/binary.exe"})

    tool_req = next(r for r in captured_requests if r.method == "POST" and "tools/call" in r.read().decode())
    assert tool_req.headers["mcp-session-id"] == "test-session-uuid-1234"
    print("[4/13] Session header attached to tool calls: PASSED")

    tool_body = json.loads(tool_req.read())
    assert tool_body["method"] == "tools/call"
    assert tool_body["params"]["name"] == "inspect_pe_imports"
    assert tool_body["params"]["arguments"] == {"path": "/fake/binary.exe"}
    print("[5/13] JSON-RPC request structure verification: PASSED")

    assert tool_resp["tool"] == "inspect_pe_imports"
    assert "imports" in tool_resp["parsed"]["evidence"]
    assert "KERNEL32.dll" in tool_resp["parsed"]["evidence"]["imports"]
    print("[6/13] Tool response JSON extraction & parsing: PASSED")

    # -------------------------------------------------------------
    # Test 7: MCP Tool Error Handling (isError=true)
    # -------------------------------------------------------------
    error_caught = False
    try:
        await client.call_tool("failing_tool", {"path": "/fake/broken.exe"})
    except ReaToolExecutionError as exc:
        error_caught = True
        assert "invalid PE magic" in str(exc)
        assert exc.raw_result.get("isError") is True

    assert error_caught
    print("[7/13] MCP tool error (isError=true) handling: PASSED")

    # -------------------------------------------------------------
    # Test 8: Missing Session ID on Initialize
    # -------------------------------------------------------------
    def no_session_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "result": {}})

    broken_client = ReaMcpClient(base_url=base_url, transport=httpx.MockTransport(no_session_handler))
    missing_session_caught = False
    try:
        await broken_client.initialize()
    except ReaProtocolError as exc:
        missing_session_caught = True
        assert "omitted mandatory 'mcp-session-id'" in str(exc)

    assert missing_session_caught
    print("[8/13] Missing session ID error handling: PASSED")

    # -------------------------------------------------------------
    # Test 9: Invalid JSON Response
    # -------------------------------------------------------------
    client.session_id = "test-session-uuid-1234"
    invalid_json_caught = False
    try:
        await client.call_tool("invalid_json_tool")
    except ReaProtocolError as exc:
        invalid_json_caught = True
        assert "unparseable response" in str(exc)

    assert invalid_json_caught
    print("[9/13] Invalid JSON response handling: PASSED")

    # -------------------------------------------------------------
    # Test 10: Connection Timeout Handling
    # -------------------------------------------------------------
    def timeout_handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("Network unreachable")

    unreachable_client = ReaMcpClient(base_url=base_url, transport=httpx.MockTransport(timeout_handler))
    timeout_caught = False
    try:
        await unreachable_client.initialize()
    except ReaConnectionError as exc:
        timeout_caught = True
        assert "Connection timed out" in str(exc)

    assert timeout_caught
    print("[10/13] Connection timeout handling: PASSED")

    # -------------------------------------------------------------
    # Test 11: Explicit Session Cleanup via DELETE /mcp
    # -------------------------------------------------------------
    captured_requests.clear()
    await client.close_session()
    delete_req = captured_requests[0]
    assert delete_req.method == "DELETE"
    assert delete_req.headers["mcp-session-id"] == "test-session-uuid-1234"
    assert client.session_id is None
    print("[11/13] Session cleanup via DELETE /mcp: PASSED")

    # -------------------------------------------------------------
    # Test 12: Context Manager Clean Session Teardown on Exception
    # -------------------------------------------------------------
    captured_requests.clear()
    context_error_caught = False
    try:
        async with ReaMcpClient(base_url=base_url, transport=mock_transport) as session_ctx:
            await session_ctx.call_tool("failing_tool")
    except ReaToolExecutionError:
        context_error_caught = True

    assert context_error_caught
    delete_ctx_reqs = [r for r in captured_requests if r.method == "DELETE"]
    assert len(delete_ctx_reqs) == 1
    print("[12/13] Automatic session cleanup after tool failure: PASSED")

    # -------------------------------------------------------------
    # Test 13: Strict Non-Retry Policy on Operation Timeout
    # -------------------------------------------------------------
    tool_call_count = 0

    def slow_tool_handler(req: httpx.Request) -> httpx.Response:
        nonlocal tool_call_count
        if req.method == "POST" and "mcp-session-id" not in req.headers:
            return httpx.Response(200, headers={"mcp-session-id": "slow-session"}, json={"result": {}})
        if req.method == "POST" and "mcp-session-id" in req.headers:
            body = json.loads(req.read())
            if body.get("method") == "notifications/initialized":
                return httpx.Response(200, json={})
            if body.get("method") == "tools/call":
                tool_call_count += 1
                raise httpx.ReadTimeout("Analyzer execution deadline exceeded")
        return httpx.Response(200, json={})

    slow_client = ReaMcpClient(base_url=base_url, transport=httpx.MockTransport(slow_tool_handler))
    timeout_op_caught = False
    try:
        await slow_client.call_tool("heavy_decompilation")
    except ReaOperationTimeoutError as exc:
        timeout_op_caught = True
        assert "NOT be automatically retried" in str(exc)

    assert timeout_op_caught
    assert tool_call_count == 1, f"CRITICAL BUG: Uncertain tool call was retried {tool_call_count} times!"
    print("[13/13] Strict non-retry policy on read timeout: PASSED (Zero duplicate requests)")

    # =============================================================
    # STREAMING RESPONSE SIZE AUDIT TESTS
    # =============================================================

    # -------------------------------------------------------------
    # Test 14: Response Exceeding Limit through Chunked Transfer (No Content-Length)
    # -------------------------------------------------------------
    oversized_chunks = [b"A" * 60, b"B" * 60, b"C" * 60]  # Total: 180 bytes
    oversized_stream = TrackingByteStream(oversized_chunks)

    def chunked_oversized_handler(req: httpx.Request) -> httpx.Response:
        if "mcp-session-id" not in req.headers:
            return httpx.Response(200, headers={"mcp-session-id": "stream-session"}, json={"result": {}})
        body = json.loads(req.read())
        if body.get("method") == "notifications/initialized":
            return httpx.Response(200, json={})
        # Note: Transfer-Encoding: chunked, NO Content-Length
        return httpx.Response(
            200,
            headers={"transfer-encoding": "chunked", "content-type": "application/json"},
            stream=oversized_stream,
        )

    # Set limit to 100 bytes
    stream_client = ReaMcpClient(
        base_url=base_url,
        max_response_bytes=100,
        transport=httpx.MockTransport(chunked_oversized_handler),
    )

    oversized_caught = False
    try:
        await stream_client.call_tool("streaming_tool")
    except ReaResponseTooLargeError as exc:
        oversized_caught = True
        assert "streamed response exceeded maximum permitted size of 100 bytes" in str(exc)

    assert oversized_caught, "Expected ReaResponseTooLargeError was not raised for chunked oversized stream!"
    # Verify stream was aborted early: only 2 chunks yielded before hitting 120 bytes > 100
    assert oversized_stream.chunks_yielded == 2, f"Expected 2 chunks before abort, got {oversized_stream.chunks_yielded}"
    print("[14/18] Chunked transfer without Content-Length exceeding limit: PASSED (Aborted after 2 chunks)")

    # -------------------------------------------------------------
    # Test 15: Response Exactly at the Configured Limit
    # -------------------------------------------------------------
    exact_payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"content": [{"type": "text", "text": "OK"}]},
    }).encode("utf-8")
    exact_len = len(exact_payload)

    def exact_limit_handler(req: httpx.Request) -> httpx.Response:
        if "mcp-session-id" not in req.headers:
            return httpx.Response(200, headers={"mcp-session-id": "exact-session"}, json={"result": {}})
        body = json.loads(req.read())
        if body.get("method") == "notifications/initialized":
            return httpx.Response(200, json={})
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "content-length": str(exact_len)},
            content=exact_payload,
        )

    exact_client = ReaMcpClient(
        base_url=base_url,
        max_response_bytes=exact_len,  # Exactly at the limit
        transport=httpx.MockTransport(exact_limit_handler),
    )
    exact_res = await exact_client.call_tool("exact_limit_tool")
    assert exact_res["tool"] == "exact_limit_tool"
    assert exact_res["raw_text"] == "OK"
    print(f"[15/18] Response exactly at configured limit ({exact_len} bytes): PASSED")

    # -------------------------------------------------------------
    # Test 16: Response Below the Configured Limit
    # -------------------------------------------------------------
    below_client = ReaMcpClient(
        base_url=base_url,
        max_response_bytes=exact_len + 100,  # Below limit
        transport=httpx.MockTransport(exact_limit_handler),
    )
    below_res = await below_client.call_tool("below_limit_tool")
    assert below_res["tool"] == "below_limit_tool"
    assert below_res["raw_text"] == "OK"
    print(f"[16/18] Response below configured limit ({exact_len} < {exact_len + 100} bytes): PASSED")

    # -------------------------------------------------------------
    # Test 17: Oversized SSE (Server-Sent Events) Response
    # -------------------------------------------------------------
    sse_lines = [
        b"event: message\n",
        b"data: {\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"content\":[{\"type\":\"text\",\"text\":\"",
        b"Z" * 150,  # Oversized payload
        b"\"}]}}\n\n",
    ]
    sse_stream = TrackingByteStream(sse_lines)

    def sse_handler(req: httpx.Request) -> httpx.Response:
        if "mcp-session-id" not in req.headers:
            return httpx.Response(200, headers={"mcp-session-id": "sse-session"}, json={"result": {}})
        body = json.loads(req.read())
        if body.get("method") == "notifications/initialized":
            return httpx.Response(200, json={})
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=sse_stream,
        )

    sse_client = ReaMcpClient(
        base_url=base_url,
        max_response_bytes=80,  # Small limit to trigger on SSE streaming
        transport=httpx.MockTransport(sse_handler),
    )

    sse_oversized_caught = False
    try:
        await sse_client.call_tool("sse_tool")
    except ReaResponseTooLargeError as exc:
        sse_oversized_caught = True
        assert "streamed response exceeded maximum permitted size of 80 bytes" in str(exc)

    assert sse_oversized_caught, "Expected ReaResponseTooLargeError on oversized SSE stream!"
    print("[17/18] Oversized SSE response immediate streaming rejection: PASSED")

    # -------------------------------------------------------------
    # Test 18: Guaranteed Response Stream Cleanup After Rejection
    # -------------------------------------------------------------
    cleanup_stream = TrackingByteStream([b"DATA" * 50, b"MORE" * 50])

    def cleanup_handler(req: httpx.Request) -> httpx.Response:
        if "mcp-session-id" not in req.headers:
            return httpx.Response(200, headers={"mcp-session-id": "clean-session"}, json={"result": {}})
        body = json.loads(req.read())
        if body.get("method") == "notifications/initialized":
            return httpx.Response(200, json={})
        return httpx.Response(200, stream=cleanup_stream, headers={"content-type": "application/json"})

    cleanup_client = ReaMcpClient(
        base_url=base_url,
        max_response_bytes=50,
        transport=httpx.MockTransport(cleanup_handler),
    )

    try:
        await cleanup_client.call_tool("cleanup_test_tool")
    except ReaResponseTooLargeError:
        pass

    # Verify stream aclose() was called in finally block
    assert cleanup_stream.closed is True, "Stream was NOT cleanly closed on rejection!"
    print("[18/18] Guaranteed response stream cleanup on size rejection: PASSED (aclose confirmed)")

    print("=" * 65)
    print("ALL 18 REA MCP CLIENT & STREAMING AUDIT TESTS PASSED!")
    print("=" * 65)


async def test_mcp_client_suite():
    """Pytest entrypoint for REA MCP HTTP Client tests."""
    await run_all_mcp_client_tests()


if __name__ == "__main__":
    asyncio.run(run_all_mcp_client_tests())
