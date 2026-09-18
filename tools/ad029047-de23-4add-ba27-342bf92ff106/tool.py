import toolforge
from mcp.server.auth.middleware.auth_context import get_access_token

__all__ = ["greet_user"]


def greet_user(name: str = "") -> dict[str, str]:
    """Return a friendly greeting, optionally personalized with a name.

    Args:
        name: Name to greet. Leading and trailing whitespace is ignored.
            Omit this argument or leave it blank for a generic greeting.

    Returns:
        A dictionary with a "message" containing the greeting.

    Uses only the supplied name, not profile data. Makes no external requests
    and does not modify or persist data.
    """
    # Obtain caller context without exposing credentials or requesting tokens.
    _access_token = get_access_token()
    _credential = toolforge.get_caller_credential()

    display_name = name.strip()
    message = f"Hello, {display_name}!" if display_name else "Hello! Nice to meet you."
    return {"message": message}
