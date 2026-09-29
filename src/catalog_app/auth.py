import os

from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl
from toolforge import EntraTokenVerifier, OBOSettings


def build_auth():
    tenant_id = os.environ["TOOLFORGE_MCP_ENTRA_TENANT_ID"]
    audience = os.environ["TOOLFORGE_MCP_ENTRA_AUDIENCE"]
    permission = os.environ["TOOLFORGE_MCP_ENTRA_PERMISSION"]
    client_id = os.environ["TOOLFORGE_MCP_ENTRA_CLIENT_ID"]
    return (
        AuthSettings(
            issuer_url=AnyHttpUrl(
                f"https://login.microsoftonline.com/{tenant_id.lower()}/v2.0"
            ),
            resource_server_url=AnyHttpUrl(os.environ["TOOLFORGE_MCP_RESOURCE_URL"]),
            required_scopes=[permission],
        ),
        EntraTokenVerifier(
            tenant_id=tenant_id,
            audience=audience,
            permission=permission,
            client_id=client_id,
        ),
        OBOSettings(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=os.environ.get("TOOLFORGE_MCP_ENTRA_CLIENT_SECRET"),
            managed_identity_client_id=os.environ.get(
                "TOOLFORGE_MCP_ENTRA_MANAGED_IDENTITY_CLIENT_ID"
            ),
        ),
    )
