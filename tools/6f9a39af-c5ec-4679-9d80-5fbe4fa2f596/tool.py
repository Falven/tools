__all__ = ["friendly_user_greeting"]


def friendly_user_greeting(name: str = "") -> dict[str, str]:
    """Return a friendly greeting, optionally personalized with the user's name.

    Args:
        name: Name to greet. If omitted or blank, use "there".
    """
    display_name = name.strip() or "there"
    return {"message": f"Hello, {display_name}!"}
