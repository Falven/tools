__all__ = ["ey_find_client"]


def ey_find_client(name: str) -> dict:
    """Return the matching mock client for a client-name lookup."""
    client = (
        {"client_id": "client_northstar", "name": "Northstar Retail"}
        if name.strip().casefold() in {"northstar", "northstar retail"}
        else None
    )
    return {
        "client": client,
        "mock": True,
        "as_of": "2026-09-14",
    }
