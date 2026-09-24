"""Neon Snake's authenticated MCP interface, replay verifier, and score store."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal, NamedTuple

from mcp.server.apps import Apps, ResourceCsp
from mcp.server.auth.middleware.auth_context import get_access_token

__all__ = ["new_tool"]
apps = Apps()
RESOURCE_URI = "ui://neon-snake-70c8ba87/app.html"
ASSETS = Path(__file__).parent
BOARD_SIZE = 18
MAX_STEPS = 16000
RUN_TTL_MS = 6 * 60 * 60 * 1000
RULES = {
    "version": 1,
    "board_size": BOARD_SIZE,
    "points_per_food": 10,
    "foods_per_level": 5,
    "initial_tick_ms": 165,
    "minimum_tick_ms": 75,
    "level_tick_reduction_ms": 12,
    "max_steps": MAX_STEPS,
}
_DIRECTIONS = ((0, -1), (1, 0), (0, 1), (-1, 0))
_ORDER = "score DESC, duration_ms ASC, finished_at ASC, run_id ASC"
_READ = {"readOnlyHint": True, "openWorldHint": False}
_WRITE = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}


class _Player(NamedTuple):
    tenant_id: str
    player_id: str
    claimed_name: str
    claimed_email: str


def _name(value: Any) -> str:
    if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        return ""
    value = " ".join(value.split())
    return value if 1 <= len(value) <= 80 else ""


def _email(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if len(value) > 254 or "#ext#" in value.lower():
        return ""
    if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value):
        return ""
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        return ""
    return value


def _hash(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=True).encode()).hexdigest()


def _identity(token: Any) -> _Player | None:
    """Use only middleware-verified claims; never decode or forward a bearer token."""
    if token is None:
        return None
    claims = token.claims or {}
    if claims.get("idtyp") == "app" or (claims.get("roles") and not claims.get("scp")):
        return None
    issuer = claims.get("iss")
    tenant = claims.get("tid")
    oid = claims.get("oid")
    subject = token.subject or claims.get("sub")
    if all(isinstance(v, str) and v for v in (tenant, oid)):
        # Entra oid is immutable within its tenant. Names/emails are never keys.
        tenant_id = _hash("entra-tenant", tenant)
        player_id = _hash("entra-user", tenant, oid)
    elif all(isinstance(v, str) and v for v in (issuer, subject)):
        tenant_id = _hash("issuer", issuer)
        player_id = _hash("subject", issuer, subject)
    else:
        return None
    display_name = _name(claims.get("name"))
    if not display_name:
        given = claims.get("given_name") or ""
        family = claims.get("family_name") or ""
        if isinstance(given, str) and isinstance(family, str):
            display_name = _name(f"{given} {family}")
    email = next(
        (clean for key in ("email", "preferred_username", "upn")
         if (clean := _email(claims.get(key)))),
        "",
    )
    return _Player(tenant_id, player_id, display_name, email)


def _mask_email(email: str) -> str:
    if not email:
        return ""
    local, domain = email.rsplit("@", 1)
    return f"{local[:1]}•••@{domain}"


def _now() -> int:
    return time.time_ns() // 1_000_000


def _db_path() -> Path:
    configured = os.environ.get("NEON_SNAKE_DB_PATH")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise OSError("NEON_SNAKE_DB_PATH must be an absolute file path.")
        return path
    # Outside the source checkout: runtime personal data must never be published.
    return Path.home() / ".local" / "share" / "toolforge" / "neon-snake" / "scores.sqlite3"


@contextmanager
def _database():
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.touch(mode=0o600, exist_ok=True)
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA busy_timeout = 10000")
        db.execute("PRAGMA journal_mode = WAL")
        db.execute("PRAGMA foreign_keys = ON")
        if db.execute("PRAGMA user_version").fetchone()[0] > 1:
            raise sqlite3.DatabaseError("Unsupported score schema.")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                tenant_id TEXT NOT NULL,
                player_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                email TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (tenant_id, player_id)
            );
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                player_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                email TEXT NOT NULL,
                seed INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'finished')),
                score INTEGER,
                apples INTEGER,
                steps INTEGER,
                duration_ms INTEGER,
                reason TEXT,
                finished_at INTEGER,
                trace_sha TEXT
            );
            CREATE INDEX IF NOT EXISTS runs_leaderboard
                ON runs(tenant_id, status, score DESC, duration_ms, finished_at, run_id);
            CREATE INDEX IF NOT EXISTS runs_owner
                ON runs(tenant_id, player_id, status);
            PRAGMA user_version = 1;
        """)
        yield db
    finally:
        if db.in_transaction:
            db.rollback()
        db.close()


class _Game:
    """Deterministic rules, mirrored in app.js and checked with parity tests."""

    def __init__(self, seed: int):
        self.rng = seed & 0xFFFFFFFF or 1
        self.snake = [(6, 9), (5, 9), (4, 9), (3, 9)]
        self.direction = 1
        self.apples = 0
        self.steps = 0
        self.duration_ms = 0
        self.over = ""
        self.food = self._food()

    @property
    def score(self) -> int:
        return self.apples * RULES["points_per_food"]

    @property
    def interval(self) -> int:
        return max(
            RULES["minimum_tick_ms"],
            RULES["initial_tick_ms"]
            - (self.apples // RULES["foods_per_level"]) * RULES["level_tick_reduction_ms"],
        )

    def _food(self) -> tuple[int, int] | None:
        occupied = set(self.snake)
        free = [(x, y) for y in range(BOARD_SIZE) for x in range(BOARD_SIZE)
                if (x, y) not in occupied]
        if not free:
            return None
        x = self.rng
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self.rng = x & 0xFFFFFFFF
        return free[self.rng % len(free)]

    def step(self, direction: int) -> None:
        if self.over:
            raise ValueError("Moves after the end of a run are not valid.")
        if direction not in range(4) or (direction + 2) % 4 == self.direction:
            raise ValueError("The replay contains an invalid turn.")
        self.direction = direction
        self.steps += 1
        self.duration_ms += self.interval
        dx, dy = _DIRECTIONS[direction]
        head = (self.snake[0][0] + dx, self.snake[0][1] + dy)
        eating = head == self.food
        if not (0 <= head[0] < BOARD_SIZE and 0 <= head[1] < BOARD_SIZE):
            self.over = "wall"
        elif head in (self.snake if eating else self.snake[:-1]):
            self.over = "self"
        else:
            self.snake.insert(0, head)
            if eating:
                self.apples += 1
                self.food = self._food()
                if self.food is None:
                    self.over = "win"
            else:
                self.snake.pop()
        if self.steps >= MAX_STEPS and not self.over:
            self.over = "limit"


def _replay(seed: int, directions: str) -> _Game:
    if not isinstance(directions, str) or not 1 <= len(directions) <= MAX_STEPS:
        raise ValueError("The run replay is empty or too long.")
    if re.fullmatch(r"[0-3]+", directions) is None:
        raise ValueError("The replay must contain only direction digits.")
    game = _Game(seed)
    for direction in directions:
        game.step(int(direction))
    if not game.over:
        raise ValueError("Only completed runs can be recorded.")
    return game


def _profile(db: sqlite3.Connection, player: _Player) -> dict[str, str]:
    row = db.execute(
        "SELECT display_name, email FROM profiles WHERE tenant_id = ? AND player_id = ?",
        (player.tenant_id, player.player_id),
    ).fetchone()
    return {
        "display_name": player.claimed_name or (row["display_name"] if row else ""),
        "email": player.claimed_email or (row["email"] if row else ""),
    }


def _store_profile(db: sqlite3.Connection, player: _Player, profile: dict[str, str]):
    db.execute("""
        INSERT INTO profiles VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(tenant_id, player_id) DO UPDATE SET
            display_name = excluded.display_name,
            email = excluded.email,
            updated_at = excluded.updated_at
    """, (player.tenant_id, player.player_id, profile["display_name"], profile["email"], _now()))


def _base(player: _Player | None) -> dict[str, Any]:
    return {
        "kind": "neon_snake",
        "protocol": 1,
        "ok": True,
        "title": "Neon Snake",
        "rules": RULES,
        "player": {
            "authenticated": player is not None,
            "display_name": player.claimed_name if player else "Guest player",
            "email_hint": _mask_email(player.claimed_email) if player else "",
            "ready": False,
            "missing_fields": [],
            "name_from_sign_in": bool(player and player.claimed_name),
            "email_from_sign_in": bool(player and player.claimed_email),
            "best_score": 0,
            "best_rank": None,
            "total_runs": 0,
        },
        "leaderboard": [],
        "scope": "all",
        "total_runs": 0,
        "total_players": 0,
        "storage": {
            "available": True,
            "kind": "sqlite",
            "scope": "same_sign_in_tenant",
            "durability": "server_filesystem",
            "notice": "Keep the server database on a persistent volume to retain scores across redeployments.",
        },
        "message": (
            "Open the Neon Snake App to play. Use arrow keys, WASD, swipes, or the direction pad. "
            "Space/P pauses. Eat coral energy cells for 10 points; avoid walls and your tail. "
            "Completed ranked runs save automatically, highest score first. "
            "Sign in with a personal account to record scores; guest practice is not saved."
        ),
    }


def _snapshot(db: sqlite3.Connection, player: _Player, scope: str = "all") -> dict[str, Any]:
    result = _base(player)
    profile = _profile(db, player)
    missing = [key for key in ("display_name", "email") if not profile[key]]
    result["player"].update(
        display_name=profile["display_name"] or "Player",
        email_hint=_mask_email(profile["email"]),
        ready=not missing,
        missing_fields=missing,
    )
    ranked = f"""
        WITH ranked AS (
            SELECT *, ROW_NUMBER() OVER (ORDER BY {_ORDER}) AS rank
            FROM runs WHERE tenant_id = ? AND status = 'finished'
        )
    """
    sql = ranked + "SELECT * FROM ranked "
    params: list[Any] = [player.tenant_id]
    if scope == "mine":
        sql += "WHERE player_id = ? "
        params.append(player.player_id)
    rows = db.execute(sql + "ORDER BY rank LIMIT 10", params).fetchall()
    result["leaderboard"] = [
        {
            "rank": row["rank"],
            "display_name": row["display_name"],
            "email_hint": _mask_email(row["email"]),
            "score": row["score"],
            "duration_ms": row["duration_ms"],
            "recorded_at_ms": row["finished_at"],
            "is_you": row["player_id"] == player.player_id,
        }
        for row in rows
    ]
    stats = db.execute(
        ranked + """SELECT COUNT(*) AS total_runs, COALESCE(MAX(score), 0) AS best_score,
                    MIN(rank) AS best_rank FROM ranked WHERE player_id = ?""",
        (player.tenant_id, player.player_id),
    ).fetchone()
    result["player"].update(dict(stats))
    totals = db.execute(
        """SELECT COUNT(*) AS total_runs, COUNT(DISTINCT player_id) AS total_players
           FROM runs WHERE tenant_id = ? AND status = 'finished'""",
        (player.tenant_id,),
    ).fetchone()
    result.update(dict(totals))
    result["scope"] = scope
    result["message"] = (
        f"Neon Snake is ready for {result['player']['display_name']}. "
        f"Personal best: {stats['best_score']} points in {stats['total_runs']} completed runs. "
        "Open App to play with arrow keys/WASD or touch; Space/P pauses. "
        "The scoreboard is sorted by score descending, then shortest active time, then oldest finish. "
        "Runs save automatically with your name and e-mail; only masked e-mail is displayed. "
        "Scores are visible to other players in your sign-in tenant. "
        + ("Complete the missing profile fields in the App before a ranked run." if missing else "")
    )
    return result


def _error(code: str, message: str) -> dict[str, Any]:
    return {"kind": "neon_snake", "protocol": 1, "ok": False,
            "error": {"code": code, "message": message}}


def _storage_error() -> dict[str, Any]:
    # Never return filesystem paths, SQL text, exception details, or identity claims.
    return _error(
        "storage_unavailable",
        "Score storage is temporarily unavailable. Retry, or play an unsaved practice run.",
    )


@apps.tool(resource_uri=RESOURCE_URI, title="Neon Snake · 2.5D Arcade", annotations=_READ)
def new_tool() -> dict[str, Any]:
    """Open Neon Snake, an interactive Three.js 2.5D snake game.

    Takes no arguments. Returns game rules, the signed-in player's display name
    and masked e-mail, personal best, and the top 10 completed runs in their
    sign-in tenant, sorted by descending score, then shortest active time.
    Text and structured data remain useful in clients without MCP App support.

    Uses only the authenticated caller context; never supply a user identity.
    Opening may initialize an instance-local SQLite database but does not record
    a score or profile. Starting a ranked game in the App records the player's
    name/e-mail; finishing automatically verifies and saves the score. Missing
    profile details are requested once in the App. Other players see the name
    and masked e-mail, not the full address. Guest practice saves nothing.
    SQLite survives process restarts on the same filesystem; an administrator
    must persist NEON_SNAKE_DB_PATH across redeployments. No downstream scopes,
    credentials, e-mail delivery, or external profile service are used.
    """
    player = _identity(get_access_token())
    if player is None:
        return _base(None)
    try:
        with _database() as db:
            return _snapshot(db, player)
    except (OSError, sqlite3.Error):
        result = _base(player)
        result["storage"]["available"] = False
        result["message"] = _storage_error()["error"]["message"]
        return result


@apps.tool(resource_uri=RESOURCE_URI, visibility=["app"], name="neon_snake_board",
           title="Refresh Snake scores", annotations=_READ)
def _get_board(scope: Literal["all", "mine"] = "all") -> dict[str, Any]:
    """Read top 10 tenant-wide or personal runs; full e-mails are never returned."""
    player = _identity(get_access_token())
    if player is None:
        return _base(None)
    try:
        with _database() as db:
            return _snapshot(db, player, scope)
    except (OSError, sqlite3.Error):
        return _storage_error()


@apps.tool(resource_uri=RESOURCE_URI, visibility=["app"], name="neon_snake_profile",
           title="Complete Snake player profile", annotations=_WRITE)
def _save_profile(display_name: str = "", email: str = "") -> dict[str, Any]:
    """Store missing display name/e-mail for this caller only. Sign-in values win.

    Supplied e-mail is a contact label, not verified ownership or authorization.
    The App explains score visibility before the player saves these details.
    """
    player = _identity(get_access_token())
    if player is None:
        return _error("sign_in_required", "Sign in with a personal account to save a player profile.")
    try:
        with _database() as db:
            db.execute("BEGIN IMMEDIATE")
            current = _profile(db, player)
            profile = {
                "display_name": player.claimed_name or _name(display_name) or current["display_name"],
                "email": player.claimed_email or _email(email) or current["email"],
            }
            if display_name and not player.claimed_name and not _name(display_name):
                return _error("invalid_profile", "Use a display name of 1–80 characters without control characters.")
            if email and not player.claimed_email and not _email(email):
                return _error("invalid_profile", "Enter a valid e-mail address of at most 254 characters.")
            if not all(profile.values()):
                return _error("profile_required", "A name and e-mail are required for ranked scores.")
            _store_profile(db, player, profile)
            db.commit()
            return _snapshot(db, player)
    except (OSError, sqlite3.Error):
        return _storage_error()


@apps.tool(resource_uri=RESOURCE_URI, visibility=["app"], name="neon_snake_begin",
           title="Start a ranked Snake run", annotations=_WRITE)
def _begin_run() -> dict[str, Any]:
    """Create an owner-bound, six-hour game session and return its seed/rules.

    Saves the current caller's name/e-mail with the run, never an input identity.
    No score is recorded until a valid completed replay is submitted.
    """
    player = _identity(get_access_token())
    if player is None:
        return _error("sign_in_required", "Sign in with a personal account, or choose practice.")
    try:
        with _database() as db:
            db.execute("BEGIN IMMEDIATE")
            profile = _profile(db, player)
            if not all(profile.values()):
                return _error("profile_required", "Complete your name and e-mail before a ranked run.")
            now = _now()
            db.execute("DELETE FROM runs WHERE status = 'active' AND expires_at < ?", (now,))
            recent = db.execute(
                "SELECT COUNT(*) FROM runs WHERE tenant_id = ? AND player_id = ? AND created_at > ?",
                (player.tenant_id, player.player_id, now - 60_000),
            ).fetchone()[0]
            if recent >= 8:
                return _error("rate_limited", "Lots of quick restarts! Wait a minute before another ranked run.")
            _store_profile(db, player, profile)
            run_id, seed = uuid.uuid4().hex, secrets.randbelow(0xFFFFFFFF) + 1
            db.execute("""
                INSERT INTO runs(run_id, tenant_id, player_id, display_name, email,
                                 seed, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (run_id, player.tenant_id, player.player_id, profile["display_name"],
                  profile["email"], seed, now, now + RUN_TTL_MS))
            db.commit()
            result = _snapshot(db, player)
            result["run"] = {"run_id": run_id, "seed": seed, "expires_at_ms": now + RUN_TTL_MS}
            return result
    except (OSError, sqlite3.Error):
        return _storage_error()


@apps.tool(resource_uri=RESOURCE_URI, visibility=["app"], name="neon_snake_finish",
           title="Automatically record a completed Snake run",
           annotations={**_WRITE, "idempotentHint": True})
def _finish_run(run_id: str, directions: str) -> dict[str, Any]:
    """Replay direction digits (0 north, 1 east, 2 south, 3 west) and save the score.

    Inputs are the server-issued run_id and one direction per game tick, at most
    16000 digits. No client-supplied score, name, or e-mail is trusted. Requires
    the same signed-in owner, a complete valid replay, and plausible wall time.
    Exact retries are idempotent. Returns verified score and descending board.
    """
    player = _identity(get_access_token())
    if player is None:
        return _error("sign_in_required", "Reconnect the same signed-in account to save this run.")
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        return _error("invalid_run", "This game session is not valid.")
    if not isinstance(directions, str) or not 1 <= len(directions) <= MAX_STEPS:
        return _error("invalid_replay", "The replay is empty or too long.")
    digest = hashlib.sha256(directions.encode()).hexdigest()
    try:
        with _database() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM runs WHERE run_id = ? AND tenant_id = ? AND player_id = ?",
                (run_id, player.tenant_id, player.player_id),
            ).fetchone()
            if row is None:
                return _error("invalid_run", "This run is not available for the signed-in account.")
            duplicate = row["status"] == "finished"
            if duplicate:
                if row["trace_sha"] != digest:
                    return _error("already_recorded", "This run was already recorded with a different replay.")
                score, apples, duration_ms, reason = (
                    row["score"], row["apples"], row["duration_ms"], row["reason"]
                )
            else:
                now = _now()
                if now > row["expires_at"]:
                    return _error("run_expired", "This run expired after six hours and cannot be ranked.")
                try:
                    game = _replay(row["seed"], directions)
                except ValueError as error:
                    return _error("invalid_replay", str(error))
                if game.duration_ms > now - row["created_at"] + 750:
                    return _error("too_fast", "This replay is faster than the game clock. Wait a moment and retry.")
                score, apples, duration_ms, reason = game.score, game.apples, game.duration_ms, game.over
                db.execute("""
                    UPDATE runs SET status = 'finished', score = ?, apples = ?, steps = ?,
                        duration_ms = ?, reason = ?, finished_at = ?, trace_sha = ?
                    WHERE run_id = ? AND status = 'active'
                """, (score, apples, game.steps, duration_ms, reason, now, digest, run_id))
            db.commit()
            result = _snapshot(db, player)
            rank = db.execute(
                f"""SELECT rank FROM (
                    SELECT run_id, ROW_NUMBER() OVER (ORDER BY {_ORDER}) AS rank
                    FROM runs WHERE tenant_id = ? AND status = 'finished'
                ) WHERE run_id = ?""",
                (player.tenant_id, run_id),
            ).fetchone()[0]
            result["saved_run"] = {
                "score": score, "apples": apples, "duration_ms": duration_ms,
                "reason": reason, "rank": rank, "already_saved": duplicate,
            }
            return result
    except (OSError, sqlite3.Error):
        return _storage_error()


@apps.tool(resource_uri=RESOURCE_URI, visibility=["app"], name="neon_snake_forget",
           title="Delete my Snake data",
           annotations={"readOnlyHint": False, "destructiveHint": True,
                        "idempotentHint": True, "openWorldHint": False})
def _forget_my_data(confirm: bool = False) -> dict[str, Any]:
    """With confirm=true, remove only this caller's profile, runs, and scores.

    The App asks for explicit confirmation. Database backups are managed by the
    server administrator; this operation deletes records in the active database.
    """
    player = _identity(get_access_token())
    if player is None:
        return _error("sign_in_required", "Sign in to manage your own score data.")
    if confirm is not True:
        return _error("confirmation_required", "Confirm that you want to delete your profile and all runs.")
    try:
        with _database() as db:
            db.execute("BEGIN IMMEDIATE")
            key = (player.tenant_id, player.player_id)
            db.execute("DELETE FROM runs WHERE tenant_id = ? AND player_id = ?", key)
            db.execute("DELETE FROM profiles WHERE tenant_id = ? AND player_id = ?", key)
            db.commit()
            result = _snapshot(db, player)
            result["message"] = "Your profile, runs, and scores were removed from the active database."
            return result
    except (OSError, sqlite3.Error):
        return _storage_error()


HTML = (ASSETS / "app.html").read_text(encoding="utf-8").replace(
    "<!-- app.js -->",
    "<script type=\"module\">\n"
    + (ASSETS / "app.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
    + "\n</script>",
)
apps.add_html_resource(
    RESOURCE_URI,
    HTML,
    title="Neon Snake",
    description="A Three.js 2.5D arcade game with automatic, account-linked scores.",
    csp=ResourceCsp(resource_domains=["https://cdn.jsdelivr.net"]),
    prefers_border=True,
)
