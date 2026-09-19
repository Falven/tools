"""A minimal interactive MCP App."""

from __future__ import annotations

from mcp.server.apps import Apps


__all__ = ["open_click_counter"]

APP_URI = "ui://click-counter/app.html"
with open(__file__.removesuffix("tool.py") + "app.html", encoding="utf-8") as _app_file:
    APP_HTML = _app_file.read()

apps = Apps()


@apps.tool(resource_uri=APP_URI)
def open_click_counter() -> dict[str, str | int]:
    """Open a small interactive click-counter MCP App.

    Call this when the user wants a simple demonstration of an MCP App or an
    inline counter they can increment and reset. The tool takes no inputs and
    returns a short status plus the counter's initial value. Its associated
    UI runs entirely in the host's sandboxed app frame; clicks only update
    local UI state and cause no external or persistent side effects.
    """
    return {
        "message": "The interactive click counter is ready.",
        "initial_count": 0,
    }


apps.add_html_resource(
    APP_URI,
    APP_HTML,
    title="Click Counter",
    prefers_border=True,
)
