"""Rally — After Hours: one model-facing MCP App, three App-only handlers."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from mcp.server import MCPServer
from pydantic import Field

from .engine import MAX_INPUTS, MAX_STEPS
from .state import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, RallyPongState

RESOURCE_URI = "ui://rally-pong/app.html"
ASSETS = Path(__file__).parent
_STATE = RallyPongState()

# Preserve submitted integer types. Never coerce booleans, decimal numbers or
# strings into apparently legitimate physics inputs at the MCP/Pydantic layer.
StrictInteger = Annotated[int, Field(strict=True)]
ReplayInput = Annotated[list[StrictInteger], Field(min_length=2, max_length=2)]
ReplayInputs = Annotated[list[ReplayInput], Field(max_length=MAX_INPUTS)]
ReplaySteps = Annotated[int, Field(strict=True, ge=1, le=MAX_STEPS)]
RunId = Annotated[str, Field(strict=True, min_length=20, max_length=128)]
PageOffset = Annotated[int, Field(strict=True, ge=0)]
PageLimit = Annotated[int, Field(strict=True, ge=1, le=MAX_PAGE_SIZE)]


@lru_cache(maxsize=1)
def _app_html() -> str:
    # Frontend generation must not be needed at import/registration time. Read
    # adjacent self-contained assets lazily, once per deployment process.
    html = (ASSETS / "app.html").read_text(encoding="utf-8")
    script = (ASSETS / "app.js").read_text(encoding="utf-8")
    marker = "<!-- app.js -->"
    if html.count(marker) != 1:
        raise ValueError("Rally HTML must contain exactly one script insertion marker.")
    return html.replace(marker, f'<script type="module">\n{script}\n</script>')


def _strict_inputs(server: MCPServer, names: tuple[str, ...]) -> None:
    """Forbid unknown fields on only Rally's signature-derived argument models.

    The pinned MCP 2.0 decorator has no argument-model configuration option and
    otherwise silently discards extras. Match the repository's Minesweeper
    compatibility pattern, covered by real calls and unaffected-tool tests.
    """
    for name in names:
        tool = server._tool_manager.get_tool(name)
        if tool is None:
            raise RuntimeError(f"Rally handler {name} was not registered.")
        model = tool.fn_metadata.arg_model
        model.model_config = {**model.model_config, "extra": "forbid", "strict": True}
        model.model_rebuild(force=True)
        tool.parameters = model.model_json_schema(by_alias=True)


def rally_pong() -> dict[str, Any]:
    """Open Rally — After Hours, a Three.js 2.5D Pong arcade, or read top scores.

    Takes no inputs. Returns controls, rules, the verified caller's player
    summary, shared leaderboard and ephemeral server epoch. The full-viewport
    App offers snappy keyboard/mouse/touch/gamepad controls, original synth
    music and separate music/effects mutes; WebGL2 is required to play.
    Opening starts no run, plays no audio and posts no score. Scores are
    in-memory, replay-verified, and reset on server restart. A delegated user
    account is required for scored play; application-only callers may read
    scores but cannot post.
    """
    return _STATE.overview()


def rally_pong_begin() -> dict[str, Any]:
    """Issue a caller-bound seed/run ID valid for 30 minutes and game constants.

    Requires verified delegated user claims. Returns player, leaderboard,
    epoch, runId and seed. At most four runs per player remain active; a fifth
    start retires only that player's oldest active run, never another's.
    """
    return _STATE.begin()


def rally_pong_finish(run_id: RunId, steps: ReplaySteps, inputs: ReplayInputs) -> dict[str, Any]:
    """Verify a complete 120 Hz replay and update the caller's in-memory best.

    Submit only the issued run_id, exact terminal steps (1..14400), and
    canonical [1-based tick, integer target] changes. Targets are -1000..1000;
    ticks must increase and repeated targets are invalid. Include serve ticks.
    Terminal means first to 7 goals or exactly 14400 ticks. Timeout counts
    earned points but is not a victory and awards no 250-point win bonus.
    The server derives all scores/names. Early, foreign, expired, malformed
    and incomplete replays cannot post. Successful retries return the same
    receipt until the original run's 30-minute TTL, even if ranks change.
    """
    return _STATE.finish(run_id, steps, inputs)


def rally_pong_scores(offset: PageOffset = 0, limit: PageLimit = DEFAULT_PAGE_SIZE) -> dict[str, Any]:
    """Read a ranked score page, caller summary and ephemeral server epoch.

    offset defaults to zero; limit defaults to 50 and must be 1..100. Rows
    carry absolute ranks, totalPlayers and nextOffset support pagination.
    No score is posted. Application-only or unidentified callers may read
    but receive canPost false and no player identity.
    """
    return _STATE.scores(offset, limit)


def rally_pong_app() -> str:
    """Serve the bundled App; native host controls provide fullscreen."""
    return _app_html()
