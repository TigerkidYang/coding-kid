from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pytest

from coding_kid.events import CancellationToken, TurnCancelled
from coding_kid.permissions import PermissionBroker
from coding_kid.sandbox import SandboxConfig, SandboxMode, SandboxRuntime
from coding_kid.tools import build_tool_registry
from coding_kid.web import HttpResponse, MAX_RESPONSE_BYTES, WebError, WebRuntime
from coding_kid.workflow import ApprovalPolicy, CollaborationMode, WorkflowState


PUBLIC_IP = "93.184.216.34"


def public_resolver(_host: str, _port: int) -> tuple[str, ...]:
    return (PUBLIC_IP,)


def test_search_requires_key_and_formats_numbered_provenance() -> None:
    with pytest.raises(WebError, match="BRAVE_SEARCH_API_KEY"):
        WebRuntime(brave_api_key="").search("python agents")

    observed: list[tuple[str, Mapping[str, str]]] = []

    def requester(url: str, headers: Mapping[str, str]) -> HttpResponse:
        observed.append((url, headers))
        return HttpResponse(
            200,
            {"content-type": "application/json"},
            b'{"web":{"results":['
            b'{"title":"Official docs","url":"https://example.com/docs",'
            b'"description":"Useful summary"},'
            b'{"title":"unsafe","url":"file:///secret"}'
            b"]}}",
        )

    result = WebRuntime(brave_api_key="secret-token", requester=requester).search(
        "python agents", 5
    )

    assert "[1] Official docs" in result
    assert "https://example.com/docs" in result
    assert "file:///secret" not in result
    assert "Untrusted external" in result
    assert "secret-token" not in result
    assert observed[0][1]["X-Subscription-Token"] == "secret-token"


def test_fetch_follows_public_redirect_and_extracts_text() -> None:
    calls: list[str] = []

    def requester(url: str, _headers: Mapping[str, str]) -> HttpResponse:
        calls.append(url)
        if len(calls) == 1:
            return HttpResponse(302, {"Location": "/article"}, b"")
        return HttpResponse(
            200,
            {"Content-Type": "text/html; charset=utf-8"},
            b"<title>Example</title><script>ignore()</script><h1>Hello</h1><p>World</p>",
        )

    result = WebRuntime(resolver=public_resolver, requester=requester).fetch(
        "https://example.com/start#fragment"
    )

    assert calls == ["https://example.com/start", "https://example.com/article"]
    assert "Title: Example" in result
    assert "Hello World" in result
    assert "ignore" not in result
    assert "Citation: [1] https://example.com/article" in result


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://user:password@example.com/",
        "http://example.com:8080/",
        "http://localhost/",
    ],
)
def test_fetch_rejects_unsafe_url_forms(url: str) -> None:
    with pytest.raises(WebError):
        WebRuntime(resolver=public_resolver, requester=lambda *_: None).fetch(url)  # type: ignore[arg-type]


def test_fetch_rejects_private_or_mixed_dns_and_redirects() -> None:
    private = WebRuntime(
        resolver=lambda _host, _port: ("127.0.0.1",),
        requester=lambda *_: HttpResponse(200, {}, b"no"),
    )
    with pytest.raises(WebError, match="non-public"):
        private.fetch("http://internal.example/")

    mixed = WebRuntime(
        resolver=lambda _host, _port: (PUBLIC_IP, "10.0.0.2"),
        requester=lambda *_: HttpResponse(200, {}, b"no"),
    )
    with pytest.raises(WebError, match="non-public"):
        mixed.fetch("https://mixed.example/")

    def redirect_requester(_url: str, _headers: Mapping[str, str]) -> HttpResponse:
        return HttpResponse(302, {"location": "http://private.example/"}, b"")

    def redirect_resolver(host: str, _port: int) -> tuple[str, ...]:
        return ("10.0.0.3",) if host == "private.example" else (PUBLIC_IP,)

    with pytest.raises(WebError, match="non-public"):
        WebRuntime(resolver=redirect_resolver, requester=redirect_requester).fetch(
            "https://public.example/"
        )


def test_fetch_rejects_binary_encoded_and_oversized_content() -> None:
    responses = [
        HttpResponse(200, {"content-type": "application/pdf"}, b"pdf"),
        HttpResponse(
            200,
            {"content-type": "text/plain", "content-encoding": "gzip"},
            b"compressed",
        ),
        HttpResponse(
            200,
            {"content-type": "text/plain"},
            b"x" * (MAX_RESPONSE_BYTES + 1),
        ),
    ]
    runtime = WebRuntime(
        resolver=public_resolver, requester=lambda *_: responses.pop(0)
    )
    with pytest.raises(WebError, match="content type"):
        runtime.fetch("https://example.com/one")
    with pytest.raises(WebError, match="content encoding"):
        runtime.fetch("https://example.com/two")
    with pytest.raises(WebError, match="exceeds"):
        runtime.fetch("https://example.com/three")


def test_web_tools_are_mode_visible_but_sandbox_network_governed(
    tmp_path: Path,
) -> None:
    runtime = WebRuntime(
        brave_api_key="token",
        resolver=public_resolver,
        requester=lambda *_: HttpResponse(
            200, {"content-type": "application/json"}, b'{"web":{"results":[]}}'
        ),
    )
    sandbox = SandboxRuntime(
        SandboxConfig(
            SandboxMode.WORKSPACE_WRITE,
            tmp_path,
            tmp_path,
            network_enabled=False,
        )
    )
    registry = build_tool_registry(sandbox_runtime=sandbox, web_runtime=runtime)
    names = {
        item["name"] for item in registry.definitions_for_mode(CollaborationMode.PLAN)
    }
    assert {"web_search", "web_fetch"} <= names

    broker = PermissionBroker(ApprovalPolicy.FULL_ACCESS, WorkflowState())
    authorization = registry.authorize(
        "web_search", {"query": "test", "count": 1}, broker
    )
    assert authorization.allowed is False
    assert "sandbox network policy" in authorization.message


def test_search_and_redirect_fetch_honor_turn_cancellation() -> None:
    token = CancellationToken()
    token.cancel()
    requested = False

    def should_not_request(*_args: object) -> HttpResponse:
        nonlocal requested
        requested = True
        return HttpResponse(200, {}, b"{}")

    runtime = WebRuntime(brave_api_key="token", requester=should_not_request)
    with pytest.raises(TurnCancelled):
        runtime.search("cancelled", cancellation_token=token)
    assert requested is False

    redirect_token = CancellationToken()

    def cancel_on_redirect(*_args: object) -> HttpResponse:
        redirect_token.cancel()
        return HttpResponse(302, {"location": "/next"}, b"")

    with pytest.raises(TurnCancelled):
        WebRuntime(resolver=public_resolver, requester=cancel_on_redirect).fetch(
            "https://example.com/start",
            cancellation_token=redirect_token,
        )
