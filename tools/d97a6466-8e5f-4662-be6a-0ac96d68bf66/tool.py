__all__ = ["greet_user"]


def greet_user(name: str = "") -> str:
    """Return a friendly greeting, optionally addressing the user by name.

    Args:
        name: The user's name. Omit or leave blank for a general greeting.
    """
    name = name.strip()
    if name:
        return f"Hello, {name}! Nice to meet you."
    return "Hello! Nice to meet you."
