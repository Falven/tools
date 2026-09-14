__all__ = ["greet_2"]


def greet_2(name: str = "user") -> dict[str, str]:
    """Greet a user by name."""
    return {"message": f"Hello, {name}!"}
