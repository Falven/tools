"""Focused reader tests; all snapshots are synthetic temporary fixtures.

Run: uv run --no-sync python -m unittest src.catalog_app.tools.daily_ai_briefing.test_reader -v
"""

import asyncio
from contextlib import chdir
from datetime import UTC, datetime
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from mcp.client import Client
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

reader = importlib.import_module(__package__)
TOOL_NAME = "get_daily_ai_briefing"


class ReaderTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "latest.json"
        self.production_path = reader._SNAPSHOT_PATH
        patcher = mock.patch.object(reader, "_SNAPSHOT_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(reader, "_utc_now", return_value=datetime(2026, 10, 5, 17, tzinfo=UTC))
        self.clock = patcher.start()
        self.addCleanup(patcher.stop)
        self.snapshot = {
            "edition_date": "2026-10-05",
            "covers_date": "2026-10-04",
            "timezone": "America/New_York",
            "generated_at": "2026-10-05T12:00:00Z",
            "briefing_markdown": "# Fixture briefing — not a published edition\n\n[Saved item](https://example.test/item)\n",
            "source_urls": ["https://example.test/item"],
            "source_access_limitations": ["Fixture source's full text was unavailable."],
        }
        self.save(self.snapshot)
        self.server = MCPServer("daily-ai-briefing-test")
        reader.register(self.server)

    def save(self, value):
        self.path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    def call(self):
        return asyncio.run(self.server.call_tool(TOOL_NAME, {}))

    def assert_invalid(self, value, message):
        self.save(value)
        with self.assertRaisesRegex(ToolError, message):
            self.call()

    def test_registration_is_lazy_exactly_one_read_only_no_argument_tool(self):
        server = MCPServer("registration-test")
        with mock.patch.object(Path, "read_text", side_effect=AssertionError("registration read a file")):
            reader.register(server)
        tools = asyncio.run(server.list_tools())
        self.assertEqual([tool.name for tool in tools], [TOOL_NAME])
        tool = tools[0]
        self.assertEqual(tool.input_schema["type"], "object")
        self.assertEqual(tool.input_schema.get("properties", {}), {})
        self.assertEqual(tool.input_schema.get("required", []), [])
        self.assertEqual(set(tool.output_schema["required"]), set(self.snapshot) | {"is_current"})
        self.assertEqual(tool.output_schema["properties"]["is_current"]["type"], "boolean")
        self.assertEqual(tool.output_schema["properties"]["source_urls"]["items"]["type"], "string")
        self.assertTrue(tool.annotations.read_only_hint)
        self.assertFalse(tool.annotations.open_world_hint)
        self.assertFalse(tool.annotations.destructive_hint)
        self.assertIn("is_current=false", tool.description)
        self.assertIn("never relabel", tool.description)
        self.assertIn("Catalog publication Git branch", tool.description)
        self.assertEqual(asyncio.run(server.list_resources()), [])

    def test_real_mcp_client_returns_exact_structured_shape_with_no_arguments(self):
        async def invoke():
            async with Client(self.server) as client:
                return await client.call_tool(TOOL_NAME)

        result = asyncio.run(invoke())
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content, {**self.snapshot, "is_current": True})
        self.assertEqual(json.loads(result.content[0].text), result.structured_content)
        self.assertNotIn("is_current", json.loads(self.path.read_text(encoding="utf-8")))

    def test_module_relative_path_and_reads_ignore_working_directory(self):
        self.assertEqual(self.production_path, Path(reader.__file__).resolve().with_name("latest.json"))
        self.assertTrue(self.production_path.is_absolute())
        with chdir(self.path.parent):
            self.assertEqual(self.call().structured_content, {**self.snapshot, "is_current": True})

    def test_stale_edition_preserves_every_saved_field(self):
        self.clock.return_value = datetime(2026, 10, 6, 17, tzinfo=UTC)
        self.assertEqual(self.call().structured_content, {**self.snapshot, "is_current": False})

    def test_freshness_recomputed_at_new_york_midnight_not_utc_midnight(self):
        self.save({**self.snapshot, "edition_date": "2026-10-04", "covers_date": "2026-10-03",
                   "generated_at": "2026-10-04T12:00:00Z"})
        for instant, expected in [
            ("2026-10-04T23:59:59Z", True),
            ("2026-10-05T00:00:00Z", True),
            ("2026-10-05T03:59:59Z", True),
            ("2026-10-05T04:00:00Z", False),
        ]:
            with self.subTest(instant=instant):
                self.clock.return_value = datetime.fromisoformat(instant)
                self.assertIs(self.call().structured_content["is_current"], expected)

    def test_dst_short_and_long_days_use_local_calendar_boundaries(self):
        cases = [
            ("2026-03-08", "2026-03-07", "2026-03-08T05:00:00Z", [
                ("2026-03-08T05:00:00Z", True),
                ("2026-03-08T06:59:59Z", True),
                ("2026-03-08T07:00:00Z", True),
                ("2026-03-09T03:59:59Z", True),
                ("2026-03-09T04:00:00Z", False),
            ]),
            ("2026-11-01", "2026-10-31", "2026-11-01T04:00:00Z", [
                ("2026-11-01T04:00:00Z", True),
                ("2026-11-01T05:59:59Z", True),
                ("2026-11-01T06:00:00Z", True),
                ("2026-11-02T04:59:59Z", True),
                ("2026-11-02T05:00:00Z", False),
            ]),
        ]
        for edition, coverage, generated, instants in cases:
            saved = {**self.snapshot, "edition_date": edition, "covers_date": coverage, "generated_at": generated}
            self.save(saved)
            for instant, expected in instants:
                with self.subTest(instant=instant):
                    self.clock.return_value = datetime.fromisoformat(instant)
                    self.assertEqual(self.call().structured_content, {**saved, "is_current": expected})

    def test_reads_newly_saved_snapshot_without_restart(self):
        self.clock.return_value = datetime(2026, 10, 6, 17, tzinfo=UTC)
        self.assertFalse(self.call().structured_content["is_current"])
        replacement = {**self.snapshot, "edition_date": "2026-10-06", "covers_date": "2026-10-05",
                       "generated_at": "2026-10-06T12:00:00Z", "briefing_markdown": "# Replacement fixture"}
        self.save(replacement)
        self.assertEqual(self.call().structured_content, {**replacement, "is_current": True})

    def test_read_does_not_use_network_or_change_snapshot_bytes_or_mtime(self):
        before = (self.path.read_bytes(), self.path.stat().st_mtime_ns)
        with (
            mock.patch("socket.socket.connect", side_effect=AssertionError("network access")),
            mock.patch("socket.getaddrinfo", side_effect=AssertionError("DNS access")),
            mock.patch.object(Path, "write_text", side_effect=AssertionError("file write")),
            mock.patch.object(Path, "write_bytes", side_effect=AssertionError("file write")),
        ):
            self.assertFalse(self.call().is_error)
            self.clock.return_value = datetime(2026, 10, 6, 17, tzinfo=UTC)
            self.assertFalse(self.call().structured_content["is_current"])
        self.assertEqual((self.path.read_bytes(), self.path.stat().st_mtime_ns), before)

    def test_missing_snapshot_is_explicit_mcp_error_without_fallback(self):
        self.path.unlink()

        async def invoke():
            async with Client(self.server) as client:
                return await client.call_tool(TOOL_NAME)

        result = asyncio.run(invoke())
        self.assertTrue(result.is_error)
        self.assertIsNone(result.structured_content)
        self.assertIn("latest.json is missing", result.content[0].text)
        self.assertFalse(self.path.exists())

    def test_unreadable_and_non_utf8_snapshots_are_explicit_errors(self):
        with mock.patch.object(Path, "read_text", side_effect=PermissionError("fixture access denied")):
            with self.assertRaisesRegex(ToolError, "cannot be read as UTF-8"):
                self.call()
        self.path.write_bytes(b"\xff\xfe")
        with self.assertRaisesRegex(ToolError, "cannot be read as UTF-8"):
            self.call()

    def test_malformed_json_and_duplicate_keys_are_errors(self):
        duplicate = json.dumps(self.snapshot)[:-1] + ', "edition_date": "2026-10-05"}'
        for value in ["", "{", "not JSON", '{"edition_date":}', duplicate]:
            with self.subTest(value=value):
                self.path.write_text(value, encoding="utf-8")
                before = (self.path.read_bytes(), self.path.stat().st_mtime_ns)
                with self.assertRaisesRegex(ToolError, "malformed JSON"):
                    self.call()
                self.assertEqual((self.path.read_bytes(), self.path.stat().st_mtime_ns), before)

    def test_exactly_seven_fields_required_and_is_current_cannot_be_persisted(self):
        for value in [None, [], "snapshot", True, 123, {},
                      {**self.snapshot, "is_current": True}, {**self.snapshot, "extra": "value"}]:
            with self.subTest(value=value):
                self.assert_invalid(value, "exactly these seven saved fields")
        for field in self.snapshot:
            with self.subTest(missing=field):
                self.assert_invalid({key: value for key, value in self.snapshot.items() if key != field},
                                    "exactly these seven saved fields")

    def test_dates_must_be_real_canonical_calendar_dates(self):
        invalid_dates = [None, 20261005, True, "", "20261005", "2026-W41-1", "2026-10-5",
                         "2026/10/05", "2026-02-30", "2026-10-05T00:00:00Z"]
        for field in ["edition_date", "covers_date"]:
            for value in invalid_dates:
                with self.subTest(field=field, value=value):
                    self.assert_invalid({**self.snapshot, field: value}, field + " must be a valid date")

    def test_coverage_is_previous_calendar_day_including_year_and_leap_boundaries(self):
        for coverage in ["2026-10-05", "2026-10-03", "2026-10-06"]:
            with self.subTest(coverage=coverage):
                self.assert_invalid({**self.snapshot, "covers_date": coverage}, "immediately before edition_date")
        for edition, coverage in [("2026-01-01", "2025-12-31"), ("2024-03-01", "2024-02-29"),
                                  ("2026-03-01", "2026-02-28")]:
            with self.subTest(edition=edition):
                saved = {**self.snapshot, "edition_date": edition, "covers_date": coverage,
                         "generated_at": f"{edition}T12:00:00Z"}
                self.save(saved)
                self.assertEqual(self.call().structured_content, {**saved, "is_current": False})

    def test_timezone_must_be_new_york(self):
        for value in [None, "UTC", "US/Eastern", "-04:00", 123]:
            with self.subTest(value=value):
                self.assert_invalid({**self.snapshot, "timezone": value}, "timezone must be America/New_York")

    def test_generated_timestamp_is_aware_utc_and_preserved(self):
        for value in [None, 123, "", "yesterday", "2026-10-05", "2026-10-05T12:00:00",
                      "2026-10-05T12:00:00-04:00", "2026-10-05T12:00:00+01:00",
                      "2026-10-05 12:00:00Z", "2026-10-05T25:00:00Z", "2026-02-30T12:00:00Z"]:
            with self.subTest(value=value):
                self.assert_invalid({**self.snapshot, "generated_at": value}, "ISO 8601 UTC timestamp")
        for value in ["2026-10-05T12:00:00Z", "2026-10-05T12:00:00+00:00",
                      "2026-10-05T12:00:00.123456Z"]:
            with self.subTest(value=value):
                self.save({**self.snapshot, "generated_at": value})
                self.assertEqual(self.call().structured_content["generated_at"], value)

    def test_future_edition_and_generated_timestamp_are_invalid(self):
        self.assert_invalid({**self.snapshot, "edition_date": "2026-10-06", "covers_date": "2026-10-05"},
                            "edition_date is in the future")
        # UTC has rolled over, but New York is still on the preceding calendar day.
        self.clock.return_value = datetime(2026, 10, 5, 3, tzinfo=UTC)
        self.assert_invalid({**self.snapshot, "generated_at": "2026-10-04T12:00:00Z"},
                            "edition_date is in the future")
        self.clock.return_value = datetime(2026, 10, 5, 17, tzinfo=UTC)
        self.assert_invalid({**self.snapshot, "generated_at": "2026-10-05T17:00:00.000001Z"},
                            "generated_at is in the future")
        self.save({**self.snapshot, "generated_at": "2026-10-05T17:00:00Z"})
        self.assertFalse(self.call().is_error)

    def test_markdown_must_be_nonblank_text(self):
        for value in [None, 123, True, [], "", " \t\n"]:
            with self.subTest(value=value):
                self.assert_invalid({**self.snapshot, "briefing_markdown": value}, "briefing_markdown must be")

    def test_sources_must_be_nonempty_array_of_http_urls(self):
        invalid = [None, [], "https://example.test", [1], [""], [" "], ["relative/path"],
                   ["ftp://example.test/item"], ["https://"], ["https:///item"],
                   ["https://example.test:bad/item"], ["https://example.test:65536/item"],
                   ["https://example.test:0/item"], ["https://user:secret@example.test/item"],
                   ["https://[broken/item"], ["https://exa mple.test/item"],
                   ["https://example.test/\nitem"], ["https://example.test/\x00item"],
                   ["https://example.test\\item"]]
        for value in invalid:
            with self.subTest(value=value):
                self.assert_invalid({**self.snapshot, "source_urls": value}, "source_urls must be")
        urls = ["https://example.test/item?q=a%20b#section", "http://example.test:8080/item"]
        self.save({**self.snapshot, "source_urls": urls})
        self.assertEqual(self.call().structured_content["source_urls"], urls)

    def test_limitations_may_be_empty_but_must_be_array_of_nonblank_strings(self):
        for value in [None, "Unavailable", {}, [None], [1], [False], [""], [" \n"]]:
            with self.subTest(value=value):
                self.assert_invalid({**self.snapshot, "source_access_limitations": value},
                                    "source_access_limitations must be")
        self.save({**self.snapshot, "source_access_limitations": []})
        self.assertEqual(self.call().structured_content["source_access_limitations"], [])


if __name__ == "__main__":
    unittest.main()
