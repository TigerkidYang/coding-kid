from __future__ import annotations

import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from coding_kid.capabilities import CapabilityRuntime, CapabilityStartupError
from coding_kid.agent import run_turn
from coding_kid.context import SessionContext
from coding_kid.context_manager import ContextBudget, ContextManager
from coding_kid.skills import SkillTurnState


def _context(tmp_path: Path) -> SessionContext:
    return SessionContext(
        cwd=tmp_path,
        project_root=tmp_path,
        operating_system="Windows",
        shell="cmd.exe",
        model="test/model",
        local_date="2026-08-04",
        project_instructions=(),
        project_instructions_truncated=False,
    )


def _write_config(home: Path, servers: dict[str, object]) -> None:
    home.mkdir()
    (home / "capabilities.json").write_text(
        json.dumps({"mcpServers": servers}), encoding="utf-8"
    )


def _stdio_server(**overrides: object) -> dict[str, object]:
    fixture = Path(__file__).parent / "fixtures" / "mcp_server.py"
    value: dict[str, object] = {
        "transport": "stdio",
        "command": sys.executable,
        "args": [str(fixture)],
        "startupTimeoutSeconds": 10,
        "toolTimeoutSeconds": 2,
    }
    value.update(overrides)
    return value


def test_stdio_discovery_call_and_cleanup(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_config(home, {"local": _stdio_server(enabledTools=["echo"])})

    runtime = CapabilityRuntime.capture(_context(tmp_path), home=home)
    try:
        assert [tool.qualified_name for tool in runtime.tools] == ["mcp__local__echo"]
        registry = runtime.registry_for_turn(SkillTurnState(runtime.snapshot.skills))
        definition = next(
            item
            for item in registry.definitions()
            if item["name"] == "mcp__local__echo"
        )
        assert definition["strict"] is False
        result = registry.dispatch("mcp__local__echo", {"text": "hello"})
        assert '"echo": "hello"' in result
        assert '"structuredContent"' in result
    finally:
        runtime.close()

    assert not runtime._thread.is_alive()


def test_optional_failure_warns_but_required_failure_aborts(tmp_path: Path) -> None:
    optional_home = tmp_path / "optional"
    _write_config(
        optional_home,
        {"missing": _stdio_server(command="definitely-not-a-command")},
    )
    runtime = CapabilityRuntime.capture(_context(tmp_path), home=optional_home)
    try:
        assert runtime.tools == ()
        assert "Optional MCP server missing connection failed" in "\n".join(
            runtime.warnings
        )
    finally:
        runtime.close()

    required_home = tmp_path / "required"
    _write_config(
        required_home,
        {"missing": _stdio_server(command="definitely-not-a-command", required=True)},
    )
    with pytest.raises(CapabilityStartupError):
        CapabilityRuntime.capture(_context(tmp_path), home=required_home)


def test_mcp_tool_timeout_is_bounded(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_config(
        home,
        {"local": _stdio_server(enabledTools=["wait"], toolTimeoutSeconds=0.05)},
    )
    runtime = CapabilityRuntime.capture(_context(tmp_path), home=home)
    try:
        registry = runtime.registry_for_turn(SkillTurnState(runtime.snapshot.skills))
        started = time.monotonic()
        result = registry.dispatch("mcp__local__wait", {"milliseconds": 1000})
        assert time.monotonic() - started < 1
        assert result.startswith("ERROR:")
    finally:
        runtime.close()


def test_normalized_tool_collisions_skip_both_tools(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_config(home, {"local": _stdio_server()})
    runtime = CapabilityRuntime.capture(_context(tmp_path), home=home)
    try:
        names = {tool.qualified_name for tool in runtime.tools}
        assert "mcp__local__same_name" not in names
        assert any("collision" in warning for warning in runtime.warnings)
    finally:
        runtime.close()


def test_plugin_namespaces_skills_and_mcp_tools(tmp_path: Path) -> None:
    home = tmp_path / "home"
    plugin = tmp_path / "example"
    skill = plugin / "skills" / "guide"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\ndescription: Use the example tool.\n---\nCall the echo tool.\n",
        encoding="utf-8",
    )
    manifest = plugin / ".coding-kid-plugin"
    manifest.mkdir()
    (manifest / "plugin.json").write_text(
        json.dumps(
            {
                "name": "example",
                "description": "Example",
                "skills": ["skills"],
                "mcpServers": ".mcp.json",
            }
        ),
        encoding="utf-8",
    )
    (plugin / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "local": _stdio_server(enabledTools=["echo"]),
                }
            }
        ),
        encoding="utf-8",
    )
    home.mkdir()
    (home / "capabilities.json").write_text(
        json.dumps({"plugins": [{"path": str(plugin)}]}), encoding="utf-8"
    )

    runtime = CapabilityRuntime.capture(_context(tmp_path), home=home)
    try:
        assert runtime.snapshot.skills.skills[0].name == "example:guide"
        assert runtime.tools[0].qualified_name == "mcp__example__local__echo"
    finally:
        runtime.close()


def test_streamable_http_transport(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "mcp_server.py"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, str(fixture), "--http", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.05)
        home = tmp_path / "home"
        _write_config(
            home,
            {
                "remote": {
                    "transport": "streamable_http",
                    "url": f"http://127.0.0.1:{port}/mcp",
                    "enabledTools": ["echo"],
                }
            },
        )
        runtime = CapabilityRuntime.capture(_context(tmp_path), home=home)
        try:
            assert runtime.tools[0].qualified_name == "mcp__remote__echo"
            registry = runtime.registry_for_turn(
                SkillTurnState(runtime.snapshot.skills)
            )
            assert '"echo": "web"' in registry.dispatch(
                "mcp__remote__echo", {"text": "web"}
            )
        finally:
            runtime.close()
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_skill_to_mcp_to_final_answer_protocol(tmp_path: Path) -> None:
    home = tmp_path / "home"
    skill = home / "skills" / "guide"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\ndescription: Echo through MCP.\n---\nCall mcp__local__echo.\n",
        encoding="utf-8",
    )
    (home / "capabilities.json").write_text(
        json.dumps({"mcpServers": {"local": _stdio_server(enabledTools=["echo"])}}),
        encoding="utf-8",
    )
    context = _context(tmp_path)
    runtime = CapabilityRuntime.capture(context, home=home)
    manager = ContextManager(context, ContextBudget(32_768, "test"))
    manager.conversation.append_user("Use the guide")
    responses = iter(
        [
            SimpleNamespace(
                output=[_tool_call("one", "skill", {"name": "guide"})], usage=None
            ),
            SimpleNamespace(
                output=[_tool_call("two", "mcp__local__echo", {"text": "capability"})],
                usage=None,
            ),
            SimpleNamespace(output=[_text_message("Done.")], usage=None),
        ]
    )
    calls: list[tuple[list[object], list[dict[str, object]]]] = []

    def provider(
        instructions: str,
        messages: list[object],
        tools: list[dict[str, object]],
    ) -> object:
        calls.append((list(messages), tools))
        return next(responses)

    try:
        state = SkillTurnState(runtime.snapshot.skills)
        answer = run_turn(
            manager,
            provider,
            tool_registry=runtime.registry_for_turn(state),
            instruction_overlays=(runtime.skill_metadata(),),
        )
    finally:
        runtime.close()

    assert answer == "Done."
    assert "Call mcp__local__echo" in str(calls[1][0])
    assert '"echo": "capability"' in str(calls[2][0])
    assert calls[0][1] == calls[1][1] == calls[2][1]


def _tool_call(call_id: str, name: str, arguments: dict[str, object]) -> object:
    return SimpleNamespace(
        type="function_call",
        call_id=call_id,
        name=name,
        arguments=json.dumps(arguments),
    )


def _text_message(text: str) -> object:
    return SimpleNamespace(
        type="message",
        content=[SimpleNamespace(type="output_text", text=text)],
    )
