# ToolForge tool catalog

This repository holds the Python tools served by your ToolForge instance. A new catalog has shared Python configuration but no tools yet. Each tool lives in `tools/<tool-id>/`, with its entrypoint in `tool.py`. ToolForge discovers the entrypoints, and the running instance serves published, enabled tools to MCP clients.

The root `pyproject.toml` declares dependencies shared by all tools. ToolForge generates the matching `requirements.lock`.

## Create and publish a tool

In ToolForge, create a tool, open its source, and write a Python function that accepts the inputs your client will provide. Give it a docstring that tells callers what it does, and return a value. Name the exported function in a literal, one-item `__all__` list. For example, `tools/greet/tool.py` could contain:

```python
__all__ = ["greet"]


def greet(name: str) -> str:
    """Return a greeting for a name."""
    return f"Hello, {name}!"
```

Here, `greet` is the MCP tool name. The docstring becomes its description, the function signature defines its input schema, and the return value goes back to the caller. The tool ID in the directory path identifies its place in the catalog. Keep that directory name stable when changing the tool's code.

Saving in the editor or committing in its workspace leaves a draft. Use Publish in ToolForge when you want that version to become active. You can keep supporting code and data beside `tool.py` in the same tool directory. Each tool's focused workspace shows its own directory and the shared Python files; this README appears at the catalog root for reference.

## Work through Git

Git remote configuration is optional. If your ToolForge instance has a repository and branch configured, you can edit tool directories there and commit your changes to that branch. ToolForge synchronizes the branch and makes valid tools available to the running instance when they are enabled. Keep the path `tools/<tool-id>/tool.py` and the exported function contract above. A clone of this repository does not serve MCP requests; clients connect to the running ToolForge instance.

If a remote is configured, change this README in a normal Git checkout. The focused ToolForge editor shows the selected tool and shared Python files.

## Dependencies and runtime values

Dependencies in `pyproject.toml` apply to the whole catalog. Change them through ToolForge's shared Python configuration and Publish so ToolForge generates a matching `requirements.lock`. An edit to `pyproject.toml` alone can leave the lock out of sync and prevent activation. Do not hand-edit the lock file.

Put API keys and other runtime values in ToolForge's Server Tool Environment. That configuration supplies them to the tool process without putting them in Git. Keep credentials out of tool source, supporting files, and this README.

## Connect an MCP client

In ToolForge, open Configuration > Server > MCP and choose Copy MCP endpoint. The URL points to the running instance's `/mcp` route, which uses Streamable HTTP. The same panel shows Required permission. Your client must send a Microsoft Entra bearer token for the instance's configured tenant and audience, with that delegated scope or application role.

The [MCP Inspector CLI](https://github.com/modelcontextprotocol/inspector/blob/main/clients/cli/README.md#remote-servers) is one way to check the connection. It requires [Node.js 22.19 or newer](https://github.com/modelcontextprotocol/inspector/blob/main/package.json). With a valid access token already available in `TOOLFORGE_ACCESS_TOKEN`, replace the URL below with the endpoint copied from ToolForge:

```bash
npx @modelcontextprotocol/inspector --cli "https://<instance-host>/mcp" --transport http --method tools/list --header "Authorization: Bearer $TOOLFORGE_ACCESS_TOKEN"
```

The result lists tools available to that identity. An empty list is expected until a tool has been published and enabled. Create your first tool in ToolForge, publish it, then list tools again.
