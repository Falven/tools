"""Stdlib tests for Rally physics, verified identity, replay state and MCP schema.

Run: uv run python -m unittest discover -s tests -p 'test_rally_pong.py' -v
Node parity uses the owned test_rally_core.mjs fixture without browser packages.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

from tests.fixtures.catalog import register_catalog_tool
from unittest import mock

from mcp.server import MCPServer
from mcp.server.apps import Apps
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.server.mcpserver.exceptions import ToolError

import catalog_app.tools.rally_pong as app_module
from catalog_app.tools.rally_pong import engine, state as state_module
from catalog_app.tools.rally_pong.state import RallyPongState

ROOT = Path(__file__).resolve().parents[1]
NO_EVENT = {"playerHit": False, "aiHit": False, "wall": False, "goal": None, "ended": False}


def claims_for(player: str = "Alice", **overrides) -> dict:
    return {
        "tid": "private-tenant-A",
        "oid": f"private-object-{player}",
        "sub": f"private-subject-{player}",
        "iss": "https://issuer.example.test/tenant-A",
        "scp": "access_as_user",
        "name": player,
        "email": f"{player.lower()}@private.example.test",
        **overrides,
    }


@contextmanager
def verified(claims: dict | None, *, scopes=None, subject="ignored-token-subject"):
    caller = AuthenticatedUser(AccessToken(
        token="not-a-jwt-and-never-decoded-or-stored",
        client_id="ignored-verified-client",
        scopes=["access_as_user"] if scopes is None else scopes,
        subject=subject,
        claims=claims,
    ))
    token = auth_context_var.set(caller)
    try:
        yield
    finally:
        auth_context_var.reset(token)


class Clock:
    def __init__(self, now: float = 1_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def live(**overrides) -> dict:
    return {**engine.create_game(0), "serveTicks": 0, "vx": 100, "vy": 0, "aiThinkTicks": 1_000, **overrides}


@lru_cache(maxsize=32)
def played_game(seed: int = 0, mode: str = "idle") -> dict:
    """Deterministic fixture controller, never used by the App or server."""
    game = engine.create_game(seed)
    while game["alive"]:
        target = game["target"]
        if mode == "idle":
            target = 0
        elif mode == "follow" or game["steps"] % 12 == 0:
            desired = game["ballY"]
            if mode == "aim" and game["vx"] < 0:
                desired += 950 if game["aiY"] > 0 else -950
            target = max(-1_000, min(1_000, engine.trunc_div(desired * 1_000, engine.PADDLE_LIMIT)))
        engine.advance(game, target)
    return game


class EngineTests(unittest.TestCase):
    def test_initial_contract_and_independent_allocations(self):
        self.assertEqual(engine.CONSTANTS["width"], 20_000)
        self.assertEqual(engine.CONSTANTS["height"], 12_000)
        self.assertEqual(engine.CONSTANTS["tickRate"], 120)
        self.assertEqual(engine.CONSTANTS["maxSteps"], 14_400)
        self.assertEqual(engine.create_game(0), {
            "steps": 0, "rng": 0, "target": 0, "playerY": 0, "aiY": 0,
            "ballX": 0, "ballY": 0, "vx": 0, "vy": 0, "playerGoals": 0,
            "aiGoals": 0, "score": 0, "hits": 0, "rally": 0, "bestRally": 0,
            "alive": True, "won": False, "serveTicks": 90, "inputs": [],
            "ballSpeed": 100, "serveDirection": -1, "aiTarget": 0,
            "aiThinkTicks": 0, "endedByLimit": False,
        })
        first = engine.create_game(0)
        first["inputs"].append([1, 100])
        self.assertEqual(engine.create_game(0)["inputs"], [])
        self.assertEqual(engine.create_game(-1), engine.create_game(0xFFFFFFFF))
        self.assertEqual(engine.create_game(2**32), engine.create_game(0))
        self.assertEqual(engine.create_game(2**32 + 1), engine.create_game(1))

    def test_trunc_div_has_explicit_negative_semantics(self):
        for numerator, denominator, expected in ((9, 4, 2), (-9, 4, -2), (9, -4, -2), (-9, -4, 2), (-1, 4, 0)):
            self.assertEqual(engine.trunc_div(numerator, denominator), expected)
        with self.assertRaises(ZeroDivisionError):
            engine.trunc_div(1, 0)

    def test_serve_ticks_are_included_and_seeded_launch_moves_on_tick91(self):
        game = engine.create_game(0)
        for _ in range(89):
            self.assertEqual(engine.advance(game), NO_EVENT)
            self.assertEqual(game["rng"], 0)
            self.assertEqual(game["ballX"], 0)
            self.assertEqual(game["vx"], 0)
        engine.advance(game)
        self.assertEqual(game["steps"], 90)
        self.assertEqual(game["serveTicks"], 0)
        self.assertEqual(game["rng"], 1_013_904_223)
        self.assertLess(game["vx"], 0)
        self.assertGreaterEqual(abs(game["vy"]), 18)
        self.assertEqual(game["ballX"], 0)
        vx, vy = game["vx"], game["vy"]
        engine.advance(game)
        self.assertEqual((game["ballX"], game["ballY"]), (vx, vy))

    def test_player_bounds_rate_target_mapping_and_canonical_changes(self):
        game = engine.create_game(0)
        for _ in range(40):
            before = game["playerY"]
            engine.advance(game, -1_000)
            self.assertLessEqual(abs(game["playerY"] - before), 250)
        self.assertEqual(game["playerY"], -4_900)
        for _ in range(40):
            engine.advance(game, 1_000)
        self.assertEqual(game["playerY"], 4_900)
        self.assertEqual(game["inputs"], [[1, -1_000], [41, 1_000]])
        tiny = engine.create_game(0)
        engine.advance(tiny, -1)
        self.assertEqual(tiny["playerY"], -4)

    def test_invalid_live_input_is_not_recorded_or_coerced(self):
        for target in (-1001, 1001, 1.0, 1.2, "1", True, False, {}, float("nan"), float("inf")):
            with self.subTest(target=target):
                game = engine.create_game(0)
                engine.advance(game, target)
                self.assertEqual(game["target"], 0)
                self.assertEqual(game["inputs"], [])

    def test_player_center_collision_reflects_and_scores(self):
        game = live(ballX=-8_800, vx=-100)
        self.assertEqual(engine.advance(game), {**NO_EVENT, "playerHit": True})
        self.assertEqual((game["ballX"], game["vx"], game["vy"]), (-8_740, 105, 0))
        self.assertEqual((game["score"], game["hits"], game["rally"], game["bestRally"]), (10, 1, 1, 1))

    def test_ai_center_collision_does_not_score_player_points(self):
        game = live(ballX=8_800)
        self.assertEqual(engine.advance(game), {**NO_EVENT, "aiHit": True})
        self.assertEqual(game["vx"], -105)
        self.assertEqual((game["score"], game["hits"], game["rally"]), (0, 0, 1))

    def test_swept_collision_radius_edges_and_missed_plane(self):
        for y, hit in ((1280, True), (1281, False), (-1280, True), (-1281, False)):
            game = live(ballX=-8_800, ballY=y, vx=-100)
            self.assertEqual(engine.advance(game)["playerHit"], hit)
        game = live(ballX=-8_800, ballY=1_250, vx=-100, vy=100)
        self.assertTrue(engine.advance(game)["playerHit"])  # contact1270, end1350
        for vx in (-100, 100):
            self.assertFalse(engine.advance(live(ballX=-8_900, vx=vx))["playerHit"])

    def test_edge_deflection_motion_spin_and_speed_cap(self):
        for sign in (-1, 1):
            game = live(ballX=-8_800, ballY=1_100 * sign, vx=-100)
            engine.advance(game)
            self.assertEqual((game["vx"], game["vy"]), (70, 78 * sign))
        stationary = live(ballX=-8_800, vx=-100, playerY=245, target=50)
        moving = live(ballX=-8_800, vx=-100, playerY=-5, target=50)
        engine.advance(stationary)
        engine.advance(moving)
        self.assertEqual(stationary["playerY"], moving["playerY"])
        self.assertEqual((stationary["vy"], moving["vy"]), (-17, 9))
        capped = live(ballX=-8_800, ballY=1_350, vx=-100)
        engine.advance(capped, 1000)
        self.assertEqual((capped["vx"], capped["vy"]), (55, 89))
        fast = live(ballX=-8_800, ballY=1_000, vx=-180, rally=100)
        engine.advance(fast)
        self.assertEqual(fast["ballSpeed"], 180)
        self.assertLessEqual(fast["vx"]**2 + fast["vy"]**2, 180**2)

    def test_wall_reflection_preserves_overshoot_and_corner_is_bounded(self):
        for sign in (-1, 1):
            game = live(ballY=5_800 * sign, vy=80 * sign)
            self.assertTrue(engine.advance(game)["wall"])
            self.assertEqual((game["ballY"], game["vy"]), (5_760 * sign, -80 * sign))
        corner = live(ballX=-8_800, ballY=5_810, vx=-100, vy=50, playerY=4_900, target=1000)
        event = engine.advance(corner)
        self.assertTrue(event["wall"] and event["playerHit"])
        self.assertLessEqual(abs(corner["ballY"]), 5_820)

    def test_ai_is_speed_limited_seeded_reactive_and_recovers_on_serve(self):
        first = live(ballY=4_000, aiThinkTicks=0)
        second = deepcopy(first)
        engine.advance(first)
        engine.advance(second)
        self.assertEqual(first, second)
        self.assertEqual(first["aiY"], 65)
        self.assertTrue(14 <= first["aiThinkTicks"] <= 28)
        target, rng = first["aiTarget"], first["rng"]
        first["ballY"] = -4_000
        engine.advance(first)
        self.assertEqual((first["aiTarget"], first["rng"]), (target, rng))
        first.update(serveTicks=10, aiY=1000)
        engine.advance(first)
        self.assertEqual(first["aiTarget"], 0)
        self.assertEqual(first["aiY"], 935)

    def test_goal_reset_and_next_serve_direction(self):
        game = live(ballX=10_170, rally=4, bestRally=4)
        self.assertEqual(engine.advance(game), {**NO_EVENT, "goal": "player"})
        self.assertEqual((game["score"], game["playerGoals"]), (100, 1))
        self.assertEqual((game["rally"], game["bestRally"], game["serveTicks"]), (0, 4, 90))
        self.assertEqual((game["ballX"], game["ballY"], game["vx"], game["vy"]), (0, 0, 0, 0))
        for _ in range(90):
            engine.advance(game)
        self.assertGreater(game["vx"], 0)
        self.assertEqual(game["ballX"], 0)
        loss = live(ballX=-10_170, vx=-100, score=30)
        self.assertEqual(engine.advance(loss)["goal"], "ai")
        self.assertEqual((loss["score"], loss["aiGoals"], loss["serveDirection"]), (30, 1, -1))

    def test_seventh_goal_bonus_is_once_and_terminal_state_is_immutable(self):
        game = live(ballX=10_170, playerGoals=6, score=600)
        self.assertEqual(engine.advance(game), {**NO_EVENT, "goal": "player", "ended": True})
        self.assertEqual(game["score"], 950)
        self.assertTrue(game["won"])
        self.assertFalse(game["alive"])
        self.assertFalse(game["endedByLimit"])
        self.assertEqual(game["serveTicks"], 0)
        ended = deepcopy(game)
        self.assertEqual(engine.advance(game, -1000), {**NO_EVENT, "ended": True})
        self.assertEqual(game, ended)
        loss = live(ballX=-10_170, vx=-100, aiGoals=6)
        self.assertTrue(engine.advance(loss)["ended"])
        self.assertFalse(loss["won"])
        self.assertEqual(loss["score"], 0)

    def test_timeout_keeps_points_without_victory_even_when_leading(self):
        game = live(steps=14_399, playerGoals=6, aiGoals=1, score=750)
        self.assertTrue(engine.advance(game)["ended"])
        self.assertEqual(game["steps"], 14_400)
        self.assertEqual(game["score"], 750)
        self.assertFalse(game["won"])
        self.assertTrue(game["endedByLimit"])
        final_goal = live(steps=14_399, playerGoals=6, ballX=10_170, score=600)
        engine.advance(final_goal)
        self.assertTrue(final_goal["won"])
        self.assertFalse(final_goal["endedByLimit"])

    def test_replay_shape_is_canonical_strict_and_bounded(self):
        invalid = [
            (0, []), (-1, []), (14401, []), (True, []), (1.0, []), ("1", []),
            (20, None), (20, {}), (20, ()), (20, [[0, 1]]), (20, [[21, 1]]),
            (20, [[1, 0]]), (20, [[1, 3], [1, 4]]), (20, [[2, 3], [1, 4]]),
            (20, [[1, 3], [2, 3]]), (20, [[1, -1001]]), (20, [[1, 1001]]),
            (20, [[True, 1]]), (20, [[1, False]]), (20, [[1.0, 1]]), (20, [[1, 1.0]]),
            (20, [[1, "1"]]), (20, [[1]]), (20, [[1, 1, 1]]), (20, [(1, 1)]),
            (1, [[1, 1], [2, 2]]),
        ]
        for steps, inputs in invalid:
            with self.subTest(steps=steps, inputs=inputs), self.assertRaises(engine.ReplayError):
                engine.validate_replay_shape(steps, inputs)
        engine.validate_replay_shape(20, [[1, -1000], [2, 1000], [20, 0]])
        maximum = [[tick, -1 if tick % 2 == 0 else 1] for tick in range(1, 14_401)]
        engine.validate_replay_shape(14_400, maximum)
        with self.assertRaises(engine.ReplayError):
            engine.validate_replay_shape(14_400, maximum + [[14_401, 2]])

    def test_golden_idle_replay_exact_terminal_and_upward_duration_rounding(self):
        game, duration = engine.simulate_replay(0, 1387, [])
        self.assertEqual(duration, 11559)
        self.assertEqual((game["playerGoals"], game["aiGoals"], game["hits"], game["score"]), (0, 7, 0, 0))
        for steps in (1, 1386, 1388, 14400):
            with self.subTest(steps=steps), self.assertRaises(engine.ReplayError):
                engine.simulate_replay(0, steps, [])

    def test_reaction_and_edge_aim_are_attainable_winning_fixtures(self):
        reactive = played_game(0, "reactive")
        self.assertEqual((reactive["steps"], reactive["score"], reactive["hits"]), (11207, 1270, 32))
        self.assertEqual((reactive["playerGoals"], reactive["aiGoals"]), (7, 0))
        self.assertTrue(reactive["won"])
        aimed = played_game(0, "aim")
        self.assertEqual((aimed["steps"], aimed["score"], aimed["hits"]), (6180, 1080, 13))
        self.assertEqual((aimed["playerGoals"], aimed["aiGoals"]), (7, 1))
        self.assertTrue(aimed["won"])
        for fixture in (reactive, aimed):
            game, _ = engine.simulate_replay(0, fixture["steps"], fixture["inputs"])
            self.assertEqual(game, fixture)
        for seed in range(12):
            idle = played_game(seed)
            self.assertLess(idle["steps"], 1800)
            self.assertEqual(idle["aiGoals"], 7)

    def test_exact_timeout_replay_is_complete_without_win_bonus(self):
        fixture = played_game(7, "follow")
        game, duration = engine.simulate_replay(7, fixture["steps"], fixture["inputs"])
        self.assertEqual(game, fixture)
        self.assertEqual(duration, 120_000)
        self.assertEqual(game["steps"], 14_400)
        self.assertTrue(game["endedByLimit"])
        self.assertFalse(game["won"])
        self.assertEqual(game["score"], game["hits"] * 10 + game["playerGoals"] * 100)

    def test_many_seeded_random_inputs_preserve_integer_bounds_and_score_formula(self):
        for seed in range(8):
            game = engine.create_game(seed * 123456789)
            rng = seed
            previous_player, previous_ai = 0, 0
            while game["alive"]:
                rng = (1664525 * rng + 1013904223) & 0xFFFFFFFF
                engine.advance(game, rng % 2001 - 1000)
                for key, value in game.items():
                    if not isinstance(value, (bool, list)):
                        self.assertIs(type(value), int, key)
                self.assertLessEqual(abs(game["playerY"]), 4900)
                self.assertLessEqual(abs(game["aiY"]), 4900)
                self.assertLessEqual(abs(game["playerY"] - previous_player), 250)
                self.assertLessEqual(abs(game["aiY"] - previous_ai), 65)
                self.assertLessEqual(abs(game["ballY"]), 5820)
                self.assertLessEqual(abs(game["ballX"]), 10180)
                self.assertLessEqual(abs(game["vx"]), 180)
                self.assertLessEqual(abs(game["vy"]), 180)
                self.assertEqual(game["score"], game["hits"] * 10 + game["playerGoals"] * 100 + (250 if game["won"] else 0))
                previous_player, previous_ai = game["playerY"], game["aiY"]
            replayed, _ = engine.simulate_replay(seed * 123456789, game["steps"], game["inputs"])
            self.assertEqual(replayed, game)
            self.assertLessEqual(len(game["inputs"]), 14_400)

    @unittest.skipUnless(shutil.which("node"), "Node is required for cross-language parity")
    def test_python_js_complete_replays_events_and_checkpoints_are_identical(self):
        result = subprocess.run(
            [shutil.which("node"), str(ROOT / "tests/test_rally_core.mjs"), "--fixtures"],
            cwd=ROOT, check=True, capture_output=True, text=True, timeout=30,
        )
        fixtures = json.loads(result.stdout)
        self.assertEqual(fixtures["constants"], engine.CONSTANTS)
        for fixture in fixtures["fixtures"]:
            with self.subTest(seed=fixture["seed"], mode=fixture["mode"]):
                expected = fixture["game"]
                self.assertEqual(engine.create_game(fixture["seed"]), fixture["initial"])
                game, duration = engine.simulate_replay(fixture["seed"], expected["steps"], expected["inputs"])
                self.assertEqual(game, expected)
                self.assertEqual(duration, fixture["durationMs"])
                game = engine.create_game(fixture["seed"])
                changes = dict(expected["inputs"])
                events, checkpoints = [], []
                for tick in range(1, expected["steps"] + 1):
                    event = engine.advance(game, changes.get(tick, game["target"]))
                    if any(event.values()):
                        events.append({"tick": tick, **event})
                    if tick % 137 == 0 or not game["alive"]:
                        checkpoints.append({key: value for key, value in game.items() if key != "inputs"})
                self.assertEqual(events, fixture["events"])
                self.assertEqual(checkpoints, fixture["checkpoints"])


class StateTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.store = RallyPongState(clock=self.clock, seed_factory=lambda: 0)

    def play(self, player="Alice", mode="idle", *, store=None, seed=0):
        store = store or self.store
        fixture = played_game(seed, mode)
        with verified(claims_for(player)):
            run = store.begin()
            self.assertNotIn("error", run)
            self.clock.advance(fixture["steps"] / 120 + 1)
            result = store.finish(run["runId"], fixture["steps"], fixture["inputs"])
            self.assertNotIn("error", result)
        return run, result

    def test_anonymous_public_read_has_no_mutation_or_post_eligibility(self):
        result = self.store.overview()
        self.assertEqual(result["title"], "Rally — After Hours")
        self.assertFalse(result["canPost"])
        self.assertIsNone(result["player"])
        self.assertEqual(result["leaderboard"], [])
        self.assertTrue(result["ephemeral"])
        self.assertIn("120 seconds", " ".join(result["rules"]))
        self.assertIn("250", " ".join(result["rules"]))
        self.assertIn("Space or P", " ".join(result["controls"]))
        self.assertIn("M toggles music", " ".join(result["controls"]))
        self.assertIn("left stick", " ".join(result["controls"]))
        self.assertIn("WebGL2", " ".join(result["requirements"]))
        self.assertIn("Three.js", " ".join(result["requirements"]))
        self.assertEqual(self.store.begin()["error"]["code"], "ineligible")
        self.assertEqual(self.store.finish("unknown" * 6, 1387, [])["error"]["code"], "ineligible")
        self.assertEqual((self.store._runs, self.store._players, self.store._receipts), ({}, {}, {}))

    def test_rejects_application_claims_missing_scope_and_missing_verified_identity(self):
        invalid = [
            None, {}, claims_for(scp=None), claims_for(scp=""), claims_for(scp=" \t"),
            claims_for(scp=["access_as_user"]), claims_for(idtyp="app"), claims_for(idtyp=" APP "),
            claims_for(tid=None, oid=None, iss=None, sub=None),
            claims_for(tid=None, oid="object", iss=None),
            claims_for(tid=None, oid=None, iss="issuer", sub=" "),
        ]
        for claims in invalid:
            with self.subTest(claims=claims), verified(claims):
                self.assertFalse(self.store.scores()["canPost"])
                self.assertEqual(self.store.begin()["error"]["code"], "ineligible")
                self.assertEqual(self.store.finish("x" * 43, 1387, [])["error"]["code"], "ineligible")
        self.assertEqual(self.store._runs, {})

    def test_verified_claims_not_token_subject_scopes_or_client_fields_identify_user(self):
        with verified(claims_for(), scopes=[], subject="spoof-one"):
            first = self.store.scores()["player"]
        with verified(claims_for(), scopes=["different"], subject="spoof-two"):
            second = self.store.scores()["player"]
        self.assertEqual(first, second)
        self.assertEqual(first["name"], "Alice")
        self.assertRegex(first["id"], r"^p_[0-9a-f]{32}$")
        self.assertEqual(self.store._players, {})

    def test_tenant_object_pair_is_case_insensitive_and_fallback_is_issuer_scoped(self):
        def identity(**overrides):
            with verified(claims_for(**overrides)):
                return self.store.scores()["player"]["id"]
        self.assertEqual(identity(tid=" TENANT ", oid=" OBJECT "), identity(tid="tenant", oid="object"))
        self.assertNotEqual(identity(tid="one"), identity(tid="two"))
        self.assertNotEqual(identity(oid="one"), identity(oid="two"))
        self.assertEqual(identity(), identity(sub="ignored-sub", iss="ignored-issuer"))
        self.assertNotEqual(identity(tid=None, oid=None, iss="one"), identity(tid=None, oid=None, iss="two"))
        self.assertNotEqual(identity(tid=None, oid=None, sub="one"), identity(tid=None, oid=None, sub="two"))
        self.assertNotEqual(identity(tid="a|b", oid="c"), identity(tid="a", oid="b|c"))

    def test_name_is_sanitized_only_from_name_without_emails_or_identifier_fallback(self):
        cases = [
            (None, "Player"), (123, "Player"), ("", "Player"), (" \n", "Player"),
            ("user@example.test", "Player"), ("Alice <user@example.test>", "Player"),
            ("private-object-Alice", "Player"), ("PRIVATE-OBJECT-ALICE", "Player"),
            ("private-subject-Alice", "Player"), ("private-tenant-A", "Player"),
            ("  A\x00lice  \u202e Smith  ", "Alice Smith"), ("Cafe\u0301", "Café"),
            ("A" * 100, "A" * 48),
        ]
        for candidate, expected in cases:
            with self.subTest(candidate=candidate), verified(claims_for(name=candidate)):
                self.assertEqual(self.store.scores()["player"]["name"], expected)

    def test_new_epoch_resets_board_runs_and_salted_identifiers(self):
        run, result = self.play()
        new_store = RallyPongState(clock=self.clock, seed_factory=lambda: 0)
        with verified(claims_for()):
            fresh = new_store.scores()
            self.assertNotEqual(fresh["epoch"], result["epoch"])
            self.assertNotEqual(fresh["player"]["id"], result["player"]["id"])
            self.assertEqual(fresh["leaderboard"], [])
            self.assertEqual(fresh["player"]["best"], 0)
            self.assertEqual(new_store.finish(run["runId"], 1387, [])["error"]["code"], "unavailable_run")

    def test_begin_exposes_only_issued_seed_constants_and_own_summary(self):
        with verified(claims_for()):
            first, second = self.store.begin(), self.store.begin()
        self.assertNotEqual(first["runId"], second["runId"])
        self.assertEqual(first["seed"], 0)
        self.assertEqual(first["constants"]["runTtlMs"], 1_800_000)
        for key, value in engine.CONSTANTS.items():
            self.assertEqual(first["constants"][key], value)
        self.assertEqual(first["player"]["best"], 0)
        self.assertTrue(first["canPost"])
        self.assertEqual(self.store._players, {})
        first["constants"]["tickRate"] = 2
        with verified(claims_for()):
            self.assertEqual(self.store.begin()["constants"]["tickRate"], 120)

    def test_finish_derives_all_stats_and_retains_no_tokens_or_raw_identifiers(self):
        _, result = self.play(mode="aim")
        expected = played_game(0, "aim")
        for key in ("score", "hits", "playerGoals", "aiGoals", "bestRally", "won", "steps", "endedByLimit"):
            self.assertEqual(result[key], expected[key])
        self.assertTrue(result["personalBest"])
        self.assertEqual(result["rank"], 1)
        retained = json.dumps([self.store._runs, self.store._receipts, self.store._players, result])
        for private in ("private-tenant-A", "private-object-Alice", "private-subject-Alice", "alice@private.example.test", "not-a-jwt", "ignored-token-subject", "ignored-verified-client"):
            self.assertNotIn(private, retained)

    def test_foreign_missing_expired_and_malformed_run_ids_are_indistinguishable(self):
        with verified(claims_for()):
            run = self.store.begin()
        with verified(claims_for("Bob")):
            foreign = self.store.finish(run["runId"], 1387, [])
            for run_id in ("x" * 43, "", 123, True, "x" * 129):
                self.assertEqual(self.store.finish(run_id, 1387, []), foreign)
        self.clock.advance(1_800)
        with verified(claims_for()):
            self.assertEqual(self.store.finish(run["runId"], 1387, []), foreign)
        self.assertEqual(foreign["error"]["code"], "unavailable_run")
        self.assertEqual(self.store._players, {})

    def test_minimum_real_duration_includes_serves_and_too_fast_retry_is_safe(self):
        with verified(claims_for()):
            run = self.store.begin()
            result = self.store.finish(run["runId"], 1387, [])
            self.assertEqual(result["error"]["code"], "too_fast")
            self.assertEqual(result["error"]["retryAfterMs"], 10_559)
            self.assertIn(run["runId"], self.store._runs)
            self.assertEqual(self.store._players, {})
            self.clock.advance(10.560)
            self.assertNotIn("error", self.store.finish(run["runId"], 1387, []))

    def test_verification_cpu_time_does_not_count_as_real_play_time(self):
        original = state_module.simulate_replay

        def slow_verification(*args):
            self.clock.advance(120)
            return original(*args)

        with verified(claims_for()):
            run = self.store.begin()
            with mock.patch.object(state_module, "simulate_replay", side_effect=slow_verification):
                result = self.store.finish(run["runId"], 1387, [])
            self.assertEqual(result["error"]["code"], "too_fast")
            self.assertEqual(self.store._players, {})
            self.assertNotIn("error", self.store.finish(run["runId"], 1387, []))

    def test_receipt_ttl_is_the_original_issue_time_not_finish_or_retry_time(self):
        with verified(claims_for()):
            run = self.store.begin()
            self.clock.advance(120)
            first = self.store.finish(run["runId"], 1387, [])
            self.clock.advance(1_679)
            self.assertEqual(self.store.finish(run["runId"], 1387, []), first)
            self.clock.advance(1)
            result = self.store.finish(run["runId"], 1387, [])
            self.assertEqual(result["error"]["code"], "unavailable_run")
            self.assertEqual(self.store._receipts, {})
            self.assertEqual(self.store.scores()["totalPlayers"], 1)

    def test_invalid_and_incomplete_replays_do_not_consume_or_modify_run(self):
        with verified(claims_for()):
            run = self.store.begin()
            before = deepcopy(self.store._runs)
            self.clock.advance(120)
            for steps, inputs in ((1, []), (1386, []), (1388, []), (True, []), (1387, [[1, 0]]), (1387, [[1, True]])):
                result = self.store.finish(run["runId"], steps, inputs)
                self.assertEqual(result["error"]["code"], "invalid_replay")
                self.assertEqual(self.store._runs, before)
                self.assertEqual(self.store._players, {})
            self.assertNotIn("error", self.store.finish(run["runId"], 1387, []))

    def test_one_personal_best_strict_improvements_and_deterministic_ties(self):
        self.play("Alice")
        self.play("Bob", "follow")
        self.play("Charlie", "follow")
        _, better = self.play("Alice", "aim")
        self.assertTrue(better["personalBest"])
        self.assertEqual(better["rank"], 1)
        achievement = self.store._achievement
        _, equal = self.play("Alice", "aim")
        _, lower = self.play("Bob")
        self.assertFalse(equal["personalBest"])
        self.assertFalse(lower["personalBest"])
        self.assertEqual(lower["score"], 0)
        self.assertEqual(lower["player"]["best"], 960)
        self.assertEqual(self.store._achievement, achievement)
        with verified(claims_for("Charlie")):
            board = self.store.scores()["leaderboard"]
        self.assertEqual([row["name"] for row in board], ["Alice", "Bob", "Charlie"])
        self.assertEqual([row["score"] for row in board], [1080, 960, 960])
        self.assertEqual([row["isYou"] for row in board], [False, False, True])
        self.assertEqual(len(self.store._players), 3)

    def test_idempotent_receipt_is_exact_owned_and_defensively_copied(self):
        run, first = self.play()
        self.play("Bob", "aim")
        with verified(claims_for()):
            again = self.store.finish(run["runId"], 1387, [])
            self.assertEqual(again, first)
            self.assertEqual(again["rank"], 1)  # historical receipt, not new rank2
            again["leaderboard"][0]["name"] = "corrupted"
            again["player"]["best"] = 900000
            self.assertEqual(self.store.finish(run["runId"], 1387, []), first)
            changed_payload = played_game(0, "aim")
            self.assertEqual(self.store.finish(run["runId"], changed_payload["steps"], changed_payload["inputs"]), first)
        with verified(claims_for("Bob")):
            self.assertEqual(self.store.finish(run["runId"], 1387, [])["error"]["code"], "unavailable_run")
        self.assertEqual(self.store._achievement, 2)
        self.assertEqual(len(self.store._receipts), 2)

    def test_simultaneous_finish_converges_on_single_receipt_and_best(self):
        with verified(claims_for()):
            run = self.store.begin()
        self.clock.advance(12)
        barrier = threading.Barrier(4)
        original = state_module.simulate_replay

        def synchronized(*args):
            result = original(*args)
            barrier.wait(timeout=10)
            return result

        def finish_once(_):
            with verified(claims_for()):
                return self.store.finish(run["runId"], 1387, [])

        with mock.patch.object(state_module, "simulate_replay", side_effect=synchronized):
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(finish_once, range(4)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertNotIn("error", results[0])
        self.assertEqual((len(self.store._receipts), len(self.store._players), self.store._achievement), (1, 1, 1))

    def test_simulation_runs_outside_lock_and_expiry_during_verification_cannot_post(self):
        original = state_module.simulate_replay

        def expire(*args):
            acquired = self.store._lock.acquire(blocking=False)
            self.assertTrue(acquired, "replay must not hold shared lock")
            if acquired:
                self.store._lock.release()
            self.clock.advance(1800)
            return original(*args)

        with verified(claims_for()):
            run = self.store.begin()
            self.clock.advance(12)
            with mock.patch.object(state_module, "simulate_replay", side_effect=expire):
                result = self.store.finish(run["runId"], 1387, [])
        self.assertEqual(result["error"]["code"], "unavailable_run")
        self.assertEqual((self.store._players, self.store._receipts), ({}, {}))

    def test_retirement_during_verification_prevents_late_commit(self):
        store = RallyPongState(clock=self.clock, seed_factory=lambda: 0, max_per_player=1)
        original = state_module.simulate_replay

        def retire(*args):
            self.assertNotIn("error", store.begin())
            return original(*args)

        with verified(claims_for()):
            run = store.begin()
            self.clock.advance(12)
            with mock.patch.object(state_module, "simulate_replay", side_effect=retire):
                result = store.finish(run["runId"], 1387, [])
        self.assertEqual(result["error"]["code"], "unavailable_run")
        self.assertEqual((store._players, store._receipts), ({}, {}))
        self.assertEqual(len(store._runs), 1)

    def test_parallel_callers_and_mutated_snapshots_cannot_leak_identity(self):
        def read_for(index):
            with verified(claims_for(f"Person {index}")):
                return self.store.scores()
        with ThreadPoolExecutor(max_workers=5) as pool:
            snapshots = list(pool.map(read_for, range(20)))
        self.assertEqual([s["player"]["name"] for s in snapshots], [f"Person {i}" for i in range(20)])
        self.assertEqual(len({s["player"]["id"] for s in snapshots}), 20)
        self.assertEqual(self.store._players, {})
        self.play("Alice")
        self.play("Bob")
        with verified(claims_for("Bob")):
            snapshot = self.store.scores()
            snapshot["leaderboard"][0]["name"] = "not Alice"
            fresh = self.store.scores()
            self.assertEqual(fresh["leaderboard"][0]["name"], "Alice")
            self.assertEqual(fresh["player"]["name"], "Bob")
        for key in ("runId", "seed", "issued", "expires", "owner"):
            self.assertNotIn(f'"{key}"', json.dumps(fresh))

    def test_fifth_start_retires_only_own_oldest_run(self):
        with verified(claims_for("Bob")):
            foreign = self.store.begin()
        with verified(claims_for()):
            runs = [self.store.begin() for _ in range(5)]
            self.assertNotIn(runs[0]["runId"], self.store._runs)
            self.assertEqual(self.store.finish(runs[0]["runId"], 1387, [])["error"]["code"], "unavailable_run")
            self.assertTrue(all(run["runId"] in self.store._runs for run in runs[1:]))
        self.assertIn(foreign["runId"], self.store._runs)
        self.assertEqual(len(self.store._runs), 5)

    def test_own_retirement_still_works_at_shared_active_record_and_player_caps(self):
        store = RallyPongState(clock=self.clock, seed_factory=lambda: 0,
                               max_active=2, max_records=2, max_players=2, max_per_player=1)
        with verified(claims_for()):
            old = store.begin()
        with verified(claims_for("Bob")):
            foreign = store.begin()
        with verified(claims_for()):
            replacement = store.begin()
            self.assertNotIn("error", replacement)
        self.assertEqual(set(store._runs), {foreign["runId"], replacement["runId"]})
        self.assertNotIn(old["runId"], store._runs)
        with verified(claims_for("Charlie")):
            self.assertEqual(store.begin()["error"]["code"], "capacity")
        self.assertIn(foreign["runId"], store._runs)

    def test_global_capacity_never_evicts_other_players_and_expiry_frees_slots(self):
        store = RallyPongState(clock=self.clock, seed_factory=lambda: 0, max_active=2)
        with verified(claims_for()):
            first = store.begin()
        with verified(claims_for("Bob")):
            second = store.begin()
        before = deepcopy(store._runs)
        with verified(claims_for("Charlie")):
            self.assertEqual(store.begin()["error"]["code"], "capacity")
        self.assertEqual(store._runs, before)
        self.assertEqual(set(store._runs), {first["runId"], second["runId"]})
        self.clock.advance(1800)
        with verified(claims_for("Charlie")):
            self.assertNotIn("error", store.begin())
        self.assertEqual(len(store._runs), 1)

    def test_receipt_slot_reservations_survive_full_capacity_until_original_ttl(self):
        store = RallyPongState(clock=self.clock, seed_factory=lambda: 0, max_records=2)
        first, receipt = self.play(store=store)
        with verified(claims_for("Bob")):
            second = store.begin()
        with verified(claims_for("Charlie")):
            self.assertEqual(store.begin()["error"]["code"], "capacity")
        self.clock.advance(12)
        with verified(claims_for("Bob")):
            self.assertNotIn("error", store.finish(second["runId"], 1387, []))
        with verified(claims_for()):
            self.assertEqual(store.finish(first["runId"], 1387, []), receipt)
            self.assertEqual(store.begin()["error"]["code"], "capacity")
        self.assertEqual((len(store._runs), len(store._receipts)), (0, 2))
        self.clock.advance(1801)
        with verified(claims_for("Charlie")):
            self.assertNotIn("error", store.begin())
        self.assertEqual(store._receipts, {})
        self.assertEqual(len(store._players), 2)  # best scores persist for epoch

    def test_player_slots_are_reserved_at_begin_and_released_on_unplayed_expiry(self):
        store = RallyPongState(clock=self.clock, seed_factory=lambda: 0, max_players=2)
        with verified(claims_for()):
            first = store.begin()
        with verified(claims_for("Bob")):
            second = store.begin()
        with verified(claims_for("Charlie")):
            self.assertEqual(store.begin()["error"]["code"], "capacity")
            self.assertIsNotNone(store.scores()["player"])
        self.clock.advance(12)
        with verified(claims_for()):
            self.assertNotIn("error", store.finish(first["runId"], 1387, []))
        self.clock.advance(1800)
        with verified(claims_for("Charlie")):
            self.assertNotIn("error", store.begin())
        self.assertNotIn(second["runId"], store._runs)
        self.assertEqual(len(store._players), 1)

    def test_concurrent_starts_respect_global_capacity(self):
        store = RallyPongState(clock=self.clock, seed_factory=lambda: 0, max_active=3)
        def begin_for(index):
            with verified(claims_for(f"Person {index}")):
                return store.begin()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(begin_for, range(20)))
        self.assertEqual(sum("error" not in result for result in results), 3)
        self.assertEqual(len(store._runs), 3)
        self.assertEqual(store._players, {})

    def test_pagination_top_ten_absolute_ranks_and_strict_page_bounds(self):
        for index in range(55):
            self.play(f"Person {index}")
        with verified(claims_for("Person 52")):
            first = self.store.scores()
            self.assertEqual((len(first["leaderboard"]), first["totalPlayers"], first["nextOffset"]), (50, 55, 50))
            second = self.store.scores(offset=50)
            self.assertEqual([row["rank"] for row in second["leaderboard"]], [51, 52, 53, 54, 55])
            self.assertTrue(second["leaderboard"][2]["isYou"])
            self.assertIsNone(second["nextOffset"])
            self.assertEqual(len(self.store.overview()["leaderboard"]), 10)
            self.assertEqual(len(self.store.scores(limit=100)["leaderboard"]), 55)
            self.assertEqual(self.store.scores(offset=55)["leaderboard"], [])
        for offset, limit in ((-1, 50), (0, 0), (0, 101), (True, 50), (0, False), (0.0, 50), (0, "50")):
            self.assertEqual(self.store.scores(offset, limit)["error"]["code"], "invalid_page")

    def test_completed_timeout_receipt_has_earned_score_and_no_win(self):
        store = RallyPongState(clock=self.clock, seed_factory=lambda: 7)
        _, result = self.play(mode="follow", store=store, seed=7)
        self.assertTrue(result["endedByLimit"])
        self.assertFalse(result["won"])
        self.assertEqual(result["durationMs"], 120_000)
        self.assertEqual(result["score"], result["hits"] * 10 + result["playerGoals"] * 100)

    def test_constructor_rejects_unbounded_or_invalid_limits(self):
        for key in ("max_active", "max_per_player", "max_players", "max_records"):
            for invalid in (0, -1, True, 1.0, None):
                with self.subTest(key=key, invalid=invalid), self.assertRaises(ValueError):
                    RallyPongState(**{key: invalid})
        for invalid in (0, -1, True, None, "30", float("nan"), float("inf")):
            with self.subTest(ttl=invalid), self.assertRaises(ValueError):
                RallyPongState(ttl_seconds=invalid)


class AppContractTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.store = RallyPongState(clock=self.clock, seed_factory=lambda: 0)
        self.patch = mock.patch.object(app_module, "_STATE", self.store)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        app_module._app_html.cache_clear()
        self.addCleanup(app_module._app_html.cache_clear)
        self.server = MCPServer("rally-pong-test", extensions=[Apps()])

    def test_exact_registration_one_public_zero_input_tool_and_three_app_only_handlers(self):
        with mock.patch.object(Path, "read_text", side_effect=AssertionError("registration read an asset")):
            register_catalog_tool(self.server, "rally_pong")
        tools = asyncio.run(self.server.list_tools())
        self.assertEqual({tool.name for tool in tools}, {"rally_pong", "rally_pong_begin", "rally_pong_finish", "rally_pong_scores"})
        public = [tool for tool in tools if tool.meta["ui"].get("visibility") != ["app"]]
        self.assertEqual([tool.name for tool in public], ["rally_pong"])
        self.assertEqual(public[0].input_schema["properties"], {})
        for tool in tools:
            self.assertIs(tool.input_schema["additionalProperties"], False)
            self.assertEqual(tool.meta["ui"]["resourceUri"], "ui://rally-pong/app.html")
            if tool.name != "rally_pong":
                self.assertEqual(tool.meta["ui"]["visibility"], ["app"])
        finish = next(tool for tool in tools if tool.name == "rally_pong_finish")
        schema = finish.input_schema["properties"]
        self.assertEqual(set(schema), {"run_id", "steps", "inputs"})
        self.assertEqual(schema["steps"]["maximum"], 14400)
        self.assertEqual(schema["steps"]["minimum"], 1)
        self.assertEqual(schema["inputs"]["maxItems"], 14400)
        self.assertEqual(schema["inputs"]["items"]["minItems"], 2)
        self.assertEqual(schema["inputs"]["items"]["maxItems"], 2)
        scores = next(tool for tool in tools if tool.name == "rally_pong_scores")
        self.assertEqual(scores.input_schema["properties"]["limit"]["default"], 50)
        self.assertEqual(scores.input_schema["properties"]["limit"]["maximum"], 100)

    def test_resource_inlines_adjacent_assets_lazily_and_is_cached_without_network_permissions(self):
        register_catalog_tool(self.server, "rally_pong")
        resources = asyncio.run(self.server.list_resources())
        self.assertEqual(len(resources), 1)
        resource = resources[0]
        self.assertEqual(str(resource.uri), app_module.RESOURCE_URI)
        self.assertEqual(resource.mime_type, "text/html;profile=mcp-app")
        self.assertEqual(resource.meta["ui"]["csp"], {"resourceDomains": [], "connectDomains": []})
        self.assertNotIn("permissions", resource.meta["ui"])
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory)
            (assets / "app.html").write_text("<!doctype html><main>Rally</main><!-- app.js -->", encoding="utf-8")
            (assets / "app.js").write_text("globalThis.__rally_test = 1;", encoding="utf-8")
            with mock.patch.object(app_module, "ASSETS", assets):
                result = list(asyncio.run(self.server.read_resource(app_module.RESOURCE_URI)))
                html = result[0].content
                self.assertIn('<script type="module">', html)
                self.assertIn("globalThis.__rally_test = 1;", html)
                self.assertNotIn("<!-- app.js -->", html)
                with mock.patch.object(Path, "read_text", side_effect=AssertionError("cache miss")):
                    self.assertEqual(app_module._app_html(), html)

    def test_missing_or_multiple_asset_markers_fail_clearly_and_are_not_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory)
            (assets / "app.js").write_text("export {};", encoding="utf-8")
            with mock.patch.object(app_module, "ASSETS", assets):
                for html in ("no marker", "<!-- app.js --><!-- app.js -->"):
                    (assets / "app.html").write_text(html, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "exactly one"):
                        app_module._app_html()
                (assets / "app.html").write_text("<!-- app.js -->", encoding="utf-8")
                self.assertIn("export {};", app_module._app_html())

    def test_real_mcp_calls_use_verified_context_and_never_client_score_or_name(self):
        register_catalog_tool(self.server, "rally_pong")
        with verified(claims_for()):
            overview = asyncio.run(self.server.call_tool("rally_pong", {})).structured_content
            self.assertEqual(overview["player"]["name"], "Alice")
            begin = asyncio.run(self.server.call_tool("rally_pong_begin", {})).structured_content
            self.clock.advance(12)
            result = asyncio.run(self.server.call_tool("rally_pong_finish", {
                "run_id": begin["runId"], "steps": 1387, "inputs": [],
            })).structured_content
            self.assertEqual(result["score"], 0)
            self.assertEqual(result["player"]["name"], "Alice")
        with verified(claims_for("Bob")):
            scores = asyncio.run(self.server.call_tool("rally_pong_scores", {})).structured_content
            self.assertEqual(scores["player"]["name"], "Bob")
            self.assertEqual(scores["leaderboard"][0]["name"], "Alice")
            self.assertFalse(scores["leaderboard"][0]["isYou"])
        with verified(claims_for("Application", scp="", idtyp="app")):
            result = asyncio.run(self.server.call_tool("rally_pong", {})).structured_content
            self.assertFalse(result["canPost"])
            denied = asyncio.run(self.server.call_tool("rally_pong_begin", {})).structured_content
            self.assertEqual(denied["error"]["code"], "ineligible")

    def test_mcp_forbids_spoofed_identity_score_seed_clock_and_unknown_fields(self):
        register_catalog_tool(self.server, "rally_pong")
        with verified(claims_for()):
            run = self.store.begin()
            self.clock.advance(12)
            for name, args in (
                ("rally_pong", {}), ("rally_pong_begin", {}),
                ("rally_pong_finish", {"run_id": run["runId"], "steps": 1387, "inputs": []}),
                ("rally_pong_scores", {}),
            ):
                for key in ("score", "name", "oid", "player_id", "seed", "durationMs", "clock"):
                    with self.subTest(tool=name, key=key), self.assertRaises(ToolError):
                        asyncio.run(self.server.call_tool(name, {**args, key: "spoofed"}))
            self.assertEqual(len(self.store._runs), 1)
            self.assertEqual((self.store._players, self.store._receipts), ({}, {}))

    def test_strict_argument_hardening_does_not_modify_another_tools_defaults(self):
        @self.server.tool()
        def unrelated(value: int) -> dict[str, int]:
            return {"value": value}

        before = asyncio.run(self.server.list_tools())[0].input_schema
        register_catalog_tool(self.server, "rally_pong")
        after = next(tool.input_schema for tool in asyncio.run(self.server.list_tools()) if tool.name == "unrelated")
        self.assertEqual(before, after)
        result = asyncio.run(self.server.call_tool("unrelated", {"value": "7", "extra": "ignored"})).structured_content
        self.assertEqual(result, {"value": 7})

    def test_mcp_rejects_boolean_float_string_and_oversized_replay_arguments(self):
        register_catalog_tool(self.server, "rally_pong")
        with verified(claims_for()):
            run = self.store.begin()
            self.clock.advance(12)
            invalid = [
                {"steps": True, "inputs": []}, {"steps": 1387.0, "inputs": []},
                {"steps": "1387", "inputs": []}, {"steps": 14401, "inputs": []},
                {"steps": 1387, "inputs": [[True, 1]]}, {"steps": 1387, "inputs": [[1, False]]},
                {"steps": 1387, "inputs": [[1.0, 1]]}, {"steps": 1387, "inputs": [[1, 1.0]]},
                {"steps": 1387, "inputs": [[1, "1"]]}, {"steps": 1387, "inputs": [[1, 1, 2]]},
                {"steps": 1387, "inputs": [[1, 1]] * 14401},
            ]
            for args in invalid:
                with self.subTest(args=str(args)[:100]), self.assertRaises(ToolError):
                    asyncio.run(self.server.call_tool("rally_pong_finish", {"run_id": run["runId"], **args}))
        self.assertEqual(self.store._players, {})
        for args in ({"offset": True}, {"limit": 1.0}, {"limit": "50"}, {"limit": 101}):
            with self.subTest(args=args), self.assertRaises(ToolError):
                asyncio.run(self.server.call_tool("rally_pong_scores", args))


if __name__ == "__main__":
    unittest.main()
