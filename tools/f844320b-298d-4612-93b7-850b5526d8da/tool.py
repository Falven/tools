__all__ = ["greet_user"]


def greet_user(name: str = "there") -> dict[str, str]:
    """Greet the user with a friendly message, optionally using their name.

    Args:
        name: The user's name. Omitted or blank names produce "Hello, there!".

    Returns:
        A dictionary containing the greeting in its message field.
    """
    display_name = name.strip() or "there"
    return {"message": f"Hello, {display_name}!"}
