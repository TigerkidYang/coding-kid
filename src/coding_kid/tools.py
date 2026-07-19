"""The small set of local tools available to the model."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

ToolFunction = Callable[..., str]
ToolEntry = dict[str, Any]


def execute(command: str) -> str:
    """Run one foreground shell command and return all useful output."""
    completed = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    stdout = completed.stdout.rstrip()
    stderr = completed.stderr.rstrip()
    return f"exit_code: {completed.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"


def read(path: str) -> str:
    """Read a UTF-8 text file."""
    return Path(path).read_text(encoding="utf-8")


def write(path: str, content: str) -> str:
    """Create or completely overwrite a UTF-8 text file."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return f"Wrote {file_path}"


def search(query: str, path: str = ".") -> str:
    """Search file names and UTF-8 text contents below a path."""
    root = Path(path)
    files = (
        [root]
        if root.is_file()
        else sorted(item for item in root.rglob("*") if item.is_file())
    )
    matches: list[str] = []

    for file_path in files:
        display_path = (
            file_path.name if root.is_file() else str(file_path.relative_to(root))
        )
        if query in file_path.name:
            matches.append(f"FILE {display_path}")

        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        for line_number, line in enumerate(lines, start=1):
            if query in line:
                matches.append(f"TEXT {display_path}:{line_number}:{line}")

    return "\n".join(matches) if matches else "No matches found."


def patch(path: str, old_text: str, new_text: str) -> str:
    """Replace one unique, exact text fragment in a UTF-8 file."""
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
    count = content.count(old_text)
    if count == 0:
        raise ValueError("old_text was not found")
    if count > 1:
        raise ValueError(f"old_text appears {count} times; make it unique")

    file_path.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
    return f"Patched {file_path}"


def delete(path: str) -> str:
    """Delete one file."""
    file_path = Path(path)
    file_path.unlink()
    return f"Deleted {file_path}"


# The registry is both the dispatch table and the source of model-visible tool
# definitions. Keeping it explicit makes the first version easy to inspect.
TOOLS: dict[str, ToolEntry] = {
    "execute": {
        "description": "Run one foreground shell command in the current directory.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
            "additionalProperties": False,
        },
        "function": execute,
    },
    "read": {
        "description": "Read a UTF-8 text file.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        "function": read,
    },
    "write": {
        "description": "Create or completely overwrite a UTF-8 text file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        "function": write,
    },
    "search": {
        "description": "Search file names and text contents below a path.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "path": {"type": "string", "default": "."},
            },
            "required": ["query", "path"],
            "additionalProperties": False,
        },
        "function": search,
    },
    "patch": {
        "description": "Replace one unique, exact text fragment in a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
            "additionalProperties": False,
        },
        "function": patch,
    },
    "delete": {
        "description": "Delete one file.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        "function": delete,
    },
}


def tool_definitions() -> list[dict[str, Any]]:
    """Build the tool definitions sent to the model."""
    return [
        {
            "type": "function",
            "name": name,
            "description": entry["description"],
            "parameters": entry["parameters"],
            "strict": True,
        }
        for name, entry in TOOLS.items()
    ]


def dispatch_tool(name: str, arguments: dict[str, Any]) -> str:
    """Call a registered tool and turn failures into model-readable text."""
    entry = TOOLS.get(name)
    if entry is None:
        return f"ERROR: Unknown tool: {name}"

    function: ToolFunction = entry["function"]
    try:
        return function(**arguments)
    except Exception as error:  # The model needs the error so it can recover.
        return f"ERROR: {type(error).__name__}: {error}"
