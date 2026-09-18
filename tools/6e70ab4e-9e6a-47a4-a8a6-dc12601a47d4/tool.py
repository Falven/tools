__all__ = ["friendly_user_greeting"]


def friendly_user_greeting(name: str = "") -> dict[str, str]:
    """Greet the user, optionally using their name.

    Args:
        name: The user's name. Omit or leave blank for a generic greeting.
    """
    name = name.strip()
    return {"message": f"Hello, {name}!" if name else "Hello!"}
