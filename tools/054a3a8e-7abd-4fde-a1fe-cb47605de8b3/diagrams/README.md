# ToolForge on Azure

This diagram follows the architecture brief supplied in the conversation. It is a
logical design, not a discovered deployment or an independently audited inventory.

## Open the editable board

1. Enable and call `paperweave_whiteboard` in ToolForge, then select **Open App**.
2. In Paperweave, choose **More tools (…) → Import JSON**.
3. Choose `toolforge-azure.paperweave.json` and select **Import as a new board**.
4. Use **Shift+1** to fit the diagram, then zoom in to review its detail.
5. Use **Share** to obtain the resulting board code for other users or agents.

Import creates a separate board; it does not overwrite an existing shared board.
If the App is not connected, import remains local-only. Export JSON to preserve
local work. A live board code allows both reading and editing by authorized users
of the tool; share it only with intended collaborators.

The main Paperweave tool was not advertised in the MCP connection used to prepare
these files. These are an importable artifact and an SVG companion, not a claim
that a live board has been created or that a browser import has been tested.

## Files

- `toolforge-azure.paperweave.json`: native, editable Paperweave version 1 board.
- `toolforge-azure.svg`: self-contained, cut-paper SVG overview. Open it in a
  browser or a vector editor. No external image, font, script, or network access
  is required. Its connector routes are arranged for static presentation;
  Paperweave automatically routes the equivalent editable threads.

## Reading the design

- Read left to right: browser/MCP callers → public HTTPS ingress → Next.js →
  Python over localhost. Copilot belongs to the Next.js process.
- The hosting frame is the application boundary. The replica frame encloses the
  shared container and its disposable local checkout/Python environments.
  Published Python tools execute with the host's permissions.
- Azure Container Apps is the primary host. Azure App Service is an alternative,
  not an additional runtime hop.
- The VNet frame describes compute integration and the private PostgreSQL path.
  It does not make public application ingress private.
- PostgreSQL connectivity passes through a private endpoint and private DNS.
  PostgreSQL is durable application state and cross-replica coordination;
  the Git remote stores the published catalog, shared dependencies, and history.
- Key Vault and Blob retain authenticated public service endpoints by default.
  Managed identity is used for Azure service access where configured, distinct
  from delegated user authorization for downstream APIs.
- Optional Blob attachments pass through the application, never directly from
  the browser to Blob. Optional integrations and image deployment use dashed
  threads. Other traffic uses solid threads.
- The native board uses `↔` labels for two-way exchanges; the SVG also shows
  arrowheads at both ends. The two small unlabelled pins only route threads and
  are not additional infrastructure.
- Git and external integrations are outside the application and VNet frames.

No application source, default template, credentials, shared board, or published
Tool identity is changed by these diagram files.

## Validation status

The artifact verifier passed 10 static checks, including JSON syntax, the import
size limit, the native format marker, and selected required labels/connections.
The JSON is 11,732 bytes. No static check failed.

The full schema/topology command was **not executed** because the secure command
sandbox is unavailable (`bwrap` is not installed). The overall verification
result is therefore **incomplete**, not a full pass. Live App import, SVG browser
rendering, and shared-board persistence have not been tested in this connection.
