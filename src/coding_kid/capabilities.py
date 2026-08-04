"""Session-scoped Skills, Plugins, and MCP lifecycle management."""

from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
import json
from pathlib import Path
import re
import threading
from typing import Any

import httpx2
from mcp import Client, StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

from coding_kid.capability_config import (
    CapabilityConfigError,
    MCPServerConfig,
    load_capability_config,
    parse_mcp_servers,
)
from coding_kid.context import SessionContext
from coding_kid.context_manager import estimate_tokens, normalize_protocol_value
from coding_kid.events import CancellationToken
from coding_kid.plugins import Plugin, load_plugins
from coding_kid.skills import SkillCatalog, SkillTurnState, discover_skills
from coding_kid.tools import DEFAULT_TOOL_REGISTRY, ToolEntry, ToolRegistry

MAX_MCP_TOOLS = 64
MAX_MCP_DESCRIPTION = 1024
DEFAULT_TOOL_DEFINITION_CHAR_BUDGET = 8_000
TOOL_DEFINITION_WINDOW_PERCENT = 10
TOOL_COMPONENT = re.compile(r"[^A-Za-z0-9_-]")


class CapabilityStartupError(RuntimeError):
    """Raised when configuration or a required capability cannot start."""


@dataclass(frozen=True)
class MCPTool:
    qualified_name: str
    server_key: str
    remote_name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class MCPServerStatus:
    name: str
    state: str
    tool_count: int = 0
    detail: str = ""


@dataclass(frozen=True)
class CapabilitySnapshot:
    plugins: tuple[Plugin, ...]
    skills: SkillCatalog
    servers: tuple[MCPServerConfig, ...]
    warnings: tuple[str, ...]


class CapabilityRuntime:
    """Own one immutable discovery snapshot and live MCP clients for a session."""

    def __init__(
        self,
        snapshot: CapabilitySnapshot,
        *,
        context_window: int | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.context_window = context_window
        self._warnings = list(snapshot.warnings)
        self._statuses: list[MCPServerStatus] = []
        self._clients: dict[str, Client] = {}
        self._http_clients: dict[str, httpx2.AsyncClient] = {}
        self._configs = {
            server.qualified_server_name: server for server in snapshot.servers
        }
        self._tools: tuple[MCPTool, ...] = ()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="coding-kid-mcp",
            daemon=True,
        )
        self._closed = False
        self._thread.start()
        try:
            self._submit(self._start(), timeout=self._startup_wait())
        except BaseException:
            self.close()
            raise

    @classmethod
    def capture(
        cls,
        context: SessionContext,
        *,
        context_window: int | None = None,
        home: Path | None = None,
    ) -> CapabilityRuntime:
        config = load_capability_config(home)
        outcome = load_plugins(config.plugins)
        warnings = list(outcome.warnings)
        servers = list(config.mcp_servers)
        for plugin in outcome.plugins:
            if plugin.mcp_config is None:
                continue
            try:
                servers.extend(_load_plugin_servers(plugin))
            except (OSError, json.JSONDecodeError, CapabilityConfigError) as error:
                warnings.append(
                    f"Plugin {plugin.name} MCP configuration was skipped: "
                    f"{type(error).__name__}"
                )
        identities = [
            server.qualified_server_name for server in servers if server.enabled
        ]
        if len(identities) != len(set(identities)):
            raise CapabilityStartupError("Duplicate enabled MCP server identity")
        skills = discover_skills(context, home=home, plugins=outcome.plugins)
        warnings.extend(skills.warnings)
        snapshot = CapabilitySnapshot(
            outcome.plugins,
            skills,
            tuple(servers),
            tuple(warnings),
        )
        return cls(snapshot, context_window=context_window)

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(self._warnings)

    @property
    def statuses(self) -> tuple[MCPServerStatus, ...]:
        return tuple(self._statuses)

    @property
    def tools(self) -> tuple[MCPTool, ...]:
        return self._tools

    def skill_metadata(self) -> str:
        return self.snapshot.skills.render(self.context_window)

    def registry_for_turn(
        self,
        skill_state: SkillTurnState,
        cancellation_token: CancellationToken | None = None,
    ) -> ToolRegistry:
        registry = DEFAULT_TOOL_REGISTRY.with_tool(
            "skill",
            {
                "description": (
                    "Load the complete instructions for one available Skill. "
                    "Call this before following a matching Skill."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string", "minLength": 1}},
                    "required": ["name"],
                    "additionalProperties": False,
                },
                "function": skill_state.load,
            },
        )
        for tool in self._tools:
            entry: ToolEntry = {
                "description": tool.description,
                "parameters": tool.parameters,
                "strict": False,
                "function": self._tool_function(tool, cancellation_token),
            }
            registry = registry.with_tool(tool.qualified_name, entry)
        return registry

    def summary(self) -> str:
        connected = sum(status.state == "connected" for status in self._statuses)
        return (
            f"Capabilities: {len(self.snapshot.skills.skills)} Skills, "
            f"{len(self.snapshot.plugins)} Plugins, "
            f"{connected}/{len(self._statuses)} MCP servers, "
            f"{len(self._tools)} MCP tools"
        )

    def status_text(self) -> str:
        lines = [self.summary()]
        if self.snapshot.plugins:
            lines.append(
                "Plugins: " + ", ".join(plugin.name for plugin in self.snapshot.plugins)
            )
        if self.snapshot.skills.skills:
            lines.append(
                "Skills: "
                + ", ".join(skill.name for skill in self.snapshot.skills.skills)
            )
        for status in self._statuses:
            suffix = f" ({status.detail})" if status.detail else ""
            lines.append(
                f"MCP {status.name}: {status.state}, {status.tool_count} tools{suffix}"
            )
        lines.extend(f"Warning: {warning}" for warning in self._warnings)
        return "\n".join(lines)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._thread.is_alive():
            try:
                self._submit(self._close_clients(), timeout=10)
            except Exception:  # Shutdown remains best-effort.
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=10)
        if not self._loop.is_closed():
            self._loop.close()

    def __enter__(self) -> CapabilityRuntime:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _startup_wait(self) -> float:
        enabled = [
            server.startup_timeout for server in self.snapshot.servers if server.enabled
        ]
        return (max(enabled) if enabled else 1) + 5

    def _submit(self, coroutine: Any, *, timeout: float) -> Any:
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout=timeout)
        except BaseException:
            future.cancel()
            raise

    async def _start(self) -> None:
        configs = [server for server in self.snapshot.servers if server.enabled]
        results = await asyncio.gather(
            *(self._connect_server(server) for server in configs),
            return_exceptions=True,
        )
        discovered: list[MCPTool] = []
        required_failure = False
        for config, result in zip(configs, results, strict=True):
            if isinstance(result, BaseException):
                detail = f"connection failed ({type(result).__name__})"
                self._statuses.append(
                    MCPServerStatus(
                        config.qualified_server_name, "failed", detail=detail
                    )
                )
                if config.required:
                    required_failure = True
                else:
                    self._warnings.append(
                        f"Optional MCP server {config.qualified_server_name} {detail}"
                    )
            else:
                discovered.extend(result)
                self._statuses.append(
                    MCPServerStatus(
                        config.qualified_server_name,
                        "connected",
                        len(result),
                    )
                )
        if required_failure:
            await self._close_clients()
            raise CapabilityStartupError("One or more required MCP servers failed")
        self._tools = self._select_tools(discovered)

    async def _connect_server(self, config: MCPServerConfig) -> list[MCPTool]:
        async with asyncio.timeout(config.startup_timeout):
            if config.transport == "stdio":
                parameters = StdioServerParameters(
                    command=config.command or "",
                    args=list(config.args),
                    env=dict(config.env),
                    cwd=config.cwd,
                    encoding_error_handler="replace",
                )
                transport = stdio_client(parameters)
            else:
                headers = dict(config.headers) | dict(config.env_headers)
                http_client = httpx2.AsyncClient(headers=headers, follow_redirects=True)
                self._http_clients[config.qualified_server_name] = http_client
                transport = streamable_http_client(
                    config.url or "",
                    http_client=http_client,
                )
            client = Client(transport, read_timeout_seconds=config.tool_timeout)
            await client.__aenter__()
            self._clients[config.qualified_server_name] = client
            try:
                return await self._list_tools(config, client)
            except BaseException:
                self._clients.pop(config.qualified_server_name, None)
                await client.__aexit__(None, None, None)
                if config.transport == "streamable_http":
                    self._http_clients.pop(config.qualified_server_name, None)
                    await http_client.aclose()
                raise

    async def _list_tools(
        self, config: MCPServerConfig, client: Client
    ) -> list[MCPTool]:
        tools: list[MCPTool] = []
        cursor: str | None = None
        while True:
            result = await client.list_tools(cursor=cursor)
            for remote in result.tools:
                if (
                    config.enabled_tools is not None
                    and remote.name not in config.enabled_tools
                ):
                    continue
                if remote.name in config.disabled_tools:
                    continue
                component = _normalize_component(remote.name)
                prefix = "mcp__"
                if config.plugin_name:
                    prefix += f"{_normalize_component(config.plugin_name)}__"
                qualified = f"{prefix}{_normalize_component(config.name)}__{component}"
                schema = remote.input_schema
                if not isinstance(schema, dict) or schema.get("type") != "object":
                    self._warnings.append(
                        f"MCP tool {qualified} skipped: input schema is not an object"
                    )
                    continue
                tools.append(
                    MCPTool(
                        qualified,
                        config.qualified_server_name,
                        remote.name,
                        (remote.description or remote.title or remote.name)[
                            :MAX_MCP_DESCRIPTION
                        ],
                        schema,
                    )
                )
            cursor = result.next_cursor
            if not cursor:
                break
        return tools

    def _select_tools(self, tools: list[MCPTool]) -> tuple[MCPTool, ...]:
        grouped: dict[str, list[MCPTool]] = {}
        for tool in tools:
            grouped.setdefault(tool.qualified_name, []).append(tool)
        unique: list[MCPTool] = []
        for name, matches in grouped.items():
            if len(matches) > 1:
                self._warnings.append(
                    f"MCP tool name collision after normalization; skipped all: {name}"
                )
            else:
                unique.append(matches[0])
        selected: list[MCPTool] = []
        omitted = 0
        token_budget = (
            max(1, self.context_window * TOOL_DEFINITION_WINDOW_PERCENT // 100)
            if self.context_window
            else None
        )
        for tool in sorted(unique, key=lambda item: item.qualified_name):
            definition = _tool_definition(tool)
            candidate = [_tool_definition(item) for item in selected] + [definition]
            within_budget = (
                estimate_tokens(candidate) <= token_budget
                if token_budget is not None
                else len(json.dumps(candidate, ensure_ascii=False))
                <= DEFAULT_TOOL_DEFINITION_CHAR_BUDGET
            )
            if len(selected) < MAX_MCP_TOOLS and within_budget:
                selected.append(tool)
            else:
                omitted += 1
        if omitted:
            self._warnings.append(
                f"{omitted} MCP tool(s) omitted by count or context budget; use enabledTools allowlists"
            )
        return tuple(selected)

    def _tool_function(
        self,
        tool: MCPTool,
        cancellation_token: CancellationToken | None,
    ) -> Any:
        def invoke(**arguments: Any) -> str:
            config = self._configs[tool.server_key]
            future = asyncio.run_coroutine_threadsafe(
                self._call_tool(tool, arguments), self._loop
            )
            try:
                while True:
                    if cancellation_token is not None and cancellation_token.cancelled:
                        future.cancel()
                        return "ERROR: MCP tool call cancelled"
                    try:
                        result = future.result(timeout=min(0.05, config.tool_timeout))
                        return _normalize_tool_result(result)
                    except FutureTimeoutError:
                        if future.done():
                            return _normalize_tool_result(future.result())
            except BaseException:
                future.cancel()
                raise

        return invoke

    async def _call_tool(self, tool: MCPTool, arguments: dict[str, Any]) -> Any:
        config = self._configs[tool.server_key]
        client = self._clients[tool.server_key]
        async with asyncio.timeout(config.tool_timeout):
            return await client.call_tool(tool.remote_name, arguments)

    async def _close_clients(self) -> None:
        clients = list(self._clients.items())
        self._clients.clear()
        for _, client in reversed(clients):
            try:
                await client.__aexit__(None, None, None)
            except Exception:
                pass
        http_clients = list(self._http_clients.values())
        self._http_clients.clear()
        for client in http_clients:
            try:
                await client.aclose()
            except Exception:
                pass


def _load_plugin_servers(plugin: Plugin) -> tuple[MCPServerConfig, ...]:
    assert plugin.mcp_config is not None
    value = json.loads(plugin.mcp_config.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CapabilityConfigError("Plugin MCP config must be an object")
    raw = value.get("mcpServers", value)
    if not isinstance(raw, dict):
        raise CapabilityConfigError("Plugin mcpServers must be an object")
    return parse_mcp_servers(raw, base_path=plugin.root, plugin_name=plugin.name)


def _normalize_component(value: str) -> str:
    return TOOL_COMPONENT.sub("_", value)


def _tool_definition(tool: MCPTool) -> dict[str, Any]:
    return {
        "type": "function",
        "name": tool.qualified_name,
        "description": tool.description,
        "parameters": tool.parameters,
        "strict": False,
    }


def _normalize_tool_result(result: Any) -> str:
    payload: dict[str, Any] = {
        "content": [normalize_protocol_value(item) for item in result.content]
    }
    if result.structured_content is not None:
        payload["structuredContent"] = normalize_protocol_value(
            result.structured_content
        )
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return f"ERROR: {rendered}" if result.is_error else rendered
