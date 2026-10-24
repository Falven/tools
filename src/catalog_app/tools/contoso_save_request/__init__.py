"""Save a Contoso request through conversation or its MCP App."""

from typing import Annotated, Any

from azure.core import MatchConditions
from azure.data.tables import UpdateMode
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from ..contoso_open_request import (
    RequestId,
    _customer_partition,
    _owned_request,
    _storage,
    _view,
)

BusinessObjective = Annotated[str, Field(strict=True, max_length=4000)]
Revision = Annotated[
    str, Field(strict=True, max_length=256, pattern=r'^(?:W/)?"[^"\r\n]+"$')
]


def contoso_save_request(
    request_id: RequestId, business_objective: BusinessObjective, revision: Revision
) -> dict[str, Any]:
    """Save the signed-in customer's draft business objective with its last-read revision."""
    partition = _customer_partition()
    with _storage() as table:
        entity = _owned_request(table, partition, request_id)
        if entity["Status"] != "draft":
            raise ToolError("Only draft requests can be edited.")
        update = {
            "PartitionKey": partition,
            "RowKey": request_id,
            "BusinessObjective": business_objective,
        }
        result = table.update_entity(
            update,
            mode=UpdateMode.MERGE,
            etag=revision,
            match_condition=MatchConditions.IfNotModified,
        )
        return _view({**entity, **update}, result["etag"])
