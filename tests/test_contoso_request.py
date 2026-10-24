"""Contoso's public MCP boundary with controlled caller and storage fixtures.

These checks do not establish live Azure access or ToolForge/Foundry integration.
"""

import os
from contextlib import contextmanager
from copy import deepcopy
import unittest
from unittest.mock import patch

from azure.core import MatchConditions
from azure.core.exceptions import ResourceModifiedError, ResourceNotFoundError
from azure.data.tables import UpdateMode
from mcp.client import Client
from mcp.server import MCPServer
from mcp.server.apps import Apps
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken

from tests.fixtures.catalog import register_catalog_tool

TENANT = "22222222-2222-2222-2222-222222222222"
CUSTOMER = "33333333-3333-3333-3333-333333333333"
OTHER_CUSTOMER = "44444444-4444-4444-4444-444444444444"
REQUEST_ID = "CONTOSO-DEMO-001"
ENVIRONMENT = {
    "CONTOSO_STORAGE_CONNECTION_STRING": "synthetic-secret-not-for-output",
    "CONTOSO_REQUESTS_TABLE": "ContosoRequests",
}


@contextmanager
def verified(claims):
    context = auth_context_var.set(
        AuthenticatedUser(
            AccessToken(
                token="synthetic-bearer-not-for-output",
                client_id="controlled-client",
                scopes=["ToolForge.MCP.Access"],
                claims=claims,
            )
        )
    )
    try:
        yield
    finally:
        auth_context_var.reset(context)


class Row(dict):
    def __init__(self, values, etag='"1"'):
        super().__init__(values)
        self.metadata = {"etag": etag}


class Table:
    """Controlled Azure SDK boundary; it does not emulate Azure authentication."""

    def __init__(self):
        self.race_before_update = False
        self.rows = {
            (f"contoso:{TENANT}:{CUSTOMER}", REQUEST_ID): Row(
                {
                    "PartitionKey": f"contoso:{TENANT}:{CUSTOMER}",
                    "RowKey": REQUEST_ID,
                    "DemoId": "contoso-demo",
                    "Title": "Contractor timesheet approvals",
                    "BusinessObjective": "Reduce manual timesheet follow-up.",
                    "Status": "draft",
                }
            ),
        }

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get_entity(self, partition_key, row_key):
        try:
            return deepcopy(self.rows[(partition_key, row_key)])
        except KeyError:
            raise ResourceNotFoundError("Not found") from None

    def update_entity(
        self, entity, mode=UpdateMode.MERGE, *, etag=None, match_condition=None
    ):
        key = (entity["PartitionKey"], entity["RowKey"])
        current = self.rows[key]
        if self.race_before_update:
            self.race_before_update = False
            current["BusinessObjective"] = "A newer saved objective."
            current.metadata["etag"] = '"2"'
        if match_condition == MatchConditions.IfNotModified and etag not in (
            "*",
            current.metadata["etag"],
        ):
            raise ResourceModifiedError("Changed")
        revision = int(current.metadata["etag"][1:-1]) + 1
        values = {**current, **entity} if mode == UpdateMode.MERGE else dict(entity)
        self.rows[key] = Row(values, f'"{revision}"')
        return {"etag": f'"{revision}"'}


class ContosoRequestTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.server = MCPServer("contoso-request-check", extensions=[Apps()])
        register_catalog_tool(self.server, "contoso_open_request")
        register_catalog_tool(self.server, "contoso_save_request")
        self.table = Table()

    async def call(self, name, arguments, claims=None):
        if claims is None:
            claims = {"tid": TENANT, "oid": CUSTOMER, "scp": "ToolForge.MCP.Access"}
        with (
            verified(claims),
            patch.dict(os.environ, ENVIRONMENT),
            patch(
                "azure.data.tables.TableClient.from_connection_string",
                return_value=self.table,
            ),
        ):
            async with Client(self.server) as client:
                result = await client.call_tool(name, arguments)
        self.assertNotIn("synthetic-secret-not-for-output", result.model_dump_json())
        self.assertNotIn("synthetic-bearer-not-for-output", result.model_dump_json())
        return result

    async def test_open_and_save_are_model_and_app_visible_without_storage_configuration(
        self,
    ):
        with patch.dict(os.environ, {}, clear=True):
            async with Client(self.server) as client:
                tools = (await client.list_tools()).tools
        visible = [
            tool.name
            for tool in tools
            if "model" in tool.meta.get("ui", {}).get("visibility", ["model", "app"])
        ]
        self.assertCountEqual(visible, ["contoso_open_request", "contoso_save_request"])
        descriptors = {tool.name: tool for tool in tools}
        save_ui = descriptors["contoso_save_request"].meta["ui"]
        self.assertIn("app", save_ui["visibility"])
        self.assertEqual(
            save_ui["resourceUri"],
            descriptors["contoso_open_request"].meta["ui"]["resourceUri"],
        )

    async def test_open_reads_the_customers_saved_request(self):
        result = await self.call("contoso_open_request", {"request_id": REQUEST_ID})
        self.assertFalse(result.is_error, result.content)
        self.assertEqual(
            result.structured_content,
            {
                "request_id": REQUEST_ID,
                "title": "Contractor timesheet approvals",
                "business_objective": "Reduce manual timesheet follow-up.",
                "status": "draft",
                "next_action": "Review your business objective and save any changes.",
                "revision": '"1"',
            },
        )

    async def test_save_and_reopen_preserve_the_draft_and_other_fields(self):
        saved = await self.call(
            "contoso_save_request",
            {
                "request_id": REQUEST_ID,
                "business_objective": "Approve contractor timesheets in one place.",
                "revision": '"1"',
            },
        )
        self.assertFalse(saved.is_error, saved.content)
        self.server = MCPServer("replacement-contoso-server", extensions=[Apps()])
        register_catalog_tool(self.server, "contoso_open_request")
        register_catalog_tool(self.server, "contoso_save_request")
        opened = await self.call("contoso_open_request", {"request_id": REQUEST_ID})
        self.assertFalse(opened.is_error, opened.content)
        self.assertEqual(opened.structured_content, saved.structured_content)
        self.assertEqual(
            opened.structured_content["business_objective"],
            "Approve contractor timesheets in one place.",
        )
        self.assertEqual(
            opened.structured_content["title"], "Contractor timesheet approvals"
        )
        self.assertEqual(opened.structured_content["status"], "draft")
        self.assertEqual(opened.structured_content["revision"], '"2"')

    async def test_other_users_and_application_callers_cannot_read_or_change_a_request(
        self,
    ):
        for claims in (
            {"tid": TENANT, "oid": OTHER_CUSTOMER, "scp": "ToolForge.MCP.Access"},
            {"tid": OTHER_CUSTOMER, "oid": CUSTOMER, "scp": "ToolForge.MCP.Access"},
            {
                "tid": TENANT,
                "oid": CUSTOMER,
                "roles": ["ToolForge.MCP.Access.Application"],
            },
            {"tid": TENANT, "oid": CUSTOMER, "scp": " ", "idtyp": "app"},
            {"tid": TENANT, "scp": "ToolForge.MCP.Access"},
        ):
            with self.subTest(claims=claims):
                opened = await self.call(
                    "contoso_open_request", {"request_id": REQUEST_ID}, claims
                )
                changed = await self.call(
                    "contoso_save_request",
                    {
                        "request_id": REQUEST_ID,
                        "business_objective": "Unauthorized change",
                        "revision": '"1"',
                    },
                    claims,
                )
                self.assertTrue(opened.is_error)
                self.assertTrue(changed.is_error)
                self.assertNotIn("Reduce manual timesheet", opened.model_dump_json())
        current = await self.call("contoso_open_request", {"request_id": REQUEST_ID})
        self.assertEqual(
            current.structured_content["business_objective"],
            "Reduce manual timesheet follow-up.",
        )
        self.assertEqual(current.structured_content["revision"], '"1"')

    async def test_stale_and_wildcard_revisions_cannot_overwrite_current_data(self):
        for revision in ('"old"', "*", " * ", "", '""', '"old", *'):
            with self.subTest(revision=revision):
                result = await self.call(
                    "contoso_save_request",
                    {
                        "request_id": REQUEST_ID,
                        "business_objective": "Stale overwrite",
                        "revision": revision,
                    },
                )
                self.assertTrue(result.is_error)
        self.table.race_before_update = True
        raced = await self.call(
            "contoso_save_request",
            {
                "request_id": REQUEST_ID,
                "business_objective": "Racing overwrite",
                "revision": '"1"',
            },
        )
        self.assertTrue(raced.is_error)
        current = await self.call("contoso_open_request", {"request_id": REQUEST_ID})
        self.assertEqual(
            current.structured_content["business_objective"], "A newer saved objective."
        )
        self.assertEqual(current.structured_content["revision"], '"2"')

    async def test_non_draft_and_unrelated_records_are_not_editable(self):
        row = self.table.rows[(f"contoso:{TENANT}:{CUSTOMER}", REQUEST_ID)]
        row["Status"] = "submitted"
        denied = await self.call(
            "contoso_save_request",
            {
                "request_id": REQUEST_ID,
                "business_objective": "Changed",
                "revision": '"1"',
            },
        )
        self.assertTrue(denied.is_error)
        current = await self.call("contoso_open_request", {"request_id": REQUEST_ID})
        self.assertEqual(current.structured_content["status"], "submitted")
        self.assertEqual(current.structured_content["revision"], '"1"')
        row["DemoId"] = "unrelated-data"
        hidden = await self.call("contoso_open_request", {"request_id": REQUEST_ID})
        self.assertTrue(hidden.is_error)

    async def test_storage_configuration_and_errors_are_reported_without_secrets(self):
        from azure.core.exceptions import ServiceRequestError

        caller = {"tid": TENANT, "oid": CUSTOMER, "scp": "ToolForge.MCP.Access"}
        with verified(caller), patch.dict(os.environ, {}, clear=True):
            async with Client(self.server) as client:
                result = await client.call_tool(
                    "contoso_open_request", {"request_id": REQUEST_ID}
                )
        self.assertTrue(result.is_error)
        self.assertIn("CONTOSO_STORAGE_CONNECTION_STRING", result.content[0].text)
        with patch.object(
            Table,
            "get_entity",
            side_effect=ServiceRequestError("synthetic-secret-not-for-output"),
        ):
            failed = await self.call("contoso_open_request", {"request_id": REQUEST_ID})
        self.assertTrue(failed.is_error)
        self.assertIn("storage", failed.content[0].text)

    async def test_app_resource_is_available_without_customer_data_or_storage_settings(
        self,
    ):
        with patch.dict(os.environ, {}, clear=True):
            async with Client(self.server) as client:
                tools = (await client.list_tools()).tools
                entry = next(
                    tool for tool in tools if tool.name == "contoso_open_request"
                )
                result = await client.read_resource(entry.meta["ui"]["resourceUri"])
        self.assertEqual(result.contents[0].mime_type, "text/html;profile=mcp-app")
        self.assertTrue(result.contents[0].text)
        self.assertNotIn("Reduce manual timesheet follow-up.", result.contents[0].text)
        self.assertNotIn("synthetic-secret-not-for-output", result.contents[0].text)


if __name__ == "__main__":
    unittest.main()
