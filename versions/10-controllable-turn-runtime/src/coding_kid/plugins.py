"""Resolve explicitly enabled local Plugin packages without activating them."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from coding_kid.capability_config import PluginConfigEntry

PLUGIN_MANIFEST = Path(".coding-kid-plugin") / "plugin.json"
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class PluginLoadError(RuntimeError):
    """Raised when enabled Plugin identities are ambiguous."""


@dataclass(frozen=True)
class Plugin:
    name: str
    version: str | None
    description: str
    root: Path
    skill_roots: tuple[Path, ...]
    mcp_config: Path | None


@dataclass(frozen=True)
class PluginLoadOutcome:
    plugins: tuple[Plugin, ...]
    warnings: tuple[str, ...]


def load_plugins(entries: tuple[PluginConfigEntry, ...]) -> PluginLoadOutcome:
    """Load enabled manifests; malformed packages are reported and skipped."""
    plugins: list[Plugin] = []
    warnings: list[str] = []
    seen_names: set[str] = set()
    for entry in entries:
        if not entry.enabled:
            continue
        try:
            plugin = _load_plugin(entry.path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            warnings.append(f"Plugin {entry.path} was skipped: {error}")
            continue
        if plugin.name in seen_names:
            raise PluginLoadError(f"Duplicate enabled Plugin name: {plugin.name}")
        seen_names.add(plugin.name)
        plugins.append(plugin)
    return PluginLoadOutcome(tuple(plugins), tuple(warnings))


def _load_plugin(root: Path) -> Plugin:
    resolved_root = root.resolve(strict=True)
    if not resolved_root.is_dir():
        raise ValueError("Plugin root is not a directory")
    manifest_path = _contained(resolved_root, resolved_root / PLUGIN_MANIFEST)
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("plugin.json must contain an object")
    allowed = {"name", "version", "description", "skills", "mcpServers"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"unknown manifest field(s): {', '.join(unknown)}")

    name = value.get("name")
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        raise ValueError("Plugin name must match [A-Za-z0-9_-]{1,64}")
    version = value.get("version")
    if version is not None and (not isinstance(version, str) or len(version) > 64):
        raise ValueError("Plugin version must be a string of at most 64 characters")
    description = value.get("description", "")
    if not isinstance(description, str) or len(description) > 1024:
        raise ValueError("Plugin description must be at most 1024 characters")

    raw_skills = value.get("skills", [])
    if not isinstance(raw_skills, list) or not all(
        isinstance(item, str) and item for item in raw_skills
    ):
        raise ValueError("Plugin skills must be an array of relative paths")
    skill_roots: list[Path] = []
    for relative in raw_skills:
        path = _contained(resolved_root, resolved_root / relative)
        if not path.is_dir():
            raise ValueError(f"Plugin Skill root is not a directory: {relative}")
        skill_roots.append(path)

    raw_mcp = value.get("mcpServers")
    mcp_config: Path | None = None
    if raw_mcp is not None:
        if not isinstance(raw_mcp, str) or not raw_mcp:
            raise ValueError("Plugin mcpServers must be a relative JSON path")
        mcp_config = _contained(resolved_root, resolved_root / raw_mcp)
        if not mcp_config.is_file():
            raise ValueError(f"Plugin MCP config is not a file: {raw_mcp}")

    return Plugin(
        name,
        version,
        " ".join(description.split()),
        resolved_root,
        tuple(skill_roots),
        mcp_config,
    )


def _contained(root: Path, candidate: Path) -> Path:
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as error:
        raise ValueError(f"Plugin path does not exist: {candidate}") from error
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"Plugin path escapes its root: {candidate}") from error
    return resolved
