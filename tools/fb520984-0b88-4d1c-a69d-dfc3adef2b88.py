__all__ = ["ey_get_client_contacts"]


def ey_get_client_contacts(client_id: str) -> dict:
    """Return the mock client contacts and their roles."""
    contacts = {
        "client_northstar": [
            {
                "contact_id": "contact_maya",
                "name": "Maya Chen",
                "role": "technology_lead",
            },
            {
                "contact_id": "contact_sam",
                "name": "Sam Rivera",
                "role": "account_owner",
            },
        ]
    }[client_id]
    return {
        "client_id": client_id,
        "contacts": contacts,
        "mock": True,
        "as_of": "2026-09-14",
    }
