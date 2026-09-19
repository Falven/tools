from itertools import cycle
from threading import Lock

__all__ = ["greet_differently"]


_greetings = cycle(
    (
        ("friendly", "Hello, {name}!"),
        ("cheerful", "Hi there, {name}! Great to see you!"),
        ("warm", "Welcome, {name}! Hope you're having a wonderful day."),
    )
)
_greeting_lock = Lock()


def greet_differently(name: str = "there") -> dict[str, str]:
    """Return a greeting that rotates through three distinct styles.

    Provide the person or audience to greet in ``name``; omit it for a generic
    greeting. Each call advances to the next of three greetings (friendly,
    cheerful, and warm), then repeats the cycle. The rotation is maintained
    only within the current running server process and resets if it restarts.
    Returns the rendered greeting and its style. This tool has no external side
    effects.
    """
    cleaned_name = name.strip() or "there"
    with _greeting_lock:
        style, template = next(_greetings)
    return {"message": template.format(name=cleaned_name), "style": style}
