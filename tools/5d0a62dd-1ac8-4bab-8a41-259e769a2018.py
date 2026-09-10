from collections.abc import Mapping

__all__ = ["greet_calling_user"]


def greet_calling_user() -> dict[str, str]:
    """Greet the authenticated calling user using their verified identity, without exposing credentials."""
    from mcp.server.auth.middleware.auth_context import get_access_token

    access_token = get_access_token()
    if access_token is None:
        return {"error": "No authenticated caller is available. Sign in and retry."}

    claims = getattr(access_token, "claims", None)
    if not isinstance(claims, Mapping):
        return {"error": "The authenticated caller's verified identity is unavailable."}

    # Use only verified identity claims, never the raw token or application ID.
    for claim_name in (
        "name",
        "preferred_username",
        "upn",
        "email",
        "sub",
        "oid",
    ):
        identity = claims.get(claim_name)
        if isinstance(identity, str) and identity.strip():
            return {"message": f"Hello, {identity.strip()}!"}

    return {"error": "The authenticated caller has no usable user identity claim."}
