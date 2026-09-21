"""Standard-library backend regression tests; no SDK, network, or real login.

The AST loader substitutes only the App registration/authentication boundary.
All validation, persistence, revision, and presence functions come from tool.py.
These tests do NOT validate a real MCP connection or authorization deployment.
Run from the Tool Directory: python3 -m unittest discover -s tests -v
"""

import ast
import copy
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class _Apps:
    def __init__(self):
        self.tools = []
        self.resources = []

    def tool(self, **metadata):
        def decorate(function):
            self.tools.append((function.__name__, metadata))
            return function
        return decorate

    def add_html_resource(self, uri, html, **metadata):
        self.resources.append((uri, html, metadata))


class _Csp:
    def __init__(self, **kwargs):
        self.values = kwargs


def _load():
    source = ast.parse((ROOT / "tool.py").read_text(encoding="utf-8"))
    sdk_imports = {
        "mcp.server.apps",
        "mcp.server.auth.middleware.auth_context",
        "toolforge",
    }
    source.body = [
        node for node in source.body
        if not (isinstance(node, ast.ImportFrom) and node.module in sdk_imports)
    ]
    namespace = {
        "__file__": str(ROOT / "tool.py"),
        "__name__": "paperweave_backend_tests",
        "Apps": _Apps,
        "ResourceCsp": _Csp,
        "get_access_token": lambda: "TEST_AUTH_CANARY_NOT_A_TOKEN",
        "get_caller_credential": lambda: object(),
    }
    # Only our repository's tool.py is compiled here, never a caller payload.
    exec(compile(source, str(ROOT / "tool.py"), "exec"), namespace)  # noqa: S102
    return namespace


class PaperweaveBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = _load()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.ns["_DATA"] = Path(self.directory.name) / "boards"
        self.ns["get_access_token"] = lambda: "TEST_AUTH_CANARY_NOT_A_TOKEN"
        self.ns["get_caller_credential"] = lambda: object()
        self.main = self.ns["paperweave_whiteboard"]

    def tearDown(self):
        self.directory.cleanup()

    def board(self, template="blank"):
        response = self.main(template=template)
        self.assertTrue(response["ok"], response)
        return response["board"]

    def edit(self, board, ops, request="request_0001", revision=None):
        return self.main(
            action="edit", board_id=board["id"],
            base_revision=board["revision"] if revision is None else revision,
            operations=ops, request_id=request,
        )

    def test_registration_and_single_inlined_resource(self):
        self.assertEqual(self.ns["__all__"], ["paperweave_whiteboard"])
        app = self.ns["apps"]
        self.assertEqual(len(app.resources), 1)
        uri, html, metadata = app.resources[0]
        self.assertEqual(uri, "ui://paperweave/board.html")
        self.assertNotIn("<!-- app.js -->", html)
        self.assertNotIn("<!-- initial-scene -->", html)
        self.assertIn("function nodeMarkup(", html)
        self.assertIn('@modelcontextprotocol/ext-apps@2.0.0', html)
        self.assertEqual(metadata["csp"].values["resource_domains"], ["https://cdn.jsdelivr.net"])
        handlers = {name: meta for name, meta in app.tools if name != "paperweave_whiteboard"}
        self.assertEqual(set(handlers), {"paperweave_apply_changes", "paperweave_open_canvas", "paperweave_sync_canvas"})
        for meta in handlers.values():
            self.assertEqual(meta["visibility"], ["app"])
            self.assertEqual(meta["resource_uri"], uri)

    def test_create_open_and_useful_fallback(self):
        response = self.main()
        self.assertTrue(response["ok"])
        board = response["board"]
        self.assertRegex(board["id"], r"^pw_[0-9a-f]{32}$")
        self.assertEqual(board["revision"], 0)
        self.assertEqual(len(board["elements"]), 13)
        self.assertIn("13 elements", response["message"])
        self.assertIn("server's local disk", response["storage"])
        self.assertEqual(self.main(board_id=board["id"])["board"], board)

    def test_all_templates_have_valid_threads(self):
        for name in ("blank", "studio", "flow", "mindmap"):
            with self.subTest(template=name):
                board = self.board(name)
                self.ns["_limits"](board["elements"])
                ids = [e["id"] for e in board["elements"]]
                self.assertEqual(len(ids), len(set(ids)))

    def test_add_update_rename_and_cascade_delete(self):
        board = self.board()
        result = self.edit(board, [
            {"op": "add", "element": {"id": "a", "text": "Alpha"}},
            {"op": "add", "element": {"id": "b", "text": "Beta"}},
            {"op": "add", "element": {"id": "link", "kind": "connector", "source": "a", "target": "b"}},
        ])
        self.assertTrue(result["ok"], result)
        result = self.edit(result["board"], [
            {"op": "update", "id": "a", "changes": {"x": 550, "text": "Changed"}},
            {"op": "rename", "text": "Our diagram"},
        ], "request_0002")
        self.assertEqual(result["board"]["title"], "Our diagram")
        a = next(e for e in result["board"]["elements"] if e["id"] == "a")
        self.assertEqual(a["x"], 550)
        self.assertEqual(a["_by"], "agent")
        result = self.edit(result["board"], [{"op": "delete", "id": "a"}], "request_0003")
        self.assertEqual([e["id"] for e in result["board"]["elements"]], ["b"])

    def test_failure_is_atomic(self):
        board = self.board()
        result = self.edit(board, [
            {"op": "add", "element": {"id": "valid"}},
            {"op": "update", "id": "missing", "changes": {"text": "No"}},
        ])
        self.assertFalse(result["ok"])
        self.assertEqual(self.main(board_id=board["id"])["board"], board)

    def test_dangling_threads_and_duplicate_ids_are_rejected(self):
        board = self.board()
        for ops in (
            [{"op": "add", "element": {"kind": "connector", "source": "x", "target": "y"}}],
            [{"op": "add", "element": {"id": "same"}}, {"op": "add", "element": {"id": "same"}}],
        ):
            result = self.edit(board, ops)
            self.assertEqual(result["code"], "validation")
        self.assertEqual(self.main(board_id=board["id"])["board"]["revision"], 0)

    def test_revision_conflict_returns_latest_without_overwrite(self):
        board = self.board()
        saved = self.edit(board, [{"op": "rename", "text": "First editor"}])
        conflict = self.edit(board, [{"op": "rename", "text": "Stale editor"}], "request_0002")
        self.assertEqual(conflict["code"], "conflict")
        self.assertEqual(conflict["board"], saved["board"])
        self.assertEqual(self.main(board_id=board["id"])["board"]["title"], "First editor")

    def test_same_request_is_deduplicated_even_after_later_edits(self):
        board = self.board()
        ops = [{"op": "add", "element": {"id": "once"}}]
        first = self.edit(board, ops)
        second = self.edit(first["board"], [{"op": "rename", "text": "Later"}], "request_0002")
        replay = self.edit(board, ops)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["applied_revision"], 1)
        self.assertEqual(replay["board"], second["board"])
        self.assertEqual(len(replay["board"]["elements"]), 1)
        invalid = self.edit(board, [{"op": "rename", "text": "Different payload"}])
        self.assertEqual(invalid["code"], "request_reused")

    def test_simultaneous_edits_have_only_one_winner(self):
        board = self.board()
        def worker(index):
            return self.edit(board, [{"op": "rename", "text": f"Editor {index}"}], f"request_{index:04d}")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, [1, 2]))
        self.assertEqual(sum(bool(result["ok"]) for result in results), 1)
        self.assertEqual(sum(result.get("code") == "conflict" for result in results), 1)
        self.assertEqual(self.main(board_id=board["id"])["board"]["revision"], 1)

    def test_boards_are_isolated_and_unknown_codes_do_not_create(self):
        first, second = self.board(), self.board()
        self.edit(first, [{"op": "rename", "text": "Only the first"}])
        self.assertEqual(self.main(board_id=second["id"])["board"], second)
        self.assertEqual(self.main(board_id="pw_" + "0" * 32)["code"], "not_found")
        self.assertEqual(self.main(board_id="../../other-file")["code"], "validation")

    def test_finite_coordinates_and_payload_limits(self):
        board = self.board()
        for value in (float("inf"), float("nan"), True, 20001, "12", 10 ** 1000):
            with self.subTest(value_type=type(value).__name__):
                result = self.edit(board, [{"op": "add", "element": {"x": value}}])
                self.assertEqual(result["code"], "validation")
        too_many = [{"op": "add", "element": {"id": f"e_{i}"}} for i in range(401)]
        self.assertEqual(self.edit(board, too_many)["code"], "validation")
        self.assertEqual(self.edit(board, [])["code"], "validation")
        self.assertEqual(self.main(board_id=board["id"])["board"]["revision"], 0)

    def test_stroke_normalization_and_point_limit(self):
        board = self.board()
        stroke = {"id": "pen", "kind": "stroke", "x": 100, "y": 100, "points": [[-20, -10], [50, 70]]}
        result = self.edit(board, [{"op": "add", "element": stroke}])
        self.assertTrue(result["ok"], result)
        e = result["board"]["elements"][0]
        self.assertEqual((e["x"], e["y"], e["w"], e["h"]), (80, 90, 70, 80))
        self.assertEqual(e["points"], [[0, 0], [70, 80]])
        huge = [{"op": "add", "element": {"id": f"stroke{i}", "kind": "stroke", "points": [[0, 0], [1, 1]] * 500}} for i in range(21)]
        self.assertEqual(self.edit(result["board"], huge, "request_0002")["code"], "validation")

    def test_anonymous_presence_ttl_and_revision_filter(self):
        board = self.board()
        sync = self.ns["paperweave_sync_canvas"]
        with patch.object(self.ns["time"], "time", return_value=1000):
            first = sync(board["id"], 0, "s_aaaaaaaaaaaa", {"x": 100, "y": 200})
            second = sync(board["id"], 0, "s_bbbbbbbbbbbb")
        self.assertIsNone(first["board"])
        self.assertEqual(len(second["peers"]), 2)
        self.assertEqual(second["peers"][0]["cursor"], {"x": 100, "y": 200})
        with patch.object(self.ns["time"], "time", return_value=1021):
            expired = sync(board["id"], 0, "s_bbbbbbbbbbbb")
        self.assertEqual(len(expired["peers"]), 1)
        self.assertEqual(expired["peers"][0]["label"], "Maker BBBB")

    def test_app_edits_have_human_audit_and_auth_guard(self):
        board = self.board()
        handler = self.ns["paperweave_apply_changes"]
        response = handler(board["id"], 0, [{"op": "rename", "text": "A human edit"}], "request_0001")
        self.assertEqual(response["board"]["history"][-1]["actor"], "person")
        self.assertNotIn("TEST_AUTH_CANARY", json.dumps(response))
        self.ns["get_access_token"] = lambda: None
        for function, args in (
            (self.main, {}),
            (self.ns["paperweave_open_canvas"], {}),
            (self.ns["paperweave_sync_canvas"], {"board_id": board["id"]}),
            (handler, {"board_id": board["id"], "base_revision": 1, "operations": [], "request_id": "request_0002"}),
        ):
            self.assertEqual(function(**args)["code"], "auth_required")

    def test_content_is_data_and_input_is_not_mutated(self):
        board = self.board()
        label = '<script>alert("not executable")</script> & a thought'
        ops = [{"op": "add", "element": {"id": "safe", "text": label}}]
        original = copy.deepcopy(ops)
        result = self.edit(board, ops)
        self.assertEqual(ops, original)
        self.assertEqual(result["board"]["elements"][0]["text"], label)
        self.assertNotIn("TEST_AUTH_CANARY", json.dumps(result))

    def test_unavailable_store_returns_sanitized_error(self):
        blocker = Path(self.directory.name) / "not-a-directory"
        blocker.write_text("test", encoding="utf-8")
        self.ns["_DATA"] = blocker
        response = self.main()
        self.assertEqual(response["code"], "storage_unavailable")
        self.assertNotIn(str(blocker), json.dumps(response))


if __name__ == "__main__":
    unittest.main()
