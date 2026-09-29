# ToolForge Catalog

This repository holds the MCP Application served by ToolForge. The configured Git branch is the publication authority. New catalogs contain no Tools.

## Source layout

```text
pyproject.toml
requirements.lock
src/catalog_app/server.py
src/catalog_app/tools/
```

`server.py` creates the official MCP SDK server. The factory passes its keyword arguments to the SDK constructor. To customize the name, title or instructions, set those constructor arguments in this file. Server shows the applied native metadata read-only.

Each Tool has one readable Python package under `src/catalog_app/tools/`. Its directory name is its Tool ID. Keep that name when changing the Tool's public MCP Name. A Tool package defines `ENABLED` and `register(server)`:

```python
ENABLED = False


def register(server):
    @server.tool()
    def greet(name: str) -> str:
        """Return a greeting."""
        return f"Hello, {name}!"
```

A managed Tool registers one model-facing operation and may include App Handlers, resources, modules, and assets in the same directory. The Server Workspace can enable, disable, or delete that whole Tool. You can add other native SDK registrations outside this convention; edit those in files.

## Publish

Commit and push to the configured branch. ToolForge sandboxes use the provider directly as `origin`; a local commit alone does not Publish. In the Server Workspace, Enable/Disable and Delete each commit and push immediately. A rejected push keeps your work for recovery. Accepted commits reach each deployment through Catalog Synchronization, then the Tool Server activates them. Check the applied Catalog Generation before treating a change as live.

The shared `pyproject.toml` defines dependencies. ToolForge's sandbox pre-commit hook updates `requirements.lock` from staged dependency changes. In another checkout, use the same ToolForge version as the service:

```sh
toolforge-mcp lock "$PWD/pyproject.toml" --output requirements.lock
```

Stage the manifest and generated lock together. Do not edit the lock by hand.

## Credentials and MCP access

Set runtime API keys in **Server → Environment variables**. Keep secrets out of this repository. During an authenticated MCP call, `mcp.server.auth.middleware.auth_context.get_access_token()` provides verified caller claims. For delegated downstream API calls, use `toolforge.get_caller_credential()` and request the target API's scopes through `get_token()`.

Copy the `/mcp` endpoint from **Server → MCP**. Clients send a Microsoft Entra bearer token with the configured delegated scope or application role. The MCP Inspector can list enabled Tools after publication:

```sh
npx @modelcontextprotocol/inspector --cli "https://<instance-host>/mcp" --transport http --method tools/list --header "Authorization: Bearer $TOOLFORGE_ACCESS_TOKEN"
```
