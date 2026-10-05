"""Bounded, process-local Minesweeper games and verified users' best wins.

All mutable state is protected by one lock. No persistence, raw caller IDs,
client clocks, client scores, or client-generated mine layouts are used.
Expired/retired/foreign run IDs are deliberately indistinguishable. A retained
run reserves its last response so retries cannot toggle a flag or post twice.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
import hashlib
import hmac
import json
import math
import secrets
import threading
import time
import unicodedata
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token

from . import engine

RUN_TTL_SECONDS = 2 * 60 * 60
MAX_RUNS = 1024
MAX_PER_PLAYER = 3
MAX_PLAYERS = 5000
LEADERBOARD_LIMIT = 50


def _nonempty_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _clean_name(value: str) -> str:
    return " ".join(unicodedata.normalize(
        "NFC", "".join(char for char in value if not unicodedata.category(char).startswith("C"))
    ).split())


def _display_name(claims: Mapping[str, Any]) -> str:
    candidate = claims.get("name")
    if not isinstance(candidate, str):
        return "Player"
    candidate = _clean_name(candidate)
    # Only the verified name claim is eligible. Never fall back to email, UPN,
    # oid, or subject; reject names containing those identifiers as well. NFKC
    # checking catches full-width @ and normalization/case variants privately.
    probe = unicodedata.normalize("NFKC", candidate).casefold()
    private_values = [
        unicodedata.normalize("NFKC", _clean_name(value)).casefold()
        for key in ("tid", "oid", "sub", "iss", "email", "upn", "preferred_username")
        if isinstance(value := claims.get(key), str) and value.strip()
    ]
    if not candidate or "@" in probe or any(value and value in probe for value in private_values):
        return "Player"
    return candidate[:48].rstrip() or "Player"


class MinesweeperState:
    """One server epoch; clock and private sampler are injectable for tests."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] | None = None,
        sampler: engine.MineSampler | None = None,
        max_runs: int = MAX_RUNS,
        max_per_player: int = MAX_PER_PLAYER,
        max_players: int = MAX_PLAYERS,
        ttl_seconds: float = RUN_TTL_SECONDS,
    ) -> None:
        if (
            any(type(limit) is not int or limit < 1 for limit in (max_runs, max_per_player, max_players))
            or type(ttl_seconds) not in (int, float)
            or not math.isfinite(ttl_seconds)
            or ttl_seconds <= 0
        ):
            raise ValueError("State capacities and finite TTL must be positive.")
        self._clock = clock or time.monotonic
        self._sample = sampler or secrets.SystemRandom().sample
        self._secret = secrets.token_bytes(32)
        self.epoch = secrets.token_urlsafe(18)
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._players: dict[str, dict[str, Any]] = {}
        self._achievement = 0
        self._max_runs = max_runs
        self._max_per_player = max_per_player
        self._max_players = max_players
        self._ttl_seconds = ttl_seconds

    def _caller(self) -> dict[str, str] | None:
        # Authentication belongs to MCP middleware. No token decoding, HTTP
        # headers, environment identity, token.subject, or token.scopes inference.
        token = get_access_token()
        claims = getattr(token, "claims", None)
        if not isinstance(claims, Mapping):
            return None
        scope = claims.get("scp")
        if not isinstance(scope, str) or not scope.split():
            return None
        idtyp = claims.get("idtyp")
        if idtyp is not None and (not isinstance(idtyp, str) or idtyp.strip().lower() == "app"):
            return None
        tenant = _nonempty_string(claims.get("tid"))
        object_id = _nonempty_string(claims.get("oid"))
        if tenant and object_id:
            identity = ["tenant-object", tenant.lower(), object_id.lower()]
        else:
            issuer = _nonempty_string(claims.get("iss"))
            subject = _nonempty_string(claims.get("sub"))
            if not issuer or not subject:
                return None
            identity = ["issuer-subject", issuer, subject]
        digest = hmac.new(
            self._secret,
            json.dumps(identity, ensure_ascii=True, separators=(",", ":")).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {"id": f"p_{digest[:32]}", "name": _display_name(claims)}

    def _failure(self, code: str, message: str, *, game: dict[str, Any] | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "error": {"code": code, "message": message},
            "epoch": self.epoch,
            "ephemeral": True,
        }
        if game is not None:
            result["game"] = game
        return result

    def _prune(self, now: float) -> None:
        # Caller holds the lock. Scores last for this process, not the run TTL.
        for run_id in [key for key, run in self._runs.items() if now >= run["expires"]]:
            del self._runs[run_id]

    def _ordered_players(self) -> list[dict[str, Any]]:
        return sorted(
            self._players.values(),
            key=lambda player: (-player["score"], player["elapsedMs"], player["achieved"]),
        )

    def _snapshot(
        self, caller: dict[str, str] | None, ordered: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        # Construct new public containers; no internal run or score row escapes.
        if ordered is None:
            ordered = self._ordered_players()
        caller_id = caller["id"] if caller else None
        best = self._players.get(caller_id) if caller_id else None
        return {
            "epoch": self.epoch,
            "ephemeral": True,
            "canPlay": caller is not None,
            "player": {
                "id": caller["id"],
                "name": caller["name"],
                "bestScore": best["score"] if best else 0,
            } if caller else None,
            "leaderboard": [
                {
                    "rank": index + 1,
                    "name": player["name"],
                    "score": player["score"],
                    "difficulty": player["difficulty"],
                    "elapsedMs": player["elapsedMs"],
                    "isYou": player["id"] == caller_id,
                }
                for index, player in enumerate(ordered[:LEADERBOARD_LIMIT])
            ],
            "totalPlayers": len(ordered),
        }

    def scores(self) -> dict[str, Any]:
        caller = self._caller()
        with self._lock:
            self._prune(self._clock())
            return self._snapshot(caller)

    def overview(self) -> dict[str, Any]:
        return {
            **self.scores(),
            "title": "Minesweeper",
            "description": (
                "A nostalgic 2.5D Minesweeper App with server-authoritative boards and shared high scores. "
                "Only wins count. Games and scores live only in server memory and reset on restart. "
                "A verified delegated user account is required to play."
            ),
            "rules": [
                "Reveal every non-mine cell to win. A revealed number counts mines in its eight neighbors.",
                "Mines are placed on the first actual reveal; that cell and all its neighbors are safe.",
                "Empty regions flood open. Flags block reveals; toggle them freely, up to the mine count.",
                "Chord a revealed cell when its adjacent flag count matches its number. Wrong flags can detonate a mine.",
                "The server clock starts on the first actual reveal and freezes on win or loss; switching away does not pause it.",
                "Score = revealedCount × 10 × difficulty multiplier. Only a win adds (1000 + max(0, 1000 − floor(elapsedSeconds))) × multiplier.",
                "Only wins post. Each player keeps one best across all difficulties: score descending, elapsed milliseconds ascending, then first achieved.",
                f"The shared leaderboard shows the top {LEADERBOARD_LIMIT} wins. Runs expire two hours after start; only your newest three runs are retained.",
                "Scores are ephemeral and reset when this server process restarts. Music and effects can be muted separately in the App.",
            ],
            "difficulties": engine.difficulties_metadata(),
        }

    def start(self, difficulty: str = "beginner") -> dict[str, Any]:
        caller = self._caller()
        if caller is None:
            return self._failure("ineligible", "Sign in with a delegated user account to play.")
        if type(difficulty) is not str or difficulty not in engine.DIFFICULTIES:
            return self._failure("invalid_difficulty", "difficulty must be beginner, intermediate, or expert.")
        with self._lock:
            now = self._clock()
            self._prune(now)
            owned = [key for key, run in self._runs.items() if run["owner"] == caller["id"]]
            # Insertion order resolves equal issue times. Retire only this user's
            # oldest retained run; never silently evict another user's live game.
            retire_id = owned[0] if len(owned) >= self._max_per_player else None
            if len(self._runs) - int(retire_id is not None) >= self._max_runs:
                return self._failure("capacity", "This server's run memory is full. Try again later.")
            reserved = set(self._players)
            reserved.update(
                run["owner"] for run in self._runs.values()
                if run["game"].status in ("ready", "playing")
            )
            if caller["id"] not in reserved and len(reserved) >= self._max_players:
                return self._failure("capacity", "This server's player memory is full. Try again later or after a restart.")
            run_id = secrets.token_urlsafe(32)
            while run_id in self._runs:
                run_id = secrets.token_urlsafe(32)
            game = engine.create_game(difficulty)
            if retire_id is not None:
                del self._runs[retire_id]
            self._runs[run_id] = {
                "owner": caller["id"],
                "issued": now,
                "expires": now + self._ttl_seconds,
                "game": game,
                "last_request": None,
                "last_response": None,
            }
            return {**self._snapshot(caller), "game": engine.snapshot(game, run_id, now)}

    def move(self, run_id: str, action: str, cell: int, revision: int) -> dict[str, Any]:
        caller = self._caller()
        if caller is None:
            return self._failure("ineligible", "Sign in with a delegated user account to play.")
        if type(run_id) is not str or not 20 <= len(run_id) <= 128:
            return self._failure("unavailable_run", "Run unavailable. Start a new game.")
        if type(action) is not str or action not in ("reveal", "flag", "chord"):
            return self._failure("invalid_action", "action must be reveal, flag, or chord.")
        if type(cell) is not int or not 0 <= cell < engine.MAX_CELLS:
            return self._failure("invalid_cell", "cell must be an integer index inside this board.")
        if type(revision) is not int or revision < 0:
            return self._failure("invalid_revision", "revision must be a nonnegative integer.")
        with self._lock:
            now = self._clock()
            self._prune(now)
            run = self._runs.get(run_id)
            if run is None or run["owner"] != caller["id"]:
                return self._failure("unavailable_run", "Run unavailable. Start a new game.")
            game = run["game"]
            if cell >= game.difficulty.size:
                return self._failure("invalid_cell", "cell must be an integer index inside this board.")
            request = (revision, action, cell)
            # Check exact retry before revision mismatch, including the winning
            # move's now-stale revision. Return the original time/rank/receipt.
            if request == run["last_request"]:
                return deepcopy(run["last_response"])
            if revision != game.revision:
                return self._failure(
                    "stale_revision", "The board changed. Resync from the returned game before moving again.",
                    game=engine.snapshot(game, run_id, now),
                )
            if game.status in ("won", "lost"):
                # Do not replace the last move's receipt: it remains retryable.
                return {**self._snapshot(caller), "game": engine.snapshot(game, run_id, now)}

            changed = engine.apply_move(game, action, cell, now, self._sample)
            receipt: dict[str, Any] = {}
            if game.status == "won":
                points, elapsed = engine.score(game, now), engine.elapsed_ms(game, now)
                previous = self._players.get(caller["id"])
                personal_best = previous is None or (
                    -points, elapsed
                ) < (-previous["score"], previous["elapsedMs"])
                if personal_best:
                    self._achievement += 1
                    self._players[caller["id"]] = {
                        "id": caller["id"],
                        "name": caller["name"],
                        "score": points,
                        "difficulty": game.difficulty.id,
                        "elapsedMs": elapsed,
                        "achieved": self._achievement,
                    }
                ordered = self._ordered_players()
                rank = next(index + 1 for index, player in enumerate(ordered) if player["id"] == caller["id"])
                receipt = {"recorded": True, "personalBest": personal_best, "rank": rank}
            else:
                ordered = None
            result = {
                **self._snapshot(caller, ordered),
                "game": engine.snapshot(game, run_id, now, changed),
                **receipt,
            }
            run["last_request"] = request
            run["last_response"] = result
            return deepcopy(result)
