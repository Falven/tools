# ToolForge Catalog

## Work on a Tool

Find the Tool at `src/catalog_app/tools/<tool_id>/`. The readable Python package name is its Tool ID; edits inside that directory preserve it. Keep one model-facing Tool and any related App Handlers or resources in that package.

The package's `__init__.py` defines a literal `ENABLED` value and `register(server)`. Register the Tool and related capabilities inside that callback with the official MCP SDK. Other Python modules and assets can live beside it. Registrations outside this convention belong to the MCP Application but are not managed by ToolForge's Tool list.

Keep the scaffold's `tool_directory` scope around each `register(server)` call. ToolForge hosting uses that scope to associate registrations with the Tool ID, including callables imported from shared modules. Its `nullcontext` fallback lets the same application run with a plain official SDK server.

## Server configuration

`src/catalog_app/server.py` creates the MCP server. Keep the name, title, description and instructions as explicit constructor arguments in repository source, without separate metadata constants. The scaffold uses `name="toolforge"` and empty strings for the other three values. Use `**kwargs` for hosting options such as authentication. The Server Workspace displays applied metadata read-only. Server Workspace Enable/Disable and Delete each commit and push immediately.

## Publish and dependencies

Commit and push to the configured Git branch; provider acceptance defines Publish. A local commit is recoverable work, not a published Tool. The sandbox pre-commit hook generates `requirements.lock` when staged dependency manifests change. Outside a ToolForge sandbox, run `toolforge-mcp lock "$PWD/pyproject.toml" --output requirements.lock` with the service's ToolForge version and commit the generated lock with its manifest.

Store runtime secrets in ToolForge's Tool Environment, not in Git. During an authenticated MCP call, use the verified request context for caller claims. `toolforge.get_caller_credential()` supplies delegated downstream credentials; terminal execution has no MCP caller context.
