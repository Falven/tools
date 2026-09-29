<p align="center">
  <img src="./toolforge-logo.png" alt="ToolForge logo" width="96" height="96">
</p>

<h1 align="center">ToolForge</h1>

<p align="center">This repository stores the MCP application served by your ToolForge instance.</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#work-with-git">Work with Git</a> ·
  <a href="#dependencies-and-secrets">Dependencies and secrets</a> ·
  <a href="#connect-via-mcp">Connect via MCP</a>
</p>

ToolForge runs the application in this repository and serves its published, enabled tools to MCP clients. New catalogs start with a Python application scaffold and no tools.

## Quick start

1. In ToolForge, create a tool and open its source. New tools start disabled, with their entry module commented out.
2. Write a Python function inside `register(server)` that accepts client inputs and returns a value. Give it a docstring and register it with `@server.tool()`.
3. Commit and push your changes to publish them. Native Source Control pushes after a commit; terminal and agent commands must push explicitly.

For example, `src/catalog_app/tools/greet/__init__.py`:

```python
def register(server):
    @server.tool()
    def greet(name: str) -> str:
        """Return a greeting for a name."""
        return f"Hello, {name}!"
```

This example shows an enabled tool. When editing a disabled tool, keep its comment layer in place, then enable it in **Server → Tools** after publishing.

| Python                              | MCP                       |
| ----------------------------------- | ------------------------- |
| Function name (`greet`), by default | Tool name                 |
| Docstring                           | Tool description          |
| Function signature                  | Input schema              |
| Return value                        | Result sent to the caller |

## Work with Git

Each ToolForge sandbox checks out the Catalog, with `origin` pointing directly to the configured Git repository:

- Edit tools and server configuration in this repository.
- Commit and push changes to the configured branch. A local commit alone does not publish them.
- Edit this README in a normal Git checkout.

The configured Git repository and branch are the source of truth. A change is published when that repository accepts the push. ToolForge follows the branch and restarts the MCP application to apply changes; check the applied commit before treating a change as live.

Enable, Disable, and Delete in **Server → Tools** each commit and push immediately. Enable and Disable remove or add a comment layer around the tool's entry module; Delete removes the tool and its supporting files.

`server.py` defines the server's name, title, description, and instructions directly in the constructor. Edit these values in the repository. The Server page displays the applied title and instructions read-only.

MCP clients connect to the running ToolForge instance. A Git clone does not serve MCP requests.

## Dependencies and secrets

Edit the shared `pyproject.toml` and any declared local package manifests. The ToolForge sandbox's Git pre-commit hook generates `requirements.lock` from staged manifests; a failed compile stops the commit. Code-only changes do not need a new lock.

In a checkout without that hook, use the same installed ToolForge version as the service to generate the lock, then stage it with the manifest changes, commit, and push:

```bash
toolforge-mcp lock "$PWD/pyproject.toml" --output requirements.lock
```

> [!WARNING]
> Changing `pyproject.toml` alone can leave the lock out of sync and prevent activation. Do not hand-edit `requirements.lock`.

In ToolForge, open **Server → Environment variables** to set API keys and other runtime values. ToolForge passes them to the tool process without storing them in Git. Keep credentials out of tool source, supporting files, and this README.

`auth.py` configures Entra authentication and OBO. Supply its environment values, including credentials, through deployment configuration. These are separate from the tool environment values edited in Server.

## Connect via MCP

1. In ToolForge, open **Server → MCP → Server information** and copy the endpoint. The instance's `/mcp` endpoint uses Streamable HTTP.
2. Configure your client to send a Microsoft Entra bearer token for the configured tenant and audience, including the required delegated scope or application role. These settings are defined in `auth.py` and read from the deployment environment by default.

### Check with MCP Inspector

The [MCP Inspector CLI](https://github.com/modelcontextprotocol/inspector/blob/main/clients/cli/README.md#remote-servers) requires [Node.js 22.19 or newer](https://github.com/modelcontextprotocol/inspector/blob/main/package.json). With a valid access token already in `TOOLFORGE_ACCESS_TOKEN`, replace the URL below with the endpoint you copied:

```bash
npx @modelcontextprotocol/inspector --cli "https://<instance-host>/mcp" --transport http --method tools/list --header "Authorization: Bearer $TOOLFORGE_ACCESS_TOKEN"
```

This lists the tools available to your identity. An empty list is expected until a tool is published and enabled. Create your first tool in ToolForge, publish and enable it, then run the command again.
