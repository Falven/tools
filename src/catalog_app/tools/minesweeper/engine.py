"""Server-only Minesweeper rules, using only the standard library.

No board, seed, or mine layout is accepted from the client. The state owner
supplies a monotonic timestamp and a private random sampler to ``apply_move``.
Only ``snapshot``/``visible_cells`` may cross the MCP boundary; a Game contains
private mine positions and must never be serialized directly.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Any, Literal

DifficultyId = Literal["beginner", "intermediate", "expert"]
Action = Literal["reveal", "flag", "chord"]
Status = Literal["ready", "playing", "won", "lost"]
MineSampler = Callable[[Sequence[int], int], Iterable[int]]

COVERED = -2
FLAGGED = -3
MINE = -1
EXPLODED = -4
INCORRECT_FLAG = -5
MAX_CELLS = 16 * 30


@dataclass(frozen=True, slots=True)
class Difficulty:
    id: DifficultyId
    name: str
    rows: int
    cols: int
    mine_count: int
    multiplier: int

    @property
    def size(self) -> int:
        return self.rows * self.cols


DIFFICULTIES: Mapping[str, Difficulty] = MappingProxyType({
    "beginner": Difficulty("beginner", "Beginner", 9, 9, 10, 1),
    "intermediate": Difficulty("intermediate", "Intermediate", 16, 16, 40, 2),
    "expert": Difficulty("expert", "Expert", 16, 30, 99, 3),
})


@dataclass(slots=True)
class Game:
    difficulty: Difficulty
    status: Status = "ready"
    revision: int = 0
    mines: frozenset[int] | None = None
    numbers: tuple[int, ...] | None = None
    revealed: set[int] = field(default_factory=set)
    flags: set[int] = field(default_factory=set)
    exploded: int | None = None
    started_at: float | None = None
    finished_at: float | None = None


def difficulties_metadata() -> list[dict[str, Any]]:
    """Return fresh, public difficulty records, not mutable engine objects."""
    return [
        {
            "id": spec.id,
            "name": spec.name,
            "rows": spec.rows,
            "cols": spec.cols,
            "mineCount": spec.mine_count,
            "multiplier": spec.multiplier,
        }
        for spec in DIFFICULTIES.values()
    ]


def create_game(difficulty: str = "beginner") -> Game:
    if type(difficulty) is not str or difficulty not in DIFFICULTIES:
        raise ValueError("difficulty must be beginner, intermediate, or expert.")
    return Game(difficulty=DIFFICULTIES[difficulty])


def neighbors(cell: int, rows: int, cols: int) -> tuple[int, ...]:
    """Return adjacent cell indices in row-major order, without edge wrapping."""
    row, col = divmod(cell, cols)
    return tuple(
        y * cols + x
        for y in range(max(0, row - 1), min(rows, row + 2))
        for x in range(max(0, col - 1), min(cols, col + 2))
        if y != row or x != col
    )


def _plant_mines(game: Game, first_cell: int, sample: MineSampler) -> None:
    spec = game.difficulty
    protected = {first_cell, *neighbors(first_cell, spec.rows, spec.cols)}
    candidates = [cell for cell in range(spec.size) if cell not in protected]
    chosen = list(sample(candidates, spec.mine_count))
    # Fail before changing the game if a replacement random source violates the
    # contract. Production uses SystemRandom.sample, never a predictable seed.
    if (
        len(chosen) != spec.mine_count
        or any(type(cell) is not int or cell not in candidates for cell in chosen)
        or len(set(chosen)) != spec.mine_count
    ):
        raise ValueError("The private mine sampler returned an invalid layout.")
    mines = frozenset(chosen)
    numbers = tuple(
        sum(adjacent in mines for adjacent in neighbors(cell, spec.rows, spec.cols))
        for cell in range(spec.size)
    )
    game.mines, game.numbers = mines, numbers


def _flood(game: Game, targets: Iterable[int]) -> None:
    """Reveal zero regions and their numbered borders, respecting every flag."""
    assert game.mines is not None and game.numbers is not None
    pending = deque(targets)
    while pending:
        cell = pending.popleft()
        if cell in game.revealed or cell in game.flags or cell in game.mines:
            continue
        game.revealed.add(cell)
        if game.numbers[cell] == 0:
            pending.extend(neighbors(cell, game.difficulty.rows, game.difficulty.cols))


def _lose(game: Game, mine: int, now: float) -> None:
    game.status = "lost"
    game.exploded = mine
    game.finished_at = now


def visible_cells(game: Game) -> list[int]:
    """Encode a fresh public board, never revealing live covered-cell contents.

    At loss, correct flags remain flags, wrong flags become -5, unflagged mines
    become -1, and the triggering mine becomes -4. At victory all mines are
    auto-flagged. Safe cells not reached before loss remain covered.
    """
    cells: list[int] = []
    for cell in range(game.difficulty.size):
        if cell == game.exploded:
            value = EXPLODED
        elif cell in game.flags:
            value = (
                INCORRECT_FLAG
                if game.status == "lost" and cell not in (game.mines or ())
                else FLAGGED
            )
        elif game.status == "lost" and cell in (game.mines or ()):
            value = MINE
        elif cell in game.revealed:
            assert game.numbers is not None
            value = game.numbers[cell]
        else:
            value = COVERED
        cells.append(value)
    return cells


def apply_move(game: Game, action: str, cell: int, now: float, sample: MineSampler) -> list[int]:
    """Apply one validated action and return changed public cell indices.

    Every legal nonterminal request consumes one revision, even a no-op. A
    reveal on a flag is a no-op, so it neither generates mines nor starts time.
    Chords require exactly the adjacent number of flags; a wrong matching set
    loses atomically, rather than winning from a lucky traversal order.
    """
    if type(action) is not str or action not in ("reveal", "flag", "chord"):
        raise ValueError("action must be reveal, flag, or chord.")
    if type(cell) is not int or not 0 <= cell < game.difficulty.size:
        raise ValueError("cell must be an integer index inside this board.")
    if game.status in ("won", "lost"):
        return []

    before = visible_cells(game)
    if action == "flag":
        if cell in game.flags:
            game.flags.remove(cell)
        elif cell not in game.revealed and len(game.flags) < game.difficulty.mine_count:
            game.flags.add(cell)
    elif action == "reveal":
        if cell not in game.flags and cell not in game.revealed:
            if game.mines is None:
                _plant_mines(game, cell, sample)
                game.started_at = now
                game.status = "playing"
            if cell in game.mines:
                _lose(game, cell, now)
            else:
                _flood(game, (cell,))
    elif cell in game.revealed:
        assert game.numbers is not None and game.mines is not None
        adjacent = neighbors(cell, game.difficulty.rows, game.difficulty.cols)
        if sum(index in game.flags for index in adjacent) == game.numbers[cell]:
            targets = [index for index in adjacent if index not in game.flags and index not in game.revealed]
            hit = next((index for index in targets if index in game.mines), None)
            if hit is not None:
                _lose(game, hit, now)
            else:
                _flood(game, targets)

    if game.status == "playing" and len(game.revealed) == game.difficulty.size - game.difficulty.mine_count:
        game.status = "won"
        game.finished_at = now
        game.flags = set(game.mines or ())
    game.revision += 1
    return [index for index, (old, new) in enumerate(zip(before, visible_cells(game))) if old != new]


def elapsed_ms(game: Game, now: float) -> int:
    if game.started_at is None:
        return 0
    end = game.finished_at if game.finished_at is not None else now
    return max(0, math.floor((end - game.started_at) * 1000))


def score(game: Game, now: float) -> int:
    multiplier = game.difficulty.multiplier
    points = len(game.revealed) * 10 * multiplier
    if game.status == "won":
        points += (1000 + max(0, 1000 - elapsed_ms(game, now) // 1000)) * multiplier
    return points


def snapshot(game: Game, run_id: str, now: float, changed: Sequence[int] = ()) -> dict[str, Any]:
    """Return only public game data, with independent arrays on every call."""
    return {
        "runId": run_id,
        "revision": game.revision,
        "difficulty": game.difficulty.id,
        "rows": game.difficulty.rows,
        "cols": game.difficulty.cols,
        "mineCount": game.difficulty.mine_count,
        "status": game.status,
        "cells": visible_cells(game),
        "flagsUsed": len(game.flags),
        "revealedCount": len(game.revealed),
        "score": score(game, now),
        "elapsedMs": elapsed_ms(game, now),
        "changed": list(changed),
    }
