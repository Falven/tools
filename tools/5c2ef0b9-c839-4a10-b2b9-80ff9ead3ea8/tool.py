import toolforge
from mcp.server.auth.middleware.auth_context import get_access_token

__all__ = ["greet_jim"]


def greet_jim() -> dict[str, str]:
    """Generate a friendly greeting addressed to Jim.

    Takes no inputs and returns {"message": "Hello, Jim!"}.
    Only generates text; it does not contact Jim or send a message.
    """
    _access_token = get_access_token()
    _credential = toolforge.get_caller_credential()
    return {"message": "Hello, Jim!"}
