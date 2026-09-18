__all__ = ["greet_user"]


def greet_user(name: str = "") -> dict[str, str]:
    """Return a friendly greeting, optionally personalized with a display name.

    Supply name to address the user personally. Surrounding whitespace is
    removed; an omitted or blank name produces a generic greeting. Returns a
    dictionary with a single message string. Does not look up account details,
    send messages, or modify external data.
    """
    import toolforge
    from mcp.server.auth.middleware.auth_context import get_access_token

    # Keep caller context private; no downstream tokens are needed.
    _access_token = get_access_token()
    _caller_credential = toolforge.get_caller_credential()

    display_name = name.strip()
    greeting = f"Hello, {display_name}!" if display_name else "Hello!"
    return {"message": f"{greeting} Nice to meet you."}
