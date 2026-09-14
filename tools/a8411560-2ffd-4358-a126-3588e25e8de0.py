__all__ = ["greet_5"]


def greet_5(name: str) -> dict[str, str]:
    """Greet a user by name with a friendly message."""
    cleaned_name = name.strip()
    if not cleaned_name:
        raise ValueError("name must not be empty")
    return {"message": f"Hello, {cleaned_name}!"}
