from pathlib import Path

from coding_kid.tools import TOOLS, dispatch_tool


def test_write_and_read_file(tmp_path: Path) -> None:
    path = tmp_path / "notes" / "lesson.txt"

    write_result = dispatch_tool(
        "write", {"path": str(path), "content": "first lesson"}
    )
    read_result = dispatch_tool("read", {"path": str(path)})

    assert write_result == f"Wrote {path}"
    assert read_result == "first lesson"


def test_patch_replaces_one_exact_text_fragment(tmp_path: Path) -> None:
    path = tmp_path / "example.py"
    path.write_text("answer = 41\n", encoding="utf-8")

    result = dispatch_tool(
        "patch",
        {"path": str(path), "old_text": "41", "new_text": "42"},
    )

    assert result == f"Patched {path}"
    assert path.read_text(encoding="utf-8") == "answer = 42\n"


def test_patch_rejects_missing_or_ambiguous_text(tmp_path: Path) -> None:
    path = tmp_path / "example.txt"
    path.write_text("same same", encoding="utf-8")

    missing = dispatch_tool(
        "patch",
        {"path": str(path), "old_text": "absent", "new_text": "new"},
    )
    ambiguous = dispatch_tool(
        "patch",
        {"path": str(path), "old_text": "same", "new_text": "new"},
    )

    assert missing.startswith("ERROR:")
    assert "not found" in missing
    assert ambiguous.startswith("ERROR:")
    assert "2 times" in ambiguous


def test_search_finds_file_names_and_text(tmp_path: Path) -> None:
    (tmp_path / "needle_name.py").write_text("nothing here\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("a needle in text\n", encoding="utf-8")

    result = dispatch_tool("search", {"query": "needle", "path": str(tmp_path)})

    assert "FILE needle_name.py" in result
    assert "TEXT other.py:1:a needle in text" in result


def test_delete_removes_file(tmp_path: Path) -> None:
    path = tmp_path / "temporary.txt"
    path.write_text("temporary", encoding="utf-8")

    result = dispatch_tool("delete", {"path": str(path)})

    assert result == f"Deleted {path}"
    assert not path.exists()


def test_execute_returns_exit_code_stdout_and_stderr() -> None:
    command = (
        "python -c \"import sys; print('hello'); "
        "print('problem', file=sys.stderr); sys.exit(3)\""
    )

    result = dispatch_tool("execute", {"command": command})

    assert "exit_code: 3" in result
    assert "stdout:\nhello" in result
    assert "stderr:\nproblem" in result


def test_unknown_tool_and_bad_arguments_become_errors() -> None:
    assert dispatch_tool("missing", {}).startswith("ERROR: Unknown tool")
    assert dispatch_tool("read", {}).startswith("ERROR:")


def test_every_tool_has_model_visible_metadata() -> None:
    assert set(TOOLS) == {"execute", "read", "write", "search", "patch", "delete"}
    for name, tool in TOOLS.items():
        assert tool["description"]
        assert tool["parameters"]["type"] == "object"
        assert callable(tool["function"]), name
