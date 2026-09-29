import importlib
import pkgutil
from contextlib import nullcontext

from mcp.server import MCPServer
from mcp.server.apps import Apps

from . import tools


def create_server(**kwargs):
    server_class = kwargs.pop("server_class", MCPServer)
    server = server_class(
        name="toolforge",
        title="",
        description="",
        instructions="",
        extensions=[Apps()],
        **kwargs,
    )
    for entry in sorted(
        pkgutil.iter_modules(tools.__path__, tools.__name__ + "."),
        key=lambda entry: entry.name,
    ):
        if entry.ispkg:
            module = importlib.import_module(entry.name)
            register = getattr(module, "register", None)
            if register:
                tool_id = entry.name.rsplit(".", 1)[-1]
                scope = getattr(server, "tool_directory", nullcontext)
                with scope(tool_id):
                    register(server)
    return server
