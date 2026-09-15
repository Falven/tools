__all__ = ["ey_get_client_priorities"]


def ey_get_client_priorities(client_id: str) -> dict:
    """Return the mock priorities recorded for a client."""
    priorities = {
        "client_northstar": [
            {
                "need_code": "order_processing",
                "description": "Process orders faster.",
            },
            {
                "need_code": "data_protection",
                "description": "Protect customer data.",
            },
        ]
    }[client_id]
    return {
        "client_id": client_id,
        "priorities": priorities,
        "mock": True,
        "as_of": "2026-09-14",
    }
