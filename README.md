<p align="center">
  <img src="./toolforge-logo.png" alt="ToolForge logo" width="96" height="96">
</p>

<h1 align="center">ToolForge</h1>

<p align="center">This repository contains the tools your ToolForge instance makes available to agents through MCP.</p>

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
tool_directory = getattr(server, "tool_directory", nullcontext)
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

An [MCP App](https://modelcontextprotocol.io/extensions/apps/overview) adds an interactive interface, such as a form or dashboard, to a tool result. Choose **Open App** at the end of the latest reply that returned one, or choose **View App** at the top of the right sidebar's new-tab page. This entry appears only in sessions with an App result. Both open the latest successful App result in the current conversation. Use the sidebar's Fullscreen control to expand it.

New App results replace the displayed App. Switching tabs or collapsing the sidebar keeps its state; closing or reloading starts it again with the latest result and current published interface. Other MCP clients need [MCP Apps](https://modelcontextprotocol.io/extensions/apps/overview) support to display the interface. Clients without it still receive the tool's result.

The App's files and handlers are published with its tool and follow the same Enable, Disable, and Delete controls.

## Copilot Skills

Project skills live under `.agents/skills/<name>/`, with instructions in `SKILL.md` and supporting files beside it. Install or edit them through Copilot or the Sandbox terminal. Saved files can be used without committing or pushing. This repo includes the upstream `agent-browser` skill; the Sandbox provides its CLI and browser.

## Publish changes

The MCP server uses GitOps: it automatically pulls and applies changes from the configured remote branch.

Push your commits to publish them. ToolForge's Source Control pushes automatically after a commit. The sandbox's pre-commit hook runs `uv sync --all-packages` and stages `uv.lock` when a fully staged package manifest changes.

Check the tool's status in **Tools**. **Active** means the tool is available; hover over its status indicator for details.

## Manage tools

In **Tools**, Disable comments out the Tool's registration block in `server.py` so agents can no longer call it. Its implementation stays in the repository. Enable restores the block. Delete removes both the block and Tool folder.

New Tool starts with a commented registration block in a general repository Session. Editing the function alone does not enable it; uncomment and publish the block with your implementation, or use **Tools → Enable**.

Each action commits and pushes the change immediately.

## Authentication and credentials

This Catalog requires MISE verification of Microsoft Entra authentication for all MCP calls and accepts both user and application tokens. Authentication is enforced before Tool code runs. The pinned MISE wheel is stored in `wheelhouse/`; Linux also needs the declared ICU dependency. Verification failures deny access. `src/catalog_app/server.py` imports and constructs the chosen `CatalogAuth` provider from `auth.py`. The provider implements the official Model Context Protocol Python SDK (`mcp` package) `TokenVerifier`, exposes SDK `AuthSettings`, and can supply a delegated Azure Core `TokenCredential`. To use another bearer provider, add a class in `src/catalog_app/auth.py`. The starter file already imports these types:

```python
class MyAuth:
    settings = AuthSettings(
        issuer_url=AnyHttpUrl("https://issuer.example.com"),
        resource_server_url=AnyHttpUrl("https://mcp.example.com/mcp"),
        required_scopes=["mcp.read"],
    )

    async def verify_token(self, token: str) -> AccessToken | None:
        raise NotImplementedError("Validate this provider's tokens")

    def delegated_credential(
        self, caller: AccessToken
    ) -> AbstractContextManager[TokenCredential] | None:
        return None  # No downstream delegation for this provider.
```

In `server.py`, import `MyAuth` instead of `MiseAuth` and replace the `MiseAuth(...)` construction with `auth = MyAuth()`. This shows the interface, not a working verifier: set your issuer, resource URL, and scopes, and validate tokens before publishing. Replacing the SDK bearer provider alone does not add a nonbearer HTTP authentication flow or change how ToolForge Web and Copilot obtain tokens.

Tools can use on-behalf-of (OBO) authentication to call downstream APIs with the signed-in user's delegated permissions. `server.py` reads the environment at startup and passes the settings to `MiseAuth`, which stores them. MISE requires the client ID at startup. Other OBO settings are optional until a Tool requests a credential. A custom provider can return a context manager yielding an Azure Core `TokenCredential`, or `None` when delegation is unavailable. `catalog_app.credentials.get_caller_credential()` returns that invocation-scoped credential; `credentials.py` closes it at the end of the Tool call, so do not retain it afterward.

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
