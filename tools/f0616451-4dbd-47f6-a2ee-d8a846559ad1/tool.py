__all__ = ["greet_user"]


def greet_user(name: str = "") -> dict[str, str]:
    """Return a friendly greeting, optionally personalized with the user's name.

    Args:
        name: The user's name. Omit or leave blank for a generic greeting.
    """
    display_name = name.strip() or "there"
    return {"message": f"Hello, {display_name}!"}
