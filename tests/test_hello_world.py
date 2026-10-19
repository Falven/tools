"""Check the greeting and its production registration using an isolated MCP client."""

import unittest

from mcp.client import Client
from mcp.server import MCPServer
from mcp.server.apps import Apps

from catalog_app.tools.hello_world import hello_world
from tests.fixtures.catalog import register_catalog_tool


class HelloWorldTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.server = MCPServer("hello-world-tests", extensions=[Apps()])
        register_catalog_tool(self.server, "hello_world")

    def test_exact_greeting(self):
        self.assertEqual(hello_world(), "hello world")

    async def test_registration_and_schema(self):
        tools = await self.server.list_tools()
        self.assertEqual([tool.name for tool in tools], ["hello_world"])
        tool = tools[0]
        self.assertEqual(tool.input_schema["properties"], {})
        self.assertFalse(tool.input_schema.get("required"))
        self.assertTrue(tool.annotations.read_only_hint)
        self.assertTrue(tool.annotations.idempotent_hint)
        self.assertFalse(tool.annotations.destructive_hint)
        self.assertFalse(tool.annotations.open_world_hint)

    async def test_mcp_call(self):
        async with Client(self.server) as client:
            for _ in range(2):
                result = await client.call_tool("hello_world", {})
                self.assertFalse(result.is_error)
                self.assertEqual(len(result.content), 1)
                self.assertEqual(result.content[0].text, "hello world")


if __name__ == "__main__":
    unittest.main()
