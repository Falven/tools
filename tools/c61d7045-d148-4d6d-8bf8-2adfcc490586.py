__all__ = ["greet_3"]


def greet_3(name: str = "there") -> dict[str, str]:
    """Greet a user by name with a friendly message."""
    cleaned_name = name.strip() or "there"
    return {"message": f"Hello, {cleaned_name}!"}
