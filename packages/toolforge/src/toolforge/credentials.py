from __future__ import annotations

import json
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

from azure.core.credentials import AccessToken as AzureAccessToken
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import ManagedIdentityCredential, OnBehalfOfCredential


class ReauthorizationRequired(Exception):
    def __init__(self, claims: str | None = None) -> None:
        super().__init__("The caller must sign in again before this tool can continue.")
        self.claims = claims


@dataclass(frozen=True)
class OBOSettings:
    tenant_id: str
    client_id: str
    client_secret: str | None
    managed_identity_client_id: str | None


@dataclass
class _Caller:
    assertion: str
    settings: OBOSettings
    credential: _CallerCredential | None = None


_caller: ContextVar[_Caller | None] = ContextVar("toolforge_caller", default=None)


def _set_caller_credential(
    access_token: Any, settings: OBOSettings
) -> Token[_Caller | None]:
    claims = access_token.claims or {}
    if not (
        isinstance(claims.get("tid"), str)
        and isinstance(claims.get("oid"), str)
        and isinstance(claims.get("scp"), str)
        and claims["scp"].strip()
    ):
        return _caller.set(None)
    return _caller.set(_Caller(access_token.token, settings))


def _reset_caller_credential(token: Token[_Caller | None]) -> None:
    caller = _caller.get()
    if caller and caller.credential:
        caller.credential.close()
    _caller.reset(token)


class _CallerCredential:
    def __init__(self, caller: _Caller) -> None:
        kwargs: dict[str, Any] = {
            "tenant_id": caller.settings.tenant_id,
            "client_id": caller.settings.client_id,
            "user_assertion": caller.assertion,
        }
        self._closed = False
        self._managed_identity: ManagedIdentityCredential | None = None
        if caller.settings.client_secret:
            kwargs["client_secret"] = caller.settings.client_secret
        else:
            managed_identity_client_id = caller.settings.managed_identity_client_id

            def client_assertion() -> str:
                if self._managed_identity is None:
                    self._managed_identity = ManagedIdentityCredential(
                        client_id=managed_identity_client_id
                    )
                return self._managed_identity.get_token(
                    "api://AzureADTokenExchange/.default"
                ).token

            kwargs["client_assertion_func"] = client_assertion
        self._credential = OnBehalfOfCredential(**kwargs)

    def get_token(self, *scopes: str, **kwargs: Any) -> AzureAccessToken:
        if self._closed:
            raise RuntimeError("The delegated Tool credential is no longer active.")
        try:
            return self._credential.get_token(*scopes, **kwargs)
        except ClientAuthenticationError as error:
            detail: dict[str, Any] = {}
            response = getattr(error, "response", None)
            if response is not None:
                try:
                    value = json.loads(response.text())
                    if isinstance(value, dict):
                        detail = value
                except (AttributeError, TypeError, ValueError):
                    pass
            claims = detail.get("claims")
            codes = detail.get("error_codes", [])
            if not isinstance(codes, list):
                codes = []
            if (
                isinstance(claims, str)
                or detail.get("error")
                in {"interaction_required", "consent_required", "login_required"}
                or any(code in {50076, 50079, 50158, 65001} for code in codes)
            ):
                raise ReauthorizationRequired(
                    claims if isinstance(claims, str) else None
                ) from None
            raise RuntimeError(
                "ToolForge could not obtain a downstream token. Check downstream authorization configuration."
            ) from None

    def close(self) -> None:
        self._closed = True
        self._credential.close()
        if self._managed_identity:
            self._managed_identity.close()


def get_caller_credential() -> _CallerCredential:
    """Return the current invocation's delegated Azure credential.

    Pass downstream WWW-Authenticate claims challenges to get_token(claims=...).
    """
    caller = _caller.get()
    if caller is None:
        raise RuntimeError("A delegated Test Caller is required for this credential.")
    if caller.credential is None:
        caller.credential = _CallerCredential(caller)
    return caller.credential
