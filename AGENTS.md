# ToolForge repository

## Layout and Tool contract

Each Tool lives in `tools/<tool-id>/`, with its entrypoint in `tool.py`
and supporting code and data alongside it.

Export one top-level function through a literal one-item `__all__` list.
Existing tools may instead expose a single public top-level function.
The function's lowercase ASCII snake_case name, limited to 48 characters,
is its MCP name and must be unique across the catalog. Its signature
defines the input schema. Its docstring becomes the MCP tool description
for calling agents and should explain inputs, outputs, and side effects.

## Python environment and dependencies

The repository-root `pyproject.toml` defines shared Python configuration.
`[project].requires-python` selects Python. Declare additional dependencies
there or in declared local package manifests.

`requirements.lock` is generated. In ToolForge sandboxes, the Git
pre-commit hook generates and stages it from staged dependency manifests.

Without that hook, use the service's ToolForge package version and run
this from the repository root:

`toolforge-mcp lock "$PWD/pyproject.toml" --output requirements.lock`

Commit changed manifests together with their generated lock.

## MCP runtime and authentication

Published tools run on ToolForge's MCP server with Microsoft Entra
authentication. The runtime includes MCP Python SDK v2 (`mcp`) and
Azure Identity (`azure.identity`).

Inside the entrypoint during an authenticated MCP invocation,
`mcp.server.auth.middleware.auth_context.get_access_token()` provides
the caller's token and verified claims.

For delegated user calls, ToolForge's included
`toolforge.get_caller_credential()` helper provides an invocation-scoped
Azure credential for downstream APIs. Request the target API's
authorized scopes through its `get_token()` method.

Ordinary terminal execution has no authenticated MCP caller context.

## Publication

Publication requires committing and pushing changes to the Catalog's
configured branch. A local commit or a push only to an external Git
remote does not publish to ToolForge.

Publication, MCP activation, and Tool enablement are separate states.
MCP calls execute the currently active published code; a successful
push alone does not establish that the changed Tool is being served.
