# Contoso request App

This first demo gate opens one saved software request, edits its business
objective, and reopens the current saved value. Intake creation, clarification,
and submission are outside this Tool's current scope.

## Runtime configuration

Set these values in **ToolForge → Server → Environment variables**:

| Variable | Value |
| --- | --- |
| `CONTOSO_STORAGE_CONNECTION_STRING` | Connection string for the approved demo storage account. |
| `CONTOSO_REQUESTS_TABLE` | Existing Azure Table containing the demo request. |

The MCP service uses the Azure Tables SDK. It does not create the table or seed
records. Storage configuration is read when a Tool runs; Tool discovery and App
assets remain available before configuration. Credentials stay in the server
environment and are never sent to the App.

## Operator fixture

Create this entity in the configured table for the customer who will run the
demo. Use that customer's verified Entra tenant ID and object ID as canonical,
lowercase UUIDs.

| Property | Value |
| --- | --- |
| `PartitionKey` | `contoso:<tenant-id>:<customer-object-id>` |
| `RowKey` | `CONTOSO-DEMO-001` |
| `DemoId` | `contoso-demo` |
| `Title` | `Contractor timesheet approvals` |
| `BusinessObjective` | `Reduce manual timesheet follow-up.` |
| `Status` | `draft` |

Azure Table Storage supplies the ETag. Do not create a separate revision
property. Each response returns the ETag as `revision`.

## MCP interface

- `contoso_open_request(request_id)` is the model-facing Tool. It reads the
  signed-in customer's request and attaches `ui://contoso-request/app.html`.
- `contoso_save_request(request_id, business_objective, revision)` is an
  App-only handler. **Save draft** explicitly changes `BusinessObjective` on a
  draft. The handler preserves the other properties and uses the supplied ETag
  for a conditional update. Empty, wildcard, and stale revisions are rejected.

Both operations derive ownership from verified `tid` and `oid` claims and
require a nonempty delegated `scp` claim. Application-only callers are rejected.
Client-supplied owner fields cannot grant access. Rows without the `contoso-demo`
marker are hidden.

The form bundles the official MCP App SDK. On opening, it takes only the request
ID from the retained result and fetches the current record through the host.
Reloading or reopening performs a read; it never replays a save.

## Build and check

From this Tool's `frontend` directory:

```sh
npm ci --ignore-scripts
npm run build
```

Commit `app.js` and `THIRD_PARTY_NOTICES.txt` with the frontend sources and lock.
From the repository root:

```sh
uv sync --frozen
uv run --frozen python -m unittest tests.test_contoso_request -v
```

These tests use the public MCP client with controlled verified-principal and
Azure SDK fixtures. They establish Tool discovery, ownership, conditional writes,
and read/save/reopen behavior. Live Azure, Foundry, and Microsoft 365 access must
be checked separately.

For that live gate, open `CONTOSO-DEMO-001` through the customer agent, change the
business objective, select **Save draft**, and reopen the App. Confirm the saved
value is visible and that the row's ETag changed only for the save. Also verify
that a different customer and an application-only caller cannot read or edit it.
