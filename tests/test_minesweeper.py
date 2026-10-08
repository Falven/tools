"""Standard-library tests for authoritative Minesweeper and its MCP boundary.

Run with the existing environment:
    .venv/bin/python -m unittest discover -s tests -p 'test_minesweeper.py' -v
HTML/resource tests use synthetic adjacent assets; frontend generation is not a
prerequisite. Only test helpers may inspect private mines to solve a board.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import random
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

import catalog_app.tools.minesweeper as app_module
from catalog_app.tools.minesweeper import engine
from catalog_app.tools.minesweeper.state import LEADERBOARD_LIMIT, MinesweeperState

SNAPSHOT_KEYS = {"epoch", "ephemeral", "canPlay", "player", "leaderboard", "totalPlayers"}
GAME_KEYS = {
    "runId", "revision", "difficulty", "rows", "cols", "mineCount", "status", "cells",
    "flagsUsed", "revealedCount", "score", "elapsedMs", "changed",
}
ROW_KEYS = {"rank", "name", "score", "difficulty", "elapsedMs", "isYou"}
FIXTURE_MINES = frozenset({0, 2, 18, 20, 60, 62, 70, 72, 78, 80})


def claims_for(player="Alice", **overrides):
    return {
        "tid": "private-tenant-A", "oid": f"private-object-{player}",
        "sub": f"private-subject-{player}", "iss": "https://issuer.example.test/tenant-A",
        "scp": "access_as_user", "name": player,
        "email": f"{player.lower()}@private.example.test", **overrides,
    }


@contextmanager
def verified(claims, *, scopes=None, subject="ignored-token-subject"):
    caller = AuthenticatedUser(AccessToken(
        token="not-a-jwt-and-never-decoded", client_id="verified-client",
        scopes=["access_as_user"] if scopes is None else scopes,
        subject=subject, claims=claims,
    ))
    token = auth_context_var.set(caller)
    try:
        yield
    finally:
        auth_context_var.reset(token)


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def spread_sample(population, count):
    return random.Random(314159).sample(population, count)


def tail_sample(population, count):
    return list(population[-count:])


def planted_game(mines=FIXTURE_MINES, *, revealed=(), flags=()):
    game = engine.create_game()
    game.mines = frozenset(mines)
    game.numbers = tuple(
        sum(index in game.mines for index in engine.neighbors(cell, 9, 9))
        for cell in range(81)
    )
    game.status = "playing"
    game.started_at = 1000.0
    game.revealed = set(revealed)
    game.flags = set(flags)
    return game


class EngineTests(unittest.TestCase):
    def test_difficulty_contract_and_unplanted_initial_state(self):
        expected = [("beginner", 9, 9, 10, 1), ("intermediate", 16, 16, 40, 2), ("expert", 16, 30, 99, 3)]
        for name, rows, cols, mines, multiplier in expected:
            with self.subTest(difficulty=name):
                game = engine.create_game(name)
                self.assertEqual((game.difficulty.rows, game.difficulty.cols, game.difficulty.mine_count,
                                  game.difficulty.multiplier), (rows, cols, mines, multiplier))
                self.assertEqual(game.status, "ready")
                self.assertEqual(game.revision, 0)
                self.assertIsNone(game.mines)
                self.assertIsNone(game.numbers)
                self.assertIsNone(game.started_at)
                self.assertEqual(engine.visible_cells(game), [-2] * (rows * cols))
                self.assertEqual(engine.score(game, 12345), 0)
                self.assertEqual(engine.elapsed_ms(game, 12345), 0)

    def test_neighbors_corners_edges_and_no_row_wrapping(self):
        self.assertEqual(engine.neighbors(0, 9, 9), (1, 9, 10))
        self.assertEqual(engine.neighbors(8, 9, 9), (7, 16, 17))
        self.assertEqual(engine.neighbors(80, 9, 9), (70, 71, 79))
        self.assertEqual(engine.neighbors(4, 9, 9), (3, 5, 12, 13, 14))
        self.assertEqual(engine.neighbors(40, 9, 9), (30, 31, 32, 39, 41, 48, 49, 50))
        self.assertEqual(engine.neighbors(479, 16, 30), (448, 449, 478))
        self.assertNotIn(9, engine.neighbors(8, 9, 9))

    def test_every_cell_is_a_safe_first_reveal_for_every_difficulty(self):
        # Exhaust all 817 possible first cells, including each corner and edge.
        for name, spec in engine.DIFFICULTIES.items():
            for first in range(spec.size):
                game = engine.create_game(name)
                engine.apply_move(game, "reveal", first, 1000.0, spread_sample)
                protected = {first, *engine.neighbors(first, spec.rows, spec.cols)}
                self.assertEqual(len(game.mines), spec.mine_count)
                self.assertTrue(game.mines.isdisjoint(protected), (name, first))
                self.assertEqual(game.numbers[first], 0)
                self.assertIn(first, game.revealed)
                self.assertNotEqual(game.status, "lost")

    def test_multiple_random_layouts_remain_safe_and_exact(self):
        for seed in range(30):
            game = engine.create_game("expert")
            engine.apply_move(game, "reveal", 245, 0.0, random.Random(seed).sample)
            self.assertEqual(len(game.mines), 99)
            self.assertTrue(game.mines.isdisjoint({245, *engine.neighbors(245, 16, 30)}))
            self.assertEqual(len(game.numbers), 480)
            self.assertEqual(game.started_at, 0.0)

    def test_flags_and_chords_do_not_plant_or_start_time(self):
        game = engine.create_game()
        sampler = mock.Mock(side_effect=spread_sample)
        for action, cell in [("chord", 0), ("flag", 40), ("reveal", 40), ("chord", 40)]:
            engine.apply_move(game, action, cell, 0, sampler)
        self.assertEqual(game.revision, 4)
        self.assertEqual(game.status, "ready")
        self.assertIsNone(game.mines)
        self.assertIsNone(game.started_at)
        sampler.assert_not_called()
        engine.apply_move(game, "flag", 40, 100, sampler)
        engine.apply_move(game, "reveal", 40, 200, sampler)
        self.assertEqual(game.started_at, 200)
        self.assertEqual(sampler.call_count, 1)
        engine.apply_move(game, "reveal", 40, 999, sampler)
        self.assertEqual(sampler.call_count, 1)
        self.assertEqual(game.started_at, 200)

    def test_flags_on_neighbors_remain_safe_at_generation(self):
        game = engine.create_game()
        engine.apply_move(game, "flag", 39, 0, spread_sample)
        engine.apply_move(game, "reveal", 40, 20, spread_sample)
        self.assertNotIn(39, game.mines)
        self.assertNotIn(39, game.revealed)
        self.assertEqual(engine.visible_cells(game)[39], -3)

    def test_flood_opens_zero_regions_and_borders_but_not_flags(self):
        game = engine.create_game()
        engine.apply_move(game, "flag", 8, 0, tail_sample)
        changed = engine.apply_move(game, "reveal", 0, 1000, tail_sample)
        self.assertEqual(game.status, "playing")
        self.assertEqual(len(game.revealed), 70)
        self.assertNotIn(8, game.revealed)
        self.assertEqual(len(changed), 70)
        self.assertTrue(any(game.numbers[cell] > 0 for cell in game.revealed))
        self.assertTrue(game.revealed.isdisjoint(game.mines))
        engine.apply_move(game, "flag", 8, 1010, tail_sample)
        changed = engine.apply_move(game, "reveal", 8, 1020, tail_sample)
        self.assertEqual(game.status, "won")
        self.assertEqual(game.flags, set(game.mines))
        self.assertEqual(set(changed), {8, *game.mines})
        self.assertEqual(len(game.revealed), 71)

    def test_flag_limit_toggle_and_revealed_cell_noops(self):
        game = engine.create_game()
        for cell in range(10):
            self.assertEqual(engine.apply_move(game, "flag", cell, 0, spread_sample), [cell])
        self.assertEqual(engine.apply_move(game, "flag", 10, 1, spread_sample), [])
        self.assertEqual(len(game.flags), 10)
        self.assertEqual(game.revision, 11)
        engine.apply_move(game, "flag", 0, 2, spread_sample)
        engine.apply_move(game, "flag", 10, 3, spread_sample)
        self.assertEqual(len(game.flags), 10)
        game = planted_game(revealed={10})
        self.assertEqual(engine.apply_move(game, "flag", 10, 1001, spread_sample), [])
        self.assertEqual(engine.apply_move(game, "reveal", 10, 1002, spread_sample), [])
        self.assertEqual(game.revision, 2)
        self.assertEqual(game.flags, set())

    def test_matching_chord_reveals_all_unflagged_neighbors(self):
        game = planted_game(revealed={10}, flags={0, 2, 18, 20})
        self.assertEqual(game.numbers[10], 4)
        changed = engine.apply_move(game, "chord", 10, 1001, spread_sample)
        self.assertEqual(changed, [1, 9, 11, 19])
        self.assertEqual(game.revealed, {1, 9, 10, 11, 19})
        self.assertEqual(game.flags, {0, 2, 18, 20})
        self.assertEqual(game.status, "playing")

    def test_chord_requires_revealed_cell_and_exact_flag_count(self):
        for revealed, flags, cell in [({10}, {0, 2, 18}, 10), ({10}, {0, 2, 18, 20, 1}, 10),
                                      (set(), {0, 2, 18, 20}, 10), ({10}, set(), 80)]:
            game = planted_game(revealed=revealed, flags=flags)
            before = engine.visible_cells(game)
            self.assertEqual(engine.apply_move(game, "chord", cell, 1001, spread_sample), [])
            self.assertEqual(engine.visible_cells(game), before)
            self.assertEqual(game.revision, 1)

    def test_wrong_matching_chord_loses_atomically_and_marks_wrong_flags(self):
        game = planted_game(revealed={10}, flags={0, 2, 18, 1})
        before = engine.visible_cells(game)
        changed = engine.apply_move(game, "chord", 10, 1005, spread_sample)
        self.assertEqual(game.status, "lost")
        self.assertEqual(game.exploded, 20)
        self.assertEqual(game.revealed, {10})
        cells = engine.visible_cells(game)
        self.assertEqual(cells[20], -4)
        self.assertEqual(cells[1], -5)
        self.assertEqual(cells[0], -3)
        self.assertEqual(cells[60], -1)
        self.assertEqual(cells[9], -2)
        self.assertEqual(changed, [index for index in range(81) if before[index] != cells[index]])
        self.assertEqual(engine.score(game, 9999), 10)

    def test_zero_chord_can_reveal_a_previously_flagged_safe_neighbor(self):
        game = engine.create_game()
        engine.apply_move(game, "flag", 8, 0, tail_sample)
        engine.apply_move(game, "reveal", 0, 1, tail_sample)
        engine.apply_move(game, "flag", 8, 2, tail_sample)
        self.assertEqual(game.numbers[7], 0)
        engine.apply_move(game, "chord", 7, 3, tail_sample)
        self.assertEqual(game.status, "won")

    def test_direct_mine_reveal_loses_and_terminal_is_frozen(self):
        game = planted_game(revealed={10}, flags={0, 1})
        engine.apply_move(game, "reveal", 20, 1004.25, spread_sample)
        self.assertEqual(game.status, "lost")
        frozen = deepcopy(game)
        for action in ("reveal", "flag", "chord"):
            self.assertEqual(engine.apply_move(game, action, 11, 2000, spread_sample), [])
            self.assertEqual(game, frozen)
        self.assertEqual(engine.elapsed_ms(game, 9999), 4250)
        self.assertEqual(engine.score(game, 9999), 10)
        self.assertEqual(engine.visible_cells(game)[1], -5)

    def test_won_board_is_auto_flagged_and_terminal_frozen(self):
        game = engine.create_game()
        engine.apply_move(game, "reveal", 0, 0, tail_sample)
        self.assertEqual(game.status, "won")
        self.assertEqual(game.started_at, 0)
        self.assertEqual(game.finished_at, 0)
        self.assertEqual(engine.score(game, 100), 2710)
        self.assertEqual(game.flags, set(game.mines))
        self.assertNotIn(-2, engine.visible_cells(game))
        self.assertEqual(engine.visible_cells(game).count(-3), 10)
        before = deepcopy(game)
        engine.apply_move(game, "flag", min(game.mines), 1000, tail_sample)
        self.assertEqual(game, before)

    def test_all_number_values_including_eight(self):
        game = planted_game(mines={0, 1, 2, 9, 11, 18, 19, 20, 78, 80}, revealed={10})
        self.assertEqual(game.numbers[10], 8)
        self.assertEqual(engine.visible_cells(game)[10], 8)
        for cell, number in enumerate(game.numbers):
            self.assertEqual(number, len(set(engine.neighbors(cell, 9, 9)) & game.mines))

    def test_live_snapshots_never_expose_mines_or_covered_numbers(self):
        game = planted_game(revealed={10}, flags={0, 1})
        view = engine.snapshot(game, "opaque-run", 1005)
        self.assertEqual(set(view), GAME_KEYS)
        self.assertEqual(view["cells"][10], 4)
        self.assertEqual(view["cells"][20], -2)
        self.assertEqual(view["cells"][0], -3)
        self.assertEqual(view["cells"][1], -3)  # wrong flags are not identified yet
        self.assertTrue(all(value == -2 for cell, value in enumerate(view["cells"])
                            if cell not in game.revealed | game.flags))
        for private in ("mines", "numbers", "seed", "started_at", "finished_at", "exploded"):
            self.assertNotIn(private, view)

    def test_scoring_bonus_floor_and_multipliers(self):
        for name, spec in engine.DIFFICULTIES.items():
            for seconds in (0, 0.999, 1, 15.75, 999.999, 1000, 2000):
                game = engine.create_game(name)
                game.revealed = set(range(spec.size - spec.mine_count))
                game.status = "won"
                game.started_at = 0.0
                game.finished_at = seconds
                expected = ((spec.size - spec.mine_count) * 10 + 1000 + max(0, 1000 - int(seconds))) * spec.multiplier
                self.assertEqual(engine.score(game, 99999), expected, (name, seconds))
                game.status = "lost"
                self.assertEqual(engine.score(game, 99999), len(game.revealed) * 10 * spec.multiplier)

    def test_elapsed_zero_origin_and_nonnegative_clamp(self):
        game = planted_game()
        game.started_at = 0.0
        self.assertEqual(engine.elapsed_ms(game, 1.25), 1250)
        game.started_at = 5.0
        self.assertEqual(engine.elapsed_ms(game, 4.0), 0)

    def test_fresh_games_metadata_and_snapshots_have_no_shared_mutables(self):
        first, second = engine.create_game(), engine.create_game()
        first.flags.add(0)
        self.assertEqual(second.flags, set())
        metadata = engine.difficulties_metadata()
        metadata[0]["mineCount"] = 999
        self.assertEqual(engine.difficulties_metadata()[0]["mineCount"], 10)
        changed = [0]
        view = engine.snapshot(first, "opaque", 0, changed)
        view["cells"][0] = 8
        view["changed"].append(9)
        self.assertEqual(changed, [0])
        self.assertEqual(engine.visible_cells(first)[0], -3)

    def test_invalid_core_inputs_do_not_mutate(self):
        for difficulty in ("easy", "BEGINNER", "", 1, True, [], None):
            with self.subTest(difficulty=difficulty), self.assertRaises(ValueError):
                engine.create_game(difficulty)
        for action, cell in [("boom", 0), (True, 0), ([], 0), ("flag", True), ("flag", 1.0),
                             ("flag", "1"), ("reveal", -1), ("chord", 81)]:
            game = engine.create_game()
            before = deepcopy(game)
            with self.subTest(action=action, cell=cell), self.assertRaises(ValueError):
                engine.apply_move(game, action, cell, 0, spread_sample)
            self.assertEqual(game, before)

    def test_bad_private_sampler_is_rejected_before_mutation(self):
        for chosen in ([0] * 10, list(range(10)), list(range(70, 79)), [True] + list(range(70, 79)),
                       list(range(100, 110))):
            game = engine.create_game()
            before = deepcopy(game)
            with self.subTest(chosen=chosen), self.assertRaises(ValueError):
                engine.apply_move(game, "reveal", 0, 0, lambda population, count: chosen)
            self.assertEqual(game, before)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.store = MinesweeperState(clock=self.clock, sampler=spread_sample)

    def start_playing(self, store=None, difficulty="beginner"):
        store = store or self.store
        started = store.start(difficulty)
        self.assertNotIn("error", started)
        game = started["game"]
        first = game["rows"] // 2 * game["cols"] + game["cols"] // 2
        result = store.move(game["runId"], "reveal", first, 0)
        self.assertEqual(result["game"]["status"], "playing")
        return started, result

    def solve(self, result, store=None, *, skip=None):
        store = store or self.store
        run_id = result["game"]["runId"]
        private = store._runs[run_id]["game"]
        last_request = None
        for cell in range(private.difficulty.size):
            if private.status != "playing":
                break
            if cell not in private.mines | private.revealed | private.flags and cell != skip:
                last_request = (run_id, "reveal", cell, private.revision)
                result = store.move(*last_request)
                self.assertNotIn("error", result)
        return result, last_request

    def win(self, name="Alice", difficulty="beginner", seconds=10.25, store=None):
        store = store or self.store
        with verified(claims_for(name)):
            started, result = self.start_playing(store, difficulty)
            self.clock.advance(seconds)
            result, request = self.solve(result, store)
            self.assertEqual(result["game"]["status"], "won")
            self.assertTrue(result["recorded"])
            return started, result, request

    def near_win(self):
        started, result = self.start_playing()
        run_id = started["game"]["runId"]
        private = self.store._runs[run_id]["game"]
        last = next(cell for cell in range(81) if cell not in private.mines | private.revealed)
        result = self.store.move(run_id, "flag", last, private.revision)
        result, _ = self.solve(result, skip=last)
        result = self.store.move(run_id, "flag", last, private.revision)
        self.assertEqual(result["game"]["revealedCount"], 70)
        self.assertEqual(private.status, "playing")
        return (run_id, "reveal", last, private.revision)

    def test_overview_is_useful_and_has_no_game_or_score_side_effects(self):
        with verified(claims_for()):
            view = self.store.overview()
        self.assertTrue(SNAPSHOT_KEYS <= set(view))
        self.assertEqual(view["title"], "Minesweeper")
        self.assertIn("restart", view["description"])
        self.assertGreaterEqual(len(view["rules"]), 7)
        self.assertEqual([item["id"] for item in view["difficulties"]], ["beginner", "intermediate", "expert"])
        self.assertEqual(view["player"]["bestScore"], 0)
        self.assertTrue(view["canPlay"])
        self.assertEqual(self.store._runs, {})
        self.assertEqual(self.store._players, {})

    def test_no_context_or_application_only_callers_can_only_view(self):
        context = auth_context_var.set(None)
        try:
            self.assertEqual(self.store.start()["error"]["code"], "ineligible")
            view = self.store.overview()
            self.assertFalse(view["canPlay"])
            self.assertIsNone(view["player"])
        finally:
            auth_context_var.reset(context)
        cases = [None, claims_for(scp=""), claims_for(scp=" \t\n"), claims_for(scp=None, roles=["app"]),
                 claims_for(scp=["access_as_user"]), claims_for(idtyp="app"), claims_for(idtyp=" APP "),
                 claims_for(idtyp=[]), claims_for(tid=None, oid=None, iss=None),
                 claims_for(tid=None, oid=None, sub=None)]
        for claims in cases:
            with self.subTest(claims=claims), verified(claims):
                self.assertEqual(self.store.start()["error"]["code"], "ineligible")
                self.assertEqual(self.store.move("x" * 43, "flag", 0, 0)["error"]["code"], "ineligible")
                self.assertFalse(self.store.scores()["canPlay"])
                self.assertIsNone(self.store.scores()["player"])
        self.assertEqual(self.store._runs, {})
        self.assertEqual(self.store._players, {})

    def test_identity_uses_verified_claims_not_token_scopes_or_subject(self):
        with verified(claims_for(scp=""), scopes=["access_as_user"]):
            self.assertIsNone(self.store.scores()["player"])
        with verified(claims_for(), scopes=[]):
            self.assertIsNotNone(self.store.scores()["player"])
        with verified(claims_for(tid=None, oid=None, sub=None), subject="spoof-subject"):
            self.assertIsNone(self.store.scores()["player"])

    def test_tenant_object_identity_and_verified_issuer_subject_fallback(self):
        with verified(claims_for()):
            identity = self.store.scores()["player"]["id"]
        for claims in (claims_for(sub="ignored-other-subject"),
                       claims_for(tid="PRIVATE-TENANT-A", oid="PRIVATE-OBJECT-ALICE"),
                       claims_for(name="New name")):
            with verified(claims):
                self.assertEqual(self.store.scores()["player"]["id"], identity)
        with verified(claims_for(tid="another-tenant")):
            self.assertNotEqual(self.store.scores()["player"]["id"], identity)
        with verified(claims_for(tid=None, oid=None)):
            fallback = self.store.scores()["player"]["id"]
            self.assertNotEqual(fallback, identity)
        with verified(claims_for(tid=None, oid=None, iss="other-issuer")):
            self.assertNotEqual(self.store.scores()["player"]["id"], fallback)
        with verified(claims_for(tid=None, oid=None, sub="OTHER-SUBJECT")):
            self.assertNotEqual(self.store.scores()["player"]["id"], fallback)

    def test_opaque_ids_are_salted_per_epoch_and_never_expose_raw_claims(self):
        claims = claims_for()
        other = MinesweeperState(clock=self.clock)
        with verified(claims):
            result = self.store.start()
            fresh = other.scores()
        self.assertRegex(result["player"]["id"], r"^p_[0-9a-f]{32}$")
        self.assertNotEqual(result["player"]["id"], fresh["player"]["id"])
        self.assertNotEqual(result["epoch"], fresh["epoch"])
        serialized = json.dumps(result) + repr(self.store._runs)
        for key in ("tid", "oid", "sub", "iss", "email"):
            self.assertNotIn(claims[key], serialized)
        self.assertNotIn("not-a-jwt-and-never-decoded", serialized)

    def test_private_identifiers_and_email_are_never_display_labels(self):
        bad_names = [None, 42, "\x00\u202e\t", "alice@example.test", "alice＠example.test",
                     "private-object-Alice", "PRIVATE-OBJECT-ALICE", "User private-object-Alice",
                     "private-subject-Alice", "private-tenant-A", "alice@private.example.test"]
        for name in bad_names:
            with self.subTest(name=name), verified(claims_for(name=name)):
                self.assertEqual(self.store.scores()["player"]["name"], "Player")
        with verified(claims_for(name="  Ju\u0301lia\x00\u202e \n💣  ")):
            self.assertEqual(self.store.scores()["player"]["name"], "Júlia 💣")
        with verified(claims_for(name="名前" * 50)):
            self.assertEqual(len(self.store.scores()["player"]["name"]), 48)
        with verified(claims_for(name=None, preferred_username="visible@email.test")):
            self.assertEqual(self.store.scores()["player"]["name"], "Player")

    def test_start_contract_unguessable_ids_and_no_random_layout_or_clock(self):
        sampler = mock.Mock(side_effect=spread_sample)
        store = MinesweeperState(clock=self.clock, sampler=sampler)
        with verified(claims_for()):
            first, second = store.start(), store.start("expert")
        self.assertEqual(set(first), SNAPSHOT_KEYS | {"game"})
        self.assertEqual(set(first["game"]), GAME_KEYS)
        self.assertEqual(set(first["player"]), {"id", "name", "bestScore"})
        self.assertRegex(first["game"]["runId"], r"^[A-Za-z0-9_-]{43}$")
        self.assertNotEqual(first["game"]["runId"], second["game"]["runId"])
        self.assertEqual(first["game"]["cells"], [-2] * 81)
        self.assertEqual(first["game"]["changed"], [])
        self.assertEqual(first["game"]["elapsedMs"], 0)
        self.assertEqual(first["game"]["revision"], 0)
        self.assertEqual(len(second["game"]["cells"]), 480)
        sampler.assert_not_called()

    def test_start_strict_difficulty_does_not_allocate_on_error(self):
        with verified(claims_for()):
            for difficulty in ("easy", "Beginner", None, True, 1, [], {}):
                with self.subTest(difficulty=difficulty):
                    error = self.store.start(difficulty)
                    self.assertEqual(error["error"]["code"], "invalid_difficulty")
                    self.assertEqual(set(error), {"error", "epoch", "ephemeral"})
        self.assertEqual(self.store._runs, {})

    def test_moves_reject_coercions_and_bad_bounds_without_mutation(self):
        with verified(claims_for()):
            run_id = self.store.start()["game"]["runId"]
            before = deepcopy(self.store._runs)
            invalid = [
                ("flag", True, 0, "invalid_cell"), ("flag", 0.0, 0, "invalid_cell"),
                ("flag", "0", 0, "invalid_cell"), ("flag", -1, 0, "invalid_cell"),
                ("flag", 81, 0, "invalid_cell"), ("flag", 480, 0, "invalid_cell"),
                ("flag", None, 0, "invalid_cell"), ("flag", 0, True, "invalid_revision"),
                ("flag", 0, 0.0, "invalid_revision"), ("flag", 0, "0", "invalid_revision"),
                ("flag", 0, -1, "invalid_revision"), ("flag", 0, None, "invalid_revision"),
                ("unknown", 0, 0, "invalid_action"), (True, 0, 0, "invalid_action"),
                ([], 0, 0, "invalid_action"),
            ]
            for action, cell, revision, code in invalid:
                with self.subTest(action=action, cell=cell, revision=revision):
                    self.assertEqual(self.store.move(run_id, action, cell, revision)["error"]["code"], code)
                    self.assertEqual(self.store._runs, before)
            for invalid_id in (None, 7, True, "short", "x" * 129, []):
                self.assertEqual(self.store.move(invalid_id, "flag", 0, 0)["error"]["code"], "unavailable_run")
        self.assertEqual(self.store._players, {})

    def test_noops_advance_revision_and_flags_do_not_start_elapsed_time(self):
        with verified(claims_for()):
            game = self.store.start()["game"]
            run_id = game["runId"]
            for action, cell in [("chord", 0), ("flag", 0), ("reveal", 0), ("chord", 0)]:
                self.clock.advance(20)
                result = self.store.move(run_id, action, cell, game["revision"])
                self.assertEqual(result["game"]["revision"], game["revision"] + 1)
                game = result["game"]
                self.assertEqual(game["elapsedMs"], 0)
                self.assertEqual(game["status"], "ready")
            self.assertEqual(game["changed"], [])
            self.assertIsNone(self.store._runs[run_id]["game"].mines)

    def test_server_clock_starts_on_first_actual_reveal_not_start(self):
        with verified(claims_for()):
            game = self.store.start()["game"]
            self.clock.advance(300)
            result = self.store.move(game["runId"], "reveal", 40, 0)
            self.assertEqual(result["game"]["elapsedMs"], 0)
            self.clock.advance(10.25)
            result = self.store.move(game["runId"], "reveal", 40, 1)  # valid no-op
            self.assertEqual(result["game"]["elapsedMs"], 10250)
            self.assertEqual(result["game"]["score"], result["game"]["revealedCount"] * 10)

    def test_wrong_flag_loss_and_other_losses_never_post(self):
        with verified(claims_for()):
            _, result = self.start_playing()
            run_id = result["game"]["runId"]
            private = self.store._runs[run_id]["game"]
            self.assertEqual(self.store.scores()["leaderboard"], [])
            result = self.store.move(run_id, "reveal", min(private.mines), private.revision)
            self.assertEqual(result["game"]["status"], "lost")
            self.assertEqual(result["totalPlayers"], 0)
            self.assertNotIn("recorded", result)
            self.assertEqual(result["player"]["bestScore"], 0)
        self.assertEqual(self.store._players, {})
        self.assertEqual(self.store._achievement, 0)

    def test_foreign_missing_retired_and_expired_runs_share_error_without_game(self):
        with verified(claims_for("Alice")):
            _, result = self.start_playing()
            run_id = result["game"]["runId"]
        with verified(claims_for("Bob")):
            foreign = self.store.move(run_id, "reveal", 1, 0)
            missing = self.store.move("z" * 43, "reveal", 1, 0)
            self.assertEqual(foreign, missing)
            self.assertNotIn("game", foreign)
        with verified(claims_for("Alice")):
            result, request = self.solve(result)
        with verified(claims_for("Bob")):
            self.assertEqual(self.store.move(*request), missing)
        self.clock.advance(7200)
        with verified(claims_for("Alice")):
            self.assertEqual(self.store.move(*request), missing)

    def test_exact_last_request_retry_returns_original_complete_snapshot(self):
        with verified(claims_for()):
            run_id = self.store.start()["game"]["runId"]
            first = self.store.move(run_id, "flag", 0, 0)
            self.clock.advance(10)
            again = self.store.move(run_id, "flag", 0, 0)
            self.assertEqual(again, first)
            self.assertEqual(again["game"]["flagsUsed"], 1)
            self.assertEqual(again["game"]["revision"], 1)
            # A boolean compares equal to integer zero/one in Python, but may
            # never bypass strict validation into the retry key.
            self.assertEqual(self.store.move(run_id, "flag", False, 0)["error"]["code"], "invalid_cell")
            self.assertEqual(self.store.move(run_id, "flag", 0, False)["error"]["code"], "invalid_revision")
            second = self.store.move(run_id, "flag", 0, 1)
            self.assertEqual(second["game"]["flagsUsed"], 0)
            self.assertEqual(self.store.move(run_id, "flag", 0, 0)["error"]["code"], "stale_revision")

    def test_stale_and_future_revision_return_safe_current_game_at_top_level(self):
        with verified(claims_for()):
            _, first = self.start_playing()
            run_id = first["game"]["runId"]
            self.clock.advance(5)
            for revision in (0, 123456789):
                stale = self.store.move(run_id, "flag", 1, revision)
                self.assertEqual(stale["error"]["code"], "stale_revision")
                self.assertEqual(set(stale), {"error", "epoch", "ephemeral", "game"})
                self.assertNotIn("game", stale["error"])
                self.assertEqual(stale["game"]["revision"], 1)
                self.assertEqual(stale["game"]["elapsedMs"], 5000)
                self.assertEqual(stale["game"]["cells"], first["game"]["cells"])
                self.assertEqual(stale["game"]["changed"], [])
                stale["game"]["cells"][0] = 1234
            self.assertEqual(self.store._runs[run_id]["game"].revision, 1)

    def test_terminal_moves_are_frozen_without_replacing_winning_retry(self):
        _, won, request = self.win()
        frozen = deepcopy(self.store._runs[request[0]])
        self.clock.advance(100)
        with verified(claims_for()):
            for action in ("reveal", "flag", "chord"):
                terminal = self.store.move(request[0], action, 0, won["game"]["revision"])
                self.assertEqual(terminal["game"], {**won["game"], "changed": []})
                self.assertEqual(self.store._runs[request[0]], frozen)
            self.assertEqual(self.store.move(*request), won)
            stale = self.store.move(request[0], "chord", 0, 0)
            self.assertEqual(stale["error"]["code"], "stale_revision")
            self.assertEqual(stale["game"]["status"], "won")
        self.assertEqual(self.store._achievement, 1)

    def test_win_is_recorded_once_with_expected_score_and_exact_receipt(self):
        _, won, request = self.win(seconds=10.25)
        self.assertEqual(won["game"]["score"], 2700)
        self.assertEqual(won["game"]["elapsedMs"], 10250)
        self.assertTrue(won["personalBest"])
        self.assertEqual(won["rank"], 1)
        self.assertEqual(won["totalPlayers"], 1)
        self.assertEqual(won["player"]["bestScore"], 2700)
        self.assertEqual(set(won["leaderboard"][0]), ROW_KEYS)
        self.win("Bob", "expert", seconds=20)
        self.clock.advance(5)
        with verified(claims_for("Alice")):
            self.assertEqual(self.store.move(*request), won)
            self.assertEqual(self.store.scores()["leaderboard"][1]["name"], "Alice")
        self.assertEqual(self.store._achievement, 2)

    def test_score_descending_then_elapsed_ascending_then_first_achieved(self):
        self.win("Alice", seconds=10.75)
        self.win("Bob", seconds=10.25)
        self.win("Carol", seconds=10.25)
        self.win("Dave", "expert", seconds=400)
        with verified(claims_for("Alice")):
            board = self.store.scores()["leaderboard"]
        self.assertEqual([row["name"] for row in board], ["Dave", "Bob", "Carol", "Alice"])
        self.assertEqual([row["rank"] for row in board], [1, 2, 3, 4])
        self.assertEqual([row["isYou"] for row in board], [False, False, False, True])
        self.assertEqual([row["elapsedMs"] for row in board[1:]], [10250, 10250, 10750])
        self.assertEqual([row["score"] for row in board[1:]], [2700] * 3)

    def test_equal_score_faster_time_improves_personal_best_but_exact_tie_does_not(self):
        self.win("Alice", seconds=10.75)
        self.win("Bob", seconds=10.25)
        _, improved, _ = self.win("Alice", seconds=10.25)
        self.assertTrue(improved["personalBest"])
        self.assertEqual(improved["rank"], 2)  # Bob reached this score/time first.
        achieved = self.store._achievement
        _, tied, _ = self.win("Alice", seconds=10.25)
        self.assertFalse(tied["personalBest"])
        self.assertEqual(tied["rank"], 2)
        self.assertEqual(self.store._achievement, achieved)
        _, faster, _ = self.win("Alice", seconds=10.0)
        self.assertTrue(faster["personalBest"])
        self.assertEqual(faster["rank"], 1)
        self.assertEqual(faster["game"]["score"], improved["game"]["score"])

    def test_one_highest_best_across_all_difficulties(self):
        self.win("Alice", seconds=2)
        _, expert, _ = self.win("Alice", "expert", seconds=100)
        _, lesser, _ = self.win("Alice", "intermediate", seconds=0)
        self.assertFalse(lesser["personalBest"])
        self.assertTrue(lesser["recorded"])
        self.assertEqual(lesser["player"]["bestScore"], expert["game"]["score"])
        self.assertEqual(lesser["totalPlayers"], 1)
        self.assertEqual(lesser["leaderboard"][0]["difficulty"], "expert")
        self.assertEqual(self.store._achievement, 2)

    def test_bounded_leaderboard_and_full_rank_outside_visible_rows(self):
        last = None
        for index in range(LEADERBOARD_LIMIT + 2):
            _, last, _ = self.win(f"Person {index}", seconds=10)
        self.assertEqual(last["rank"], LEADERBOARD_LIMIT + 2)
        self.assertEqual(last["totalPlayers"], LEADERBOARD_LIMIT + 2)
        self.assertEqual(len(last["leaderboard"]), LEADERBOARD_LIMIT)
        self.assertEqual(last["leaderboard"][0]["name"], "Person 0")
        self.assertFalse(any(row["isYou"] for row in last["leaderboard"]))

    def test_all_returned_containers_are_independent_including_retry_cache(self):
        started, won, request = self.win()
        expected = deepcopy(won)
        won["game"]["cells"][0] = 999
        won["game"]["changed"].append(999)
        won["leaderboard"][0]["name"] = "corrupted"
        won["player"]["bestScore"] = 9999999
        started["game"]["cells"][0] = 999
        with verified(claims_for()):
            self.assertEqual(self.store.move(*request), expected)
            scores = self.store.scores()
            scores["leaderboard"][0]["score"] = 9999999
            scores["player"]["name"] = "mutated"
            view = self.store.overview()
            view["difficulties"][0]["rows"] = 500
            view["rules"].clear()
            self.assertEqual(self.store.scores()["leaderboard"][0]["score"], 2700)
            self.assertEqual(self.store.overview()["difficulties"][0]["rows"], 9)
            self.assertGreater(len(self.store.overview()["rules"]), 5)

    def test_player_summaries_and_leaderboard_rows_do_not_leak_other_ids(self):
        self.win("Alice")
        self.win("Bob", seconds=20)
        with verified(claims_for("Alice")):
            alice = self.store.scores()
        with verified(claims_for("Bob")):
            bob = self.store.scores()
        self.assertEqual(alice["player"]["name"], "Alice")
        self.assertEqual(bob["player"]["name"], "Bob")
        self.assertEqual([row["isYou"] for row in alice["leaderboard"]], [True, False])
        self.assertEqual([row["isYou"] for row in bob["leaderboard"]], [False, True])
        self.assertNotIn(bob["player"]["id"], json.dumps(alice))
        for row in alice["leaderboard"]:
            self.assertEqual(set(row), ROW_KEYS)
        serialized = json.dumps(alice)
        for private in ("runId", "owner", "mines", "seed", "issued", "expires", "achieved"):
            self.assertNotIn(f'"{private}"', serialized)

    def test_parallel_callers_keep_their_own_verified_context(self):
        def view(index):
            with verified(claims_for(f"Person {index}")):
                return self.store.scores()
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(view, range(20)))
        self.assertEqual([row["player"]["name"] for row in results], [f"Person {i}" for i in range(20)])
        self.assertEqual(len({row["player"]["id"] for row in results}), 20)
        self.assertEqual(self.store._players, {})

    def test_concurrent_duplicate_flag_requests_toggle_only_once(self):
        with verified(claims_for()):
            run_id = self.store.start()["game"]["runId"]
        barrier = threading.Barrier(8)
        def move(_):
            with verified(claims_for()):
                barrier.wait(timeout=5)
                return self.store.move(run_id, "flag", 1, 0)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(move, range(8)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(results[0]["game"]["revision"], 1)
        self.assertEqual(results[0]["game"]["flagsUsed"], 1)

    def test_concurrent_conflicting_moves_only_one_commits(self):
        with verified(claims_for()):
            run_id = self.store.start()["game"]["runId"]
        barrier = threading.Barrier(2)
        def move(cell):
            with verified(claims_for()):
                barrier.wait(timeout=5)
                return self.store.move(run_id, "flag", cell, 0)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(move, [1, 2]))
        self.assertEqual(sum("error" not in result for result in results), 1)
        stale = next(result for result in results if "error" in result)
        self.assertEqual(stale["error"]["code"], "stale_revision")
        self.assertEqual(stale["game"]["revision"], 1)
        self.assertEqual(stale["game"]["flagsUsed"], 1)

    def test_concurrent_winning_retries_post_exactly_once(self):
        with verified(claims_for()):
            request = self.near_win()
        self.clock.advance(1.25)
        barrier = threading.Barrier(6)
        def finish(_):
            with verified(claims_for()):
                barrier.wait(timeout=5)
                return self.store.move(*request)
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(finish, range(6)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertTrue(results[0]["recorded"])
        self.assertTrue(results[0]["personalBest"])
        self.assertEqual(self.store._achievement, 1)
        self.assertEqual(len(self.store._players), 1)

    def test_fourth_start_retires_only_own_oldest_including_terminal_receipts(self):
        _, old, request = self.win("Alice")
        with verified(claims_for("Bob")):
            foreign = self.store.start()["game"]["runId"]
        with verified(claims_for("Alice")):
            newer = [self.store.start()["game"]["runId"] for _ in range(3)]
            self.assertEqual(self.store.move(*request)["error"]["code"], "unavailable_run")
        self.assertNotIn(old["game"]["runId"], self.store._runs)
        self.assertTrue(all(run_id in self.store._runs for run_id in newer))
        self.assertIn(foreign, self.store._runs)
        self.assertEqual(len(self.store._runs), 4)
        self.assertEqual(len(self.store._players), 1)

    def test_shared_capacity_rejects_without_evicting_other_players(self):
        store = MinesweeperState(clock=self.clock, max_runs=2)
        with verified(claims_for("Alice")):
            first = store.start()["game"]["runId"]
        with verified(claims_for("Bob")):
            second = store.start()["game"]["runId"]
        before = deepcopy(store._runs)
        with verified(claims_for("Carol")):
            self.assertEqual(store.start()["error"]["code"], "capacity")
            self.assertIsNotNone(store.scores()["player"])
        self.assertEqual(store._runs, before)
        self.assertEqual(set(store._runs), {first, second})

    def test_own_oldest_replacement_still_works_at_shared_capacity(self):
        store = MinesweeperState(clock=self.clock, max_runs=1, max_per_player=1)
        with verified(claims_for()):
            first = store.start()["game"]["runId"]
            second = store.start()["game"]["runId"]
            self.assertNotEqual(first, second)
            self.assertEqual(set(store._runs), {second})
            self.assertEqual(store.move(first, "reveal", 0, 0)["error"]["code"], "unavailable_run")

    def test_original_ttl_is_not_extended_by_moves_or_retries(self):
        store = MinesweeperState(clock=self.clock, max_runs=1)
        with verified(claims_for()):
            run_id = store.start()["game"]["runId"]
            self.clock.advance(7199)
            first = store.move(run_id, "flag", 0, 0)
            self.assertEqual(store.move(run_id, "flag", 0, 0), first)
            self.clock.advance(1)
            self.assertEqual(store.move(run_id, "flag", 0, 0)["error"]["code"], "unavailable_run")
        with verified(claims_for("Bob")):
            self.assertNotIn("error", store.start())
        self.assertEqual(len(store._runs), 1)

    def test_terminal_receipts_survive_until_ttl_while_scores_survive_expiry(self):
        store = MinesweeperState(clock=self.clock, sampler=spread_sample, max_runs=1)
        started, result, request = self.win(store=store, seconds=10)
        with verified(claims_for("Bob")):
            self.assertEqual(store.start()["error"]["code"], "capacity")
        with verified(claims_for("Alice")):
            self.assertEqual(store.move(*request), result)
        self.clock.advance(7190)
        with verified(claims_for("Alice")):
            scores = store.scores()  # getter prunes exactly at original expiry
            self.assertEqual(scores["totalPlayers"], 1)
            self.assertEqual(store._runs, {})
            self.assertEqual(store.move(*request)["error"]["code"], "unavailable_run")
        with verified(claims_for("Bob")):
            self.assertNotIn("error", store.start())
        self.assertNotIn(started["game"]["runId"], store._runs)

    def test_player_slots_are_reserved_before_start_not_denied_after_winning(self):
        store = MinesweeperState(clock=self.clock, sampler=spread_sample, max_players=2)
        with verified(claims_for("Alice")):
            _, alice = self.start_playing(store)
        with verified(claims_for("Bob")):
            _, bob = self.start_playing(store)
        with verified(claims_for("Carol")):
            self.assertEqual(store.start()["error"]["code"], "capacity")
        for name, result in (("Alice", alice), ("Bob", bob)):
            with verified(claims_for(name)):
                won, _ = self.solve(result, store)
                self.assertTrue(won["recorded"])
        self.assertEqual(len(store._players), 2)
        with verified(claims_for("Carol")):
            self.assertEqual(store.start()["error"]["code"], "capacity")
        with verified(claims_for("Alice")):
            self.assertNotIn("error", store.start())  # existing best owner still plays

    def test_loss_and_expiry_release_unscored_player_reservations(self):
        store = MinesweeperState(clock=self.clock, sampler=spread_sample, max_players=1)
        with verified(claims_for("Alice")):
            _, playing = self.start_playing(store)
            run_id = playing["game"]["runId"]
            private = store._runs[run_id]["game"]
        with verified(claims_for("Bob")):
            self.assertEqual(store.start()["error"]["code"], "capacity")
        with verified(claims_for("Alice")):
            self.assertEqual(store.move(run_id, "reveal", min(private.mines), private.revision)["game"]["status"], "lost")
        with verified(claims_for("Bob")):
            self.assertNotIn("error", store.start())
        self.clock.advance(7200)
        with verified(claims_for("Carol")):
            self.assertNotIn("error", store.start())
        self.assertEqual(store._players, {})

    def test_restart_resets_scores_runs_epoch_and_opaque_player_ids(self):
        _, result, request = self.win()
        fresh = MinesweeperState(clock=self.clock, sampler=spread_sample)
        with verified(claims_for()):
            view = fresh.scores()
            self.assertNotEqual(result["epoch"], view["epoch"])
            self.assertNotEqual(result["player"]["id"], view["player"]["id"])
            self.assertEqual(view["leaderboard"], [])
            self.assertEqual(view["player"]["bestScore"], 0)
            self.assertEqual(fresh.move(*request)["error"]["code"], "unavailable_run")
        self.assertEqual(fresh._runs, {})
        self.assertEqual(fresh._players, {})

    def test_configuration_is_strict_bounded_and_finite(self):
        bad = [{"max_runs": value} for value in (0, -1, True, 1.0)]
        bad += [{"max_per_player": 0}, {"max_players": False}]
        bad += [{"ttl_seconds": value} for value in (0, -1, True, "7200", float("nan"), float("inf"))]
        for kwargs in bad:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                MinesweeperState(**kwargs)

    def test_game_state_and_scoring_do_not_use_files_or_wall_clock(self):
        with mock.patch("builtins.open", side_effect=AssertionError("unexpected persistence")), \
             mock.patch("time.time", side_effect=AssertionError("wall clock used")):
            self.win()
            with verified(claims_for()):
                self.assertEqual(self.store.scores()["totalPlayers"], 1)


class AppContractTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.store = MinesweeperState(clock=self.clock, sampler=spread_sample)
        patch = mock.patch.object(app_module, "_STATE", self.store)
        patch.start()
        self.addCleanup(patch.stop)
        app_module._app_html.cache_clear()
        self.addCleanup(app_module._app_html.cache_clear)
        self.server = MCPServer("minesweeper-test", extensions=[Apps()])

    def call(self, name, arguments):
        return asyncio.run(self.server.call_tool(name, arguments)).structured_content

    def test_registration_is_asset_independent_with_one_model_facing_tool(self):
        with mock.patch.object(Path, "read_text", side_effect=AssertionError("registration read frontend")):
            register_catalog_tool(self.server, "minesweeper")
        tools = asyncio.run(self.server.list_tools())
        self.assertEqual({tool.name for tool in tools}, {
            "minesweeper", "minesweeper_start", "minesweeper_move", "minesweeper_scores",
        })
        visible = [tool.name for tool in tools if tool.meta["ui"].get("visibility") != ["app"]]
        self.assertEqual(visible, ["minesweeper"])
        for tool in tools:
            self.assertEqual(tool.meta["ui"]["resourceUri"], "ui://minesweeper/app.html")
            self.assertFalse(tool.input_schema["additionalProperties"])
            if tool.name != "minesweeper":
                self.assertEqual(tool.meta["ui"]["visibility"], ["app"])

    def test_input_schemas_are_exact_and_bounded(self):
        register_catalog_tool(self.server, "minesweeper")
        tools = {tool.name: tool for tool in asyncio.run(self.server.list_tools())}
        self.assertEqual(tools["minesweeper"].input_schema["properties"], {})
        self.assertEqual(tools["minesweeper_scores"].input_schema["properties"], {})
        start = tools["minesweeper_start"].input_schema
        self.assertEqual(set(start["properties"]), {"difficulty"})
        self.assertEqual(start["properties"]["difficulty"]["enum"], ["beginner", "intermediate", "expert"])
        self.assertEqual(start["properties"]["difficulty"]["default"], "beginner")
        move = tools["minesweeper_move"].input_schema
        self.assertEqual(set(move["properties"]), {"run_id", "action", "cell", "revision"})
        self.assertEqual(set(move["required"]), {"run_id", "action", "cell", "revision"})
        self.assertEqual(move["properties"]["action"]["enum"], ["reveal", "flag", "chord"])
        self.assertEqual(move["properties"]["cell"]["type"], "integer")
        self.assertEqual(move["properties"]["cell"]["minimum"], 0)
        self.assertEqual(move["properties"]["cell"]["exclusiveMaximum"], 480)
        self.assertEqual(move["properties"]["revision"]["minimum"], 0)
        self.assertEqual(move["properties"]["run_id"]["minLength"], 20)
        self.assertEqual(move["properties"]["run_id"]["maxLength"], 128)

    def test_real_calls_use_verified_context_and_domain_error_shape(self):
        register_catalog_tool(self.server, "minesweeper")
        with verified(claims_for("Alice")):
            main = self.call("minesweeper", {})
            self.assertEqual(main["player"]["name"], "Alice")
            self.assertEqual(self.store._runs, {})
            start = self.call("minesweeper_start", {})
            self.assertEqual(start["game"]["difficulty"], "beginner")
            result = self.call("minesweeper_move", {
                "run_id": start["game"]["runId"], "action": "reveal", "cell": 40, "revision": 0,
            })
            self.assertEqual(result["game"]["revision"], 1)
            self.assertEqual(result["game"]["status"], "playing")
            stale = self.call("minesweeper_move", {
                "run_id": start["game"]["runId"], "action": "flag", "cell": 0, "revision": 0,
            })
            self.assertEqual(stale["error"]["code"], "stale_revision")
            self.assertEqual(stale["game"]["revision"], 1)
        with verified(claims_for("Bob")):
            denied = self.call("minesweeper_move", {
                "run_id": start["game"]["runId"], "action": "reveal", "cell": 0, "revision": 1,
            })
            self.assertEqual(denied["error"]["code"], "unavailable_run")
            self.assertNotIn("game", denied)
            self.assertEqual(self.call("minesweeper_scores", {})["player"]["name"], "Bob")
        with verified(claims_for("App", scp="", idtyp="app")):
            self.assertEqual(self.call("minesweeper_start", {})["error"]["code"], "ineligible")
            self.assertFalse(self.call("minesweeper", {})["canPlay"])

    def test_strict_mcp_validation_rejects_booleans_floats_strings_and_invalid_values(self):
        register_catalog_tool(self.server, "minesweeper")
        with verified(claims_for()):
            run_id = self.store.start()["game"]["runId"]
            base = {"run_id": run_id, "action": "flag", "cell": 0, "revision": 0}
            invalid = [{"cell": value} for value in (True, False, 0.0, "0", "true", None, -1, 480)]
            invalid += [{"revision": value} for value in (True, 0.0, "0", "true", None, -1)]
            invalid += [{"action": value} for value in ("FLAG", "boom", True, [], None)]
            invalid += [{"run_id": value} for value in (True, 100, "short", "x" * 129)]
            for args in invalid:
                with self.subTest(args=args), self.assertRaises(ToolError):
                    self.call("minesweeper_move", {**base, **args})
            for field in base:
                with self.subTest(missing=field), self.assertRaises(ToolError):
                    self.call("minesweeper_move", {key: value for key, value in base.items() if key != field})
            for difficulty in ("easy", "BEGINNER", True, [], None):
                with self.subTest(difficulty=difficulty), self.assertRaises(ToolError):
                    self.call("minesweeper_start", {"difficulty": difficulty})
            self.assertEqual(self.store._runs[run_id]["game"].revision, 0)
            self.assertEqual(self.store._runs[run_id]["game"].flags, set())

    def test_unknown_identity_score_clock_and_layout_arguments_are_forbidden(self):
        register_catalog_tool(self.server, "minesweeper")
        with verified(claims_for()):
            run_id = self.store.start()["game"]["runId"]
            for name, args in [("minesweeper", {}), ("minesweeper_start", {}),
                               ("minesweeper_scores", {}), ("minesweeper_move", {
                                   "run_id": run_id, "action": "flag", "cell": 0, "revision": 0,
                               })]:
                for key, value in [("name", "Spoof"), ("oid", "someone-else"), ("score", 999999),
                                   ("elapsedMs", 0), ("mines", []), ("player", {"id": "spoof"})]:
                    with self.subTest(tool=name, key=key), self.assertRaises(ToolError):
                        self.call(name, {**args, key: value})
        self.assertEqual(len(self.store._runs), 1)
        self.assertEqual(self.store._runs[run_id]["game"].revision, 0)
        self.assertEqual(self.store._players, {})

    def test_strict_schema_hardening_does_not_change_other_tools(self):
        register_catalog_tool(self.server, "minesweeper")
        @self.server.tool()
        def unrelated(value: int) -> dict[str, int]:
            return {"value": value}
        self.assertEqual(self.call("unrelated", {"value": "2", "extra": "ignored"}), {"value": 2})
        other = next(tool for tool in asyncio.run(self.server.list_tools()) if tool.name == "unrelated")
        self.assertNotEqual(other.input_schema.get("additionalProperties"), False)

    def test_resource_csp_and_lazy_adjacent_html_js_inlining_and_cache(self):
        register_catalog_tool(self.server, "minesweeper")
        resources = asyncio.run(self.server.list_resources())
        self.assertEqual(len(resources), 1)
        resource = resources[0]
        self.assertEqual(str(resource.uri), "ui://minesweeper/app.html")
        self.assertEqual(resource.mime_type, "text/html;profile=mcp-app")
        self.assertEqual(resource.meta["ui"]["csp"], {"resourceDomains": [], "connectDomains": []})
        self.assertNotIn("permissions", resource.meta["ui"])
        assets = Path("/synthetic/minesweeper-assets")
        contents = {
            assets / "app.html": "<!doctype html><main>Minesweeper</main><!-- app.js -->",
            assets / "app.js": "globalThis.__minesweeper_test = 1;",
        }
        def read_asset(path, *, encoding):
            self.assertEqual(encoding, "utf-8")
            return contents[path]
        with mock.patch.object(app_module, "ASSETS", assets), \
             mock.patch.object(Path, "read_text", autospec=True, side_effect=read_asset) as reader:
            results = list(asyncio.run(self.server.read_resource(app_module.RESOURCE_URI)))
            self.assertEqual(len(results), 1)
            html = results[0].content
            self.assertIn('<script type="module">', html)
            self.assertIn("globalThis.__minesweeper_test = 1;", html)
            self.assertNotIn("<!-- app.js -->", html)
            self.assertEqual(reader.call_count, 2)
            self.assertEqual(app_module._app_html(), html)
            self.assertEqual(reader.call_count, 2)

    def test_missing_or_duplicate_script_marker_is_rejected_without_real_assets(self):
        for html in ("<!doctype html><main>No marker</main>", "<!-- app.js --><!-- app.js -->"):
            app_module._app_html.cache_clear()
            with mock.patch.object(Path, "read_text", side_effect=[html, "export {};"]):
                with self.assertRaisesRegex(ValueError, "exactly one"):
                    app_module._app_html()

    def test_registration_and_overview_work_when_frontend_files_are_absent(self):
        with mock.patch.object(Path, "read_text", side_effect=FileNotFoundError("not built yet")):
            register_catalog_tool(self.server, "minesweeper")
            with verified(claims_for()):
                self.assertEqual(self.call("minesweeper", {})["title"], "Minesweeper")
            with self.assertRaises(FileNotFoundError):
                app_module._app_html()


if __name__ == "__main__":
    unittest.main()
