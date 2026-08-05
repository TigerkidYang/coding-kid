"""Load the user-owned configuration that may start external capabilities."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CAPABILITIES_FILENAME = "capabilities.json"


class CapabilityConfigError(RuntimeError):
    """Raised when executable capability configuration is ambiguous or invalid."""


@dataclass(frozen=True)
class PluginConfigEntry:
    path: Path
    enabled: bool = True


@dataclass(frozen=True)
class CapabilityConfig:
    path: Path
    plugins: tuple[PluginConfigEntry, ...]
    mcp_servers: tuple[MCPServerConfig, ...]


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    transport: str
    enabled: bool = True
    required: bool = False
    command: str | None = None
    args: tuple[str, ...] = ()
    cwd: Path | None = None
    env: tuple[tuple[str, str], ...] = field(default=(), repr=False)
    url: str | None = None
    headers: tuple[tuple[str, str], ...] = ()
    env_headers: tuple[tuple[str, str], ...] = field(default=(), repr=False)
    startup_timeout: float = 10.0
    tool_timeout: float = 120.0
    enabled_tools: tuple[str, ...] | None = None
    disabled_tools: tuple[str, ...] = ()
    plugin_name: str | None = None

    @property
    def qualified_server_name(self) -> str:
        return f"{self.plugin_name}__{self.name}" if self.plugin_name else self.name


ENV_REFERENCE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
SERVER_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def coding_kid_home() -> Path:
    """Return the shared Coding Kid state/configuration directory."""
    configured = os.getenv("CODING_KID_HOME")
    return (
        Path(configured).expanduser().resolve()
        if configured
        else (Path.home() / ".coding-kid").resolve()
    )


def load_capability_config(home: Path | None = None) -> CapabilityConfig:
    """Read and strictly validate capabilities.json without starting anything."""
    root = (home or coding_kid_home()).resolve()
    path = root / CAPABILITIES_FILENAME
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return CapabilityConfig(path, (), ())
    except OSError as error:
        raise CapabilityConfigError(f"Could not read {path}: {error}") from error

    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise CapabilityConfigError(f"Invalid JSON in {path}: {error}") from error
    if not isinstance(value, dict):
        raise CapabilityConfigError(f"{path} must contain a JSON object")
    _reject_unknown(value, {"plugins", "mcpServers"}, "capability config")

    raw_plugins = value.get("plugins", [])
    if not isinstance(raw_plugins, list):
        raise CapabilityConfigError("plugins must be an array")
    plugins: list[PluginConfigEntry] = []
    for index, raw in enumerate(raw_plugins):
        if not isinstance(raw, dict):
            raise CapabilityConfigError(f"plugins[{index}] must be an object")
        _reject_unknown(raw, {"path", "enabled"}, f"plugins[{index}]")
        raw_path = raw.get("path")
        enabled = raw.get("enabled", True)
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise CapabilityConfigError(f"plugins[{index}].path must be a string")
        if not isinstance(enabled, bool):
            raise CapabilityConfigError(f"plugins[{index}].enabled must be boolean")
        plugin_path = Path(raw_path).expanduser()
        if not plugin_path.is_absolute():
            plugin_path = path.parent / plugin_path
        plugins.append(PluginConfigEntry(plugin_path.resolve(), enabled))

    raw_servers = value.get("mcpServers", {})
    if not isinstance(raw_servers, dict):
        raise CapabilityConfigError("mcpServers must be an object")
    servers = parse_mcp_servers(raw_servers, base_path=path.parent)
    return CapabilityConfig(path, tuple(plugins), servers)


def parse_mcp_servers(
    value: dict[str, Any],
    *,
    base_path: Path,
    plugin_name: str | None = None,
) -> tuple[MCPServerConfig, ...]:
    """Strictly parse server declarations and resolve safe environment references."""
    servers: list[MCPServerConfig] = []
    for name, raw in value.items():
        label = f"MCP server {name!r}"
        if not isinstance(name, str) or not SERVER_NAME.fullmatch(name):
            raise CapabilityConfigError(
                "MCP server names must match [A-Za-z0-9_-]{1,64}"
            )
        if not isinstance(raw, dict):
            raise CapabilityConfigError(f"{label} must be an object")
        allowed = {
            "transport",
            "command",
            "args",
            "cwd",
            "env",
            "url",
            "headers",
            "envHeaders",
            "enabled",
            "required",
            "startupTimeoutSeconds",
            "toolTimeoutSeconds",
            "enabledTools",
            "disabledTools",
        }
        _reject_unknown(raw, allowed, label)
        transport = raw.get("transport")
        if transport not in {"stdio", "streamable_http"}:
            raise CapabilityConfigError(
                f"{label}.transport must be stdio or streamable_http"
            )
        enabled = _boolean(raw, "enabled", True, label)
        required = _boolean(raw, "required", False, label)
        startup = _positive_number(raw, "startupTimeoutSeconds", 10, label)
        tool_timeout = _positive_number(raw, "toolTimeoutSeconds", 120, label)
        enabled_tools = _string_list(raw, "enabledTools", label, optional=True)
        disabled_tools = _string_list(raw, "disabledTools", label) or ()
        command: str | None = None
        args: tuple[str, ...] = ()
        cwd: Path | None = None
        env: tuple[tuple[str, str], ...] = ()
        url: str | None = None
        headers: tuple[tuple[str, str], ...] = ()
        env_headers: tuple[tuple[str, str], ...] = ()
        if transport == "stdio":
            command = _nonempty_string(raw.get("command"), f"{label}.command")
            args = _string_list(raw, "args", label) or ()
            raw_cwd = raw.get("cwd")
            if raw_cwd is not None:
                cwd_text = _nonempty_string(raw_cwd, f"{label}.cwd")
                cwd = Path(cwd_text).expanduser()
                if not cwd.is_absolute():
                    cwd = base_path / cwd
                cwd = cwd.resolve()
            env = _environment_map(raw.get("env", {}), f"{label}.env")
            if "url" in raw or "headers" in raw or "envHeaders" in raw:
                raise CapabilityConfigError(f"{label} mixes HTTP fields with stdio")
        else:
            url = _nonempty_string(raw.get("url"), f"{label}.url")
            headers = _literal_map(raw.get("headers", {}), f"{label}.headers")
            env_headers = _environment_headers(
                raw.get("envHeaders", {}), f"{label}.envHeaders"
            )
            if any(key in raw for key in ("command", "args", "cwd", "env")):
                raise CapabilityConfigError(f"{label} mixes stdio fields with HTTP")
        servers.append(
            MCPServerConfig(
                name=name,
                transport=transport,
                enabled=enabled,
                required=required,
                command=command,
                args=args,
                cwd=cwd,
                env=env,
                url=url,
                headers=headers,
                env_headers=env_headers,
                startup_timeout=startup,
                tool_timeout=tool_timeout,
                enabled_tools=enabled_tools,
                disabled_tools=disabled_tools,
                plugin_name=plugin_name,
            )
        )
    return tuple(servers)


def _boolean(value: dict[str, Any], key: str, default: bool, label: str) -> bool:
    result = value.get(key, default)
    if not isinstance(result, bool):
        raise CapabilityConfigError(f"{label}.{key} must be boolean")
    return result


def _positive_number(
    value: dict[str, Any], key: str, default: float, label: str
) -> float:
    result = value.get(key, default)
    if isinstance(result, bool) or not isinstance(result, (int, float)) or result <= 0:
        raise CapabilityConfigError(f"{label}.{key} must be a positive number")
    return float(result)


def _string_list(
    value: dict[str, Any], key: str, label: str, *, optional: bool = False
) -> tuple[str, ...] | None:
    if key not in value and optional:
        return None
    result = value.get(key, [])
    if not isinstance(result, list) or not all(
        isinstance(item, str) and item for item in result
    ):
        raise CapabilityConfigError(f"{label}.{key} must be an array of strings")
    return tuple(result)


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CapabilityConfigError(f"{label} must be a non-empty string")
    return value


def _literal_map(value: Any, label: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and key and isinstance(item, str)
        for key, item in value.items()
    ):
        raise CapabilityConfigError(f"{label} must be an object of strings")
    return tuple(value.items())


def _environment_map(value: Any, label: str) -> tuple[tuple[str, str], ...]:
    pairs = _literal_map(value, label)
    resolved: list[tuple[str, str]] = []
    for key, reference in pairs:
        match = ENV_REFERENCE.fullmatch(reference)
        if match is None:
            raise CapabilityConfigError(
                f"{label}.{key} must be a complete ${{ENV_NAME}} reference"
            )
        env_name = match.group(1)
        if env_name not in os.environ:
            raise CapabilityConfigError(
                f"{label}.{key} references missing environment variable {env_name}"
            )
        resolved.append((key, os.environ[env_name]))
    return tuple(resolved)


def _environment_headers(value: Any, label: str) -> tuple[tuple[str, str], ...]:
    pairs = _literal_map(value, label)
    resolved: list[tuple[str, str]] = []
    for header, env_name in pairs:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env_name):
            raise CapabilityConfigError(
                f"{label}.{header} must name an environment variable"
            )
        if env_name not in os.environ:
            raise CapabilityConfigError(
                f"{label}.{header} references missing environment variable {env_name}"
            )
        resolved.append((header, os.environ[env_name]))
    return tuple(resolved)


def _reject_unknown(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise CapabilityConfigError(f"Unknown {label} field(s): {', '.join(unknown)}")
