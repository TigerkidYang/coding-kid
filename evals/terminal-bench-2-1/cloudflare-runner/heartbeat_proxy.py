"""Local OpenAI-compatible proxy that keeps long SSE requests alive."""

from __future__ import annotations

import json
import itertools
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx

UPSTREAM = "http://127.0.0.1:8787"
LISTEN = ("127.0.0.1", 8788)
HEARTBEAT = b": " + (b" " * 4094) + b"\n\n"
JSON_HEARTBEAT = b" " * 4096
UPSTREAM_RETRY_STATUSES = {502, 503, 504}
UPSTREAM_MAX_ATTEMPTS = 3
REQUEST_IDS = itertools.count(1)
HOP_HEADERS = {
    "connection",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.client_address[0]} {format % args}", flush=True)

    def do_GET(self) -> None:
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def _request_body(self) -> bytes:
        length = int(self.headers.get("content-length", "0"))
        return self.rfile.read(length) if length else b""

    def _headers(self) -> dict[str, str]:
        return {
            name: value
            for name, value in self.headers.items()
            if name.casefold() not in HOP_HEADERS
        }

    def _proxy(self) -> None:
        body = self._request_body()
        streaming = False
        responses_request = self.path.rstrip("/").endswith("/responses") and body
        if responses_request:
            try:
                streaming = json.loads(body).get("stream") is True
            except (json.JSONDecodeError, AttributeError):
                pass
        if streaming:
            self._proxy_stream(body)
        elif responses_request:
            self._proxy_json_keepalive(body)
        else:
            self._proxy_regular(body)

    def _proxy_json_keepalive(self, body: bytes) -> None:
        events: queue.Queue[tuple[str, Any]] = queue.Queue()
        request_id = next(REQUEST_IDS)
        started = time.monotonic()
        heartbeat_count = 1
        print(
            f"json_keepalive_start id={request_id} path={self.path} bytes={len(body)}",
            flush=True,
        )

        def relay() -> None:
            try:
                for attempt in range(1, UPSTREAM_MAX_ATTEMPTS + 1):
                    response = httpx.request(
                        self.command,
                        f"{UPSTREAM}{self.path}",
                        headers=self._headers(),
                        content=body,
                        timeout=None,
                    )
                    if (
                        response.status_code not in UPSTREAM_RETRY_STATUSES
                        or attempt == UPSTREAM_MAX_ATTEMPTS
                    ):
                        break
                    print(
                        f"json_upstream_retry id={request_id} "
                        f"status={response.status_code} attempt={attempt} "
                        f"elapsed={time.monotonic() - started:.1f}",
                        flush=True,
                    )
                    time.sleep(2)
                print(
                    f"json_upstream_complete id={request_id} "
                    f"status={response.status_code} attempt={attempt} "
                    f"bytes={len(response.content)} "
                    f"elapsed={time.monotonic() - started:.1f}",
                    flush=True,
                )
                events.put(("response", response.content))
            except Exception as error:
                print(
                    f"json_upstream_error id={request_id} "
                    f"elapsed={time.monotonic() - started:.1f} error={error!r}",
                    flush=True,
                )
                payload = json.dumps({"error": str(error)}).encode()
                events.put(("response", payload))

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        self.close_connection = True
        self._write_chunk(JSON_HEARTBEAT)
        threading.Thread(target=relay, daemon=True).start()
        while True:
            try:
                kind, value = events.get(timeout=15)
            except queue.Empty:
                kind, value = "heartbeat", None
            try:
                if kind == "response":
                    self._write_chunk(value)
                    self._write_chunk(b"")
                    print(
                        f"json_client_complete id={request_id} "
                        f"heartbeats={heartbeat_count} "
                        f"elapsed={time.monotonic() - started:.1f}",
                        flush=True,
                    )
                    break
                heartbeat_count += 1
                self._write_chunk(JSON_HEARTBEAT)
            except (BrokenPipeError, ConnectionResetError):
                print(
                    f"json_client_disconnect id={request_id} "
                    f"heartbeats={heartbeat_count} "
                    f"elapsed={time.monotonic() - started:.1f}",
                    flush=True,
                )
                break

    def _proxy_regular(self, body: bytes) -> None:
        try:
            response = httpx.request(
                self.command,
                f"{UPSTREAM}{self.path}",
                headers=self._headers(),
                content=body,
                timeout=None,
            )
        except Exception as error:
            payload = json.dumps({"error": str(error)}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(response.status_code)
        for name, value in response.headers.items():
            if name.casefold() not in HOP_HEADERS:
                self.send_header(name, value)
        self.send_header("Content-Length", str(len(response.content)))
        self.end_headers()
        self.wfile.write(response.content)

    def _proxy_stream(self, body: bytes) -> None:
        events: queue.Queue[tuple[str, Any]] = queue.Queue()

        def relay() -> None:
            try:
                with httpx.stream(
                    self.command,
                    f"{UPSTREAM}{self.path}",
                    headers=self._headers(),
                    content=body,
                    timeout=None,
                ) as response:
                    if response.status_code >= 400:
                        events.put(
                            ("error", response.read().decode("utf-8", "replace"))
                        )
                        return
                    for chunk in response.iter_raw():
                        if chunk:
                            events.put(("chunk", chunk))
            except Exception as error:
                events.put(("error", str(error)))
            finally:
                events.put(("done", None))

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        self.close_connection = True
        self._write_chunk(HEARTBEAT)
        threading.Thread(target=relay, daemon=True).start()
        while True:
            try:
                kind, value = events.get(timeout=15)
            except queue.Empty:
                kind, value = "heartbeat", None
            try:
                if kind == "chunk":
                    self._write_chunk(value)
                elif kind == "error":
                    payload = json.dumps(
                        {"type": "error", "error": {"message": str(value)}}
                    ).encode()
                    self._write_chunk(b"event: error\ndata: " + payload + b"\n\n")
                elif kind == "heartbeat":
                    self._write_chunk(HEARTBEAT)
                elif kind == "done":
                    self._write_chunk(b"")
                    break
            except (BrokenPipeError, ConnectionResetError):
                break

    def _write_chunk(self, payload: bytes) -> None:
        if payload:
            self.wfile.write(f"{len(payload):X}\r\n".encode("ascii"))
            self.wfile.write(payload)
            self.wfile.write(b"\r\n")
        else:
            self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()


if __name__ == "__main__":
    ThreadingHTTPServer(LISTEN, Handler).serve_forever()
