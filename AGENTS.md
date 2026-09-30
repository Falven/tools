# ToolForge repository

## Layout and Tool contract

Each Tool lives in `src/catalog_app/tools/<tool_id>/`, with its entry module
in `__init__.py` and supporting code and data alongside it. The package name
is its Tool ID; renaming the package changes that identity.

Expose `register(server: MCPServer) -> None` from the entry module, importing
`MCPServer` from `mcp.server`. Inside the callback, register exactly one
model-facing Tool with `@server.tool()`. Related App Handlers and resources
may share the package; mark App Handlers with
`meta={"ui": {"visibility": ["app"]}}`. Preserve the scaffold's
`tool_directory` scope around each callback so ToolForge can associate
registrations with their Tool ID.

Use lowercase snake_case for new Tool IDs and tool names. The function name
is its MCP name unless `name=` overrides it. MCP tool names must be unique
across the server; package paths do not prefix them. Check existing registrations,
including disabled Tools, before choosing a name.

The signature defines the input schema. The docstring is the default Tool
description for calling agents and should explain inputs, outputs, and side
effects. The return value is sent back to the caller.

## Python environment and dependencies

The repository-root `pyproject.toml` defines shared Python configuration.
`[project].requires-python` selects Python. Declare additional dependencies
there or in declared local package manifests. Keep `mcp`, `azure-identity`,
`PyJWT[crypto]`, and `toolforge-mcp` in the dependencies; the `toolforge-mcp`
pin must match the serving version.

`requirements.lock` is generated. In ToolForge sandboxes, the Git
pre-commit hook generates and stages it from staged dependency manifests.

Without that hook, use the service's ToolForge package version and run
this from the repository root:

`toolforge-mcp lock "$PWD/pyproject.toml" --output requirements.lock`

Commit changed manifests together with their generated lock.

## MCP runtime and authentication

`src/catalog_app/server.py` creates `EntraMCPServer` using MCP Python SDK v2.
Set `name`, `title`, `description`, and `instructions` directly in its
constructor; `**kwargs` supplies hosting options. The **Server** page displays
the applied title and instructions read-only.

`src/catalog_app/auth.py` configures Microsoft Entra authentication and OBO.
The default server requires authentication for all MCP calls, before Tool
code runs. It accepts both user and application tokens. Keep auth secrets
in the deployment environment.

During an authenticated Tool call,
`mcp.server.auth.middleware.auth_context.get_access_token()` provides the
caller's token and verified claims.

For delegated user calls, `toolforge.get_caller_credential()` provides an
invocation-scoped Azure credential for downstream APIs. Request the target
API's authorized scopes through `get_token()`. Application-only calls cannot
use this OBO credential. Terminal execution has no MCP caller context.

Set shared Tool credentials under **Server → Environment variables**.
These values are available to all Tools on the server and kept out of Git.

## Publication

Commit and push to the configured remote branch to publish changes.
ToolForge's Source Control pushes after committing; terminal commands must
push explicitly. ToolForge automatically pulls that branch and restarts the
MCP application. Check **Server → Tools** for activation; a successful push
does not establish that the changed Tool is being served.

Enable and Disable remove or add one comment layer around the entry module.
Empty or comment-only entry modules are disabled; newly authored Tools can
register directly without a separate Enable step. Delete removes the Tool's
folder. Each UI action commits and pushes immediately.
