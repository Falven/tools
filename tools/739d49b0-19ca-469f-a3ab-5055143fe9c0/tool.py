__all__ = ["new_tool"]


def new_tool(name: str = "") -> dict[str, str]:
    """Greet the user, optionally including their name.

    Args:
        name: Name to greet. Omit or leave blank for a general greeting.
    """
    from mcp.server.auth.middleware.auth_context import get_access_token
    from toolforge import get_caller_credential

    # Resolve caller context without exposing authentication information.
    _access_token = get_access_token()
    _caller_credential = get_caller_credential()

    display_name = name.strip()
    message = f"Hello, {display_name}!" if display_name else "Hello! Welcome!"
    return {"message": message}
