"""Hello World tool with a minimal MCP App view."""

from mcp.server import MCPServer

APP_URI = "ui://hello_world/app.html"
APP_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Hello World</title>
  </head>
  <body>
    <h1>Hello World</h1>
  </body>
</html>
"""


def register(server: MCPServer) -> None:
    @server.tool(meta={"ui": {"resourceUri": APP_URI}})
    def hello_world() -> str:
        """Return 'Hello World' with no inputs or side effects; show an MCP App in capable hosts."""
        return "Hello World"

    @server.resource(APP_URI, mime_type="text/html;profile=mcp-app")
    def hello_world_app() -> str:
        """Serve the self-contained Hello World HTML for the MCP App."""
        return APP_HTML
