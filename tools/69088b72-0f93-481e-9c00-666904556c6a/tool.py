# ruff: noqa: I001

from pathlib import Path

from mcp.server.apps import Apps, ResourceCsp


apps = Apps()
__all__ = ["snake_game"]

RESOURCE_URI = "ui://snake-game/app.html"
SOURCE_DIR = Path(__file__).parent
HTML = (SOURCE_DIR / "app.html").read_text(encoding="utf-8").replace(
    "/*__APP_JS__*/",
    (SOURCE_DIR / "app.js").read_text(encoding="utf-8"),
)


@apps.tool(resource_uri=RESOURCE_URI)
def snake_game() -> dict[str, object]:
    """Launch an interactive Snake arcade game.

    The app supports arrow keys, WASD, swipe gestures, and on-screen direction
    controls, with pause/restart actions and a locally saved high score. Returns
    a short launch confirmation and control summary for clients that cannot
    render the interactive app. The game has no server-side effects.
    """
    return {
        "message": "Snake is ready to play.",
        "controls": {
            "desktop": "Arrow keys or WASD to steer; Space to pause.",
            "touch": "Swipe on the board or use the on-screen arrow buttons.",
        },
        "objective": "Eat berries to grow and score points. Avoid walls and your own tail.",
    }


apps.add_html_resource(
    RESOURCE_URI,
    HTML,
    title="Snake Game",
    csp=ResourceCsp(resource_domains=["https://cdn.jsdelivr.net"]),
)
