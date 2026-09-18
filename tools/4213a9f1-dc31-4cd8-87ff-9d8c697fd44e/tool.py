__all__ = ["welcome_user"]


def welcome_user(name: str) -> dict[str, str]:
    """Greet a user by name with a friendly welcome message."""
    cleaned_name = name.strip()
    if not cleaned_name:
        cleaned_name = "there"
    return {"message": f"Hello, {cleaned_name}! Welcome!"}
