from pathlib import Path

from mcp.server.apps import Apps, ResourceCsp

apps = Apps()
__all__ = ["launch_tetris_game"]
RESOURCE_URI = "ui://tetris-game/app.html"
ASSETS = Path(__file__).parent
HTML = (ASSETS / "app.html").read_text(encoding="utf-8").replace(
    "<!-- app.js -->",
    f'<script type="module">\n{(ASSETS / "app.js").read_text(encoding="utf-8")}\n</script>',
)


@apps.tool(resource_uri=RESOURCE_URI)
def launch_tetris_game() -> dict[str, object]:
    """Launch an interactive falling-block Tetris-style arcade game.

    The app supports keyboard, swipe, and on-screen controls, plus pause,
    restart, ghost-piece, next-piece, level, line, score, and locally saved
    high-score features. It has no server-side effects. Returns a brief launch
    confirmation and control guide for clients that cannot render the app.
    """
    return {
        "launched": True,
        "game": "Tetris-style falling-block puzzle",
        "controls": {
            "move": "Left/Right arrows or A/D",
            "soft_drop": "Down arrow or S",
            "rotate": "Up arrow, W, or X",
            "rotate_counterclockwise": "Z",
            "hard_drop": "Space",
            "pause": "P or Escape",
            "restart": "R",
            "touch": "Swipe or use the on-screen controls",
        },
        "note": "Open the app to play. High score is stored only in the browser.",
    }


apps.add_html_resource(
    RESOURCE_URI,
    HTML,
    title="Neon Blocks",
    csp=ResourceCsp(resource_domains=["https://cdn.jsdelivr.net"]),
)
