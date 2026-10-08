"""Neon Coil: one model-facing MCP App and three App-only handlers."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from .engine import MAX_TICKS, MAX_TURNS
from .state import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, NeonCoilState

RESOURCE_URI = "ui://neon-coil/app.html"
ASSETS = Path(__file__).parent
_STATE = NeonCoilState()

# Preserve integer replay events instead of allowing Pydantic to turn booleans,
# decimal numbers, or strings into apparently legitimate committed turns.
StrictInteger = Annotated[int, Field(strict=True)]
ReplayTurn = Annotated[list[StrictInteger], Field(min_length=2, max_length=2)]
ReplayTurns = Annotated[list[ReplayTurn], Field(max_length=MAX_TURNS)]
ReplaySteps = Annotated[int, Field(strict=True, ge=1, le=MAX_TICKS)]
RunId = Annotated[str, Field(strict=True, min_length=20, max_length=128)]
PageOffset = Annotated[int, Field(strict=True, ge=0)]
PageLimit = Annotated[int, Field(strict=True, ge=1, le=MAX_PAGE_SIZE)]


@lru_cache(maxsize=1)
def _app_html() -> str:
    # Asset generation is independent of server import/registration. Read only
    # when the resource is requested, then cache this deployment's single bundle.
    html = (ASSETS / "app.html").read_text(encoding="utf-8")
    script = (ASSETS / "app.js").read_text(encoding="utf-8")
    if "<!-- app.js -->" not in html:
        raise ValueError("Neon Coil HTML is missing its script insertion marker.")
    return html.replace("<!-- app.js -->", f'<script type="module">\n{script}\n</script>')


def neon_coil() -> dict[str, Any]:
    """Open Neon Coil, a Snake arcade App, or read its rules and shared top scores.

    Takes no inputs. Returns the verified caller's player summary, current
    leaderboard, rules, and server epoch. Scores are ephemeral, in-memory,
    replay-verified, and reset on server restart; opening the App posts no score.
    A delegated user account is needed to play scored runs.
    """
    return _STATE.overview()


def neon_coil_begin() -> dict[str, Any]:
    """Issue a two-hour, caller-bound seed/run ID for a new scored game.

    Requires verified delegated user claims. Returns player, leaderboard,
    epoch and engine constants. Keeps at most four active runs per player;
    another start retires that player's oldest active run, never another's.
    """
    return _STATE.begin()


def neon_coil_finish(run_id: RunId, steps: ReplaySteps, turns: ReplayTurns) -> dict[str, Any]:
    """Verify a completed replay and update the caller's in-memory personal best.

    Submit the issued run_id, total steps including the fatal/victory tick,
    and only committed [tick, direction] changes (0 up, 1 right, 2 down,
    3 left). Both steps and turns are bounded at 18000. A still-live game
    finishes only at the exact 18000-tick limit, returning endedByLimit true.
    Score and name are derived on the server, never caller-supplied. Early,
    foreign, invalid, expired, and incomplete runs cannot post. Completed
    retries return the same receipt until the original two-hour TTL expires.
    """
    return _STATE.finish(run_id, steps, turns)


def neon_coil_scores(offset: PageOffset = 0, limit: PageLimit = DEFAULT_PAGE_SIZE) -> dict[str, Any]:
    """Read a ranked page of shared scores, caller's best, and ephemeral epoch.

    offset defaults to zero; limit defaults to 50 and must be from 1 to 100.
    Rows retain absolute ranks; totalPlayers and nextOffset support paging.
    No score is posted. Applications and callers without verified delegated
    identity may view scores but receive no player identity and cannot post.
    """
    return _STATE.scores(offset, limit)


def neon_coil_app() -> str:
    """Serve the self-contained App; native host controls handle fullscreen."""
    return _app_html()
