__all__ = ["greet_user"]


def greet_user(name: str = "") -> dict[str, str]:
    """Return a friendly greeting, optionally personalized with a supplied name.

    Args:
        name: Optional display name. Surrounding whitespace is removed.
            Omit it or supply only whitespace to receive "Hello!".

    Returns:
        A JSON object with a "message" field containing "Hello!" or
        "Hello, <name>!". No profile lookup, downstream API call, or
        persistent side effect is performed.
    """
    import toolforge
    from mcp.server.auth.middleware.auth_context import get_access_token

    # Keep authenticated caller context local; no downstream token is needed.
    _access_token = get_access_token()
    _credential = toolforge.get_caller_credential()

    display_name = name.strip()
    return {"message": f"Hello, {display_name}!" if display_name else "Hello!"}
