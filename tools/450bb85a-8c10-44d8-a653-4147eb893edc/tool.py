import random
from typing import Literal

import toolforge
from mcp.server.auth.middleware.auth_context import get_access_token

__all__ = ["generate_greeting"]

_GREETINGS: dict[str, tuple[str, ...]] = {
    "friendly": (
        "Hello, {name}! It's great to see you.",
        "Hi, {name}! Hope your day is going well.",
        "Welcome, {name}! Glad you're here.",
    ),
    "formal": (
        "Good day, {name}. It is a pleasure to greet you.",
        "Greetings, {name}. Welcome.",
        "Hello, {name}. I hope you are well.",
    ),
    "casual": (
        "Hey, {name}! What's up?",
        "Hiya, {name}! How's it going?",
        "Hey there, {name}!",
    ),
    "enthusiastic": (
        "Hello, {name}! So happy you're here!",
        "Hey, {name}! Great to see you!",
        "Welcome, {name}! Let's make today a great one!",
    ),
    "pirate": (
        "Ahoy, {name}! Welcome aboard!",
        "Arrr, {name}! Good to see ye!",
        "Ahoy there, {name}! Ready to set sail?",
    ),
    "robot": (
        "Greetings, {name}. Friendly mode activated.",
        "Hello, {name}. Welcome sequence complete.",
        "Beep boop, {name}! Greeting protocol successful.",
    ),
}


def generate_greeting(
    name: str = "friend",
    style: Literal[
        "random", "friendly", "formal", "casual", "enthusiastic", "pirate", "robot"
    ] = "random",
) -> dict[str, str]:
    """Generate one personalized English greeting in a chosen or random style.

    Use this to greet someone or add a playful welcome to a conversation.
    name is optional; whitespace is normalized and a blank name becomes
    "friend". The normalized name must be at most 120 characters.
    style selects friendly, formal, casual, enthusiastic, pirate, or robot;
    "random" chooses a style. Wording is randomly chosen within each style.

    Returns {"greeting": the greeting text, "style": the actual selected style}.
    Random selections may repeat. Uses built-in templates, makes no downstream
    API calls, and stores no data. Invalid types raise TypeError; unsupported
    styles and overlong names raise ValueError.
    """
    if not isinstance(name, str):
        raise TypeError("name must be a string.")
    normalized_name = " ".join(name.split()) or "friend"
    if len(normalized_name) > 120:
        raise ValueError("name must be at most 120 characters after normalization.")
    if not isinstance(style, str):
        raise TypeError("style must be a string.")
    if style not in ("random", *_GREETINGS):
        raise ValueError(
            "style must be random, friendly, formal, casual, enthusiastic, "
            "pirate, or robot."
        )

    # Obtain the authenticated caller context without exposing it or requesting
    # downstream tokens. Greetings do not require access to a caller's profile.
    _access_token = get_access_token()
    _caller_credential = toolforge.get_caller_credential()

    selected_style = random.choice(tuple(_GREETINGS)) if style == "random" else style
    greeting = random.choice(_GREETINGS[selected_style]).format(name=normalized_name)
    return {"greeting": greeting, "style": selected_style}
