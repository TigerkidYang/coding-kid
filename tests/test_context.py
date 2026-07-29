import os
from pathlib import Path

import pytest

from coding_kid.context import (
    PROJECT_INSTRUCTIONS_MAX_BYTES,
    ProjectInstruction,
    SessionContext,
    build_instructions,
    build_model_input,
    find_project_root,
    load_project_instructions,
    render_project_instructions,
)


def make_context(
    cwd: Path,
    *,
    instructions: tuple[ProjectInstruction, ...] = (),
    truncated: bool = False,
) -> SessionContext:
    return SessionContext(
        cwd=cwd,
        operating_system="Windows 11",
        shell="cmd.exe",
        model="test/model",
        local_date="2026-07-30",
        project_root=cwd,
        project_instructions=instructions,
        project_instructions_truncated=truncated,
    )


@pytest.mark.parametrize("marker_is_file", [False, True])
def test_find_project_root_accepts_git_directory_or_file(
    tmp_path: Path,
    marker_is_file: bool,
) -> None:
    root = tmp_path / "repo"
    cwd = root / "packages" / "app"
    cwd.mkdir(parents=True)
    marker = root / ".git"
    if marker_is_file:
        marker.write_text("gitdir: elsewhere", encoding="utf-8")
    else:
        marker.mkdir()

    assert find_project_root(cwd) == root


def test_find_project_root_uses_cwd_when_no_git_marker(tmp_path: Path) -> None:
    cwd = tmp_path / "plain"
    cwd.mkdir()

    assert find_project_root(cwd) == cwd


def test_loads_agents_files_root_to_cwd_and_excludes_other_paths(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    cwd = root / "packages" / "app"
    sibling = root / "packages" / "other"
    cwd.mkdir(parents=True)
    sibling.mkdir()
    (root / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text("outside", encoding="utf-8")
    (root / "AGENTS.md").write_text("root rules", encoding="utf-8")
    (root / "packages" / "AGENTS.md").write_text("package rules", encoding="utf-8")
    (cwd / "AGENTS.md").write_text("app rules", encoding="utf-8")
    (sibling / "AGENTS.md").write_text("sibling rules", encoding="utf-8")

    loaded, truncated = load_project_instructions(root, cwd)

    assert [item.content for item in loaded] == [
        "root rules",
        "package rules",
        "app rules",
    ]
    assert [item.path for item in loaded] == [
        (root / "AGENTS.md").resolve(),
        (root / "packages" / "AGENTS.md").resolve(),
        (cwd / "AGENTS.md").resolve(),
    ]
    assert truncated is False


def test_empty_and_missing_agents_files_are_ignored(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    (cwd / "AGENTS.md").write_text(" \n", encoding="utf-8")

    loaded, truncated = load_project_instructions(cwd, cwd)

    assert loaded == ()
    assert truncated is False


def test_project_instruction_budget_is_shared_and_visible(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    cwd = root / "nested"
    cwd.mkdir(parents=True)
    (root / "AGENTS.md").write_bytes(b"a" * (PROJECT_INSTRUCTIONS_MAX_BYTES - 2))
    (cwd / "AGENTS.md").write_bytes(b"bcdef")

    loaded, truncated = load_project_instructions(root, cwd)
    context = make_context(cwd, instructions=loaded, truncated=truncated)
    rendered = render_project_instructions(context)

    assert sum(len(item.content.encode("utf-8")) for item in loaded) == (
        PROJECT_INSTRUCTIONS_MAX_BYTES
    )
    assert loaded[-1].content == "bc"
    assert loaded[-1].truncated is True
    assert truncated is True
    assert rendered is not None
    assert "Truncated" in rendered


def test_later_file_omission_is_visible_when_budget_ends_exactly(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    cwd = root / "nested"
    cwd.mkdir(parents=True)
    (root / "AGENTS.md").write_bytes(b"a" * PROJECT_INSTRUCTIONS_MAX_BYTES)
    (cwd / "AGENTS.md").write_text("later", encoding="utf-8")

    loaded, truncated = load_project_instructions(root, cwd)
    rendered = render_project_instructions(
        make_context(cwd, instructions=loaded, truncated=truncated)
    )

    assert len(loaded) == 1
    assert truncated is True
    assert rendered is not None
    assert "Additional AGENTS.md content was omitted" in rendered


def test_invalid_utf8_uses_replacement_decoding(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    (cwd / "AGENTS.md").write_bytes(b"before\xffafter")

    loaded, _ = load_project_instructions(cwd, cwd)

    assert loaded[0].content == "before\ufffdafter"


def test_non_not_found_read_error_names_the_instruction_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    path = cwd / "AGENTS.md"
    path.write_text("rules", encoding="utf-8")
    original_read_bytes = Path.read_bytes

    def fail_read(candidate: Path) -> bytes:
        if candidate == path:
            raise PermissionError("denied")
        return original_read_bytes(candidate)

    monkeypatch.setattr(Path, "read_bytes", fail_read)

    with pytest.raises(RuntimeError, match="AGENTS.md"):
        load_project_instructions(cwd, cwd)


def test_session_capture_is_a_snapshot(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    path = cwd / "AGENTS.md"
    path.write_text("first", encoding="utf-8")

    first = SessionContext.capture(cwd)
    path.write_text("second", encoding="utf-8")
    second = SessionContext.capture(cwd)

    assert first.project_instructions[0].content == "first"
    assert second.project_instructions[0].content == "second"


def test_build_instructions_keeps_dynamic_suffixes_after_stable_context(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)

    rendered = build_instructions(
        context,
        [{"content": "Implement", "status": "in_progress"}],
        ["Recovery instruction: answer now."],
    )

    assert rendered.index("Runtime environment:") < rendered.index("Current todos:")
    assert rendered.index("Current todos:") < rendered.index("Recovery instruction:")
    assert str(tmp_path) in rendered
    assert "test/model" in rendered


def test_build_model_input_does_not_mutate_history(tmp_path: Path) -> None:
    instruction = ProjectInstruction(tmp_path / "AGENTS.md", "Use pytest.")
    context = make_context(tmp_path, instructions=(instruction,))
    messages = [{"role": "user", "content": "Fix it"}]

    first = build_model_input(context, messages)
    second = build_model_input(context, messages)

    assert messages == [{"role": "user", "content": "Fix it"}]
    assert len(first) == len(second) == 2
    assert first[0]["role"] == "user"
    assert "Use pytest." in first[0]["content"]
    assert first[1] is messages[0]


def test_session_context_captures_model_without_exposing_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_MODEL", "example/model")
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")

    context = SessionContext.capture(tmp_path)
    rendered = build_instructions(context, [])

    assert context.model == "example/model"
    assert "secret" not in rendered
    assert os.getenv("OPENROUTER_API_KEY") == "secret"
