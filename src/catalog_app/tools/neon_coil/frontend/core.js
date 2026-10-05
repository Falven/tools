// Deterministic, side-effect-free Snake rules shared with the replay verifier.
// No DOM, clocks, storage, random sources, or network belong in this module.
export const WIDTH = 24;
export const HEIGHT = 18;
export const DIRS = [[0, -1], [1, 0], [0, 1], [-1, 0]];
export const RIGHT = 1;

export function stepMs(foods) {
  return Math.max(70, 150 - Math.floor(foods / 5) * 8);
}

function placeFood(game) {
  const occupied = new Uint8Array(WIDTH * HEIGHT);
  for (let i = 0; i < game.body.length; i += 1) {
    const cell = game.body[i];
    occupied[cell[1] * WIDTH + cell[0]] = 1;
  }
  // Exactly one LCG update per placement, including the initial placement.
  game.rng = (1664525 * game.rng + 1013904223) >>> 0;
  let emptyIndex = game.rng % (WIDTH * HEIGHT - game.body.length);
  for (let index = 0; index < occupied.length; index += 1) {
    if (!occupied[index] && emptyIndex-- === 0) {
      game.food = [index % WIDTH, Math.floor(index / WIDTH)];
      return;
    }
  }
}

export function createGame(seed) {
  const game = {
    body: [[8, 9], [7, 9], [6, 9], [5, 9], [4, 9]],
    direction: RIGHT,
    food: null,
    rng: seed >>> 0,
    score: 0,
    foods: 0,
    steps: 0,
    alive: true,
    won: false,
    turns: [],
  };
  placeFood(game);
  return game;
}

export function advance(game, direction = game.direction) {
  if (!game.alive) {
    return { ate: false, dead: !game.won, won: game.won };
  }

  game.steps += 1;
  // Invalid/reversing input is ignored; only committed changes enter a replay.
  if (Number.isInteger(direction) && direction >= 0 && direction < DIRS.length
      && direction !== game.direction && direction !== (game.direction + 2) % 4) {
    game.direction = direction;
    game.turns.push([game.steps, direction]);
  }

  const delta = DIRS[game.direction];
  const x = game.body[0][0] + delta[0];
  const y = game.body[0][1] + delta[1];
  const ate = game.food !== null && x === game.food[0] && y === game.food[1];
  let collision = x < 0 || y < 0 || x >= WIDTH || y >= HEIGHT;
  // On an ordinary move the last cell vacates before the head enters it.
  const occupiedLength = game.body.length - (ate ? 0 : 1);
  for (let index = 0; !collision && index < occupiedLength; index += 1) {
    collision = game.body[index][0] === x && game.body[index][1] === y;
  }
  if (collision) {
    game.alive = false;
    return { ate: false, dead: true, won: false };
  }

  if (ate) {
    game.body.unshift([x, y]);
    game.foods += 1;
    game.score += 100;
    if (game.body.length === WIDTH * HEIGHT) {
      game.food = null;
      game.won = true;
      game.alive = false;
    } else {
      placeFood(game);
    }
  } else {
    // Reuse the vacated tail cell instead of allocating one per animation tick.
    const head = game.body.pop();
    head[0] = x;
    head[1] = y;
    game.body.unshift(head);
  }
  return { ate, dead: false, won: game.won };
}
