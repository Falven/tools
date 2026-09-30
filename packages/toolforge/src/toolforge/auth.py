from __future__ import annotations

import asyncio
import json
import logging
import os
from contextvars import ContextVar
from importlib import import_module
from typing import Any

import jwt
from jwt import PyJWKClient
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp_types import CallToolResult, TextContent
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from . import credentials

_http_request: ContextVar[Request] = ContextVar("http_request")
_logger = logging.getLogger(__name__)


class EntraTokenVerifier:
    def __init__(
        self,
        tenant_id: str,
        audience: str,
        permission: str,
        client_id: str = "",
        *,
        user_role: str | None = None,
        application_role: str | None = None,
        actor: str = "mcp",
    ) -> None:
        if (user_role is not None or application_role is not None) and (
            not user_role or not application_role
        ):
            raise ValueError(
                "Both user_role and application_role are required for role authorization."
            )
        self.tenant_id = tenant_id.lower()
        self.audience = audience
        self.permission = permission
        self.user_role = user_role
        self.application_role = application_role
        self.actor = actor
        self.mise = None
        self.key_client = None
        self._mise_validation_input = None
        if not os.environ.get("TOOLFORGE_MISE_WHEEL", "").strip():
            self.key_client = PyJWKClient(
                f"https://login.microsoftonline.com/{self.tenant_id}/discovery/v2.0/keys"
            )
            return

        mise = import_module("mise")
        self.mise = mise.Mise()
        self._mise_validation_input = mise.MiseValidationInput
        configuration = {
            "MiseVersion": "2.0",
            "AzureAd": {
                "Instance": "https://login.microsoftonline.com/",
                "TenantId": self.tenant_id,
                "ClientId": client_id,
                "Audiences": [audience],
                "ValidTenantIds": [self.tenant_id],
                "Protocols": {
                    "Bearer": {
                        "TokenTypes": {
                            "AccessToken": {"AppToken": True, "UserToken": True}
                        }
                    }
                },
            },
            "Mise": {
                # Permission and role checks run below.
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
            if self.mise is None:
                assert self.key_client is not None
                signing_key = await asyncio.to_thread(
                    self.key_client.get_signing_key_from_jwt, token
                )
                claims = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    audience=self.audience,
                    options={"require": ["exp", "iss", "tid"]},
                )
                if claims["tid"].lower() != self.tenant_id or claims["iss"] not in {
                    f"https://login.microsoftonline.com/{self.tenant_id}/v2.0",
                    f"https://sts.windows.net/{self.tenant_id}/",
                }:
                    _logger.warning(
                        "auth.failed",
                        extra={
                            "event": "auth.failed",
                            "actor": self.actor,
                            "reason": "issuer_or_tenant_mismatch",
                        },
                    )
                    return None
            else:
                assert self._mise_validation_input is not None
                validation_input = self._mise_validation_input()
                validation_input.authorization_header = f"Bearer {token}"
                request = _http_request.get()
                validation_input.original_uri_header = str(request.url)
                validation_input.original_method_header = request.method
                with await asyncio.to_thread(
                    self.mise.validate, validation_input
                ) as result:
                    if result.http_response_status_code != 200:
                        _logger.warning(
                            "auth.failed",
                            extra={
                                "event": "auth.failed",
                                "actor": self.actor,
                                "reason": "mise_validation_failed",
                                "statusCode": result.http_response_status_code,
                            },
                        )
                        return None
                    # MISE authenticated this exact bearer; preserve its JWT claim types for MCP/OBO.
                    claims = jwt.decode(token, options={"verify_signature": False})
            client_id = claims.get("azp") or claims.get("appid")
            if not isinstance(client_id, str):
                _logger.warning(
                    "auth.failed",
                    extra={
                        "event": "auth.failed",
                        "actor": self.actor,
                        "reason": "missing_client_identity",
                    },
                )
                return None
            scopes = str(claims.get("scp", "")).split()
            roles = claims.get("roles", [])
            if self.user_role is not None:
                required_role = self.user_role if scopes else self.application_role
                authorized = (
                    isinstance(roles, list)
                    and required_role in roles
                    and (not scopes or self.permission in scopes)
                )
                scopes = [self.permission] if authorized else []
            elif isinstance(roles, list) and f"{self.permission}.Application" in roles:
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
            _logger.warning(
                "auth.failed",
                extra={
                    "event": "auth.failed",
                    "actor": self.actor,
                    "reason": "token_verification_failed",
                    "errorType": type(error).__name__,
                },
            )
            return None


class EntraRequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = _http_request.set(Request(scope))
        try:
            await self.app(scope, receive, send)
        finally:
            _http_request.reset(token)


class EntraMCPServer(MCPServer[dict[str, Any]]):
    def __init__(
        self, *, obo_settings: credentials.OBOSettings | None = None, **kwargs: Any
    ) -> None:
        self._obo_settings = obo_settings
        super().__init__(**kwargs)

    async def call_tool(self, name: str, arguments: dict[str, Any], context=None):
        if context is None:
            return await super().call_tool(name, arguments, context)
        credential_token = None
        if self._obo_settings is not None:
            caller = get_access_token()
            if caller is not None:
                credential_token = credentials._set_caller_credential(
                    caller, self._obo_settings
                )
        try:
            return await super().call_tool(name, arguments, context)
        except Exception as error:
            current: BaseException | None = error
            while current is not None:
                if isinstance(current, credentials.ReauthorizationRequired):
                    return CallToolResult(
                        content=[
                            TextContent(
                                type="text",
                                text="The caller must sign in again before this tool can continue.",
                            )
                        ],
                        is_error=True,
                        _meta={
                            "toolforge/reauthorization": {
                                **({"claims": current.claims} if current.claims else {})
                            }
                        },
                    )
                current = current.__cause__ or current.__context__
            raise
        finally:
            if credential_token is not None:
                credentials._reset_caller_credential(credential_token)

    def streamable_http_app(self, **kwargs: Any) -> Starlette:
        app = super().streamable_http_app(**kwargs)
        app.add_middleware(EntraRequestContextMiddleware)
        return app
