"""Converter unit and real MCP client/resource tests, with no network required.

Run: uv run --no-sync python -m unittest discover -s tests -p 'test_celsius_to_fahrenheit.py' -v
"""

import asyncio
from contextlib import chdir
from decimal import getcontext
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from mcp.client import Client
from mcp.server import MCPServer
from mcp.server.apps import Apps

from catalog_app.tools import celsius_to_fahrenheit as converter


class ConverterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.server = MCPServer("converter-tests", extensions=[Apps()])
        converter.register(self.server)

    async def call(self, arguments=None):
        async with Client(self.server) as client:
            return await client.call_tool("celsius_to_fahrenheit", arguments or {})

    async def test_registration_and_schemas(self):
        tools = await self.server.list_tools()
        self.assertEqual([tool.name for tool in tools], ["celsius_to_fahrenheit"])
        tool = tools[0]
        self.assertEqual(tool.meta["ui"]["resourceUri"], converter.RESOURCE_URI)
        self.assertEqual(tool.input_schema["properties"]["celsius"]["type"], "number")
        self.assertEqual(tool.input_schema["properties"]["celsius"]["default"], 0)
        self.assertEqual(set(tool.output_schema["required"]), {"celsius", "fahrenheit", "formula", "result"})
        self.assertTrue(tool.annotations.read_only_hint)
        self.assertTrue(tool.annotations.idempotent_hint)
        self.assertFalse(tool.annotations.destructive_hint)
        self.assertFalse(tool.annotations.open_world_hint)

    async def test_default_and_text_fallback(self):
        result = await self.call()
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content, {
            "celsius": 0.0, "fahrenheit": 32.0,
            "formula": "°F = °C × 9/5 + 32", "result": "0 °C = 32 °F",
        })
        self.assertEqual(json.loads(result.content[0].text), result.structured_content)

    async def test_reference_points_and_decimals(self):
        for celsius, expected in [(0, 32), (100, 212), (-40, -40), (20, 68),
                                  (25, 77), (37, 98.6), (12.5, 54.5),
                                  (-273.15, -459.67), (-300, -508), (-0.0, 32)]:
            with self.subTest(celsius=celsius):
                result = await self.call({"celsius": celsius})
                self.assertFalse(result.is_error)
                self.assertEqual(result.structured_content["fahrenheit"], expected)
                self.assertNotIn("-0 °C", result.structured_content["result"])
                self.assertNotIn("98.60000000000001", result.structured_content["result"])

    async def test_rejects_nonnumeric_input_without_coercion(self):
        for value in ["25", "", "warm", None, True, False, [], {}]:
            with self.subTest(value=value):
                result = await self.call({"celsius": value})
                self.assertTrue(result.is_error)
                self.assertIsNone(result.structured_content)

    async def test_rejects_nonfinite_numbers(self):
        # Direct SDK calls cover values that compliant JSON itself cannot encode.
        from mcp.server.mcpserver.exceptions import ToolError
        for value in [float("nan"), float("inf"), float("-inf")]:
            with self.subTest(value=value):
                with self.assertRaises(ToolError):
                    await self.server.call_tool("celsius_to_fahrenheit", {"celsius": value})

    async def test_overflow_is_an_explicit_mcp_error(self):
        for value in [1.7e308, -1.7e308]:
            result = await self.call({"celsius": value})
            self.assertTrue(result.is_error)
            self.assertIn("supported numeric range", result.content[0].text)
            self.assertIsNone(result.structured_content)

    async def test_large_representable_result_avoids_intermediate_overflow(self):
        result = await self.call({"celsius": 9e307})
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["fahrenheit"], 1.62e308)

    async def test_tiny_numbers_and_repeatability(self):
        arguments = {"celsius": 1e-300}
        first = await self.call(arguments)
        second = await self.call(arguments)
        self.assertEqual(first.structured_content, second.structured_content)
        self.assertEqual(first.structured_content["fahrenheit"], 32)

    async def test_conversion_has_no_io_or_shared_decimal_context_changes(self):
        before = getcontext().copy()
        with (
            mock.patch("socket.socket.connect", side_effect=AssertionError("network")),
            mock.patch.object(Path, "read_text", side_effect=AssertionError("read")),
            mock.patch.object(Path, "write_text", side_effect=AssertionError("write")),
        ):
            result = await self.server.call_tool("celsius_to_fahrenheit", {"celsius": 37})
        self.assertEqual(result.structured_content["fahrenheit"], 98.6)
        self.assertEqual(getcontext().prec, before.prec)
        self.assertEqual(getcontext().flags, before.flags)

    async def test_resource_is_registered_and_inlines_exact_app(self):
        async with Client(self.server) as client:
            resources = await client.list_resources()
            resource = next(item for item in resources.resources if str(item.uri) == converter.RESOURCE_URI)
            self.assertEqual(resource.mime_type, "text/html;profile=mcp-app")
            self.assertEqual(resource.meta["ui"]["csp"], {
                "resourceDomains": ["https://cdn.jsdelivr.net"], "connectDomains": [],
            })
            result = await client.read_resource(converter.RESOURCE_URI)
        html = result.contents[0].text
        self.assertIn("Celsius to Fahrenheit", html)
        self.assertNotIn("<!-- app.js -->", html)
        self.assertEqual(html.count('<script type="module">'), 1)
        self.assertIn((converter.ASSETS / "app.js").read_text(encoding="utf-8"), html)
        self.assertIn("@modelcontextprotocol/ext-apps@2.0.0", html)

    async def test_asset_paths_are_independent_of_working_directory(self):
        converter._app_html.cache_clear()
        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            html = converter._app_html()
        self.assertIn('id="celsius"', html)

    async def test_registration_does_not_eagerly_read_assets(self):
        with mock.patch.object(Path, "read_text", side_effect=AssertionError("eager asset read")):
            server = MCPServer("lazy-assets", extensions=[Apps()])
            converter.register(server)
        self.assertEqual(len(await server.list_tools()), 1)


if __name__ == "__main__":
    unittest.main()
