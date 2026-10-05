<p align="center">
  <img src="./toolforge-logo.png" alt="ToolForge logo" width="96" height="96">
</p>

<h1 align="center">ToolForge</h1>

<p align="center">This repository contains the tools your ToolForge instance makes available to agents through MCP.</p>

<p align="center">
  <a href="#what-an-agent-sees">What an agent sees</a> ·
  <a href="#publish-changes">Publish changes</a> ·
  <a href="#manage-tools">Manage tools</a> ·
  <a href="#authentication-and-credentials">Authentication and credentials</a> ·
  <a href="#connect-to-your-mcp-server">Connect to your MCP Server</a>
</p>

## Included game Apps

`rally_pong()` opens **Rally — After Hours**, a full-viewport Three.js 2.5D Pong arcade with responsive controls, original synth music, independent music/SFX switches, and replay-verified signed-in high scores held only in server memory. See the [controls, build, privacy and verification notes](<src/catalog_app/tools/rally_pong/README.md>). Practice never posts scores; the leaderboard resets on server restart.

`gloaming_road()` opens **The Gloaming Road**, an original first-person fantasy MCP App with a seeded streamed world, directional swordplay, local saves, original art/audio, and a single castle rescue. See the [game's build, controls, provenance and verification notes](<src/catalog_app/tools/gloaming_road/README.md>). Opening the tool does not start a save or write server state.

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

A tool's name, description, and inputs tell an agent when to use it and how to call it. For example:

```python
from mcp.server import MCPServer


def register(server: MCPServer) -> None:
    @server.tool()
    def greet(name: str) -> str:
        """Return a greeting for a name."""
        return f"{server.title}: Hello, {name}!"
```

The `server` argument exposes the server's `name`, `title`, `description`, and `instructions`.

| Part of the tool                   | What the agent sees                                                                         |
| ---------------------------------- | ------------------------------------------------------------------------------------------- |
| Function name (`greet`)            | The tool name used to call it, unless a different name is set when registering the tool.    |
| Docstring                          | The tool description and any guidance on when and how to use it.                            |
| Parameters and types (`name: str`) | The input schema: the fields the agent fills in, their types, and whether each is required. |
| Return value                       | The data sent back to the agent. Its reply to the user may summarize that data.             |

## Publish changes

The MCP server uses GitOps: it automatically pulls and applies changes from the configured remote branch.

Push your commits to publish them. ToolForge's Source Control pushes automatically after a commit. The sandbox's pre-commit hook runs `uv sync --all-packages` and stages `uv.lock` when a fully staged package manifest changes.

Check the tool's status in **Server → Tools**. **Active** means the tool is available; hover over its status indicator for details.

## Manage tools

In **Server → Tools**, Disable comments out a tool's entry module so agents can no longer call it. Its source stays in the repository. Enable removes that comment layer. Delete removes the tool's folder.

Each action commits and pushes the change immediately.

## Authentication and credentials

The default setup requires Microsoft Entra authentication for all MCP calls and accepts both user and application tokens. Authentication is enforced before tool code runs. Tools can use on-behalf-of (OBO) authentication to call downstream APIs with the signed-in user's delegated permissions.

For calls made by a signed-in user, read their identity with `get_access_token()`:

```python
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token


def register(server: MCPServer) -> None:
    @server.tool()
    def who_am_i() -> dict[str, str]:
        """Return the signed-in user's tenant and user IDs."""
        token = get_access_token()
        return {"tenant_id": token.claims["tid"], "user_id": token.claims["oid"]}
```

The token contains verified claims.

Set API keys and other tool credentials under **Server → Environment variables**. These values are shared across all tools on this server and kept out of Git.

## Connect to your MCP Server

Open **Server → MCP → Server information** and copy the endpoint into your MCP client. Choose Streamable HTTP if your client asks for a transport.
