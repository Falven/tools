__all__ = ["greet_4"]


def greet_4(name: str = "there") -> dict[str, str]:
    """Greet a user with a friendly personalized message."""
    return {"message": f"Hello, {name}!"}
