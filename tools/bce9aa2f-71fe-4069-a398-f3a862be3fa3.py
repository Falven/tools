__all__ = ["greet_7"]


def greet_7(name: str = "user") -> dict[str, str]:
    """Greet a user by name with a friendly message."""
    return {"message": f"Hello, {name}!"}
