"""Pure deterministic Snake rules; keep in parity with ``frontend/core.js``.

This module does not read identity, time, random sources, or storage. A replay
contains only committed direction changes and its terminal tick, never a score.
"""

from __future__ import annotations

from typing import Any

WIDTH = 24
HEIGHT = 18
RIGHT = 1
DIRS = ((0, -1), (1, 0), (0, 1), (-1, 0))
MAX_TICKS = 18_000
MAX_TURNS = 18_000
POINTS_PER_FOOD = 100


class ReplayError(ValueError):
    """The submitted event stream is not a complete legal game."""


def step_ms(foods: int) -> int:
    return max(70, 150 - (foods // 5) * 8)


def _place_food(game: dict[str, Any]) -> None:
    occupied = {y * WIDTH + x for x, y in game["body"]}
    game["rng"] = (1_664_525 * game["rng"] + 1_013_904_223) & 0xFFFFFFFF
    empty_index = game["rng"] % (WIDTH * HEIGHT - len(game["body"]))
    for index in range(WIDTH * HEIGHT):
        if index not in occupied:
            if empty_index == 0:
                game["food"] = [index % WIDTH, index // WIDTH]
                return
            empty_index -= 1


def create_game(seed: int) -> dict[str, Any]:
    game = {
        "body": [[8, 9], [7, 9], [6, 9], [5, 9], [4, 9]],
        "direction": RIGHT,
        "food": None,
        "rng": seed & 0xFFFFFFFF,
        "score": 0,
        "foods": 0,
        "steps": 0,
        "alive": True,
        "won": False,
        "turns": [],
    }
    _place_food(game)
    return game


def advance(game: dict[str, Any], direction: int | None = None) -> dict[str, bool]:
    """Commit one tick, ignoring reversing/invalid input like the JS client.

    Terminal games do not advance again. A fatal tick commits its direction and
    step number but leaves the body at the last legal cells.
    """
    if not game["alive"]:
        return {"ate": False, "dead": not game["won"], "won": game["won"]}
    if direction is None:
        direction = game["direction"]
    game["steps"] += 1
    if (
        type(direction) is int
        and 0 <= direction < len(DIRS)
        and direction != game["direction"]
        and direction != (game["direction"] + 2) % 4
    ):
        game["direction"] = direction
        game["turns"].append([game["steps"], direction])

    dx, dy = DIRS[game["direction"]]
    x, y = game["body"][0]
    x, y = x + dx, y + dy
    ate = game["food"] is not None and game["food"] == [x, y]
    occupied_length = len(game["body"]) - (0 if ate else 1)
    collision = x < 0 or x >= WIDTH or y < 0 or y >= HEIGHT
    if not collision:
        collision = any(
            game["body"][index] == [x, y] for index in range(occupied_length)
        )
    if collision:
        game["alive"] = False
        return {"ate": False, "dead": True, "won": False}

    if ate:
        game["body"].insert(0, [x, y])
        game["score"] += POINTS_PER_FOOD
        game["foods"] += 1
        if len(game["body"]) == WIDTH * HEIGHT:
            game["food"] = None
            game["won"] = True
            game["alive"] = False
        else:
            _place_food(game)
    else:
        head = game["body"].pop()
        head[0], head[1] = x, y
        game["body"].insert(0, head)
    return {"ate": ate, "dead": False, "won": game["won"]}


def validate_replay_shape(steps: int, turns: list[list[int]]) -> None:
    """Bound work and require a canonical, strictly ordered input stream."""
    if type(steps) is not int or not 1 <= steps <= MAX_TICKS:
        raise ReplayError(f"steps must be an integer from 1 to {MAX_TICKS}.")
    if type(turns) is not list or len(turns) > min(MAX_TURNS, steps):
        raise ReplayError(f"turns must be a list of at most {MAX_TURNS} changes.")
    last_tick = 0
    previous_direction = RIGHT
    for turn in turns:
        if type(turn) is not list or len(turn) != 2:
            raise ReplayError("Each turn must contain exactly a tick and a direction.")
        tick, direction = turn
        if type(tick) is not int or not last_tick < tick <= steps:
            raise ReplayError("Turn ticks must be unique, increasing, and within the run.")
        if type(direction) is not int or not 0 <= direction < len(DIRS):
            raise ReplayError("Turn directions must be integers from 0 to 3.")
        if direction == previous_direction:
            raise ReplayError("Record only committed direction changes.")
        if direction == (previous_direction + 2) % 4:
            raise ReplayError("A snake cannot reverse direction.")
        last_tick, previous_direction = tick, direction


def simulate_replay(
    seed: int, steps: int, turns: list[list[int]]
) -> tuple[dict[str, Any], int]:
    """Re-simulate a completed game and return it with its minimum duration (ms).

    Every tick waits at the speed determined by the *previous* food count. This
    includes both the first and the fatal tick. No client-reported times are used.
    A still-live game is complete only at the exact 18000-tick session limit;
    the deterministic core itself remains independent of this server policy.
    """
    validate_replay_shape(steps, turns)
    game = create_game(seed)
    duration_ms = 0
    turn_index = 0
    for tick in range(1, steps + 1):
        direction = game["direction"]
        if turn_index < len(turns) and turns[turn_index][0] == tick:
            direction = turns[turn_index][1]
            turn_index += 1
        duration_ms += step_ms(game["foods"])
        advance(game, direction)
        if not game["alive"] and tick != steps:
            raise ReplayError("A replay cannot contain ticks after death or victory.")
    if game["alive"] and steps != MAX_TICKS:
        raise ReplayError("The final tick must be death, victory, or the 18000-tick session limit.")
    return game, duration_ms
