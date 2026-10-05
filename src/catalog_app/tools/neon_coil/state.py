"""Ephemeral, process-local Neon Coil runs and verified high scores.

Only the MCP middleware's verified claims identify a player. Neither tokens nor
raw subject/tenant/object identifiers are retained, logged, or sent to the App.
All retained state is bounded dictionaries protected by one threading lock.
Restarting this module's process resets the leaderboard, IDs, runs, and epoch.
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

from .engine import (
    HEIGHT,
    MAX_TICKS,
    MAX_TURNS,
    POINTS_PER_FOOD,
    RIGHT,
    WIDTH,
    ReplayError,
    simulate_replay,
)

RUN_TTL_SECONDS = 2 * 60 * 60
MAX_ACTIVE_RUNS = 2048
MAX_ACTIVE_PER_PLAYER = 4
MAX_PLAYERS = 10_000
# Each active run reserves its eventual receipt slot. Completed receipts remain
# idempotent until the original run's TTL, without evicting another active run.
MAX_RUN_RECORDS = 4096
LEADERBOARD_LIMIT = 10
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
TIMING_TOLERANCE_MS = 1000


def _nonempty_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _display_name(claims: Mapping[str, Any]) -> str:
    candidate = claims.get("name")
    if not isinstance(candidate, str):
        return "Player"
    candidate = unicodedata.normalize(
        "NFC", "".join(char for char in candidate if not unicodedata.category(char).startswith("C"))
    )
    candidate = " ".join(candidate.split()).strip()
    # Name is the only display-name source. Some tenants put an email or an
    # opaque subject in it; do not accidentally publish those as display names.
    private_values = {
        value.strip()
        for key in ("oid", "sub", "email", "upn", "preferred_username")
        if isinstance(value := claims.get(key), str) and value.strip()
    }
    if not candidate or "@" in candidate or candidate in private_values:
        return "Player"
    return candidate[:48].rstrip() or "Player"


class NeonCoilState:
    """One server epoch, with injectable clock/seed sources for deterministic tests."""

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
        if (
            any(type(limit) is not int or limit < 1 for limit in (
                max_active, max_per_player, max_players, max_records
            ))
            or ttl_seconds <= 0
        ):
            raise ValueError("State limits must be positive.")

    def _caller(self) -> dict[str, str] | None:
        # No JWT decoding, token.scopes inference, HTTP headers, environment
        # identities, client-supplied names, or cached global current-user state.
        token = get_access_token()
        if token is None:
            return None
        claims = token.claims
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
            # The fallback is still inside a verified, delegated MCP context.
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
                    "foods": entry["foods"],
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
            "title": "Neon Coil",
            "description": (
                "A neon Snake arcade game with replay-verified shared high scores. "
                "The leaderboard lives only in this server's memory and resets on restart. "
                "A signed-in delegated user account is required to post a score."
            ),
            "rules": [
                "Steer with arrow keys or WASD. Reversing directly into your neck is not allowed.",
                "Eat food to grow by one cell and earn 100 points on the 24 by 18 board.",
                "The tick starts at 150 ms and gets 8 ms faster every five foods, down to 70 ms.",
                "Hitting a wall or your body ends the run; entering a vacating tail cell is legal.",
                "Fill all 432 cells to win. A session also ends at 18000 ticks; only complete, timing-checked replays post scores.",
                "Each player has one best score. Equal scores are ranked by when they were first achieved.",
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
            # Refreshes/abandoned tabs must not lock a player out for two hours.
            # Dict insertion order provides a stable tie-break for equal issue times.
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
                    "width": WIDTH,
                    "height": HEIGHT,
                    "initialDirection": RIGHT,
                    "pointsPerFood": POINTS_PER_FOOD,
                    "initialStepMs": 150,
                    "minimumStepMs": 70,
                    "speedEveryFoods": 5,
                    "speedReductionMs": 8,
                    "maxSteps": MAX_TICKS,
                    "maxTurns": MAX_TURNS,
                    "runTtlMs": int(self._ttl_seconds * 1000),
                    "leaderboardLimit": LEADERBOARD_LIMIT,
                },
            }

    def finish(self, run_id: str, steps: int, turns: list[list[int]]) -> dict[str, Any]:
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
                # Same response for nonexistent, expired, retired, or foreign IDs.
                return self._failure("unavailable_run", "Run unavailable. Start a new run.")

        # Simulation is bounded, does not access shared state, and deliberately
        # runs outside the lock. Concurrent successful retries converge below.
        try:
            game, duration_ms = simulate_replay(run["seed"], steps, turns)
        except ReplayError as error:
            return self._failure("invalid_replay", str(error))
        actual_ms = (submitted_at - run["issued"]) * 1000
        if actual_ms + TIMING_TOLERANCE_MS < duration_ms:
            return self._failure(
                "too_fast",
                "The run was submitted sooner than its minimum possible duration. Retry after playing it in real time.",
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
                    "foods": game["foods"],
                    "achieved": self._achievement,
                }
            ordered = self._ordered_players()
            rank = next(index + 1 for index, entry in enumerate(ordered) if entry["id"] == caller["id"])
            result = {
                **self._snapshot(caller, ordered),
                "runId": run_id,
                "score": game["score"],
                "foods": game["foods"],
                "steps": game["steps"],
                "won": game["won"],
                "endedByLimit": game["alive"] and game["steps"] == MAX_TICKS,
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
