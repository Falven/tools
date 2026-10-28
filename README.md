<p align="center">
  <img src="./toolforge-logo.png" alt="ToolForge logo" width="96" height="96">
</p>

<h1 align="center">ToolForge</h1>

<p align="center">This repository contains the tools your ToolForge instance makes available to agents through MCP.</p>

The customer software-request demo tools and their MCP App now live in [Falven/crm-tools](https://github.com/Falven/crm-tools).

<p align="center">
  <a href="#what-an-agent-sees">What an agent sees</a> ·
  <a href="#interactive-mcp-apps">Interactive apps</a> ·
  <a href="#publish-changes">Publish changes</a> ·
  <a href="#manage-tools">Manage tools</a> ·
  <a href="#authentication-and-credentials">Authentication and credentials</a> ·
  <a href="#connect-to-your-mcp-server">Connect to your MCP Server</a>
</p>

## What an agent sees

When an agent connects, its MCP client receives the server's details and instructions.

```python
server = server_class(
    name="greetings",
    title="Greeting tools",
    description="Create greetings for people by name.",
    instructions="If no name was provided, ask for one before calling greet.",
)
```

| Server setting | What the client receives                                  |
| -------------- | --------------------------------------------------------- |
| Name           | The server's identifier, such as `greetings`.             |
| Title          | A readable display name for the server.                   |
| Description    | A description of what the server provides.                |
| Instructions   | Guidance for the agent on using the server and its tools. |

These settings live in the repository. The **Server** page displays the applied title and instructions read-only.

A Tool's name, description, and inputs tell an agent when to use it and how to call it. A simple Tool is a plain Python function in its package’s `__init__.py`:

```python
def hello_world() -> str:
    """Return a friendly greeting."""
    return "Hello, world!"
```

After the server constructor, `src/catalog_app/server.py` explicitly registers it:

```python
tool_directory = server.tool_directory
with tool_directory("hello_world"):
    from .tools.hello_world import hello_world

    server.add_tool(hello_world)
```

Add a similar block for each new Tool. Catalog source does not scan directories for Tools. The ToolForge `tool_directory` scope gives the Tool its ID, attributes calls and startup errors, and isolates an import or registration failure so healthy Tools can still start. The scope does not set the MCP name: that comes from the registered function's name, even when the package re-exports the function, unless registration overrides it. The function may have typed parameters; complex Tools may instead expose `register(server)` and call it in the same scope to add their Tool, resources, and App Handlers.

| Part of the tool                   | What the agent sees                                                                         |
| ---------------------------------- | ------------------------------------------------------------------------------------------- |
| Function name (`hello_world`)      | The tool name used to call it, unless a different name is set when registering the tool.    |
| Docstring                          | The tool description and any guidance on when and how to use it.                            |
| Parameters and types               | The input schema: the fields the agent fills in, their types, and whether each is required. |
| Return value                       | The data sent back to the agent. Its reply to the user may summarize that data.             |

## Interactive [MCP Apps](https://modelcontextprotocol.io/extensions/apps/overview)

An [MCP App](https://modelcontextprotocol.io/extensions/apps/overview) adds an interactive interface, such as a form or dashboard, to a tool result. Each App appears automatically inline with the call that produced it. Use its **Fullscreen** control, when available, to expand it, then return to the same inline App.

Each call retains its own App and result. Fullscreen preserves the live App's state. Leaving the conversation closes its Apps; returning loads the current published interface with each call's saved data without rerunning the producing tool. Other MCP clients need [MCP Apps](https://modelcontextprotocol.io/extensions/apps/overview) support to display the interface. Clients without it still receive the tool's result.

The App's files and handlers are published with its tool through Git.

## Copilot Skills

Project skills live under `.agents/skills/<name>/`, with instructions in `SKILL.md` and supporting files beside it. Install or edit them through Copilot or the Sandbox terminal. Saved files can be used without committing or pushing. This repo includes the upstream `agent-browser` skill; the Sandbox provides its CLI and browser.

## Publish changes

The MCP server uses GitOps: it automatically pulls and applies changes from the configured remote branch.

This Catalog owns its complete MCP execution application and dependency lock.
`python -m catalog_app` runs the transport, Tool registration, invocation reporting,
and authentication in the Catalog environment. ToolForge management supervises
that process from a separate environment and supplies no execution dependencies.

Push your commits to publish them. ToolForge's Source Control pushes automatically after a commit. The sandbox's pre-commit hook runs `uv sync --all-packages` and stages `uv.lock` when a fully staged package manifest changes.

Check the tool's status in **Tools**. **Active** means the tool is available; hover over its status indicator for details.

## Manage tools

In **Tools**, Disable comments out the Tool's registration block in `server.py` so agents can no longer call it. Its implementation stays in the repository. Enable restores the block. Delete removes both the block and Tool folder.

New Tool starts with a commented registration block in a general repository Session. Editing the function alone does not enable it; uncomment and publish the block with your implementation, or use **Tools → Enable**.

Each action commits and pushes the change immediately.

## Authentication and credentials

`authentication=MiseAuth.from_env()` in `src/catalog_app/server.py` verifies Microsoft Entra user and application tokens through MISE before Tool code runs. `src/catalog_app/mise.py` owns verification, on-behalf-of (OBO) exchange, and `MiseMCPServer`, the small server adapter that supplies the HTTP request context MISE needs. The pinned MISE wheel stays in `wheelhouse/`; Linux also uses the declared ICU dependency. Verification failures deny access.

Set `TOOLFORGE_MCP_ENTRA_SCOPE` to the full OAuth scope, such as `api://toolforge/ToolForge.MCP.Access`, for client discovery. `TOOLFORGE_MCP_ENTRA_PERMISSION` remains the short token permission, such as `ToolForge.MCP.Access`.

To use another bearer provider, implement the `CatalogAuth` contract from `src/catalog_app/auth.py` in a module such as `my_auth.py`. The provider has four members:

| Member | Responsibility |
| --- | --- |
| `settings` | Native SDK `AuthSettings`: issuer, resource URL, and required scopes. |
| `verify_token(token)` | Validate the bearer token and return a native SDK `AccessToken`, or `None` to reject it. Bind `client_id` to the verified client. |
| `caller_identity(caller)` | Return `CallerIdentity`: an explicit `principalType` of `user` or `application` and the available safe attribution fields. |
| `delegated_credential(caller)` | Return a context manager yielding an Azure Core `TokenCredential`, or `None` when delegation is unavailable. |

`CallerIdentity` supports `userId`, `userName`, `userEmail`, `entraTenantId`, and `entraObjectId`; omit fields your provider does not have. Keep assertions and raw claims in the native token, outside this projection. The provider determines whether its verified token represents a user or an application. Hosting accepts forwarded execution context only from configured trusted client IDs; application callers cannot forward user attribution.

For a custom provider that needs only the bearer token, replace the MISE import in `server.py` with `from .hosting import HostedMCPServer as server_class` and an import of your provider. Replace `authentication=MiseAuth.from_env()` with `authentication=MyAuth()`. The hosted server connects the provider to the SDK and manages each Tool call's reporting and credential lifetime. Tool registrations stay the same. Replacing the bearer provider does not change how ToolForge Web or the agent obtains tokens or add a nonbearer HTTP authentication flow.

`MiseAuth.from_env()` reads the existing environment settings once at startup. Its explicit `MiseAuth(...)` constructor remains available when settings come from elsewhere. MISE requires the client ID at startup. Other OBO settings are optional until a Tool requests a credential. `catalog_app.credentials.get_caller_credential()` returns the invocation-scoped Azure Core credential for downstream APIs; it closes when the Tool call ends, so do not retain it afterward. Application-only calls cannot use the MISE provider's OBO credential.

For calls made by a signed-in user, read their identity with `get_access_token()`:

```python
from mcp.server.auth.middleware.auth_context import get_access_token


def who_am_i() -> dict[str, str]:
    """Return the signed-in user's tenant and user IDs."""
    token = get_access_token()
    return {"tenant_id": token.claims["tid"], "user_id": token.claims["oid"]}
```

Register `who_am_i` in `server.py` with the same `tool_directory("who_am_i")` import-and-`server.add_tool()` pattern shown above. The token contains verified claims.

Set API keys and other tool credentials under **Environment variables**. These values are shared across all tools on this server and kept out of Git.

## Connect to your MCP Server

Open **MCP** and copy the endpoint into your MCP client. Choose Streamable HTTP if your client asks for a transport.
