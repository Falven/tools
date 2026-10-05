"""Bounded, ephemeral Rally — After Hours runs and replay-verified best scores.

Only the middleware's verified delegated claims identify a player. Tokens/raw
identifiers are never decoded, retained or logged. Per-epoch HMAC IDs and a
sanitized name are the only identity data stored. All mutation is lock-protected;
bounded deterministic simulations deliberately run outside that lock.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import secrets
import threading
import time
import unicodedata
from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token

from .engine import CONSTANTS, ReplayError, simulate_replay

RUN_TTL_SECONDS = 30 * 60
MAX_ACTIVE_RUNS = 2_048
MAX_ACTIVE_PER_PLAYER = 4
MAX_PLAYERS = 10_000
# Each active run reserves an eventual receipt slot. A successful finish cannot
# overfill memory or evict another run/receipt to make its own receipt fit.
MAX_RUN_RECORDS = 4_096
LEADERBOARD_LIMIT = 10
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
TIMING_TOLERANCE_MS = 1_000


def _nonempty_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _clean_name(value: str) -> str:
    value = unicodedata.normalize(
        "NFC", "".join(char for char in value if not unicodedata.category(char).startswith("C"))
    )
    return " ".join(value.split()).strip()


def _display_name(claims: Mapping[str, Any]) -> str:
    # Never fall back to an email, username, subject, client ID, or token field.
    candidate = claims.get("name")
    if not isinstance(candidate, str):
        return "Player"
    candidate = _clean_name(candidate)
    private_values = {
        _clean_name(value).casefold()
        for key in ("tid", "oid", "sub", "iss", "email", "upn", "preferred_username", "azp", "appid")
        if isinstance(value := claims.get(key), str) and value.strip()
    }
    if not candidate or "@" in candidate or candidate.casefold() in private_values:
        return "Player"
    return candidate[:48].rstrip() or "Player"


class RallyPongState:
    """One process epoch with injectable clocks/seeds for deterministic tests."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] | None = None,
        seed_factory: Callable[[], int] | None = None,
        max_active: int = MAX_ACTIVE_RUNS,
        max_per_player: int = MAX_ACTIVE_PER_PLAYER,
        max_players: int = MAX_PLAYERS,
        max_records: int = MAX_RUN_RECORDS,
        ttl_seconds: float = RUN_TTL_SECONDS,
    ) -> None:
        if (
            any(type(limit) is not int or limit < 1 for limit in (
                max_active, max_per_player, max_players, max_records
            ))
            or type(ttl_seconds) not in (int, float)
            or not math.isfinite(ttl_seconds)
            or ttl_seconds <= 0
        ):
            raise ValueError("State limits and TTL must be finite and positive.")
        self._clock = clock or time.monotonic
        self._seed_factory = seed_factory or (lambda: secrets.randbits(32))
        self._secret = secrets.token_bytes(32)
        self.epoch = secrets.token_urlsafe(18)
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._receipts: dict[str, dict[str, Any]] = {}
        self._players: dict[str, dict[str, Any]] = {}
        self._achievement = 0
        self._max_active = max_active
        self._max_per_player = max_per_player
        self._max_players = max_players
        self._max_records = max_records
        self._ttl_seconds = ttl_seconds

    def _caller(self) -> dict[str, str] | None:
        # No JWT parsing, headers, token.scopes inference, client identity fields,
        # environment identities, or global "current user" cache is permitted.
        token = get_access_token()
        if token is None:
            return None
        claims = getattr(token, "claims", None)
        if not isinstance(claims, Mapping):
            return None
        scope = claims.get("scp")
        if not isinstance(scope, str) or not scope.split():
            return None
        if isinstance(claims.get("idtyp"), str) and claims["idtyp"].strip().lower() == "app":
            return None
        tenant, object_id = _nonempty_string(claims.get("tid")), _nonempty_string(claims.get("oid"))
        if tenant and object_id:
            identity = ["tenant-object", tenant.lower(), object_id.lower()]
        else:
            issuer, subject = _nonempty_string(claims.get("iss")), _nonempty_string(claims.get("sub"))
            if not issuer or not subject:
                return None
            identity = ["issuer-subject", issuer, subject]
        digest = hmac.new(
            self._secret,
            json.dumps(identity, ensure_ascii=True, separators=(",", ":")).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {"id": f"p_{digest[:32]}", "name": _display_name(claims)}

    def _failure(self, code: str, message: str, **details: Any) -> dict[str, Any]:
        return {
            "error": {"code": code, "message": message, **details},
            "epoch": self.epoch,
            "ephemeral": True,
        }

    def _prune(self, now: float) -> None:
        for records in (self._runs, self._receipts):
            for run_id in [key for key, value in records.items() if now >= value["expires"]]:
                del records[run_id]

    def _ordered_players(self) -> list[dict[str, Any]]:
        return sorted(
            self._players.values(),
            key=lambda player: (-player["score"], player["achieved"], player["id"]),
        )

    def _snapshot(
        self,
        caller: dict[str, str] | None,
        ordered: list[dict[str, Any]] | None = None,
        *,
        offset: int = 0,
        limit: int = LEADERBOARD_LIMIT,
    ) -> dict[str, Any]:
        if ordered is None:
            ordered = self._ordered_players()
        caller_id = caller["id"] if caller else None
        best = self._players.get(caller_id) if caller_id else None
        return {
            "leaderboard": [
                {
                    "rank": offset + index + 1,
                    "id": entry["id"],
                    "name": entry["name"],
                    "score": entry["score"],
                    "hits": entry["hits"],
                    "playerGoals": entry["playerGoals"],
                    "aiGoals": entry["aiGoals"],
                    "bestRally": entry["bestRally"],
                    "won": entry["won"],
                    "isYou": entry["id"] == caller_id,
                }
                for index, entry in enumerate(ordered[offset:offset + limit])
            ],
            "totalPlayers": len(ordered),
            "nextOffset": offset + limit if offset + limit < len(ordered) else None,
            "player": {
                "id": caller["id"],
                "name": caller["name"],
                "best": best["score"] if best else 0,
            } if caller else None,
            "canPost": caller is not None,
            "epoch": self.epoch,
            "ephemeral": True,
        }

    def scores(self, offset: int = 0, limit: int = DEFAULT_PAGE_SIZE) -> dict[str, Any]:
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE:
            return self._failure("invalid_page", "offset must be a nonnegative integer and limit an integer from 1 to 100.")
        caller = self._caller()
        with self._lock:
            self._prune(self._clock())
            return self._snapshot(caller, offset=offset, limit=limit)

    def overview(self) -> dict[str, Any]:
        return {
            **self.scores(limit=LEADERBOARD_LIMIT),
            "title": "Rally — After Hours",
            "description": (
                "A fast paddle duel against a seeded, beatable AI. Scores are replay-verified, "
                "kept only in this server's memory, and reset on restart. Opening posts no "
                "score and starts no run. A delegated user account is required for scored play."
            ),
            "requirements": [
                "The interactive App needs a WebGL2-capable browser; its Three.js renderer is bundled locally.",
                "Use a keyboard, pointer/touchscreen, or gamepad. Clients without App rendering can still read rules and scores.",
            ],
            "controls": [
                "Move the left paddle with the pointer or touch, Up/Down or W/S, or the gamepad's left stick.",
                "Space or P pauses/resumes. M toggles music; N toggles sound effects.",
                "Aim with the paddle's edges; moving through contact adds spin.",
            ],
            "rules": [
                "First to 7 goals wins. A match also ends at exactly 120 seconds of play (14400 fixed 120 Hz ticks).",
                "There is a 0.75-second serve countdown at the start and after every nonterminal goal; countdowns count towards the time limit.",
                "Each player return earns 10 points, each player goal 100, and reaching 7 goals adds a 250-point win bonus.",
                "The ball speeds up on each return, from 100 to at most 180 court units per tick. Paddle edges and motion control its angle.",
                "At the time limit, earned points count but neither a victory nor the 250-point bonus is awarded, even if you are leading.",
                "Hits count player returns; rally and best rally count consecutive contacts by both paddles.",
                "Only complete, timing-checked replays post. Each player keeps one best; equal scores rank by the order first achieved.",
                "Runs and retry receipts expire 30 minutes after start. Scores and per-epoch player IDs disappear on server restart.",
            ],
        }

    def begin(self) -> dict[str, Any]:
        caller = self._caller()
        if caller is None:
            return self._failure("ineligible", "Sign in with a delegated user account to start a scored run.")
        with self._lock:
            now = self._clock()
            self._prune(now)
            owned = [key for key, run in self._runs.items() if run["owner"] == caller["id"]]
            # Starting a fifth game retires ONLY this caller's oldest active game.
            # Dict insertion order is stable even when issue timestamps tie.
            retire_id = owned[0] if len(owned) >= self._max_per_player else None
            retirement = int(retire_id is not None)
            if len(self._runs) - retirement >= self._max_active:
                return self._failure("capacity", "All active run slots are in use. Please try again later.")
            if len(self._runs) + len(self._receipts) - retirement >= self._max_records:
                return self._failure("capacity", "This server's run memory is full. Please try again later.")
            reserved_players = set(self._players)
            reserved_players.update(run["owner"] for run in self._runs.values())
            if caller["id"] not in reserved_players and len(reserved_players) >= self._max_players:
                return self._failure("capacity", "This server's player memory is full. Please try again after a restart.")
            run_id = secrets.token_urlsafe(32)
            while run_id in self._runs or run_id in self._receipts:
                run_id = secrets.token_urlsafe(32)
            seed = self._seed_factory() & 0xFFFFFFFF
            if retire_id is not None:
                del self._runs[retire_id]
            self._runs[run_id] = {
                "owner": caller["id"],
                "seed": seed,
                "issued": now,
                "expires": now + self._ttl_seconds,
            }
            return {
                **self._snapshot(caller),
                "runId": run_id,
                "seed": seed,
                "constants": {
                    **CONSTANTS,
                    "runTtlMs": int(self._ttl_seconds * 1_000),
                    "leaderboardLimit": LEADERBOARD_LIMIT,
                },
            }

    def finish(self, run_id: str, steps: int, inputs: list[list[int]]) -> dict[str, Any]:
        caller = self._caller()
        if caller is None:
            return self._failure("ineligible", "Sign in with a delegated user account to post a score.")
        if type(run_id) is not str or not 20 <= len(run_id) <= 128:
            return self._failure("unavailable_run", "Run unavailable. Start a new run.")
        with self._lock:
            submitted_at = self._clock()
            self._prune(submitted_at)
            receipt = self._receipts.get(run_id)
            if receipt is not None and receipt["owner"] == caller["id"]:
                return deepcopy(receipt["result"])
            run = self._runs.get(run_id)
            if run is None or run["owner"] != caller["id"]:
                # Indistinguishable response for foreign, nonexistent, expired,
                # and retired IDs. Knowing a run ID never confers ownership.
                return self._failure("unavailable_run", "Run unavailable. Start a new run.")

        # Bounded, pure simulation outside the shared-state lock. Concurrent
        # successful finishes of a run converge on one receipt in the commit.
        try:
            game, duration_ms = simulate_replay(run["seed"], steps, inputs)
        except ReplayError as error:
            return self._failure("invalid_replay", str(error))
        actual_ms = (submitted_at - run["issued"]) * 1_000
        if actual_ms + TIMING_TOLERANCE_MS < duration_ms:
            return self._failure(
                "too_fast",
                "The run was submitted sooner than its minimum duration. Retry after playing it in real time.",
                retryAfterMs=math.ceil(duration_ms - actual_ms - TIMING_TOLERANCE_MS),
            )

        with self._lock:
            self._prune(self._clock())
            receipt = self._receipts.get(run_id)
            if receipt is not None and receipt["owner"] == caller["id"]:
                return deepcopy(receipt["result"])
            if self._runs.get(run_id) is not run:
                return self._failure("unavailable_run", "Run unavailable. Start a new run.")
            previous = self._players.get(caller["id"])
            personal_best = previous is None or game["score"] > previous["score"]
            if personal_best:
                self._achievement += 1
                self._players[caller["id"]] = {
                    "id": caller["id"],
                    "name": caller["name"],
                    "score": game["score"],
                    "hits": game["hits"],
                    "playerGoals": game["playerGoals"],
                    "aiGoals": game["aiGoals"],
                    "bestRally": game["bestRally"],
                    "won": game["won"],
                    "achieved": self._achievement,
                }
            ordered = self._ordered_players()
            rank = next(index + 1 for index, entry in enumerate(ordered) if entry["id"] == caller["id"])
            result = {
                **self._snapshot(caller, ordered),
                "runId": run_id,
                "score": game["score"],
                "hits": game["hits"],
                "playerGoals": game["playerGoals"],
                "aiGoals": game["aiGoals"],
                "bestRally": game["bestRally"],
                "won": game["won"],
                "steps": game["steps"],
                "endedByLimit": game["endedByLimit"],
                "rank": rank,
                "personalBest": personal_best,
                "durationMs": duration_ms,
            }
            del self._runs[run_id]
            self._receipts[run_id] = {
                "owner": caller["id"],
                "expires": run["expires"],
                "result": result,
            }
            return deepcopy(result)
