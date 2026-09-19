from itertools import cycle
from threading import Lock

__all__ = ["greet_differently"]


_GREETINGS = cycle(
    (
        "Hello, {name}!",
        "Hi, {name}! Great to see you.",
        "Hey, {name}! Hope you're having a wonderful day.",
    )
)
_GREETING_LOCK = Lock()


def greet_differently(name: str = "there") -> dict[str, str]:
    """Return a greeting that rotates through three distinct styles.

    Provide the person or group to address in ``name``; blank input is treated
    as ``"there"``. Each call advances an in-memory three-greeting cycle, so
    consecutive calls in the same running server use different wording. The
    cycle resets if the server process restarts. This tool has no external side
    effects.
    """
    recipient = name.strip() or "there"
    with _GREETING_LOCK:
        template = next(_GREETINGS)
    return {"greeting": template.format(name=recipient)}
