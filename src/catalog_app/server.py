"""Set up the Catalog's access checks and Tools on the chosen MCP server."""

import os
from typing import Any

from mcp.server.apps import Apps
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.context import Context
from mcp.types import ToolAnnotations
from mcp_types import CallToolResult, InputRequiredResult
from starlette.applications import Starlette

from . import credentials
from .auth import MiseAuth, MiseRequestContextMiddleware
from .hosting import HostedMCPServer


def create_server(**kwargs: Any) -> HostedMCPServer:
    auth = MiseAuth(
        tenant_id=os.environ["TOOLFORGE_MCP_ENTRA_TENANT_ID"],
        audience=os.environ["TOOLFORGE_MCP_ENTRA_AUDIENCE"],
        permission=os.environ["TOOLFORGE_MCP_ENTRA_PERMISSION"],
        resource_url=os.environ["TOOLFORGE_MCP_RESOURCE_URL"],
        client_id=os.environ["TOOLFORGE_MCP_ENTRA_CLIENT_ID"],
        client_secret=os.environ.get("TOOLFORGE_MCP_ENTRA_CLIENT_SECRET"),
        managed_identity_client_id=os.environ.get(
            "TOOLFORGE_MCP_ENTRA_MANAGED_IDENTITY_CLIENT_ID"
        ),
    )

    class CatalogServer(HostedMCPServer):
        async def call_tool(
            self,
            name: str,
            arguments: dict[str, Any],
            context: Context[dict[str, Any], Any] | None = None,
        ) -> CallToolResult | InputRequiredResult:
            """Keep the caller's credential open for this Tool call, then close it."""
            # Skip this setup for direct Python calls that have no MCP request.
            if context is None:
                return await super().call_tool(name, arguments, context)
            # Preserve the details needed to sign in again before the MCP Python
            # library converts errors to plain text.
            return await credentials.run_with_caller(
                auth, get_access_token(), super().call_tool(name, arguments, context)
            )

        def streamable_http_app(self, **kwargs: Any) -> Starlette:
            app = super().streamable_http_app(**kwargs)
            app.add_middleware(MiseRequestContextMiddleware)
            return app

    server_class = CatalogServer
    server = server_class(
        name="toolforge",
        title="",
        description="",
        instructions="",
        extensions=[Apps()],
        auth=auth.settings,
        token_verifier=auth,
        **kwargs,
    )
    tool_directory = server.tool_directory
    with tool_directory("contoso_open_request"):
        from .tools.contoso_open_request import register

        register(server)

    with tool_directory("contoso_save_request"):
        from .tools.contoso_open_request import (
            RESOURCE_URI as CONTOSO_REQUEST_RESOURCE_URI,
        )
        from .tools.contoso_save_request import contoso_save_request

        server.add_tool(
            contoso_save_request,
            title="Save Contoso request",
            meta={
                "ui": {
                    "resourceUri": CONTOSO_REQUEST_RESOURCE_URI,
                    "visibility": ["model", "app"],
                }
            },
            annotations=ToolAnnotations(
                read_only_hint=False,
                destructive_hint=True,
                idempotent_hint=True,
                open_world_hint=False,
            ),
        )

    with tool_directory("contoso_list_requests"):
        from .tools.contoso_list_requests import contoso_list_requests

        server.add_tool(
            contoso_list_requests,
            title="List Contoso requests",
            annotations=ToolAnnotations(
                read_only_hint=True,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=False,
            ),
        )

    with tool_directory("contoso_save_answers"):
        from .tools.contoso_open_request import (
            RESOURCE_URI as CONTOSO_REQUEST_RESOURCE_URI,
        )
        from .tools.contoso_save_answers import contoso_save_answers

        server.add_tool(
            contoso_save_answers,
            title="Save Contoso clarification answers",
            meta={
                "ui": {
                    "resourceUri": CONTOSO_REQUEST_RESOURCE_URI,
                    "visibility": ["model", "app"],
                }
            },
            annotations=ToolAnnotations(
                read_only_hint=False,
                destructive_hint=True,
                idempotent_hint=True,
                open_world_hint=False,
            ),
        )

    with tool_directory("contoso_submit_answers"):
        from .tools.contoso_open_request import (
            RESOURCE_URI as CONTOSO_REQUEST_RESOURCE_URI,
        )
        from .tools.contoso_submit_answers import contoso_submit_answers

        server.add_tool(
            contoso_submit_answers,
            title="Submit Contoso clarification answers",
            meta={
                "ui": {
                    "resourceUri": CONTOSO_REQUEST_RESOURCE_URI,
                    "visibility": ["model", "app"],
                }
            },
            annotations=ToolAnnotations(
                read_only_hint=False,
                destructive_hint=True,
                idempotent_hint=True,
                open_world_hint=False,
            ),
        )

    with tool_directory("daily_ai_briefing"):
        from .tools.daily_ai_briefing import (
            get_daily_ai_briefing,
        )

        server.add_tool(
            get_daily_ai_briefing,
            title="Daily AI Briefing",
            annotations=ToolAnnotations(
                read_only_hint=True, destructive_hint=False, open_world_hint=False
            ),
        )

    with tool_directory("gloaming_road"):
        from .tools.gloaming_road import (
            RESOURCE_URI as GLOAMING_ROAD_RESOURCE_URI,
        )
        from .tools.gloaming_road import (
            gloaming_road,
            gloaming_road_app,
        )

        server.add_tool(
            gloaming_road,
            title="The Gloaming Road",
            meta={"ui": {"resourceUri": GLOAMING_ROAD_RESOURCE_URI}},
        )
        server.resource(
            GLOAMING_ROAD_RESOURCE_URI,
            mime_type="text/html;profile=mcp-app",
            title="The Gloaming Road",
            meta={"ui": {"csp": {"resourceDomains": [], "connectDomains": []}}},
        )(gloaming_road_app)

    with tool_directory("hello_world"):
        from .tools.hello_world import hello_world

        server.add_tool(
            hello_world,
            title="Hello World",
            annotations=ToolAnnotations(
                read_only_hint=True,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=False,
            ),
        )

    with tool_directory("minesweeper"):
        from .tools.minesweeper import (
            RESOURCE_URI as MINESWEEPER_RESOURCE_URI,
        )
        from .tools.minesweeper import (
            _strict_inputs as _minesweeper_strict_inputs,
        )
        from .tools.minesweeper import (
            minesweeper,
            minesweeper_app,
            minesweeper_move,
            minesweeper_scores,
            minesweeper_start,
        )

        server.add_tool(
            minesweeper,
            title="Minesweeper",
            meta={"ui": {"resourceUri": MINESWEEPER_RESOURCE_URI}},
        )
        server.add_tool(
            minesweeper_start,
            title="Start Minesweeper game",
            meta={
                "ui": {"resourceUri": MINESWEEPER_RESOURCE_URI, "visibility": ["app"]}
            },
        )
        server.add_tool(
            minesweeper_move,
            title="Play Minesweeper move",
            meta={
                "ui": {"resourceUri": MINESWEEPER_RESOURCE_URI, "visibility": ["app"]}
            },
        )
        server.add_tool(
            minesweeper_scores,
            title="Minesweeper scores",
            meta={
                "ui": {"resourceUri": MINESWEEPER_RESOURCE_URI, "visibility": ["app"]}
            },
        )
        _minesweeper_strict_inputs(
            server,
            (
                "minesweeper",
                "minesweeper_start",
                "minesweeper_move",
                "minesweeper_scores",
            ),
        )
        server.resource(
            MINESWEEPER_RESOURCE_URI,
            mime_type="text/html;profile=mcp-app",
            title="Minesweeper",
            meta={"ui": {"csp": {"resourceDomains": [], "connectDomains": []}}},
        )(minesweeper_app)

    with tool_directory("neon_coil"):
        from .tools.neon_coil import (
            RESOURCE_URI as NEON_COIL_RESOURCE_URI,
        )
        from .tools.neon_coil import (
            neon_coil,
            neon_coil_app,
            neon_coil_begin,
            neon_coil_finish,
            neon_coil_scores,
        )

        server.add_tool(
            neon_coil,
            title="Neon Coil",
            meta={"ui": {"resourceUri": NEON_COIL_RESOURCE_URI}},
        )
        server.add_tool(
            neon_coil_begin,
            title="Start Neon Coil run",
            meta={"ui": {"resourceUri": NEON_COIL_RESOURCE_URI, "visibility": ["app"]}},
        )
        server.add_tool(
            neon_coil_finish,
            title="Verify Neon Coil run",
            meta={"ui": {"resourceUri": NEON_COIL_RESOURCE_URI, "visibility": ["app"]}},
        )
        server.add_tool(
            neon_coil_scores,
            title="Neon Coil scores",
            meta={"ui": {"resourceUri": NEON_COIL_RESOURCE_URI, "visibility": ["app"]}},
        )
        server.resource(
            NEON_COIL_RESOURCE_URI,
            mime_type="text/html;profile=mcp-app",
            title="Neon Coil",
            meta={"ui": {"csp": {"resourceDomains": [], "connectDomains": []}}},
        )(neon_coil_app)

    with tool_directory("rally_pong"):
        from .tools.rally_pong import (
            RESOURCE_URI as RALLY_PONG_RESOURCE_URI,
        )
        from .tools.rally_pong import (
            _strict_inputs as _rally_pong_strict_inputs,
        )
        from .tools.rally_pong import (
            rally_pong,
            rally_pong_app,
            rally_pong_begin,
            rally_pong_finish,
            rally_pong_scores,
        )

        server.add_tool(
            rally_pong,
            title="Rally — After Hours",
            meta={"ui": {"resourceUri": RALLY_PONG_RESOURCE_URI}},
        )
        server.add_tool(
            rally_pong_begin,
            title="Start Rally run",
            meta={
                "ui": {"resourceUri": RALLY_PONG_RESOURCE_URI, "visibility": ["app"]}
            },
        )
        server.add_tool(
            rally_pong_finish,
            title="Verify Rally run",
            meta={
                "ui": {"resourceUri": RALLY_PONG_RESOURCE_URI, "visibility": ["app"]}
            },
        )
        server.add_tool(
            rally_pong_scores,
            title="Rally scores",
            meta={
                "ui": {"resourceUri": RALLY_PONG_RESOURCE_URI, "visibility": ["app"]}
            },
        )
        _rally_pong_strict_inputs(
            server,
            (
                "rally_pong",
                "rally_pong_begin",
                "rally_pong_finish",
                "rally_pong_scores",
            ),
        )
        server.resource(
            RALLY_PONG_RESOURCE_URI,
            mime_type="text/html;profile=mcp-app",
            title="Rally — After Hours",
            meta={"ui": {"csp": {"resourceDomains": [], "connectDomains": []}}},
        )(rally_pong_app)
    return server
