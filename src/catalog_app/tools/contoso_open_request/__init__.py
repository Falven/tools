"""Open a saved Contoso request and edit its draft business objective."""

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from azure.core.exceptions import (
    AzureError,
    ResourceModifiedError,
    ResourceNotFoundError,
)
from azure.data.tables import TableClient
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

RESOURCE_URI = "ui://contoso-request/app.html"
RequestId = Annotated[str, Field(strict=True, pattern=r"^[A-Za-z0-9_-]{1,128}$")]


def _customer_partition() -> str:
    caller = get_access_token()
    claims = (caller.claims or {}) if caller else {}
    if (
        claims.get("idtyp") == "app"
        or not isinstance(claims.get("scp"), str)
        or not claims["scp"].strip()
    ):
        raise ToolError("Sign in with a delegated customer account.")
    try:
        tenant, customer = UUID(claims["tid"]), UUID(claims["oid"])
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ToolError("The signed-in customer identity is unavailable.") from None
    return f"contoso:{tenant}:{customer}"


@contextmanager
def _storage():
    connection = os.environ.get("CONTOSO_STORAGE_CONNECTION_STRING", "")
    table_name = os.environ.get("CONTOSO_REQUESTS_TABLE", "")
    if not connection.strip() or not table_name.strip():
        raise ToolError(
            "Set CONTOSO_STORAGE_CONNECTION_STRING and CONTOSO_REQUESTS_TABLE in ToolForge."
        )
    try:
        with TableClient.from_connection_string(
            connection, table_name=table_name
        ) as table:
            yield table
    except ResourceNotFoundError:
        raise ToolError("Request not found.") from None
    except ResourceModifiedError:
        raise ToolError("This request changed. Reopen it before saving.") from None
    except (AzureError, ValueError):
        # Azure errors can include configured URLs or credentials; keep them out of Tool output.
        raise ToolError(
            "Contoso storage is unavailable. Check its access and configuration."
        ) from None


def _owned_request(table: TableClient, partition: str, request_id: str):
    entity = table.get_entity(partition_key=partition, row_key=request_id)
    if entity.get("DemoId") != "contoso-demo":
        raise ToolError("Request not found.")
    if any(
        not isinstance(entity.get(key), str)
        for key in ("Title", "BusinessObjective", "Status")
    ):
        raise ToolError("The saved Contoso request is incomplete.")
    return entity


def _view(entity, revision: str) -> dict[str, Any]:
    return {
        "request_id": entity["RowKey"],
        "title": entity["Title"],
        "business_objective": entity["BusinessObjective"],
        "status": entity["Status"],
        "next_action": (
            "Review your business objective and save any changes."
            if entity["Status"] == "draft"
            else "This request is read-only."
        ),
        "revision": revision,
    }


def contoso_open_request(request_id: RequestId) -> dict[str, Any]:
    """Open the signed-in customer's saved software request without changing it."""
    partition = _customer_partition()
    with _storage() as table:
        entity = _owned_request(table, partition, request_id)
        return _view(entity, entity.metadata["etag"])


def contoso_request_app() -> str:
    """Serve the request form without reading customer records."""
    assets = Path(__file__).parent
    html = (assets / "app.html").read_text(encoding="utf-8")
    script = (assets / "app.js").read_text(encoding="utf-8")
    if html.count("<!-- app.js -->") != 1:
        raise ToolError("The Contoso request interface is incomplete.")
    return html.replace(
        "<!-- app.js -->", f'<script type="module">\n{script}\n</script>'
    )


def register(server: MCPServer) -> None:
    server.add_tool(
        contoso_open_request,
        title="Open Contoso request",
        meta={"ui": {"resourceUri": RESOURCE_URI}},
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    server.resource(
        RESOURCE_URI,
        mime_type="text/html;profile=mcp-app",
        title="Contoso request",
        meta={"ui": {"csp": {"resourceDomains": [], "connectDomains": []}}},
    )(contoso_request_app)
