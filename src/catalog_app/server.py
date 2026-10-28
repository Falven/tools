"""Set up the Catalog's access checks and Tools on the chosen MCP server."""

from typing import Any

from mcp.server.apps import Apps
from mcp.types import ToolAnnotations

from .mise import MiseAuth, MiseMCPServer as server_class


def create_server(**kwargs: Any) -> server_class:
    server = server_class(
        name="toolforge",
        title="",
        description="",
        instructions="",
        authentication=MiseAuth.from_env(),
        extensions=[Apps()],
        **kwargs,
    )
    tool_directory = server.tool_directory
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
