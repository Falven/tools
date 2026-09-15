__all__ = ["ey_get_current_work"]


def ey_get_current_work(client_id: str) -> dict:
    """Return active mock EY work for a client."""
    current_work = {
        "client_northstar": [
            {
                "engagement_id": "engagement_northstar_order_processing",
                "name": "Order-processing improvement",
                "status": "active",
                "need_code": "order_processing",
                "service_id": "service_process_improvement",
                "service_name": "Process Improvement",
            }
        ]
    }[client_id]
    return {
        "client_id": client_id,
        "current_work": current_work,
        "mock": True,
        "as_of": "2026-09-14",
    }
