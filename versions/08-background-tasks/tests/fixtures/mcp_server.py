"""Small stdio MCP server used only by deterministic Version 07 tests."""

from mcp.server.mcpserver import MCPServer
import sys

server = MCPServer("coding-kid-test")


@server.tool()
def echo(text: str) -> dict[str, object]:
    """Echo text with a structured marker."""
    return {"echo": text, "readonly": True}


@server.tool()
async def wait(milliseconds: int) -> str:
    """Wait for timeout and cancellation tests."""
    import asyncio

    await asyncio.sleep(milliseconds / 1000)
    return "finished"


@server.tool(name="same.name")
def collision_dot() -> str:
    """One side of a normalized-name collision."""
    return "dot"


@server.tool(name="same_name")
def collision_underscore() -> str:
    """The other side of a normalized-name collision."""
    return "underscore"


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--http":
        server.run(
            "streamable-http",
            host="127.0.0.1",
            port=int(sys.argv[2]),
        )
    else:
        server.run("stdio")
