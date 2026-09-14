__all__ = ["greet_1"]


def greet_1(name: str = "user") -> dict[str, str]:
    """Greet a user by name."""
    return {"message": f"Hello, {name}!"}
