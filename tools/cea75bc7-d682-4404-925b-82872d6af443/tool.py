import httpx

__all__ = ["new_tool_2"]

def new_tool_2():
    """Return the locked HTTP client version."""
    return {"httpx": httpx.__version__}
