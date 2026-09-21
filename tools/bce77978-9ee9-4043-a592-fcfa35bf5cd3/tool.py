__all__ = ["new_tool_2"]


def new_tool_2() -> str:
    """Print hello world to server stdout and return it to the MCP caller.

    Takes no arguments and returns the greeting as a string. The only output
    written to stdout is the greeting; caller credentials are never exposed.
    """
    import toolforge
    from mcp.server.auth.middleware.auth_context import get_access_token

    _access_token = get_access_token()
    _credential = toolforge.get_caller_credential()

    message = "hello world"
    print(message)
    return message
