__all__ = ["ey_draft_follow_up"]


def ey_draft_follow_up(client_id: str, contact_id: str, service_id: str) -> dict:
    """Create an unsent mock follow-up draft for a client contact and service."""
    client_name = {"client_northstar": "Northstar Retail"}[client_id]
    contact_name = {
        "contact_maya": "Maya Chen",
        "contact_sam": "Sam Rivera",
    }[contact_id]
    service_name = {
        "service_cybersecurity": "Cybersecurity",
        "service_process_improvement": "Process Improvement",
    }[service_id]
    return {
        "client_id": client_id,
        "contact_id": contact_id,
        "service_id": service_id,
        "subject": f"{client_name}: {service_name} discussion",
        "body": (
            f"Hello {contact_name},\n\n"
            f"I would welcome a conversation about how {service_name} could help "
            f"{client_name}.\n\nBest,\nEY"
        ),
        "status": "draft",
        "sent": False,
        "mock": True,
        "as_of": "2026-09-14",
    }
