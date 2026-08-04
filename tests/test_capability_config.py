from __future__ import annotations

import json
from pathlib import Path

import pytest

from coding_kid.capability_config import (
    CapabilityConfigError,
    load_capability_config,
)


def test_missing_capability_config_is_empty(tmp_path: Path) -> None:
    config = load_capability_config(tmp_path)

    assert config.plugins == ()
    assert config.mcp_servers == ()
    assert config.path == tmp_path / "capabilities.json"


def test_loads_plugins_and_mcp_server_objects(tmp_path: Path) -> None:
    plugin = tmp_path / "relative-plugin"
    (tmp_path / "capabilities.json").write_text(
        json.dumps(
            {
                "plugins": [{"path": "relative-plugin"}],
                "mcpServers": {
                    "demo": {
                        "transport": "stdio",
                        "command": "python",
                        "args": ["server.py"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    config = load_capability_config(tmp_path)

    assert config.plugins[0].path == plugin.resolve()
    assert config.plugins[0].enabled is True
    assert config.mcp_servers[0].name == "demo"
    assert config.mcp_servers[0].command == "python"
    assert config.mcp_servers[0].args == ("server.py",)


def test_resolves_only_complete_environment_references(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_TOKEN", "secret-value")
    (tmp_path / "capabilities.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "demo": {
                        "transport": "stdio",
                        "command": "python",
                        "env": {"TOKEN": "${DEMO_TOKEN}"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    config = load_capability_config(tmp_path)

    assert config.mcp_servers[0].env == (("TOKEN", "secret-value"),)
    assert "secret-value" not in repr(config.path)


@pytest.mark.parametrize("reference", ["DEMO_TOKEN", "prefix-${DEMO_TOKEN}"])
def test_rejects_non_exact_environment_references(
    tmp_path: Path, reference: str
) -> None:
    (tmp_path / "capabilities.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "demo": {
                        "transport": "stdio",
                        "command": "python",
                        "env": {"TOKEN": reference},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CapabilityConfigError):
        load_capability_config(tmp_path)


@pytest.mark.parametrize(
    "value",
    [
        [],
        {"unknown": True},
        {"plugins": {}},
        {"plugins": [{"path": "x", "extra": True}]},
        {"mcpServers": []},
        {"mcpServers": {"demo": []}},
    ],
)
def test_invalid_capability_config_is_fatal(tmp_path: Path, value: object) -> None:
    (tmp_path / "capabilities.json").write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(CapabilityConfigError):
        load_capability_config(tmp_path)
