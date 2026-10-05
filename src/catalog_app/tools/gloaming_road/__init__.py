"""The Gloaming Road: a self-contained, local-save first-person fantasy MCP App."""
from functools import lru_cache
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

RESOURCE_URI = "ui://gloaming-road/app.html"
ASSETS = Path(__file__).parent


@lru_cache(maxsize=1)
def _app_html() -> str:
    html = (ASSETS / "app.html").read_text(encoding="utf-8")
    script = (ASSETS / "app.js").read_text(encoding="utf-8")
    if "<!-- app.js -->" not in html:
        raise ValueError("The Gloaming Road App template is missing its script marker.")
    return html.replace("<!-- app.js -->", f'<script type="module">\n{script}\n</script>')


def register(server: MCPServer) -> None:
    @server.tool(title="The Gloaming Road", meta={"ui": {"resourceUri": RESOURCE_URI}})
    def gloaming_road() -> dict[str, Any]:
        """Open The Gloaming Road, a single-player first-person fantasy exploration game.

        Takes no inputs. Opens an original seeded open-world game with directional
        swordplay and one mission: rescue a princess from a guarded castle. Returns
        controls and browser requirements for clients without MCP App rendering.
        Opening the App does not create a world or overwrite a save. New World
        requires an in-App choice; game progress and settings stay in this browser
        (IndexedDB/localStorage), not on the MCP server. No account, scores, payment,
        reference-site downloads, multiplayer, or external runtime service is used.
        Desktop WebGL2/WebAssembly and a keyboard/mouse or gamepad are required.
        """
        return {
            "title": "The Gloaming Road",
            "summary": "Carry your steel through flower country, misted woods and an open, seeded world. The princess is being held in the castle.",
            "play": "Use Open App or View App; the host's native Fullscreen control gives the world more room.",
            "controls": {
                "move": "WASD; Shift sprints; Space plus a direction dodges",
                "look": "Mouse capture; arrow keys also look",
                "attack": "Tap left mouse / J for a light strike; hold and release for heavy",
                "defend": "Hold right mouse / K; press during early windup to feint",
                "guard": "1 high, 2 your left, 3 your right, 4 low; deliberate mouse gestures also select",
                "interact": "E / Enter",
                "pause": "Escape; click Resume to restore mouse capture",
                "controller": "Sticks move/look; triggers strike/defend; D-pad selects guard; A interacts; B dodges; Menu pauses",
            },
            "saves": "One local world per browser App origin; New World confirms replacement. Royal-guard defeats and rescue persist. No server save.",
            "requirements": "Desktop WebGL2, WebAssembly, browser storage and audio. Some App hosts restrict pointer lock; keyboard-only and controller controls are available.",
            "audio_note": "Original locally rendered score and effects. Auditory resemblance to the reference remains unverified.",
        }

    @server.resource(
        RESOURCE_URI,
        mime_type="text/html;profile=mcp-app",
        title="The Gloaming Road",
        meta={"ui": {"csp": {"resourceDomains": [], "connectDomains": []}}},
    )
    def gloaming_road_app() -> str:
        """Serve the bundled game and original assets, without network dependencies."""
        return _app_html()
