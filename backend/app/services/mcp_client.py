import json
import logging
from typing import Any, Dict, Optional, Union
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class ReaMcpError(Exception):
    """Base exception for all REA MCP client failures."""
    pass


class ReaConnectionError(ReaMcpError):
    """Raised when REA service is unreachable or refuses connection."""
    pass


class ReaOperationTimeoutError(ReaMcpError):
    """Raised when a tool operation times out.
    
    CRITICAL: Never automatically retried, as the operation may already
    have been executed or state may have been modified by the analyzer.
    """
    pass


class ReaProtocolError(ReaMcpError):
    """Raised when the REA MCP transport violates JSON-RPC or MCP protocol rules."""
    pass


class ReaResponseTooLargeError(ReaMcpError):
    """Raised when the REA MCP server response exceeds the maximum allowed payload size."""
    pass


class ReaToolExecutionError(ReaMcpError):
    """Raised when the REA tool itself fails (e.g. isError=true or invalid target)."""

    def __init__(self, message: str, raw_result: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.raw_result = raw_result or {}


def parse_mcp_payload(target: Any, content_type: str = "") -> Dict[str, Any]:
    """Parse MCP HTTP response handling both raw application/json and text/event-stream (SSE) framing.
    
    Accepts either an httpx.Response object or a raw string/bytes payload.
    """
    if isinstance(target, httpx.Response):
        text = target.text.strip()
        ct = target.headers.get("content-type", "")
    elif isinstance(target, bytes):
        text = target.decode("utf-8", errors="replace").strip()
        ct = content_type
    elif isinstance(target, str):
        text = target.strip()
        ct = content_type
    else:
        return {}

    if not text:
        return {}

    # Check for SSE framing (event: ... \n data: ...)
    if "text/event-stream" in ct or "data:" in text:
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                payload_str = line[5:].strip()
                if payload_str:
                    try:
                        return json.loads(payload_str)
                    except json.JSONDecodeError:
                        continue

    # Standard JSON body
    if isinstance(target, httpx.Response) and hasattr(target, "json"):
        try:
            return target.json()
        except Exception:
            pass

    return json.loads(text)


class ReaMcpClient:
    """Async client communicating with REA's Model Context Protocol (MCP) Streamable HTTP service."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        connect_timeout: Optional[float] = None,
        read_timeout: Optional[float] = None,
        max_response_bytes: Optional[int] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.base_url = (base_url or settings.REA_MCP_URL).rstrip("/")
        self.connect_timeout = connect_timeout or settings.REA_CONNECT_TIMEOUT_SECONDS
        self.read_timeout = read_timeout or settings.REA_READ_TIMEOUT_SECONDS
        self.max_response_bytes = max_response_bytes or settings.REA_MAX_RESPONSE_BYTES
        self.session_id: Optional[str] = None
        self._request_counter: int = 0
        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None

    def _next_id(self) -> int:
        self._request_counter += 1
        return self._request_counter

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            timeout = httpx.Timeout(
                connect=self.connect_timeout,
                read=self.read_timeout,
                write=self.connect_timeout,
                pool=self.connect_timeout,
            )
            self._client = httpx.AsyncClient(
                timeout=timeout,
                transport=self._transport,
            )
        return self._client

    async def __aenter__(self) -> "ReaMcpClient":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close_session()

    async def initialize(self) -> str:
        """Execute MCP initialize handshake and obtain an active session ID."""
        client = self._get_client()

        init_payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "replica-lab-backend",
                    "version": settings.VERSION,
                },
            },
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        req = client.build_request("POST", self.base_url, json=init_payload, headers=headers)
        try:
            resp = await client.send(req, stream=True)
        except httpx.ConnectTimeout as exc:
            raise ReaConnectionError(f"Connection timed out reaching REA at {self.base_url}: {exc}") from exc
        except httpx.ConnectError as exc:
            raise ReaConnectionError(f"REA service is offline or unreachable at {self.base_url}: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ReaConnectionError(f"HTTP transport failure during REA initialize: {exc}") from exc

        try:
            # 1. Early Content-Length check
            content_length_header = resp.headers.get("content-length")
            if content_length_header:
                try:
                    cl = int(content_length_header)
                    if cl > self.max_response_bytes:
                        raise ReaResponseTooLargeError(
                            f"REA initialize response Content-Length ({cl} bytes) exceeds "
                            f"maximum permitted size of {self.max_response_bytes} bytes."
                        )
                except ValueError:
                    pass

            if resp.status_code != 200:
                err_bytes = bytearray()
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    err_bytes.extend(chunk)
                    if len(err_bytes) >= 4096:
                        break
                raise ReaProtocolError(
                    f"REA initialize failed with HTTP {resp.status_code}: {err_bytes.decode('utf-8', errors='replace')}"
                )

            # Extract required mcp-session-id header
            session_id = resp.headers.get("mcp-session-id")
            if not session_id:
                raise ReaProtocolError("REA server response omitted mandatory 'mcp-session-id' header.")

            # Incremental stream read with running byte count
            init_bytes = bytearray()
            running_count = 0
            async for chunk in resp.aiter_bytes():
                running_count += len(chunk)
                if running_count > self.max_response_bytes:
                    raise ReaResponseTooLargeError(
                        f"REA initialize streamed response exceeded maximum permitted size of "
                        f"{self.max_response_bytes} bytes (received > {running_count} bytes)."
                    )
                init_bytes.extend(chunk)

            content_type = resp.headers.get("content-type", "")
            raw_text = init_bytes.decode("utf-8", errors="replace")

        finally:
            await resp.aclose()

        try:
            data = parse_mcp_payload(raw_text, content_type)
        except Exception as exc:
            raise ReaProtocolError(f"REA initialize returned invalid JSON payload: {raw_text[:200]}") from exc

        if "error" in data:
            raise ReaProtocolError(f"REA initialize rejected: {data['error']}")

        self.session_id = session_id

        # Send standard notifications/initialized notification
        notif_payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }
        notif_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": self.session_id,
        }
        try:
            await client.post(self.base_url, json=notif_payload, headers=notif_headers)
        except Exception as exc:
            logger.debug("Optional notifications/initialized notice: %s", exc)

        logger.info("REA MCP session established: %s", self.session_id)
        return self.session_id

    async def call_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Invoke a specific REA tool within the active MCP session.
        
        Guarantees:
        - Validates session state before dispatch.
        - Streams HTTP responses incrementally to prevent memory exhaustion.
        - Immediately rejects responses exceeding max_response_bytes while streaming.
        - Strict non-retry policy on ReadTimeout to prevent state corruption.
        - Handles both raw JSON and SSE responses.
        - Guaranteed stream cleanup on success, exceptions, and size rejections.
        - Returns a structured dictionary containing parsed findings and raw evidence.
        """
        if not self.session_id:
            await self.initialize()

        client = self._get_client()

        body = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments or {},
            },
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": self.session_id,
        }

        req = client.build_request("POST", self.base_url, json=body, headers=headers)
        try:
            resp = await client.send(req, stream=True)
        except httpx.ConnectTimeout as exc:
            raise ReaConnectionError(f"Connection timeout while invoking '{tool_name}': {exc}") from exc
        except httpx.ReadTimeout as exc:
            # STRICT POLICY: Do not retry. The analyzer might still be executing on the host.
            raise ReaOperationTimeoutError(
                f"Execution for REA tool '{tool_name}' timed out after {self.read_timeout}s. "
                f"To prevent duplicate processing or analyzer corruption, this request will NOT be automatically retried."
            ) from exc
        except httpx.ConnectError as exc:
            raise ReaConnectionError(f"Connection lost to REA during tool '{tool_name}': {exc}") from exc
        except httpx.HTTPError as exc:
            raise ReaProtocolError(f"HTTP transport failure invoking '{tool_name}': {exc}") from exc

        try:
            # 1. Early Content-Length check (if advertised)
            content_length_header = resp.headers.get("content-length")
            if content_length_header:
                try:
                    cl = int(content_length_header)
                    if cl > self.max_response_bytes:
                        raise ReaResponseTooLargeError(
                            f"REA tool '{tool_name}' response Content-Length ({cl} bytes) exceeds "
                            f"maximum permitted size of {self.max_response_bytes} bytes."
                        )
                except ValueError:
                    pass

            if resp.status_code == 404:
                raise ReaProtocolError(f"Session '{self.session_id}' expired or was not recognized by REA.")

            if resp.status_code != 200:
                err_bytes = bytearray()
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    err_bytes.extend(chunk)
                    if len(err_bytes) >= 4096:
                        break
                raise ReaProtocolError(
                    f"REA tool call failed with HTTP {resp.status_code}: {err_bytes.decode('utf-8', errors='replace')}"
                )

            # 2. Incremental chunked streaming read with running byte count
            received_bytes = bytearray()
            running_count = 0
            try:
                async for chunk in resp.aiter_bytes():
                    running_count += len(chunk)
                    if running_count > self.max_response_bytes:
                        raise ReaResponseTooLargeError(
                            f"REA tool '{tool_name}' streamed response exceeded maximum permitted size of "
                            f"{self.max_response_bytes} bytes (received > {running_count} bytes)."
                        )
                    received_bytes.extend(chunk)
            except httpx.ReadTimeout as exc:
                raise ReaOperationTimeoutError(
                    f"Execution for REA tool '{tool_name}' timed out streaming response after {self.read_timeout}s. "
                    f"To prevent duplicate processing or analyzer corruption, this request will NOT be automatically retried."
                ) from exc

            content_type = resp.headers.get("content-type", "")
            raw_text_payload = received_bytes.decode("utf-8", errors="replace")

        finally:
            # Guaranteed stream cleanup on success, exceptions, or size rejections
            await resp.aclose()

        # 3. Payload parsing (JSON and SSE)
        try:
            data = parse_mcp_payload(raw_text_payload, content_type)
        except Exception as exc:
            raise ReaProtocolError(f"REA tool '{tool_name}' returned unparseable response: {raw_text_payload[:200]}") from exc

        # Check JSON-RPC protocol level error
        if "error" in data:
            err = data["error"]
            raise ReaToolExecutionError(
                f"REA JSON-RPC error ({err.get('code')}): {err.get('message')}",
                raw_result=data,
            )

        result = data.get("result", {})
        is_error = result.get("isError", False)
        content_items = result.get("content", [])

        raw_text = ""
        parsed_payload: Any = None

        if content_items and isinstance(content_items, list):
            first_content = content_items[0]
            if isinstance(first_content, dict) and "text" in first_content:
                raw_text = first_content["text"]
                try:
                    parsed_payload = json.loads(raw_text)
                except Exception:
                    parsed_payload = raw_text

        if is_error:
            error_detail = raw_text if raw_text else "Tool execution marked as error"
            raise ReaToolExecutionError(
                f"REA tool '{tool_name}' returned failure: {error_detail}",
                raw_result=result,
            )

        return {
            "tool": tool_name,
            "parsed": parsed_payload,
            "raw_text": raw_text,
            "raw_result": result,
        }

    async def close_session(self) -> None:
        """Terminate the active MCP session and release worker resources on REA."""
        if self.session_id and self._client and not self._client.is_closed:
            headers = {
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": self.session_id,
            }
            try:
                await self._client.delete(self.base_url, headers=headers)
                logger.info("REA MCP session terminated cleanly: %s", self.session_id)
            except Exception as exc:
                logger.debug("Non-fatal notice during session DELETE: %s", exc)

        self.session_id = None
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
