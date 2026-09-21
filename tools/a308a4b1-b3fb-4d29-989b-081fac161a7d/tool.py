"""MCP transport only; all game state is owned by GameSession."""

from pathlib import Path
from uuid import UUID

from mcp.server.apps import Apps, ResourceCsp
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.types import CallToolResult, TextContent

from .game.session import GameSession, Operator

__all__ = ["new_tool"]
apps = Apps()
_session = GameSession()
_RESOURCE = "ui://laya-plays-pokemon-a308a4b1/app.html"
_ASSETS = Path(__file__).parent


def _operator() -> Operator:
    access = get_access_token()
    claims = getattr(access, "claims", None) if access is not None else None
    if not claims or not isinstance(claims, dict) or not claims.get("scp"):
        raise ValueError("A verified delegated ToolForge caller is required.")
    if not isinstance(claims["scp"], str) or not claims["scp"].strip():
        raise ValueError("Delegated caller scopes are required.")
    try:
        return Operator(str(UUID(claims["tid"])), str(UUID(claims["oid"])))
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ValueError("Verified tenant and operator identity are required.") from None


async def _respond(tab_id: str, visible: bool, displaying: bool,
                   runtime_id: str | None, run_id: str | None,
                   revision: int | None, playback: bool) -> CallToolResult:
    try:
        operator = _operator()
        tab_id = str(UUID(tab_id))
        if revision is not None and (revision < 0 or revision > 2**53 - 1):
            raise ValueError("Invalid display revision.")
        for identifier in (runtime_id, run_id):
            if identifier is not None:
                UUID(identifier)
        view = await _session.request(operator, tab_id, visible, displaying,
                                      runtime_id, run_id, revision, playback)
    except ValueError as error:
        return CallToolResult(
            is_error=True, content=[TextContent(type="text", text=str(error))],
            structured_content={"ok": False, "status": "request_rejected"},
        )
    receipt = {"ok": True, "status": view["status"],
               "runtime_id": view["runtime_id"], "run_number": view["run_number"],
               "revision": view["revision"]}
    return CallToolResult(
        content=[TextContent(type="text", text=f"Laya Pokémon: {view['status']}.")],
        structured_content=receipt, meta={"view": view},
    )


@apps.tool(resource_uri=_RESOURCE)
def new_tool() -> dict:
    """Open Laya Plays Pokémon, a watch-only shared Pokémon Red campaign.

    No inputs. Returns a small current status and an MCP App binding. This call
    does not register presence, load the ROM/model, or advance gameplay. Open the
    App to spectate. Progress and both scoreboards exist only in this one Python
    server process and disappear on restart/reload/republish. No downstream
    credentials or scopes are requested.
    """
    get_access_token()
    return _session.status()


@apps.tool(resource_uri=_RESOURCE, visibility=["app"], name="laya_pokemon_view")
async def laya_pokemon_view(tab_id: str, visible: bool = False,
                            displaying: bool = False,
                            runtime_id: str | None = None, run_id: str | None = None,
                            revision: int | None = None) -> CallToolResult:
    """Read live state and report this authenticated tab's visibility.

    UUID tab_id is memory-only and bound to the verified caller. Optional IDs and
    revision identify the last displayed view. displaying reports that a real
    frame is rendered; it is only a presence signal, not a duration or identity.
    Does not advance gameplay.
    Returns a small receipt with the detached display snapshot only in _meta.
    """
    return await _respond(tab_id, visible, displaying, runtime_id, run_id, revision, False)


@apps.tool(resource_uri=_RESOURCE, visibility=["app"], name="laya_pokemon_playback")
async def laya_pokemon_playback(tab_id: str, visible: bool, displaying: bool,
                                runtime_id: str, run_id: str | None,
                                revision: int) -> CallToolResult:
    """Request at most one paced, bounded Laya/emulator batch while visible.

    Requires a fresh view's runtime/run/revision and the caller-bound tab UUID.
    Busy, early or stale calls return a snapshot, never queue gameplay. Mutates
    only the shared RAM session. Setup/inference/action failures pause it. Display
    payloads are in _meta; ordinary activity receipts contain no frame data.
    """
    return await _respond(tab_id, visible, displaying, runtime_id, run_id, revision, True)


_html = (_ASSETS / "app.html").read_text(encoding="utf-8")
_html = _html.replace("<!-- styles.css -->",
                      "<style>\n" + (_ASSETS / "styles.css").read_text(encoding="utf-8") + "\n</style>")
_html = _html.replace("<!-- app.js -->",
                      '<script type="module">\n' + (_ASSETS / "app.js").read_text(encoding="utf-8") + "\n</script>")
apps.add_html_resource(
    _RESOURCE, _html, title="Laya Plays Pokémon",
    csp=ResourceCsp(resource_domains=["https://cdn.jsdelivr.net"]),
)
