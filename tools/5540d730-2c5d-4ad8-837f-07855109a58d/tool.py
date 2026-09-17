__all__ = ["greet_user"]


def greet_user(name: str) -> dict[str, str]:
    """Greet a user by name with a friendly welcome message.

    Args:
        name: The name of the user to greet.
    """
    cleaned_name = name.strip()
    if not cleaned_name:
        raise ValueError("name must not be empty")

    return {"message": f"Hello, {cleaned_name}! Welcome!"}
