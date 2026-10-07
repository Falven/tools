import asyncio
import ctypes
import json
import logging
import os
import sys
from importlib import import_module
from pathlib import Path

import jwt
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl
from toolforge import OBOSettings
from toolforge.auth import _http_request


_logger = logging.getLogger(__name__)


class MiseTokenVerifier:
    def __init__(self, tenant_id: str, audience: str, permission: str, client_id: str):
        self.permission = permission
        if sys.platform == "linux":
            import icukit_pyicu

            library_directory = Path(icukit_pyicu.get_lib())
            for name in ("libicudata.so", "libicuuc.so", "libicui18n.so"):
                ctypes.CDLL(str(library_directory / name), mode=ctypes.RTLD_GLOBAL)
        mise = import_module("mise")
        self.mise = mise.Mise()
        self.validation_input = mise.MiseValidationInput
        configuration = {
            "MiseVersion": "2.0",
            "AzureAd": {
                "Instance": "https://login.microsoftonline.com/",
                "TenantId": tenant_id.lower(),
                "ClientId": client_id,
                "Audiences": [audience],
                "ValidTenantIds": [tenant_id.lower()],
                "Protocols": {
                    "Bearer": {
                        "TokenTypes": {
                            "AccessToken": {"AppToken": True, "UserToken": True}
                        }
                    }
                },
            },
            "Mise": {
                "ClaimsOnlyAuthZModule": {
                    "AuthorizationConfig": {
                        "Policies": [
                            {
                                "Name": "mcp-users",
                                "IsDefaultPolicy": True,
                                "Profile": "NonAuthorizingUser",
                            },
                            {
                                "Name": "mcp-applications",
                                "IsDefaultPolicy": True,
                                "Profile": "NonAuthorizingApp",
                            },
                        ]
                    }
                },
                "TelemetryExporterOptions": {"EnableExportingData": True},
            },
        }
        with self.mise.configure(json.dumps(configuration), "AzureAd") as result:
            if result.error_code:
                raise RuntimeError("MISE configuration failed.")

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            validation_input = self.validation_input()
            validation_input.authorization_header = f"Bearer {token}"
            request = _http_request.get()
            validation_input.original_uri_header = str(request.url)
            validation_input.original_method_header = request.method
            with await asyncio.to_thread(
                self.mise.validate, validation_input
            ) as result:
                if result.http_response_status_code != 200:
                    _logger.warning(
                        "MISE token validation failed: %s",
                        result.http_response_status_code,
                    )
                    return None
                claims = jwt.decode(token, options={"verify_signature": False})

            client_id = claims.get("azp") or claims.get("appid")
            if not isinstance(client_id, str):
                _logger.warning("Authenticated token has no client identity")
                return None
            scopes = str(claims.get("scp", "")).split()
            roles = claims.get("roles", [])
            if isinstance(roles, list) and f"{self.permission}.Application" in roles:
                scopes.append(self.permission)
            return AccessToken(
                token=token,
                client_id=client_id,
                scopes=list(dict.fromkeys(scopes)),
                expires_at=claims["exp"],
                subject=claims.get("sub"),
                claims=claims,
            )
        except Exception as error:  # noqa: BLE001 - every verification failure is an invalid token
            _logger.warning("MISE token validation failed: %s", type(error).__name__)
            return None


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
        MiseTokenVerifier(
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
