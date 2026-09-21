from pydantic import PydanticUserError

__all__ = ["load_error_preview"]


def load_error_preview():
    """Temporary preview of a published tool that cannot load."""
    return {"message": "This is a new, empty tool."}


# Temporary demonstration of the error previously raised by Paperweave.
raise PydanticUserError(
    "Please use `typing_extensions.TypedDict` instead of `typing.TypedDict` on Python < 3.12.",
    code="typed-dict-version",
)
