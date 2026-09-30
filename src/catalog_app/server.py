import importlib
import pkgutil
from contextlib import nullcontext

from mcp.server.apps import Apps
from toolforge import EntraMCPServer

from . import tools
from .auth import build_auth


def create_server(**kwargs):
    server_class = kwargs.pop("server_class", EntraMCPServer)
    auth, token_verifier, obo_settings = build_auth()
    server = server_class(
        name="toolforge",
        title="",
        description="",
        instructions="",
        extensions=[Apps()],
        auth=auth,
        token_verifier=token_verifier,
        obo_settings=obo_settings,
        **kwargs,
    )
    for entry in sorted(
        pkgutil.iter_modules(tools.__path__, tools.__name__ + "."),
        key=lambda entry: entry.name,
    ):
        if entry.ispkg:
            tool_id = entry.name.rsplit(".", 1)[-1]
            scope = getattr(server, "tool_directory", nullcontext)
            with scope(tool_id):
                module = importlib.import_module(entry.name)
                register = getattr(module, "register", None)
                if register:
                    register(server)
                    if (
                        hasattr(server, "tool_ids_by_mcp_name")
                        and tool_id not in server.tool_ids_by_mcp_name.values()
                    ):
                        raise ValueError(
                            f"Tool Directory {tool_id} registered no model-facing Tool"
                        )
    return server
