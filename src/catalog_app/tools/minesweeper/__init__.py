"""Minesweeper: one model-facing MCP App and three App-only handlers."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from mcp.server import MCPServer
from pydantic import Field

from .engine import Action, DifficultyId, MAX_CELLS
from .state import MinesweeperState

RESOURCE_URI = "ui://minesweeper/app.html"
ASSETS = Path(__file__).parent
_STATE = MinesweeperState()

RunId = Annotated[str, Field(strict=True, min_length=20, max_length=128)]
Cell = Annotated[int, Field(strict=True, ge=0, lt=MAX_CELLS)]
Revision = Annotated[int, Field(strict=True, ge=0)]


@lru_cache(maxsize=1)
def _app_html() -> str:
    # Import and registration must succeed before frontend assets are generated.
    html = (ASSETS / "app.html").read_text(encoding="utf-8")
    script = (ASSETS / "app.js").read_text(encoding="utf-8")
    if html.count("<!-- app.js -->") != 1:
        raise ValueError("Minesweeper HTML must contain exactly one script insertion marker.")
    return html.replace("<!-- app.js -->", f'<script type="module">\n{script}\n</script>')


def _strict_inputs(server: MCPServer, names: tuple[str, ...]) -> None:
    """Harden only our generated argument models, not SDK-wide defaults.

    MCP 2.0's tool decorator has no argument-model configuration parameter and
    defaults to silently dropping unknown fields. Keep signature-derived schemas
    while forbidding spoofed identity/score fields and disabling coercion. This
    small SDK compatibility step is covered by real registration/call tests.
    """
    for name in names:
        tool = server._tool_manager.get_tool(name)
        if tool is None:
            raise RuntimeError(f"Minesweeper handler {name} was not registered.")
        model = tool.fn_metadata.arg_model
        model.model_config = {**model.model_config, "extra": "forbid", "strict": True}
        model.model_rebuild(force=True)
        tool.parameters = model.model_json_schema(by_alias=True)


def minesweeper() -> dict[str, Any]:
    """Open nostalgic Minesweeper, or read rules, difficulty choices and shared top scores.

    Takes no inputs. Returns the verified caller's player summary, ephemeral
    server epoch, and highest-score-first leaderboard. Opening posts no score
    and starts no game. Only server-verified wins count; each delegated user
    keeps one best across difficulties. Games and scores are in memory only
    and disappear on server restart. A delegated user account is required to
    play; application-only callers may read the rules and scores.
    """
    return _STATE.overview()


def minesweeper_start(difficulty: DifficultyId = "beginner") -> dict[str, Any]:
    """Start a caller-bound, two-hour game; default difficulty is beginner.

    Difficulties are beginner (9x9, 10 mines, 1x), intermediate (16x16,
    40 mines, 2x), and expert (16x30, 99 mines, 3x). Returns a covered board
    with revision zero. No mines or clock exist until an actual reveal;
    its cell and neighbors are safe. Only the caller's newest three games
    are retained, including terminal receipts. No score is posted by start.
    """
    return _STATE.start(difficulty)


def minesweeper_move(run_id: RunId, action: Action, cell: Cell, revision: Revision) -> dict[str, Any]:
    """Apply reveal, flag (toggle), or chord to a zero-based row-major cell.

    cell and revision are strict integers. Send the last received revision;
    valid nonterminal moves consume one revision even when nothing opens.
    Exactly repeating the last (revision, action, cell) returns its original
    response. Other stale revisions return an error with the current game
    for resync. Terminal games are frozen. The server alone computes time,
    mines and score, and only wins update the shared best-score leaderboard.
    """
    return _STATE.move(run_id, action, cell, revision)


def minesweeper_scores() -> dict[str, Any]:
    """Read the top 50 shared wins, total players, caller's best and epoch.

    Takes no inputs and posts no score. Order is highest score, then fastest
    server elapsed milliseconds, then first achieved. Raw caller identities
    and other players' opaque IDs are never returned in leaderboard rows.
    Scores are ephemeral, process-local, and reset on server restart.
    """
    return _STATE.scores()


def minesweeper_app() -> str:
    """Serve adjacent HTML with the bundled official SDK and application code."""
    return _app_html()
