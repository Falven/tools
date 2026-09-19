from itertools import cycle
from threading import Lock

__all__ = ["greet_differently"]


_GREETINGS = cycle(
    (
        ("hello", "Hello, {name}!"),
        ("hi", "Hi, {name}—great to see you!"),
        ("greetings", "Greetings, {name}! Hope you're doing well."),
    )
)
_GREETING_LOCK = Lock()


def greet_differently(name: str = "there") -> dict[str, str]:
    """Return a greeting that rotates through three distinct phrasings.

    Pass the person or audience to greet in ``name``; blank or whitespace-only
    values are treated as ``"there"``. Each call advances a process-local,
    thread-safe three-greeting cycle and returns ``greeting`` plus a short
    ``variant`` identifier. The cycle resets if the tool worker restarts, and
    separate workers do not share rotation state. This tool has no external
    side effects.
    """
    recipient = name.strip() or "there"
    with _GREETING_LOCK:
        variant, template = next(_GREETINGS)
    return {
        "greeting": template.format(name=recipient),
        "variant": variant,
    }
