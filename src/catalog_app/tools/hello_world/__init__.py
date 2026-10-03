"""A minimal Hello World MCP App."""

from pathlib import Path

from mcp.server import MCPServer
from mcp.server.apps import APP_MIME_TYPE

APP_URI = "ui://hello_world/app.html"
ASSETS = Path(__file__).parent
HTML = (ASSETS / "app.html").read_text(encoding="utf-8").replace(
    "<!-- app.js -->",
    f'<script type="module">\n{(ASSETS / "app.js").read_text(encoding="utf-8")}\n</script>',
)


def register(server: MCPServer) -> None:
    @server.tool(meta={"ui": {"resourceUri": APP_URI}})
    def hello_world() -> str:
        """Display the Hello World app and return 'Hello World' as text.

        Takes no inputs and has no side effects.
        """
        return "Hello World"

    @server.resource(
        APP_URI,
        mime_type=APP_MIME_TYPE,
        title="Hello World",
        meta={"ui": {"csp": {"resourceDomains": ["https://cdn.jsdelivr.net"]}}},
    )
    def hello_world_app() -> str:
        return HTML
