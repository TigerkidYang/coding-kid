from __future__ import annotations

import json
from pathlib import Path

import pytest

from coding_kid.capability_config import PluginConfigEntry
from coding_kid.plugins import PluginLoadError, load_plugins


def write_plugin(
    root: Path,
    name: str,
    *,
    skills: list[str] | None = None,
    mcp_servers: str | None = None,
) -> None:
    (root / ".coding-kid-plugin").mkdir(parents=True)
    manifest: dict[str, object] = {
        "name": name,
        "version": "1.0.0",
        "description": "  Example   capability  ",
        "skills": skills or [],
    }
    if mcp_servers is not None:
        manifest["mcpServers"] = mcp_servers
    (root / ".coding-kid-plugin" / "plugin.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )


def test_loads_enabled_plugin_components(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    write_plugin(root, "demo", skills=["skills"], mcp_servers=".mcp.json")
    (root / "skills").mkdir()
    (root / ".mcp.json").write_text("{}", encoding="utf-8")

    outcome = load_plugins((PluginConfigEntry(root),))

    plugin = outcome.plugins[0]
    assert plugin.name == "demo"
    assert plugin.description == "Example capability"
    assert plugin.skill_roots == ((root / "skills").resolve(),)
    assert plugin.mcp_config == (root / ".mcp.json").resolve()


def test_disabled_and_malformed_plugins_do_not_activate(tmp_path: Path) -> None:
    disabled = tmp_path / "disabled"
    broken = tmp_path / "broken"
    write_plugin(disabled, "disabled")
    broken.mkdir()

    outcome = load_plugins(
        (PluginConfigEntry(disabled, False), PluginConfigEntry(broken))
    )

    assert outcome.plugins == ()
    assert len(outcome.warnings) == 1


def test_plugin_component_cannot_escape_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "demo"
    write_plugin(root, "demo", skills=["../outside"])

    outcome = load_plugins((PluginConfigEntry(root),))

    assert outcome.plugins == ()
    assert "escapes its root" in outcome.warnings[0]


def test_duplicate_enabled_plugin_names_are_fatal(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_plugin(first, "same")
    write_plugin(second, "same")

    with pytest.raises(PluginLoadError, match="Duplicate"):
        load_plugins((PluginConfigEntry(first), PluginConfigEntry(second)))
