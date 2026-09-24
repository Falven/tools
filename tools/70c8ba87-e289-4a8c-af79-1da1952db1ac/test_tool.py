"""Regression tests. All identities and scores here are synthetic test fixtures."""

import asyncio
import json
import os
import random
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.server.mcpserver import MCPServer

import tool


@contextmanager
def caller(oid="fixture-one", tenant="fixture-tenant", name="Fixture One",
           email="fixture.one@example.test", extra=None):
    claims = {"tid": tenant, "oid": oid, "iss": "https://issuer.example.test/",
              "sub": oid, "scp": "access_as_user", "name": name, "email": email}
    claims.update(extra or {})
    token = AccessToken(token="SYNTHETIC_NOT_A_REAL_CREDENTIAL", client_id="fixture-client",
                        scopes=["access_as_user"], subject=oid, claims=claims)
    previous = auth_context_var.set(AuthenticatedUser(token))
    try:
        yield token
    finally:
        auth_context_var.reset(previous)


def bot_trace(seed, foods=3, max_steps=1400):
    """Create an actual rule-valid replay; it never submits a client score."""
    game = tool._Game(seed)
    trace = []
    for _ in range(max_steps):
        legal = []
        for direction, (dx, dy) in enumerate(tool._DIRECTIONS):
            if (direction + 2) % 4 == game.direction:
                continue
            cell = (game.snake[0][0] + dx, game.snake[0][1] + dy)
            body = game.snake if cell == game.food else game.snake[:-1]
            if 0 <= cell[0] < 18 and 0 <= cell[1] < 18 and cell not in body:
                distance = abs(cell[0] - game.food[0]) + abs(cell[1] - game.food[1])
                legal.append((distance, direction))
        direction = (min(legal)[1] if legal and game.apples < foods else game.direction)
        game.step(direction)
        trace.append(str(direction))
        if game.over:
            break
    if not game.over:
        while not game.over:
            trace.append(str(game.direction))
            game.step(game.direction)
    return "".join(trace), game


class RulesTests(unittest.TestCase):
    def test_initial_state_and_deterministic_food(self):
        for seed in (1, 99, 2**31, 2**32 - 1):
            first, second = tool._Game(seed), tool._Game(seed)
            self.assertEqual(first.snake, [(6, 9), (5, 9), (4, 9), (3, 9)])
            self.assertEqual(first.food, second.food)
            self.assertNotIn(first.food, first.snake)
            self.assertEqual(first.score, 0)
            self.assertEqual(first.interval, 165)

    def test_wall_collision_and_final_tick(self):
        game = tool._replay(1, "1" * 12)
        self.assertEqual(game.over, "wall")
        self.assertEqual(game.steps, 12)
        self.assertEqual(game.duration_ms, 1980)
        self.assertEqual(game.snake[0], (17, 9))

    def test_reversal_incomplete_and_trailing_replays_rejected(self):
        for trace in ("3", "1", "1" * 13, "x", "", "0" * (tool.MAX_STEPS + 1)):
            with self.subTest(trace_length=len(trace)):
                with self.assertRaises(ValueError):
                    tool._replay(1, trace)

    def test_growth_and_speed_threshold(self):
        game = tool._Game(1)
        for x in range(7, 12):
            game.food = (x, 9)
            game.step(1)
        self.assertEqual(game.apples, 5)
        self.assertEqual(game.score, 50)
        self.assertEqual(len(game.snake), 9)
        self.assertEqual(game.interval, 153)
        self.assertEqual(game.duration_ms, 825)
        game.apples = 999
        self.assertEqual(game.interval, 75)

    def test_vacating_tail_is_not_a_collision(self):
        game = tool._Game(1)
        game.snake = [(1, 1), (1, 2), (0, 2), (0, 1)]
        game.direction, game.food = 0, (17, 17)
        game.step(3)
        self.assertEqual(game.over, "")
        self.assertEqual(game.snake[0], (0, 1))

    def test_body_collision(self):
        game = tool._Game(1)
        game.snake = [(1, 1), (1, 2), (0, 2), (0, 1), (0, 0), (1, 0)]
        game.direction, game.food = 0, (17, 17)
        game.step(3)
        self.assertEqual(game.over, "self")

    def test_full_board_win_and_move_limit(self):
        game = tool._Game(1)
        game.snake = [(0, 0)] + [(x, y) for y in range(18) for x in range(18)
                                if (x, y) not in ((0, 0), (1, 0))]
        game.food, game.direction = (1, 0), 1
        game.step(1)
        self.assertEqual(game.over, "win")
        self.assertEqual(len(game.snake), 324)
        self.assertIsNone(game.food)
        game = tool._Game(1)
        game.steps = tool.MAX_STEPS - 1
        game.step(1)
        self.assertEqual(game.over, "limit")

    def test_javascript_python_replay_parity(self):
        try:
            import playwright
        except ImportError:
            self.skipTest("Install the browser test dependency to run JavaScript parity.")
        node = Path(playwright.__file__).parent / "driver" / "node"
        source = (tool.ASSETS / "app.js").read_text().split("// END SNAKE ENGINE")[0]
        seeds = [1, 2**31 - 1, 2**31, 2**32 - 1]
        seeds += random.Random(42).sample(range(1, 2**32), 36)
        fixtures, expected = [], []
        for seed in seeds:
            trace, game = bot_trace(seed, foods=22)
            fixtures.append({"seed": seed, "trace": trace})
            expected.append({
                "rng": game.rng, "snake": [list(p) for p in game.snake],
                "food": list(game.food) if game.food else None, "score": game.score,
                "apples": game.apples, "steps": game.steps,
                "duration": game.duration_ms, "over": game.over,
            })
        script = source + """
            const fs = require("node:fs");
            const results = JSON.parse(fs.readFileSync(0, "utf8")).map(f => {
                const g = new SnakeEngine(f.seed);
                for (const d of f.trace) g.step(Number(d));
                return {rng:g.rng,snake:g.snake,food:g.food,score:g.score,
                    apples:g.apples,steps:g.steps,duration:g.durationMs,over:g.over};
            });
            process.stdout.write(JSON.stringify(results));
        """
        result = subprocess.run([str(node), "-e", script], input=json.dumps(fixtures),
                                text=True, capture_output=True, check=True, timeout=30)
        self.assertEqual(json.loads(result.stdout), expected)
        self.assertGreater(max(row["score"] for row in expected), 100)


class StorageTests(unittest.TestCase):
    def setUp(self):
        artifacts = tool.ASSETS / ".test-artifacts"
        artifacts.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="unit-", dir=artifacts)
        self.db_path = Path(self.temp.name) / "scores.sqlite3"
        self.env = patch.dict(os.environ, {"NEON_SNAKE_DB_PATH": str(self.db_path)})
        self.env.start()
        self.clock = 1_000_000
        self.time_patch = patch.object(tool, "_now", side_effect=lambda: self.clock)
        self.time_patch.start()

    def tearDown(self):
        self.time_patch.stop()
        self.env.stop()
        self.temp.cleanup()

    def begin(self, seed=1):
        with patch.object(tool.secrets, "randbelow", return_value=seed - 1):
            result = tool._begin_run()
        self.assertTrue(result["ok"], result)
        return result["run"]["run_id"]

    def record(self, seed=1, foods=3):
        run_id = self.begin(seed)
        replay, game = bot_trace(seed, foods)
        self.clock += game.duration_ms + 1000
        result = tool._finish_run(run_id, replay)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["saved_run"]["score"], game.score)
        return run_id, replay, result

    def test_guest_does_not_read_or_write_storage(self):
        self.assertFalse(tool.new_tool()["player"]["authenticated"])
        self.assertEqual(tool._get_board()["leaderboard"], [])
        self.assertFalse(tool._begin_run()["ok"])
        self.assertFalse(tool._save_profile("Guest", "guest@example.test")["ok"])
        self.assertFalse(self.db_path.exists())

    def test_automatic_profile_and_safe_fallback(self):
        with caller() as token:
            result = tool.new_tool()
            self.assertTrue(result["player"]["ready"])
            self.assertEqual(result["player"]["display_name"], "Fixture One")
            self.assertEqual(result["player"]["email_hint"], "f•••@example.test")
            self.assertIn("Open App", result["message"])
            self.assertNotIn(token.token, json.dumps(result))
            self.assertNotIn("fixture.one@example.test", json.dumps(result))
            with tool._database() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM profiles").fetchone()[0], 0)
            self.begin()
            with tool._database() as db:
                self.assertEqual(db.execute("SELECT email FROM profiles").fetchone()[0], "fixture.one@example.test")
            self.assertEqual(self.db_path.stat().st_mode & 0o777, 0o600)

    def test_missing_profile_requested_once(self):
        with caller(name="", email=""):
            self.assertEqual(tool._begin_run()["error"]["code"], "profile_required")
            self.assertEqual(set(tool.new_tool()["player"]["missing_fields"]), {"display_name", "email"})
            self.assertTrue(tool._save_profile("Player Label", "label@example.test")["ok"])
            self.assertTrue(tool.new_tool()["player"]["ready"])
            self.begin()

    def test_claimed_profile_cannot_be_overwritten(self):
        with caller():
            result = tool._save_profile("An impostor", "someone.else@example.test")
            self.assertTrue(result["ok"])
            with tool._database() as db:
                row = db.execute("SELECT * FROM profiles").fetchone()
                self.assertEqual(row["display_name"], "Fixture One")
                self.assertEqual(row["email"], "fixture.one@example.test")

    def test_invalid_profile_rejected_and_rolled_back(self):
        with caller(name="", email=""):
            for name, email in [("X" * 81, "x@example.test"), ("Good", "not-mail"),
                                ("Bad\nName", "x@example.test"), ("Good", "x@example.test\nINJECT")]:
                self.assertFalse(tool._save_profile(name, email)["ok"])
            self.assertFalse(tool.new_tool()["player"]["ready"])

    def test_completed_score_automatic_and_idempotent(self):
        with caller():
            run_id, replay, first = self.record()
            self.assertGreater(first["saved_run"]["score"], 0)
            second = tool._finish_run(run_id, replay)
            self.assertTrue(second["saved_run"]["already_saved"])
            self.assertEqual(second["total_runs"], 1)
            self.assertEqual(second["player"]["total_runs"], 1)
            self.assertEqual(second["player"]["best_rank"], 1)
            self.assertNotIn("fixture.one@example.test", json.dumps(second))
            self.assertEqual(tool._finish_run(run_id, replay + "1")["error"]["code"], "already_recorded")

    def test_cross_account_and_cross_tenant_protected(self):
        with caller():
            run_id, replay, _ = self.record()
        with caller(oid="other-player", name="Other", email="fixture.one@example.test"):
            self.assertEqual(tool._finish_run(run_id, replay)["error"]["code"], "invalid_run")
            self.assertEqual(tool._get_board()["total_players"], 1)
            self.assertEqual(tool._get_board("mine")["leaderboard"], [])
            self.record(seed=2, foods=1)
            self.assertEqual(tool._get_board()["total_players"], 2)
        with caller(tenant="different-tenant"):
            self.assertEqual(tool._get_board()["leaderboard"], [])
            self.assertEqual(tool._finish_run(run_id, replay)["error"]["code"], "invalid_run")

    def test_immutable_account_survives_name_and_email_changes(self):
        with caller():
            _, _, original = self.record()
        with caller(name="New Display", email="new.address@example.test"):
            current = tool.new_tool()
            self.assertEqual(current["player"]["best_score"], original["saved_run"]["score"])
            self.assertEqual(current["player"]["total_runs"], 1)
            self.assertEqual(current["player"]["display_name"], "New Display")

    def test_descending_order_and_shorter_time_tie_break(self):
        with caller():
            for seed, foods in [(1, 1), (2, 5), (3, 3), (4, 1)]:
                self.record(seed, foods)
            result = tool._get_board()
            rows = result["leaderboard"]
            self.assertEqual([r["score"] for r in rows], sorted([r["score"] for r in rows], reverse=True))
            self.assertEqual([(r["score"], -r["duration_ms"]) for r in rows],
                             sorted([(r["score"], -r["duration_ms"]) for r in rows], reverse=True))
            self.assertEqual([r["rank"] for r in rows], [1, 2, 3, 4])
            self.assertEqual(result["player"]["best_score"], rows[0]["score"])

    def test_time_validation_expiration_and_unfinished_run(self):
        with caller():
            run_id = self.begin()
            self.assertEqual(tool._finish_run(run_id, "1")["error"]["code"], "invalid_replay")
            self.assertEqual(tool._finish_run(run_id, "3")["error"]["code"], "invalid_replay")
            self.assertEqual(tool._finish_run(run_id, "1" * 12)["error"]["code"], "too_fast")
            self.assertEqual(tool.new_tool()["total_runs"], 0)
            self.clock += tool.RUN_TTL_MS + 1
            self.assertEqual(tool._finish_run(run_id, "1" * 12)["error"]["code"], "run_expired")

    def test_run_start_rate_limit(self):
        with caller():
            for _ in range(8):
                self.begin()
            self.assertEqual(tool._begin_run()["error"]["code"], "rate_limited")
            self.clock += 61000
            self.begin()

    def test_concurrent_exact_retries_record_only_once(self):
        with caller():
            run_id = self.begin()
        self.clock += 3000

        def submit():
            with caller():
                return tool._finish_run(run_id, "1" * 12)

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: submit(), range(4)))
        self.assertTrue(all(result["ok"] for result in results), results)
        self.assertEqual(sum(not r["saved_run"]["already_saved"] for r in results), 1)
        with caller():
            self.assertEqual(tool.new_tool()["total_runs"], 1)

    def test_delete_only_own_data_requires_confirmation(self):
        with caller():
            self.record()
            self.assertEqual(tool._forget_my_data()["error"]["code"], "confirmation_required")
        with caller(oid="other"):
            self.record()
        with caller():
            result = tool._forget_my_data(confirm=True)
            self.assertEqual(result["player"]["total_runs"], 0)
            self.assertEqual(result["total_runs"], 1)
            with tool._database() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM profiles").fetchone()[0], 1)

    def test_service_principal_is_not_a_shared_player(self):
        with caller(extra={"idtyp": "app", "roles": ["access"], "scp": ""}):
            self.assertFalse(tool.new_tool()["player"]["authenticated"])
            self.assertFalse(tool._begin_run()["ok"])

    def test_storage_failure_is_clear_and_sanitized(self):
        with caller(), patch.dict(os.environ, {"NEON_SNAKE_DB_PATH": self.temp.name}):
            result = tool.new_tool()
            self.assertFalse(result["storage"]["available"])
            error = tool._begin_run()
            self.assertEqual(error["error"]["code"], "storage_unavailable")
            self.assertNotIn(self.temp.name, json.dumps(error))


class InterfaceTests(unittest.TestCase):
    def test_official_mcp_sdk_tool_registration_and_fallback(self):
        async def check():
            server = MCPServer("Neon Snake tests", extensions=[tool.apps])
            tools = [entry.model_dump(by_alias=True) for entry in await server.list_tools()]
            self.assertEqual(len(tools), 6)
            self.assertEqual({entry["name"] for entry in tools}, {
                "new_tool", "neon_snake_board", "neon_snake_profile",
                "neon_snake_begin", "neon_snake_finish", "neon_snake_forget",
            })
            for entry in tools:
                self.assertEqual(entry["_meta"]["ui"]["resourceUri"], tool.RESOURCE_URI)
                if entry["name"] != "new_tool":
                    self.assertEqual(entry["_meta"]["ui"]["visibility"], ["app"])
            result = (await server.call_tool("new_tool", {})).model_dump(by_alias=True)
            self.assertFalse(result.get("isError", False))
            self.assertEqual(result["structuredContent"]["kind"], "neon_snake")
            self.assertIn("Open the Neon Snake App", result["content"][0]["text"])
            resources = await server.read_resource(tool.RESOURCE_URI)
            self.assertEqual(resources[0].mime_type, "text/html;profile=mcp-app")
            self.assertIn("class SnakeEngine", resources[0].content)
            self.assertEqual(resources[0].meta["ui"]["csp"]["resourceDomains"], ["https://cdn.jsdelivr.net"])
        asyncio.run(check())

    def test_inline_assets_and_safe_text_rendering(self):
        self.assertEqual(tool.__all__, ["new_tool"])
        self.assertNotIn("<!-- app.js -->", tool.HTML)
        self.assertNotIn('src="app.js"', tool.HTML)
        self.assertIn("three@0.180.0", tool.HTML)
        self.assertIn("ext-apps@2.0.0", tool.HTML)
        script = (tool.ASSETS / "app.js").read_text()
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("localStorage", script)
        self.assertNotIn("fetch(", script)


if __name__ == "__main__":
    unittest.main(verbosity=2)