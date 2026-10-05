"""Deterministic Rally — After Hours rules, mirrored in ``frontend/core.js``.

Coordinates, velocities and all physics intermediate values are integers. The
only random source is the game's unsigned 32-bit LCG. This module has no clocks,
I/O, authentication or retained server state. Negative y is the top of court.
"""

from __future__ import annotations

from math import isqrt
from typing import Any

WIDTH = 20_000
HEIGHT = 12_000
HALF_WIDTH = WIDTH // 2
HALF_HEIGHT = HEIGHT // 2
PADDLE_X = 9_000
PADDLE_HALF = 1_100
BALL_RADIUS = 180
PADDLE_LIMIT = HALF_HEIGHT - PADDLE_HALF
BALL_LIMIT = HALF_HEIGHT - BALL_RADIUS
PADDLE_FACE = PADDLE_X - BALL_RADIUS
TARGET_MAX = 1_000
TICK_RATE = 120
MAX_STEPS = 14_400
MAX_INPUTS = MAX_STEPS
PLAYER_SPEED = 250
AI_SPEED = 65
SERVE_TICKS = 90
TARGET_GOALS = 7
INITIAL_BALL_SPEED = 100
MAX_BALL_SPEED = 180
BALL_SPEED_INCREMENT = 5
POINTS_PER_HIT = 10
POINTS_PER_GOAL = 100
WIN_BONUS = 250

# Public wire/rendering constants. Keep keys and values identical to the JS core.
CONSTANTS = {
    "version": 1,
    "width": WIDTH,
    "height": HEIGHT,
    "halfWidth": HALF_WIDTH,
    "halfHeight": HALF_HEIGHT,
    "paddleX": PADDLE_X,
    "paddleHalf": PADDLE_HALF,
    "ballRadius": BALL_RADIUS,
    "paddleLimit": PADDLE_LIMIT,
    "targetMax": TARGET_MAX,
    "tickRate": TICK_RATE,
    "maxSteps": MAX_STEPS,
    "maxInputs": MAX_INPUTS,
    "playerSpeed": PLAYER_SPEED,
    "aiSpeed": AI_SPEED,
    "serveTicks": SERVE_TICKS,
    "targetGoals": TARGET_GOALS,
    "initialBallSpeed": INITIAL_BALL_SPEED,
    "maxBallSpeed": MAX_BALL_SPEED,
    "ballSpeedIncrement": BALL_SPEED_INCREMENT,
    "pointsPerHit": POINTS_PER_HIT,
    "pointsPerGoal": POINTS_PER_GOAL,
    "winBonus": WIN_BONUS,
}


class ReplayError(ValueError):
    """The event stream is not a canonical, complete, bounded game."""


def trunc_div(numerator: int, denominator: int) -> int:
    """Integer division towards zero, including negative operands (JS parity)."""
    magnitude = abs(numerator) // abs(denominator)
    return -magnitude if (numerator < 0) != (denominator < 0) else magnitude


def _clamp(value: int, low: int, high: int) -> int:
    return min(high, max(low, value))


def _move_towards(position: int, target: int, speed: int) -> int:
    return position + _clamp(target - position, -speed, speed)


def _random(game: dict[str, Any]) -> int:
    game["rng"] = (1_664_525 * game["rng"] + 1_013_904_223) & 0xFFFFFFFF
    return game["rng"]


def _reflect_y(y: int) -> int:
    # A legal tick travels <=180 units, so at most one wall can be crossed.
    if y > BALL_LIMIT:
        return 2 * BALL_LIMIT - y
    if y < -BALL_LIMIT:
        return -2 * BALL_LIMIT - y
    return y


def create_game(seed: int) -> dict[str, Any]:
    """Create an independent game. The initial serve is towards the player."""
    return {
        "steps": 0,
        "rng": seed & 0xFFFFFFFF,
        "target": 0,
        "playerY": 0,
        "aiY": 0,
        "ballX": 0,
        "ballY": 0,
        "vx": 0,
        "vy": 0,
        "playerGoals": 0,
        "aiGoals": 0,
        "score": 0,
        "hits": 0,
        "rally": 0,
        "bestRally": 0,
        "alive": True,
        "won": False,
        "serveTicks": SERVE_TICKS,
        "inputs": [],
        "ballSpeed": INITIAL_BALL_SPEED,
        "serveDirection": -1,
        "aiTarget": 0,
        "aiThinkTicks": 0,
        "endedByLimit": False,
    }


def _launch(game: dict[str, Any]) -> None:
    vertical = _random(game) % 91 - 45
    # No dead-flat serves, while still allowing easy initial returns.
    if abs(vertical) < 18:
        vertical = -18 if vertical < 0 else 18
    game["vy"] = vertical
    game["vx"] = game["serveDirection"] * isqrt(INITIAL_BALL_SPEED**2 - vertical**2)


def _move_ai(game: dict[str, Any]) -> int:
    before = game["aiY"]
    if game["serveTicks"] > 0:
        game["aiTarget"] = 0
        game["aiThinkTicks"] = 0
    elif game["aiThinkTicks"] <= 0:
        # Reactive, not clairvoyant: sample current y with seeded error and wait
        # 14..28 ticks before thinking again. At 65 units/tick angled shots win.
        error = _random(game) % 1_401 - 700
        observed = game["ballY"] if game["vx"] > 0 else trunc_div(game["ballY"], 2)
        game["aiTarget"] = _clamp(observed + error, -PADDLE_LIMIT, PADDLE_LIMIT)
        game["aiThinkTicks"] = 14 + _random(game) % 15
    else:
        game["aiThinkTicks"] -= 1
    game["aiY"] = _move_towards(before, game["aiTarget"], AI_SPEED)
    return game["aiY"] - before


def _return_ball(game: dict[str, Any], side: str, contact_y: int, motion: int) -> None:
    paddle_y = game["playerY"] if side == "player" else game["aiY"]
    game["rally"] += 1
    game["bestRally"] = max(game["bestRally"], game["rally"])
    speed = min(MAX_BALL_SPEED, INITIAL_BALL_SPEED + BALL_SPEED_INCREMENT * game["rally"])
    game["ballSpeed"] = speed
    offset = _clamp(contact_y - paddle_y, -PADDLE_HALF, PADDLE_HALF)
    # Integer edge deflection (75% of speed) plus paddle-motion spin. The 85%
    # vertical cap leaves a horizontal component >=52%, preventing stall loops.
    vertical = trunc_div(offset * speed * 75, PADDLE_HALF * 100)
    vertical += trunc_div(motion * speed, 1_000)
    cap = trunc_div(speed * 85, 100)
    game["vy"] = _clamp(vertical, -cap, cap)
    horizontal = isqrt(speed * speed - game["vy"] * game["vy"])
    game["vx"] = horizontal if side == "player" else -horizontal
    if side == "player":
        game["hits"] += 1
        game["score"] += POINTS_PER_HIT


def _goal(game: dict[str, Any], side: str) -> None:
    key = "playerGoals" if side == "player" else "aiGoals"
    game[key] += 1
    if side == "player":
        game["score"] += POINTS_PER_GOAL
    game["rally"] = 0
    game["ballSpeed"] = INITIAL_BALL_SPEED
    game["ballX"] = game["ballY"] = game["vx"] = game["vy"] = 0
    game["aiThinkTicks"] = 0
    # Following a goal the ball serves towards the paddle that conceded it.
    game["serveDirection"] = 1 if side == "player" else -1
    if game[key] == TARGET_GOALS:
        game["alive"] = False
        game["won"] = side == "player"
        game["serveTicks"] = 0
        if game["won"]:
            game["score"] += WIN_BONUS
    else:
        game["serveTicks"] = SERVE_TICKS


def advance(game: dict[str, Any], target: int | None = None) -> dict[str, Any]:
    """Commit one 120 Hz tick and return collision/goal/terminal events.

    Valid changed targets are automatically recorded as [1-based tick, target].
    Invalid live input is ignored; submitted replays instead reject it strictly.
    A terminal game is a no-op. ``hits`` counts player returns; ``rally`` and
    ``bestRally`` count consecutive returns by BOTH paddles. A 120-second timeout
    ends the match without a victory/bonus, even if the player is leading.
    """
    event = {"playerHit": False, "aiHit": False, "wall": False, "goal": None, "ended": not game["alive"]}
    if not game["alive"]:
        return event
    if target is None:
        target = game["target"]
    game["steps"] += 1
    if type(target) is int and -TARGET_MAX <= target <= TARGET_MAX and target != game["target"]:
        game["target"] = target
        game["inputs"].append([game["steps"], target])

    player_before = game["playerY"]
    desired = trunc_div(game["target"] * PADDLE_LIMIT, TARGET_MAX)
    game["playerY"] = _move_towards(player_before, desired, PLAYER_SPEED)
    player_motion = game["playerY"] - player_before
    ai_motion = _move_ai(game)

    if game["serveTicks"] > 0:
        game["serveTicks"] -= 1
        if game["serveTicks"] == 0:
            _launch(game)
    else:
        old_x, old_y, old_vx, old_vy = game["ballX"], game["ballY"], game["vx"], game["vy"]
        game["ballX"] += old_vx
        raw_y = old_y + old_vy
        game["ballY"] = _reflect_y(raw_y)
        if raw_y > BALL_LIMIT or raw_y < -BALL_LIMIT:
            game["vy"] = -old_vy
            event["wall"] = True

        side = None
        if old_vx < 0 and old_x >= -PADDLE_FACE and game["ballX"] <= -PADDLE_FACE:
            side, plane, paddle_y, motion = "player", -PADDLE_FACE, game["playerY"], player_motion
        elif old_vx > 0 and old_x <= PADDLE_FACE and game["ballX"] >= PADDLE_FACE:
            side, plane, paddle_y, motion = "ai", PADDLE_FACE, game["aiY"], ai_motion
        if side is not None:
            # Sweep to the paddle plane rather than testing only the tick's end.
            # A wall before contact is reflected using the same integer rule.
            contact_y = _reflect_y(old_y + trunc_div(old_vy * (plane - old_x), old_vx))
            if abs(contact_y - paddle_y) <= PADDLE_HALF + BALL_RADIUS:
                game["ballX"] = 2 * plane - game["ballX"]
                _return_ball(game, side, contact_y, motion)
                event["playerHit" if side == "player" else "aiHit"] = True

        if game["ballX"] < -HALF_WIDTH - BALL_RADIUS:
            event["goal"] = "ai"
            _goal(game, "ai")
        elif game["ballX"] > HALF_WIDTH + BALL_RADIUS:
            event["goal"] = "player"
            _goal(game, "player")

    if game["alive"] and game["steps"] >= MAX_STEPS:
        game["alive"] = False
        game["won"] = False
        game["endedByLimit"] = True
    event["ended"] = not game["alive"]
    return event


def validate_replay_shape(steps: int, inputs: list[list[int]]) -> None:
    """Bound CPU/memory and reject duplicates, redundant targets and coercions."""
    if type(steps) is not int or not 1 <= steps <= MAX_STEPS:
        raise ReplayError(f"steps must be an integer from 1 to {MAX_STEPS}.")
    if type(inputs) is not list or len(inputs) > min(MAX_INPUTS, steps):
        raise ReplayError(f"inputs must be a list of at most {MAX_INPUTS} target changes.")
    last_tick, previous_target = 0, 0
    for change in inputs:
        if type(change) is not list or len(change) != 2:
            raise ReplayError("Each input must contain exactly a tick and a target.")
        tick, target = change
        if type(tick) is not int or not last_tick < tick <= steps:
            raise ReplayError("Input ticks must be unique, increasing integers within the run.")
        if type(target) is not int or not -TARGET_MAX <= target <= TARGET_MAX:
            raise ReplayError("Input targets must be integers from -1000 to 1000.")
        if target == previous_target:
            raise ReplayError("Record only target changes, not redundant targets.")
        last_tick, previous_target = tick, target


def simulate_replay(seed: int, steps: int, inputs: list[list[int]]) -> tuple[dict[str, Any], int]:
    """Replay exactly through the seventh goal or the 14400th tick, never beyond.

    Return the authoritative game and minimum duration in whole milliseconds,
    rounded UP (including all serve ticks). No client score or timing is used.
    """
    validate_replay_shape(steps, inputs)
    game = create_game(seed)
    index = 0
    for tick in range(1, steps + 1):
        target = game["target"]
        if index < len(inputs) and inputs[index][0] == tick:
            target = inputs[index][1]
            index += 1
        advance(game, target)
        if not game["alive"] and tick != steps:
            raise ReplayError("A replay cannot contain ticks after the match ends.")
    if game["alive"]:
        raise ReplayError("The final tick must be the seventh goal or the 14400-tick time limit.")
    return game, (steps * 1_000 + TICK_RATE - 1) // TICK_RATE
