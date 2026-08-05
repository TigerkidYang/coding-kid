"""Read-only MCP server for the bundled, disabled example Plugin."""

from pathlib import Path

from mcp.server.mcpserver import MCPServer

server = MCPServer("coding-kid-readonly-inspector")


@server.tool()
def inspect_text(path: str) -> dict[str, object]:
    """Return bounded metadata and a preview for one UTF-8 text file."""
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
    return {
        "path": str(file_path.resolve()),
        "line_count": len(content.splitlines()),
        "character_count": len(content),
        "preview": content[:2_000],
    }


if __name__ == "__main__":
    server.run("stdio")
