from mcp.server.auth.middleware.auth_context import get_access_token
from toolforge import get_caller_credential

__all__ = ["new_tool"]


def new_tool(name: str = "") -> dict[str, str]:
    """Return a friendly greeting, optionally personalized with the user's name."""
    # Obtain caller context without exposing credentials or requesting tokens.
    _access_token = get_access_token()
    _credential = get_caller_credential()

    display_name = name.strip()
    message = (
        f"Hello, {display_name}!"
        if display_name
        else "Hello! Nice to meet you."
    )
    return {"message": message}
