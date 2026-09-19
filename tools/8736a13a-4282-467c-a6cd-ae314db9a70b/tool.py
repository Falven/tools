from pathlib import Path
from typing import Literal

from mcp.server.apps import Apps, ResourceCsp

apps = Apps()
__all__ = ["launch_simple_counter"]
RESOURCE_URI = "ui://simple-counter/app.html"
_count = 0


@apps.tool(resource_uri=RESOURCE_URI)
def launch_simple_counter() -> dict[str, str | int]:
    """Open a counter with increment, decrement, and reset controls.

    The count is shared by callers in this server process and survives browser
    refreshes. Reloading the tool or restarting the runtime resets it to zero.
    """
    return {
        "title": "Simple Counter",
        "initial_count": _count,
        "message": "Open the app to increment, decrement, or reset the counter.",
    }


@apps.tool(resource_uri=RESOURCE_URI, visibility=["app"])
async def update_simple_counter(
    action: Literal["read", "increment", "decrement", "reset"] = "read",
) -> dict[str, str | int]:
    """Read or change the counter stored in this tool's memory."""
    global _count
    if action == "increment":
        _count += 1
    elif action == "decrement":
        _count -= 1
    elif action == "reset":
        _count = 0
    return launch_simple_counter()


assets = Path(__file__).parent
apps.add_html_resource(
    RESOURCE_URI,
    (assets / "app.html").read_text(encoding="utf-8").replace(
        "<!-- app.js -->",
        f'<script type="module">\n{(assets / "app.js").read_text(encoding="utf-8")}\n</script>',
    ),
    title="Simple Counter",
    csp=ResourceCsp(resource_domains=["https://cdn.jsdelivr.net"]),
)
