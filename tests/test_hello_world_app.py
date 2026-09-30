"""Contract checks for the Hello World MCP App tool and HTML resource."""

import asyncio
import unittest

from mcp.server import MCPServer
from mcp.server.apps import APP_MIME_TYPE, Apps

from catalog_app.tools.hello_world import APP_URI, register


class HelloWorldAppTests(unittest.TestCase):
    def test_tool_and_app_resource(self) -> None:
        server = MCPServer("hello-world-test", extensions=[Apps()])
        register(server)

        async def check() -> None:
            tools = await server.list_tools()
            self.assertEqual([tool.name for tool in tools], ["hello_world"])
            self.assertEqual(tools[0].meta["ui"]["resourceUri"], APP_URI)

            resources = await server.list_resources()
            self.assertEqual(len(resources), 1)
            self.assertEqual(str(resources[0].uri), APP_URI)
            self.assertEqual(resources[0].mime_type, APP_MIME_TYPE)

            html_resource = list(await server.read_resource(APP_URI))
            self.assertEqual(len(html_resource), 1)
            self.assertEqual(html_resource[0].mime_type, APP_MIME_TYPE)
            self.assertIn("<h1>Hello World</h1>", html_resource[0].content)

            result = await server.call_tool("hello_world", {})
            self.assertFalse(result.is_error)
            self.assertEqual(result.content[0].text, "Hello World")

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
