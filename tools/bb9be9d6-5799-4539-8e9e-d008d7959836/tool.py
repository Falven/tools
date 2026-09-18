__all__ = ["ey_find_service"]


def ey_find_service(need_code: str) -> dict:
    """Return the mock service mapped to a documented need code."""
    service = {
        "data_protection": {
            "service_id": "service_cybersecurity",
            "name": "Cybersecurity",
            "need_code": "data_protection",
            "description": "Help protect customer data.",
        },
        "order_processing": {
            "service_id": "service_process_improvement",
            "name": "Process Improvement",
            "need_code": "order_processing",
            "description": "Help process orders faster.",
        },
    }[need_code]
    return {"service": service, "mock": True, "as_of": "2026-09-14"}
