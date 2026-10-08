"""Stdlib unittest coverage for deterministic Neon Coil and its MCP boundary.

Run: uv run python -m unittest discover -s tests -p 'test_neon_coil.py' -v
The parity test also runs the checked-in Node fixture when Node is installed.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tests.fixtures.catalog import register_catalog_tool
from unittest import mock

from mcp.server import MCPServer
from mcp.server.apps import Apps
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.server.mcpserver.exceptions import ToolError

import catalog_app.tools.neon_coil as app_module
from catalog_app.tools.neon_coil import engine, state as state_module
from catalog_app.tools.neon_coil.state import NeonCoilState

ROOT = Path(__file__).resolve().parents[1]
SEED = 305419896
TURNS = [
    [11, 2], [19, 1], [20, 0], [37, 3], [38, 2], [39, 3], [52, 2],
    [53, 1], [58, 2], [72, 1], [73, 0], [86, 1], [93, 0], [94, 3],
    [100, 2], [106, 3], [107, 0], [109, 3], [117, 2], [118, 1],
    [125, 2], [134, 3], [135, 0], [145, 3], [150, 0], [151, 1],
    [159, 2], [162, 3], [168, 2], [169, 1], [176, 0], [179, 1],
    [181, 2], [186, 3], [201, 2], [202, 1], [212, 2], [217, 1],
    [218, 0], [224, 1], [233, 0], [234, 3], [244, 2], [246, 3],
    [250, 0], [258, 3],
]


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
    """Install the same already-verified context the MCP middleware provides."""
    caller = AuthenticatedUser(AccessToken(
        token="not-a-jwt-and-never-decoded",
        client_id="verified-client",
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
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def near_full_board() -> dict:
    game = engine.create_game(0)
    path = [
        [engine.WIDTH - 1 - index if y % 2 else index, y]
        for y in range(engine.HEIGHT)
        for index in range(engine.WIDTH)
    ]
    game.update(
        body=list(reversed(path[:-1])),
        direction=3,
        food=path[-1],
        foods=426,
        score=42600,
    )
    return game


def limit_turns() -> list[list[int]]:
    # A 4x4-cell perimeter, clear of seed 0's initial food at [6,17].
    cycle = [1, 0, 3, 2]
    return [[tick, cycle[((tick - 1) // 4) % 4]] for tick in range(5, engine.MAX_TICKS + 1, 4)]


class EngineTests(unittest.TestCase):
    def test_initial_contract(self):
        self.assertEqual(engine.WIDTH, 24)
        self.assertEqual(engine.HEIGHT, 18)
        self.assertEqual(engine.DIRS, ((0, -1), (1, 0), (0, 1), (-1, 0)))
        self.assertEqual(engine.create_game(0), {
            "body": [[8, 9], [7, 9], [6, 9], [5, 9], [4, 9]],
            "direction": 1, "food": [6, 17], "rng": 1013904223,
            "score": 0, "foods": 0, "steps": 0, "alive": True,
            "won": False, "turns": [],
        })

    def test_seed_unsigned_and_lcg_row_major(self):
        fixtures = [
            (0, 1013904223, [6, 17]),
            (1, 1015568748, [13, 2]),
            (0xFFFFFFFF, 1012239698, [23, 13]),
            (SEED, 1967335287, [18, 10]),
        ]
        for seed, rng, food in fixtures:
            with self.subTest(seed=seed):
                game = engine.create_game(seed)
                empty = [[x, y] for y in range(18) for x in range(24) if [x, y] not in game["body"]]
                self.assertEqual(game["rng"], rng)
                self.assertEqual(game["food"], food)
                self.assertEqual(game["food"], empty[rng % len(empty)])
        self.assertEqual(engine.create_game(-1), engine.create_game(0xFFFFFFFF))
        self.assertEqual(engine.create_game(2**32), engine.create_game(0))
        self.assertEqual(engine.create_game(2**32 + 1), engine.create_game(1))

    def test_independent_game_allocations(self):
        first, second = engine.create_game(0), engine.create_game(0)
        first["body"][0][0] = 100
        first["turns"].append([1, 0])
        self.assertEqual(second["body"][0], [8, 9])
        self.assertEqual(second["turns"], [])

    def test_first_tick_reversal_and_record_only_changes(self):
        game = engine.create_game(0)
        engine.advance(game, 3)
        self.assertEqual(game["steps"], 1)
        self.assertEqual(game["direction"], 1)
        self.assertEqual(game["turns"], [])
        engine.advance(game, 0)
        engine.advance(game, 0)
        engine.advance(game, 2)
        self.assertEqual(game["turns"], [[2, 0]])
        engine.advance(game, 3)
        self.assertEqual(game["turns"], [[2, 0], [5, 3]])

    def test_bad_core_directions_do_not_commit(self):
        for direction in (-1, 4, 1.1, "0", True, {}):
            with self.subTest(direction=direction):
                game = engine.create_game(0)
                engine.advance(game, direction)
                self.assertEqual(game["direction"], 1)
                self.assertEqual(game["turns"], [])

    def test_food_growth_points_and_one_rng_draw(self):
        game = engine.create_game(SEED)
        for _ in range(10):
            engine.advance(game)
        before = game["rng"]
        event = engine.advance(game, 2)
        self.assertEqual(event, {"ate": True, "dead": False, "won": False})
        self.assertEqual(len(game["body"]), 6)
        self.assertEqual(game["score"], 100)
        self.assertEqual(game["foods"], 1)
        self.assertEqual(game["rng"], (1664525 * before + 1013904223) & 0xFFFFFFFF)
        self.assertNotIn(game["food"], game["body"])
        after = game["rng"]
        engine.advance(game)
        self.assertEqual(game["rng"], after)

    def test_speed_boundaries(self):
        for foods, expected in [(0, 150), (4, 150), (5, 142), (9, 142),
                                (10, 134), (49, 78), (50, 70), (427, 70)]:
            self.assertEqual(engine.step_ms(foods), expected)

    def test_fatal_tick_preserves_cells_and_terminal_noop(self):
        game = engine.create_game(0)
        for _ in range(15):
            engine.advance(game)
        before = deepcopy(game["body"])
        event = engine.advance(game)
        self.assertEqual(event, {"ate": False, "dead": True, "won": False})
        self.assertEqual(game["steps"], 16)
        self.assertEqual(game["body"], before)
        ended = deepcopy(game)
        engine.advance(game, 0)
        self.assertEqual(game, ended)

    def test_fatal_turn_is_recorded(self):
        game, duration = engine.simulate_replay(0, 24, [[16, 2], [24, 1]])
        self.assertEqual(game["body"][0], [23, 17])
        self.assertEqual(game["turns"], [[16, 2], [24, 1]])
        self.assertEqual(game["steps"], 24)
        self.assertFalse(game["alive"])
        self.assertEqual(duration, 24 * 150)

    def test_vacating_tail_is_legal(self):
        game = engine.create_game(0)
        game.update(body=[[2, 2], [2, 3], [1, 3], [1, 2]], direction=0, food=[10, 10])
        event = engine.advance(game, 3)
        self.assertEqual(event, {"ate": False, "dead": False, "won": False})
        self.assertEqual(game["body"], [[1, 2], [2, 2], [2, 3], [1, 3]])

    def test_growing_tail_and_other_body_collisions_are_fatal(self):
        game = engine.create_game(0)
        game.update(body=[[2, 2], [2, 3], [1, 3], [1, 2]], direction=0, food=[1, 2])
        body = deepcopy(game["body"])
        self.assertTrue(engine.advance(game, 3)["dead"])
        self.assertEqual(game["body"], body)
        self.assertEqual(game["score"], 0)
        game = engine.create_game(0)
        game.update(body=[[2, 2], [2, 3], [1, 3], [1, 2], [1, 1]], direction=0, food=[10, 10])
        body = deepcopy(game["body"])
        self.assertTrue(engine.advance(game, 3)["dead"])
        self.assertEqual(game["body"], body)

    def test_full_board_victory_without_rng_draw(self):
        game = near_full_board()
        rng = game["rng"]
        self.assertEqual(engine.advance(game), {"ate": True, "dead": False, "won": True})
        self.assertEqual(len(game["body"]), 432)
        self.assertEqual(game["foods"], 427)
        self.assertEqual(game["score"], 42700)
        self.assertIsNone(game["food"])
        self.assertEqual(game["rng"], rng)
        self.assertFalse(game["alive"])
        ended = deepcopy(game)
        engine.advance(game)
        self.assertEqual(game, ended)

    def test_replay_accepts_victory_terminal(self):
        with mock.patch.object(engine, "create_game", return_value=near_full_board()):
            game, duration = engine.simulate_replay(0, 1, [])
        self.assertTrue(game["won"])
        self.assertFalse(game["alive"])
        self.assertEqual(duration, 70)

    def test_straight_replay_requires_exact_terminal_tick(self):
        game, duration = engine.simulate_replay(0, 16, [])
        self.assertEqual(game["score"], 0)
        self.assertFalse(game["alive"])
        self.assertEqual(duration, 2400)
        for steps in (1, 15, 17, 18000):
            with self.subTest(steps=steps), self.assertRaises(engine.ReplayError):
                engine.simulate_replay(0, steps, [])

    def test_replay_shape_rejects_bounds_types_duplicates_and_reversal(self):
        invalid = [
            (0, []), (-1, []), (18001, []), (True, []), (16.0, []), ("16", []),
            (16, None), (16, ()), (18000, [[1, 0]] * 18001),
            (16, [[1]]), (16, [[1, 0, 3]]), (16, [(1, 0)]),
            (16, [[0, 0]]), (16, [[-1, 0]]), (16, [[17, 0]]),
            (16, [[1, 0], [1, 3]]), (16, [[2, 0], [1, 3]]),
            (16, [[1, -1]]), (16, [[1, 4]]), (16, [[True, 0]]),
            (16, [[1, False]]), (16, [[1.0, 0]]), (16, [[1, "0"]]),
            (16, [[1, 3]]), (16, [[1, 1]]),
            (16, [[1, 0], [2, 2]]), (16, [[1, 0], [2, 0]]),
        ]
        for steps, turns in invalid:
            with self.subTest(steps=steps, turns=repr(turns)[:80]):
                with self.assertRaises(engine.ReplayError):
                    engine.simulate_replay(0, steps, turns)

    def test_fixed_replay_score_and_geometry(self):
        game, duration = engine.simulate_replay(SEED, 264, TURNS)
        self.assertEqual(game["score"], 2000)
        self.assertEqual(game["foods"], 20)
        self.assertEqual(game["rng"], 1929958827)
        self.assertEqual(game["food"], [4, 10])
        self.assertEqual(game["body"][0], [0, 4])
        self.assertEqual(game["body"][-1], [14, 10])
        self.assertEqual(len(game["body"]), 25)
        self.assertEqual(game["turns"], TURNS)
        self.assertFalse(game["alive"])
        self.assertLess(duration, 264 * 150)

    def test_live_replay_only_completes_at_exact_session_limit(self):
        turns = limit_turns()
        game, duration = engine.simulate_replay(0, 18000, turns)
        self.assertTrue(game["alive"])
        self.assertFalse(game["won"])
        self.assertEqual(game["score"], 0)
        self.assertEqual(duration, 18000 * 150)
        with self.assertRaises(engine.ReplayError):
            engine.simulate_replay(0, 17999, turns)
        engine.advance(game, 1)
        self.assertEqual(game["steps"], 18001)  # core itself stays cap-free

    @unittest.skipUnless(shutil.which("node"), "Node is required for JS/Python fixture parity")
    def test_javascript_fixture_parity(self):
        completed = subprocess.run(
            ["node", str(ROOT / "tests/test_neon_core.mjs"), "--fixture"],
            cwd=ROOT, capture_output=True, text=True, check=True, timeout=30,
        )
        fixture = json.loads(completed.stdout)
        self.assertEqual(fixture["seed"], SEED)
        self.assertEqual(fixture["turns"], TURNS)
        self.assertEqual(engine.create_game(SEED), fixture["initial"])
        game, duration = engine.simulate_replay(fixture["seed"], fixture["steps"], fixture["turns"])
        self.assertEqual(game, fixture["game"])
        self.assertEqual(duration, fixture["durationMs"])
        replay = engine.create_game(SEED)
        placements = [{"tick": 0, "food": replay["food"][:], "rng": replay["rng"]}]
        changes = dict(TURNS)
        for tick in range(1, 265):
            event = engine.advance(replay, changes.get(tick, replay["direction"]))
            if event["ate"]:
                placements.append({"tick": tick, "food": replay["food"][:], "rng": replay["rng"]})
        self.assertEqual(placements, fixture["placements"])


class StateTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.store = NeonCoilState(clock=self.clock, seed_factory=lambda: SEED)

    def play(self, name="Alice", steps=16, turns=None, store=None):
        store = store or self.store
        turns = [] if turns is None else turns
        with verified(claims_for(name)):
            run = store.begin()
            self.assertNotIn("error", run)
            _, duration = engine.simulate_replay(run["seed"], steps, turns)
            self.clock.advance(duration / 1000 + 0.01)
            result = store.finish(run["runId"], steps, turns)
            self.assertNotIn("error", result)
            return run, result

    def test_no_context_and_application_only_cannot_start_or_post(self):
        token = auth_context_var.set(None)
        try:
            self.assertEqual(self.store.begin()["error"]["code"], "ineligible")
            self.assertEqual(self.store.finish("x" * 43, 16, [])["error"]["code"], "ineligible")
            self.assertIsNone(self.store.scores()["player"])
        finally:
            auth_context_var.reset(token)
        cases = [
            None,
            claims_for(scp=""), claims_for(scp=" \t\n"), claims_for(scp=["access_as_user"]),
            claims_for(scp=None, roles=["access_as_user.Application"]),
            claims_for(idtyp="app"), claims_for(idtyp=" APP "),
            claims_for(tid=None, oid=None, iss=None),
            claims_for(tid=None, oid=None, sub=None),
        ]
        for claims in cases:
            with self.subTest(claims=claims), verified(claims):
                self.assertEqual(self.store.begin()["error"]["code"], "ineligible")
                self.assertEqual(self.store.finish("x" * 43, 16, [])["error"]["code"], "ineligible")
                view = self.store.scores()
                self.assertIsNone(view["player"])
                self.assertFalse(view["canPost"])
        self.assertEqual(self.store._runs, {})
        self.assertEqual(self.store._players, {})

    def test_identity_is_from_claims_not_scopes_or_token_subject(self):
        with verified(claims_for(scp=""), scopes=["access_as_user"]):
            self.assertIsNone(self.store.scores()["player"])
        with verified(claims_for(), scopes=[]):
            self.assertIsNotNone(self.store.scores()["player"])
        with verified(claims_for(tid=None, oid=None, sub=None), subject="external-subject"):
            self.assertIsNone(self.store.scores()["player"])

    def test_tenant_object_identity_and_authenticated_subject_fallback(self):
        with verified(claims_for()):
            original = self.store.scores()["player"]["id"]
        with verified(claims_for(sub="different-ignored-subject", name="A new display name")):
            self.assertEqual(original, self.store.scores()["player"]["id"])
        with verified(claims_for(tid="PRIVATE-TENANT-A", oid="PRIVATE-OBJECT-ALICE")):
            self.assertEqual(original, self.store.scores()["player"]["id"])
        with verified(claims_for(tid="different-private-tenant")):
            self.assertNotEqual(original, self.store.scores()["player"]["id"])
        with verified(claims_for(tid=None, oid=None)):
            fallback = self.store.scores()["player"]["id"]
            self.assertNotEqual(original, fallback)
        with verified(claims_for(tid=None, oid=None, iss="https://issuer.example.test/other")):
            self.assertNotEqual(fallback, self.store.scores()["player"]["id"])

    def test_ephemeral_salted_public_ids_do_not_expose_raw_identity(self):
        claims = claims_for()
        other_store = NeonCoilState(clock=self.clock)
        with verified(claims):
            view = self.store.begin()
            other = other_store.scores()
            self.assertNotEqual(view["player"]["id"], other["player"]["id"])
            self.assertNotEqual(view["epoch"], other["epoch"])
            self.assertRegex(view["player"]["id"], r"^p_[0-9a-f]{32}$")
        serialized = json.dumps(view) + repr(self.store._runs)
        for key in ("tid", "oid", "sub", "iss", "email"):
            self.assertNotIn(claims[key], serialized)
        self.assertNotIn("not-a-jwt-and-never-decoded", serialized)

    def test_names_strip_unicode_controls_cap48_and_never_fallback_to_email(self):
        with verified(claims_for(name="  Ju\u0301lia\x00\u202e \n🐍  ")):
            self.assertEqual(self.store.scores()["player"]["name"], "Júlia 🐍")
        with verified(claims_for(name="名前" * 50)):
            self.assertEqual(len(self.store.scores()["player"]["name"]), 48)
        for name in (None, 22, "\x00\u202e\t", "someone@private.example.test", "private-object-Alice", "private-subject-Alice"):
            with self.subTest(name=name), verified(claims_for(name=name)):
                self.assertEqual(self.store.scores()["player"]["name"], "Player")

    def test_begin_contract_seed_and_unguessable_ids(self):
        with verified(claims_for()):
            first = self.store.begin()
            second = self.store.begin()
        self.assertNotEqual(first["runId"], second["runId"])
        self.assertRegex(first["runId"], r"^[A-Za-z0-9_-]{43}$")
        self.assertEqual(first["seed"], SEED)
        self.assertTrue(first["ephemeral"])
        self.assertTrue(first["canPost"])
        self.assertEqual(first["constants"]["maxSteps"], 18000)
        self.assertEqual(first["constants"]["runTtlMs"], 7200000)
        self.assertEqual(first["player"]["best"], 0)
        self.assertEqual(first["leaderboard"], [])

    def test_main_fallback_is_useful_and_posting_is_explicit(self):
        with verified(claims_for()):
            view = self.store.overview()
        self.assertEqual(view["title"], "Neon Coil")
        self.assertGreaterEqual(len(view["rules"]), 5)
        self.assertIn("restart", view["description"])
        self.assertIn("player", view)
        self.assertIn("leaderboard", view)
        self.assertEqual(self.store._players, {})
        self.assertEqual(self.store._runs, {})

    def test_foreign_ids_never_reveal_or_change_runs_or_receipts(self):
        with verified(claims_for("Alice")):
            run = self.store.begin()
        self.clock.advance(3)
        with verified(claims_for("Bob")):
            foreign = self.store.finish(run["runId"], 16, [])
            missing = self.store.finish("z" * 43, 16, [])
            self.assertEqual(foreign, missing)
        with verified(claims_for("Alice")):
            receipt = self.store.finish(run["runId"], 16, [])
            self.assertNotIn("error", receipt)
        with verified(claims_for("Bob")):
            self.assertEqual(self.store.finish(run["runId"], 16, []), missing)
        self.assertEqual(len(self.store._players), 1)

    def test_invalid_replay_leaves_score_unchanged_and_can_be_corrected(self):
        with verified(claims_for()):
            run = self.store.begin()
            self.clock.advance(5)
            for steps, turns in [(15, []), (17, []), (16, [[1, 3]]), (16, [[1, 0], [1, 3]])]:
                result = self.store.finish(run["runId"], steps, turns)
                self.assertEqual(result["error"]["code"], "invalid_replay")
                self.assertEqual(self.store._players, {})
                self.assertIn(run["runId"], self.store._runs)
            result = self.store.finish(run["runId"], 16, [])
            self.assertEqual(result["score"], 0)
            self.assertEqual(result["foods"], 0)

    def test_minimum_theoretical_duration_with_at_most_1000ms_tolerance(self):
        self.clock.now = 0.0
        with verified(claims_for()):
            run = self.store.begin()
            fast = self.store.finish(run["runId"], 16, [])
            self.assertEqual(fast["error"]["code"], "too_fast")
            self.assertEqual(fast["error"]["retryAfterMs"], 1400)
            self.clock.advance(1.399)
            self.assertEqual(self.store.finish(run["runId"], 16, [])["error"]["code"], "too_fast")
            self.clock.advance(0.002)
            self.assertEqual(self.store.finish(run["runId"], 16, [])["score"], 0)

    def test_pauses_add_walltime_without_invalidating_replay(self):
        with verified(claims_for()):
            run = self.store.begin()
            self.clock.advance(500)
            result = self.store.finish(run["runId"], 16, [])
            self.assertEqual(result["score"], 0)
            self.assertEqual(result["durationMs"], 2400)

    def test_verification_cpu_time_does_not_count_as_play_time(self):
        original = state_module.simulate_replay

        def delayed(*args):
            self.clock.advance(10)
            return original(*args)

        with verified(claims_for()):
            run = self.store.begin()
            with mock.patch.object(state_module, "simulate_replay", side_effect=delayed):
                result = self.store.finish(run["runId"], 16, [])
            self.assertEqual(result["error"]["code"], "too_fast")
            self.assertEqual(self.store._players, {})

    def test_one_highest_score_per_player_and_first_achieved_ties(self):
        _, alice_first = self.play("Alice", 17, [[11, 2], [12, 1]])
        _, bob = self.play("Bob", 17, [[11, 2], [12, 1]])
        self.assertEqual(alice_first["score"], 100)
        self.assertEqual(bob["rank"], 2)
        self.play("Charlie", 264, TURNS)
        _, alice_best = self.play("Alice", 264, TURNS)
        self.assertEqual(alice_best["rank"], 2)
        self.assertTrue(alice_best["personalBest"])
        _, equal = self.play("Alice", 264, TURNS)
        self.assertFalse(equal["personalBest"])
        self.assertEqual(equal["rank"], 2)
        _, lower = self.play("Bob")
        self.assertFalse(lower["personalBest"])
        self.assertEqual(lower["score"], 0)
        self.assertEqual(lower["player"]["best"], 100)
        self.assertEqual(len(self.store._players), 3)
        with verified(claims_for("Alice")):
            board = self.store.scores()["leaderboard"]
        self.assertEqual([row["name"] for row in board], ["Charlie", "Alice", "Bob"])
        self.assertEqual([row["score"] for row in board], [2000, 2000, 100])
        self.assertEqual([row["rank"] for row in board], [1, 2, 3])
        self.assertEqual([row["isYou"] for row in board], [False, True, False])

    def test_top_ten_and_rank_outside_top_ten(self):
        last = None
        for index in range(12):
            _, last = self.play(f"Player {11 - index}")
        self.assertEqual(last["rank"], 12)
        self.assertEqual(len(last["leaderboard"]), 10)
        self.assertFalse(any(row["isYou"] for row in last["leaderboard"]))
        self.assertEqual(last["leaderboard"][0]["name"], "Player 11")

    def test_pagination_exposes_every_player_with_absolute_ranks(self):
        for index in range(55):
            self.play(f"Person {index}")
        with verified(claims_for("Person 52")):
            first = self.store.scores()
            self.assertEqual(len(first["leaderboard"]), 50)
            self.assertEqual(first["totalPlayers"], 55)
            self.assertEqual(first["nextOffset"], 50)
            self.assertEqual([row["rank"] for row in first["leaderboard"]], list(range(1, 51)))
            second = self.store.scores(offset=first["nextOffset"], limit=50)
            self.assertEqual(len(second["leaderboard"]), 5)
            self.assertEqual([row["rank"] for row in second["leaderboard"]], list(range(51, 56)))
            self.assertIsNone(second["nextOffset"])
            self.assertEqual(second["totalPlayers"], 55)
            self.assertTrue(second["leaderboard"][2]["isYou"])
            self.assertEqual(second["leaderboard"][2]["id"], second["player"]["id"])
            combined = first["leaderboard"] + second["leaderboard"]
            self.assertEqual(len({row["id"] for row in combined}), 55)
            self.assertEqual(len(self.store.overview()["leaderboard"]), 10)
            self.assertEqual(len(self.store.scores(limit=100)["leaderboard"]), 55)
            empty = self.store.scores(offset=55, limit=10)
            self.assertEqual(empty["leaderboard"], [])
            self.assertIsNone(empty["nextOffset"])
            self.assertEqual(empty["player"]["name"], "Person 52")

    def test_pagination_rejects_invalid_bounds_and_coercions(self):
        for offset, limit in [(-1, 50), (0, 0), (0, 101), (True, 50), (0, False), (0.0, 50), (0, "50")]:
            with self.subTest(offset=offset, limit=limit):
                self.assertEqual(self.store.scores(offset, limit)["error"]["code"], "invalid_page")

    def test_exact_idempotent_receipt_and_no_duplicate_best_update(self):
        run, first = self.play("Alice", 17, [[11, 2], [12, 1]])
        self.play("Bob", 264, TURNS)
        self.clock.advance(5)
        with verified(claims_for("Alice")):
            again = self.store.finish(run["runId"], 17, [[11, 2], [12, 1]])
            self.assertEqual(again, first)
            self.assertEqual(again["rank"], 1)  # original receipt, not a fresh ranking
            again["leaderboard"][0]["name"] = "corrupted response"
            again["player"]["best"] = 9999999
            self.assertEqual(self.store.finish(run["runId"], 17, [[11, 2], [12, 1]]), first)
        self.assertEqual(len(self.store._players), 2)
        self.assertEqual(self.store._achievement, 2)
        self.assertEqual(len(self.store._receipts), 2)

    def test_simultaneous_finish_is_atomic_and_idempotent(self):
        with verified(claims_for()):
            run = self.store.begin()
        self.clock.advance(4)

        def finish_once(_):
            with verified(claims_for()):
                return self.store.finish(run["runId"], 16, [])

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(finish_once, range(4)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(len(self.store._receipts), 1)
        self.assertEqual(len(self.store._players), 1)
        self.assertEqual(self.store._achievement, 1)

    def test_user_snapshots_and_returned_dicts_do_not_leak_across_contexts(self):
        self.play("Alice", 17, [[11, 2], [12, 1]])
        self.play("Bob")
        with verified(claims_for("Alice")):
            alice = self.store.scores()
        with verified(claims_for("Bob")):
            bob = self.store.scores()
        self.assertEqual(alice["player"]["name"], "Alice")
        self.assertEqual(alice["player"]["best"], 100)
        self.assertEqual(bob["player"]["name"], "Bob")
        self.assertEqual(bob["player"]["best"], 0)
        self.assertEqual([row["isYou"] for row in alice["leaderboard"]], [True, False])
        self.assertEqual([row["isYou"] for row in bob["leaderboard"]], [False, True])
        bob["leaderboard"][0]["name"] = "not Alice"
        self.assertEqual(alice["leaderboard"][0]["name"], "Alice")
        with verified(claims_for("Alice")):
            self.assertEqual(self.store.scores()["leaderboard"][0]["name"], "Alice")
        encoded = json.dumps(alice)
        for private_field in ("runId", "seed", "issued", "expires", "owner"):
            self.assertNotIn(f'"{private_field}"', encoded)

    def test_parallel_verified_callers_get_only_their_own_player_summary(self):
        def read_for(index):
            with verified(claims_for(f"Person {index}")):
                return self.store.scores()

        with ThreadPoolExecutor(max_workers=5) as pool:
            snapshots = list(pool.map(read_for, range(20)))
        self.assertEqual([s["player"]["name"] for s in snapshots], [f"Person {i}" for i in range(20)])
        self.assertEqual(len({s["player"]["id"] for s in snapshots}), 20)
        self.assertEqual(self.store._players, {})  # viewing does not fill player memory

    def test_fifth_start_retires_only_own_oldest_active_run(self):
        with verified(claims_for("Bob")):
            foreign = self.store.begin()
        with verified(claims_for("Alice")):
            runs = [self.store.begin() for _ in range(5)]
            self.assertNotIn(runs[0]["runId"], self.store._runs)
            self.assertIn(runs[1]["runId"], self.store._runs)
            self.assertEqual(self.store.finish(runs[0]["runId"], 16, [])["error"]["code"], "unavailable_run")
            self.assertEqual(sum(r["owner"] == runs[4]["player"]["id"] for r in self.store._runs.values()), 4)
        self.assertIn(foreign["runId"], self.store._runs)
        self.assertEqual(len(self.store._runs), 5)

    def test_global_active_cap_rejects_without_evicting_other_players(self):
        store = NeonCoilState(clock=self.clock, max_active=2)
        with verified(claims_for("Alice")):
            first = store.begin()
        with verified(claims_for("Bob")):
            second = store.begin()
        before = deepcopy(store._runs)
        with verified(claims_for("Charlie")):
            self.assertEqual(store.begin()["error"]["code"], "capacity")
        self.assertEqual(store._runs, before)
        self.assertEqual(set(store._runs), {first["runId"], second["runId"]})

    def test_expired_runs_are_pruned_at_ttl_and_free_capacity(self):
        store = NeonCoilState(clock=self.clock, max_active=1)
        with verified(claims_for("Alice")):
            old = store.begin()
        self.clock.advance(7200)
        with verified(claims_for("Bob")):
            fresh = store.begin()
            self.assertNotIn("error", fresh)
        with verified(claims_for("Alice")):
            self.assertEqual(store.finish(old["runId"], 16, [])["error"]["code"], "unavailable_run")
        self.assertEqual(len(store._runs), 1)
        self.assertNotIn(old["runId"], store._runs)

    def test_receipt_reservations_bound_total_memory_and_survive_until_ttl(self):
        store = NeonCoilState(clock=self.clock, seed_factory=lambda: SEED, max_records=2)
        run, receipt = self.play("Alice", store=store)
        with verified(claims_for("Bob")):
            second = store.begin()
        with verified(claims_for("Charlie")):
            self.assertEqual(store.begin()["error"]["code"], "capacity")
        with verified(claims_for("Alice")):
            self.assertEqual(store.finish(run["runId"], 16, []), receipt)
        self.assertIn(second["runId"], store._runs)
        self.clock.advance(7201)
        with verified(claims_for("Charlie")):
            self.assertNotIn("error", store.begin())
        self.assertEqual(store._receipts, {})
        with verified(claims_for("Alice")):
            self.assertEqual(store.finish(run["runId"], 16, [])["error"]["code"], "unavailable_run")
        self.assertEqual(len(store._players), 1)  # best scores last for the epoch

    def test_best_player_capacity_is_reserved_before_runs_are_issued(self):
        store = NeonCoilState(clock=self.clock, seed_factory=lambda: SEED, max_players=2)
        with verified(claims_for("Alice")):
            alice = store.begin()
        with verified(claims_for("Bob")):
            bob = store.begin()
        with verified(claims_for("Charlie")):
            self.assertEqual(store.begin()["error"]["code"], "capacity")
            self.assertIsNotNone(store.scores()["player"])
        self.clock.advance(3)
        with verified(claims_for("Alice")):
            self.assertNotIn("error", store.finish(alice["runId"], 16, []))
        with verified(claims_for("Bob")):
            self.assertNotIn("error", store.finish(bob["runId"], 16, []))
        with verified(claims_for("Charlie")):
            self.assertEqual(store.begin()["error"]["code"], "capacity")
        self.assertEqual(len(store._players), 2)

    def test_expiry_during_verification_cannot_post(self):
        original = state_module.simulate_replay

        def expire(*args):
            self.clock.advance(7201)
            return original(*args)

        with verified(claims_for()):
            run = self.store.begin()
            self.clock.advance(5)
            with mock.patch.object(state_module, "simulate_replay", side_effect=expire):
                result = self.store.finish(run["runId"], 16, [])
            self.assertEqual(result["error"]["code"], "unavailable_run")
        self.assertEqual(self.store._players, {})
        self.assertEqual(self.store._receipts, {})

    def test_exact_limit_returns_ended_by_limit_receipt(self):
        store = NeonCoilState(clock=self.clock, seed_factory=lambda: 0)
        with verified(claims_for()):
            run = store.begin()
            self.clock.advance(2700)
            result = store.finish(run["runId"], 18000, limit_turns())
            self.assertNotIn("error", result)
            self.assertTrue(result["endedByLimit"])
            self.assertFalse(result["won"])
            self.assertEqual(result["score"], 0)
        _, ordinary = self.play("Bob")
        self.assertFalse(ordinary["endedByLimit"])


class AppContractTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.store = NeonCoilState(clock=self.clock, seed_factory=lambda: SEED)
        self.patch = mock.patch.object(app_module, "_STATE", self.store)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        app_module._app_html.cache_clear()
        self.addCleanup(app_module._app_html.cache_clear)
        self.server = MCPServer("neon-coil-test", extensions=[Apps()])

    def test_registration_is_asset_independent_and_exactly_one_model_tool(self):
        with mock.patch.object(Path, "read_text", side_effect=AssertionError("registration read an asset")):
            register_catalog_tool(self.server, "neon_coil")
        tools = asyncio.run(self.server.list_tools())
        self.assertEqual({tool.name for tool in tools}, {
            "neon_coil", "neon_coil_begin", "neon_coil_finish", "neon_coil_scores",
        })
        model_tools = [tool for tool in tools if tool.meta["ui"].get("visibility") != ["app"]]
        self.assertEqual([tool.name for tool in model_tools], ["neon_coil"])
        for tool in tools:
            self.assertEqual(tool.meta["ui"]["resourceUri"], "ui://neon-coil/app.html")
            if tool.name != "neon_coil":
                self.assertEqual(tool.meta["ui"]["visibility"], ["app"])
        finish = next(tool for tool in tools if tool.name == "neon_coil_finish")
        self.assertEqual(set(finish.input_schema["properties"]), {"run_id", "steps", "turns"})
        self.assertEqual(finish.input_schema["properties"]["steps"]["maximum"], 18000)
        self.assertEqual(finish.input_schema["properties"]["turns"]["maxItems"], 18000)

    def test_resource_loads_relative_assets_lazily_and_has_no_network_permissions(self):
        register_catalog_tool(self.server, "neon_coil")
        resources = asyncio.run(self.server.list_resources())
        self.assertEqual(len(resources), 1)
        resource = resources[0]
        self.assertEqual(str(resource.uri), app_module.RESOURCE_URI)
        self.assertEqual(resource.mime_type, "text/html;profile=mcp-app")
        self.assertEqual(resource.meta["ui"]["csp"], {"resourceDomains": [], "connectDomains": []})
        self.assertNotIn("permissions", resource.meta["ui"])
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory)
            (assets / "app.html").write_text("<!doctype html><main>Snake</main><!-- app.js -->", encoding="utf-8")
            (assets / "app.js").write_text("globalThis.__neon_test = 1;", encoding="utf-8")
            with mock.patch.object(app_module, "ASSETS", assets):
                result = list(asyncio.run(self.server.read_resource(app_module.RESOURCE_URI)))
                self.assertEqual(len(result), 1)
                html = result[0].content
                self.assertIn('<script type="module">', html)
                self.assertIn("globalThis.__neon_test = 1;", html)
                self.assertNotIn("<!-- app.js -->", html)
                with mock.patch.object(Path, "read_text", side_effect=AssertionError("cache miss")):
                    self.assertEqual(app_module._app_html(), html)

    def test_real_mcp_calls_use_verified_context_and_ignore_spoofed_identity_or_score(self):
        register_catalog_tool(self.server, "neon_coil")
        with verified(claims_for("Alice")):
            main = asyncio.run(self.server.call_tool("neon_coil", {})).structured_content
            self.assertEqual(main["player"]["name"], "Alice")
            begin = asyncio.run(self.server.call_tool("neon_coil_begin", {
                "name": "Spoofed", "oid": "someone-else", "score": 9000000,
            })).structured_content
            self.assertEqual(begin["player"]["name"], "Alice")
            self.clock.advance(4)
            result = asyncio.run(self.server.call_tool("neon_coil_finish", {
                "run_id": begin["runId"], "steps": 16, "turns": [],
                "name": "Spoofed", "score": 9000000,
            })).structured_content
            self.assertEqual(result["score"], 0)
            self.assertEqual(result["player"]["name"], "Alice")
        with verified(claims_for("Bob")):
            scores = asyncio.run(self.server.call_tool("neon_coil_scores", {})).structured_content
            self.assertEqual(scores["player"]["name"], "Bob")
            self.assertEqual(scores["leaderboard"][0]["name"], "Alice")
            self.assertFalse(scores["leaderboard"][0]["isYou"])
        with verified(claims_for("Application", scp="", idtyp="app")):
            denied = asyncio.run(self.server.call_tool("neon_coil_begin", {})).structured_content
            self.assertEqual(denied["error"]["code"], "ineligible")

    def test_mcp_input_validation_does_not_coerce_boolean_or_decimal_replay_events(self):
        register_catalog_tool(self.server, "neon_coil")
        with verified(claims_for()):
            run = self.store.begin()
            self.clock.advance(5)
            invalid = [
                {"steps": True, "turns": []}, {"steps": 16.0, "turns": []},
                {"steps": 16, "turns": [[True, 0]]},
                {"steps": 16, "turns": [[1, False]]},
                {"steps": 16, "turns": [[1, 0.0]]},
            ]
            for args in invalid:
                with self.subTest(args=args), self.assertRaises(ToolError):
                    asyncio.run(self.server.call_tool("neon_coil_finish", {"run_id": run["runId"], **args}))
        self.assertEqual(self.store._players, {})


if __name__ == "__main__":
    unittest.main()
