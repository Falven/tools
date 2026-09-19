import base64
import hashlib
import json
import os
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from mcp.server.apps import Apps, ResourceCsp
from mcp.server.auth.middleware.auth_context import get_access_token
from toolforge import get_caller_credential

apps = Apps()
__all__ = ["launch_tetris_game"]
RESOURCE_URI = "ui://tetris-game/app.html"
ASSETS = Path(__file__).parent
DEFAULT_DATA_DIR = Path.home() / ".toolforge_data"
HTML = (ASSETS / "app.html").read_text(encoding="utf-8").replace(
    "<!-- app.js -->",
    f'<script type="module">\n{(ASSETS / "app.js").read_text(encoding="utf-8")}\n</script>',
)


@apps.tool(resource_uri=RESOURCE_URI)
def launch_tetris_game() -> dict[str, object]:
    """Launch an interactive falling-block Tetris-style arcade game.

    The app supports keyboard, swipe, and on-screen controls, plus pause,
    restart, ghost-piece, next-piece, level, line, and score features. Completed
    scores are saved automatically to a shared leaderboard with the signed-in
    player's display name and email, which are visible to leaderboard viewers.
    Returns a launch confirmation and controls for clients that cannot render
    the app.
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
        "leaderboard": "Completed scores are saved automatically with player name and email.",
    }


def _claims_from_token(token: str) -> dict[str, object]:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload))
        return decoded if isinstance(decoded, dict) else {}
    except (IndexError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _caller_identity() -> tuple[str, str, str]:
    """Return a stable ID, display name, and email without exposing credentials."""
    claims: dict[str, object] = {}
    sources: list[object] = [get_access_token(), get_caller_credential()]

    for source in sources:
        if isinstance(source, Mapping):
            nested = source.get("claims")
            if isinstance(nested, Mapping):
                claims.update(nested)
            claims.update({str(key): value for key, value in source.items()})
        nested = getattr(source, "claims", None)
        if isinstance(nested, Mapping):
            claims.update(nested)
        token = source if isinstance(source, str) else getattr(source, "token", None)
        if isinstance(token, str):
            claims.update(_claims_from_token(token))

    email = str(
        claims.get("email")
        or claims.get("preferred_username")
        or claims.get("upn")
        or ""
    ).strip()
    name = str(claims.get("name") or claims.get("display_name") or "").strip()
    if not name:
        name = email.split("@", 1)[0] if email else "Player"
    if not email:
        email = "Unavailable"
    subject = str(claims.get("oid") or claims.get("sub") or email).strip()
    user_id = hashlib.sha256(subject.encode("utf-8")).hexdigest()
    return user_id, name[:120], email[:254]


def _open_scores_db() -> sqlite3.Connection:
    configured = os.environ.get("TOOLFORGE_DATA_DIR")
    data_dir = Path(configured) if configured else DEFAULT_DATA_DIR
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        database = data_dir / "tetris_scores.sqlite3"
        connection = sqlite3.connect(database, timeout=10)
    except (OSError, sqlite3.Error):
        fallback = Path("/tmp/toolforge_tetris")
        fallback.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(fallback / "tetris_scores.sqlite3", timeout=10)

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS scores (
            user_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            email TEXT NOT NULL,
            score INTEGER NOT NULL,
            lines INTEGER NOT NULL,
            level INTEGER NOT NULL,
            achieved_at TEXT NOT NULL
        )
        """
    )
    return connection


def _leaderboard(limit: int) -> list[dict[str, object]]:
    with _open_scores_db() as connection:
        rows = connection.execute(
            """
            SELECT display_name, email, score, lines, level, achieved_at
            FROM scores
            ORDER BY score DESC, lines DESC, achieved_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "rank": index,
            "name": row["display_name"],
            "email": row["email"],
            "score": row["score"],
            "lines": row["lines"],
            "level": row["level"],
            "achieved_at": row["achieved_at"],
        }
        for index, row in enumerate(rows, 1)
    ]


@apps.tool(
    resource_uri=RESOURCE_URI,
    visibility=["app"],
    name="submit_tetris_score",
)
def _submit_tetris_score(score: int, lines: int, level: int) -> dict[str, object]:
    """Save the signed-in player's best completed score and return the leaderboard."""
    clean_score = max(0, min(int(score), 100_000_000))
    clean_lines = max(0, min(int(lines), 1_000_000))
    clean_level = max(1, min(int(level), 100_000))
    user_id, name, email = _caller_identity()
    achieved_at = datetime.now(UTC).isoformat(timespec="seconds")

    with _open_scores_db() as connection:
        connection.execute(
            """
            INSERT INTO scores (
                user_id, display_name, email, score, lines, level, achieved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                display_name = excluded.display_name,
                email = excluded.email,
                score = excluded.score,
                lines = excluded.lines,
                level = excluded.level,
                achieved_at = excluded.achieved_at
            WHERE excluded.score > scores.score
            """,
            (user_id, name, email, clean_score, clean_lines, clean_level, achieved_at),
        )
        saved = connection.execute(
            "SELECT score FROM scores WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    return {
        "saved": saved is not None and saved["score"] == clean_score,
        "personal_best": saved["score"] if saved else clean_score,
        "scores": _leaderboard(25),
    }


@apps.tool(
    resource_uri=RESOURCE_URI,
    visibility=["app"],
    name="get_tetris_high_scores",
)
def _get_tetris_high_scores(limit: int = 25) -> dict[str, object]:
    """Return the shared Tetris leaderboard, including player names and emails."""
    return {"scores": _leaderboard(max(1, min(int(limit), 100)))}


apps.add_html_resource(
    RESOURCE_URI,
    HTML,
    title="Tetris",
    csp=ResourceCsp(resource_domains=["https://cdn.jsdelivr.net"]),
)
