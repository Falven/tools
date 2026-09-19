# ruff: noqa: I001

import base64
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.apps import Apps, ResourceCsp


apps = Apps()
__all__ = ["snake_game"]

RESOURCE_URI = "ui://snake-game/app.html"
SOURCE_DIR = Path(__file__).parent
SCORE_DATABASE = Path.home() / ".toolforge" / "snake-game" / "scores.sqlite3"
HTML = (SOURCE_DIR / "app.html").read_text(encoding="utf-8").replace(
    "/*__APP_JS__*/",
    (SOURCE_DIR / "app.js").read_text(encoding="utf-8"),
)


def _token_claims() -> dict[str, object]:
    token = get_access_token()
    if token is None:
        return {}

    claims = getattr(token, "claims", None)
    if isinstance(claims, dict):
        return claims

    raw_token = getattr(token, "token", "")
    if not isinstance(raw_token, str) or raw_token.count(".") != 2:
        return {}
    try:
        payload = raw_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload))
        return decoded if isinstance(decoded, dict) else {}
    except (ValueError, TypeError, json.JSONDecodeError):
        return {}


def _entra_player() -> dict[str, str] | None:
    token = get_access_token()
    claims = _token_claims()
    name = claims.get("name")
    email = (
        claims.get("email")
        or claims.get("preferred_username")
        or claims.get("upn")
        or claims.get("unique_name")
    )
    subject = (
        claims.get("oid")
        or claims.get("sub")
        or getattr(token, "subject", None)
        or getattr(token, "client_id", None)
    )
    tenant = claims.get("tid") or claims.get("iss") or ""

    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(email, str) or not email.strip() or "@" not in email:
        return None
    if not isinstance(subject, str) or not subject.strip():
        return None
    tenant_text = tenant if isinstance(tenant, str) else ""

    return {
        "key": f"{tenant_text}:{subject}",
        "name": name.strip()[:120],
        "email": email.strip().lower()[:254],
    }


def _open_score_database() -> sqlite3.Connection:
    SCORE_DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(SCORE_DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS snake_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT NOT NULL UNIQUE,
            player_key TEXT NOT NULL,
            player_name TEXT NOT NULL,
            player_email TEXT NOT NULL,
            score INTEGER NOT NULL,
            achieved_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS snake_scores_rank
        ON snake_scores(score DESC, achieved_at ASC)
        """
    )
    return connection


def _leaderboard_rows(limit: int = 20) -> list[dict[str, object]]:
    connection = _open_score_database()
    try:
        rows = connection.execute(
            """
            SELECT player_name, player_email, score, achieved_at
            FROM snake_scores
            ORDER BY score DESC, achieved_at ASC
            LIMIT ?
            """,
            (max(1, min(limit, 50)),),
        ).fetchall()
    finally:
        connection.close()
    return [
        {
            "rank": index,
            "name": row["player_name"],
            "email": row["player_email"],
            "score": row["score"],
            "achieved_at": row["achieved_at"],
        }
        for index, row in enumerate(rows, start=1)
    ]


@apps.tool(resource_uri=RESOURCE_URI)
def snake_game() -> dict[str, object]:
    """Launch an interactive Snake arcade game.

    The app supports arrow keys, WASD, swipe gestures, and on-screen direction
    controls, pause/restart actions, a local best score, and a shared persistent
    leaderboard. Players can save a completed score under the name and email
    from their signed-in Microsoft Entra identity; those details are visible to
    other leaderboard viewers. Returns a launch confirmation and control summary
    for clients that cannot render the interactive app.
    """
    return {
        "message": "Snake is ready to play.",
        "controls": {
            "desktop": "Arrow keys or WASD to steer; Space to pause.",
            "touch": "Swipe on the board or use the on-screen arrow buttons.",
        },
        "objective": "Eat berries to grow and score points. Avoid walls and your own tail.",
        "leaderboard": "Completed scores can be shared using the signed-in player's Entra name and email.",
    }


@apps.tool(
    resource_uri=RESOURCE_URI,
    visibility=["app"],
    name="get_snake_high_scores",
)
def get_snake_high_scores() -> dict[str, object]:
    """Return the shared Snake leaderboard and the current Entra player identity."""
    player = _entra_player()
    return {
        "scores": _leaderboard_rows(),
        "player": (
            {"name": player["name"], "email": player["email"]}
            if player is not None
            else None
        ),
    }


@apps.tool(
    resource_uri=RESOURCE_URI,
    visibility=["app"],
    name="save_snake_high_score",
)
def save_snake_high_score(score: int, game_id: str) -> dict[str, object]:
    """Persist one completed game score under the signed-in Entra identity."""
    if not isinstance(score, int) or score <= 0 or score > 1_000_000 or score % 10:
        raise ValueError("Score must be a positive multiple of 10.")
    if (
        not isinstance(game_id, str)
        or not 8 <= len(game_id) <= 64
        or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for character in game_id)
    ):
        raise ValueError("Invalid game identifier.")

    player = _entra_player()
    if player is None:
        raise ValueError(
            "Your signed-in Microsoft Entra identity does not include both a name and email."
        )

    achieved_at = datetime.now(UTC).isoformat()
    connection = _open_score_database()
    try:
        try:
            connection.execute(
                """
                INSERT INTO snake_scores (
                    game_id, player_key, player_name, player_email, score, achieved_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id,
                    player["key"],
                    player["name"],
                    player["email"],
                    score,
                    achieved_at,
                ),
            )
            connection.commit()
            saved = True
        except sqlite3.IntegrityError:
            saved = False
    finally:
        connection.close()

    return {
        "saved": saved,
        "score": score,
        "player": {"name": player["name"], "email": player["email"]},
        "scores": _leaderboard_rows(),
    }


apps.add_html_resource(
    RESOURCE_URI,
    HTML,
    title="Snake Game",
    csp=ResourceCsp(resource_domains=["https://cdn.jsdelivr.net"]),
)
