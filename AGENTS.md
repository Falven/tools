# ToolForge Catalog

## Work on a Tool

Find the Tool at `src/catalog_app/tools/<tool_id>/`. The readable Python package name is its Tool ID; edits inside that directory preserve it. Keep one model-facing Tool and any related App Handlers or resources in that package.

An active package `__init__.py` defines `register(server)`. Register the Tool and related capabilities inside that callback with the official MCP SDK. A new Tool starts with this entire file commented out; Disable adds one `# ` layer to the whole file, and Enable removes it to restore the source exactly. Empty and comment-only entry modules are inactive. Other Python modules and assets can live beside it. Registrations outside this convention belong to the MCP Application but are not managed by ToolForge's Tool list.

Keep the scaffold's `tool_directory` scope around each `register(server)` call. ToolForge hosting uses that scope to associate registrations with the Tool ID, including callables imported from shared modules. Its `nullcontext` fallback lets the same application run with the public SDK subclass outside ToolForge hosting.

## Server configuration

`src/catalog_app/server.py` creates `EntraMCPServer`, an official MCP SDK subclass. Keep the name, title, description and instructions as explicit constructor arguments in repository source, without separate metadata constants. The scaffold uses `name="toolforge"` and empty strings for the other three values. `src/catalog_app/auth.py` builds public MCP authentication and OBO settings from the existing MCP environment variables. Edit that file to change how the application configures authentication; keep secrets in the deployment environment. `**kwargs` carries hosting options. The Server Workspace displays applied metadata read-only. Server Workspace Enable/Disable and Delete each commit and push immediately.

## Publish and dependencies

Commit and push to the configured Git branch; provider acceptance defines Publish. A local commit is recoverable work, not a published Tool. The sandbox pre-commit hook generates `requirements.lock` when staged dependency manifests change. Outside a ToolForge sandbox, run `toolforge-mcp lock "$PWD/pyproject.toml" --output requirements.lock` with the service's ToolForge version and commit the generated lock with its manifest. Lock generation rejects a mismatched `toolforge-mcp` pin and hash-pins third-party dependencies; ToolForge installs its own runtime separately.

Store Tool secrets in ToolForge's Tool Environment and MCP auth secrets in the deployment environment, never in Git. Keep `toolforge-mcp` at the serving version, `azure-identity` and `PyJWT[crypto]` in `pyproject.toml` with a matching lock. During an authenticated MCP call, use the verified request context for caller claims. `toolforge.get_caller_credential()` supplies delegated downstream credentials; terminal execution has no MCP caller context.
