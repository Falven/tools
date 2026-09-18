import json
import random
from pathlib import Path

__all__ = ["new_tool"]


def new_tool(name: str = "") -> dict[str, str]:
    """Greet the user, choosing a random name from names.json by default.

    Args:
        name: Name to greet. Omit or leave blank to choose randomly from names.json.
    """
    from mcp.server.auth.middleware.auth_context import get_access_token
    from toolforge import get_caller_credential

    # Resolve caller context without exposing authentication information.
    _access_token = get_access_token()
    _caller_credential = get_caller_credential()

    display_name = name.strip()
    if not display_name:
        names_path = Path(__file__).with_name("names.json")
        try:
            with names_path.open(encoding="utf-8") as names_file:
                names = json.load(names_file)
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise ValueError(
                "Cannot read names.json. Provide a valid UTF-8 JSON array of names."
            ) from None

        if (
            not isinstance(names, list)
            or not names
            or not all(isinstance(item, str) and item.strip() for item in names)
        ):
            raise ValueError(
                "names.json must contain a nonempty array of nonblank strings."
            )
        display_name = random.choice(names).strip()

    return {"message": f"Hello, {display_name}!"}
