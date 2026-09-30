"""A simple greeting tool."""

from mcp.server import MCPServer


def register(server: MCPServer) -> None:
    @server.tool()
    def hello_world() -> str:
        """Return the text 'hello world' without inputs or side effects."""
        return "hello world"
