// Rally — After Hours deterministic 120 Hz physics. Mirror engine.py exactly.
// No DOM, time, random sources, network, sound or retained state in this module.
export const CONSTANTS = Object.freeze({
  version: 1,
  width: 20000,
  height: 12000,
  halfWidth: 10000,
  halfHeight: 6000,
  paddleX: 9000,
  paddleHalf: 1100,
  ballRadius: 180,
  paddleLimit: 4900,
  targetMax: 1000,
  tickRate: 120,
  maxSteps: 14400,
  maxInputs: 14400,
  playerSpeed: 250,
  aiSpeed: 65,
  serveTicks: 90,
  targetGoals: 7,
  initialBallSpeed: 100,
  maxBallSpeed: 180,
  ballSpeedIncrement: 5,
  pointsPerHit: 10,
  pointsPerGoal: 100,
  winBonus: 250,
});

const C = CONSTANTS;
const BALL_LIMIT = C.halfHeight - C.ballRadius;
const PADDLE_FACE = C.paddleX - C.ballRadius;
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
const moveTowards = (position, target, speed) => position + clamp(target - position, -speed, speed);

// All operands are exact safe integers. Normalize negative zero to integer zero.
export function truncDiv(numerator, denominator) {
  return Math.trunc(numerator / denominator) || 0;
}

function integerSqrt(value) {
  // Integer-only binary search, not floating-point sqrt/trigonometry. All game
  // magnitudes are <=180, and therefore squares/intermediates are exact in JS.
  let low = 0;
  let high = C.maxBallSpeed;
  let result = 0;
  while (low <= high) {
    const middle = truncDiv(low + high, 2);
    if (middle * middle <= value) {
      result = middle;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  return result;
}

function random(game) {
  game.rng = (Math.imul(1664525, game.rng) + 1013904223) >>> 0;
  return game.rng;
}

function reflectY(y) {
  // A legal tick travels <=180 units: at most one wall crossing per tick.
  if (y > BALL_LIMIT) return 2 * BALL_LIMIT - y;
  if (y < -BALL_LIMIT) return -2 * BALL_LIMIT - y;
  return y;
}

export function createGame(seed) {
  return {
    steps: 0,
    rng: seed >>> 0,
    target: 0,
    playerY: 0,
    aiY: 0,
    ballX: 0,
    ballY: 0,
    vx: 0,
    vy: 0,
    playerGoals: 0,
    aiGoals: 0,
    score: 0,
    hits: 0,
    rally: 0,
    bestRally: 0,
    alive: true,
    won: false,
    serveTicks: C.serveTicks,
    inputs: [],
    ballSpeed: C.initialBallSpeed,
    serveDirection: -1,
    aiTarget: 0,
    aiThinkTicks: 0,
    endedByLimit: false,
  };
}

function launch(game) {
  let vertical = random(game) % 91 - 45;
  if (Math.abs(vertical) < 18) vertical = vertical < 0 ? -18 : 18;
  game.vy = vertical;
  game.vx = game.serveDirection * integerSqrt(C.initialBallSpeed ** 2 - vertical ** 2);
}

function moveAI(game) {
  const before = game.aiY;
  if (game.serveTicks > 0) {
    game.aiTarget = 0;
    game.aiThinkTicks = 0;
  } else if (game.aiThinkTicks <= 0) {
    // A bounded, reactive opponent: seeded error +/-700 and 14..28 tick thinking.
    const error = random(game) % 1401 - 700;
    const observed = game.vx > 0 ? game.ballY : truncDiv(game.ballY, 2);
    game.aiTarget = clamp(observed + error, -C.paddleLimit, C.paddleLimit);
    game.aiThinkTicks = 14 + random(game) % 15;
  } else {
    game.aiThinkTicks -= 1;
  }
  game.aiY = moveTowards(before, game.aiTarget, C.aiSpeed);
  return game.aiY - before;
}

function returnBall(game, side, contactY, motion) {
  const paddleY = side === 'player' ? game.playerY : game.aiY;
  game.rally += 1;
  game.bestRally = Math.max(game.bestRally, game.rally);
  const speed = Math.min(C.maxBallSpeed, C.initialBallSpeed + C.ballSpeedIncrement * game.rally);
  game.ballSpeed = speed;
  const offset = clamp(contactY - paddleY, -C.paddleHalf, C.paddleHalf);
  let vertical = truncDiv(offset * speed * 75, C.paddleHalf * 100);
  vertical += truncDiv(motion * speed, 1000);
  const cap = truncDiv(speed * 85, 100);
  game.vy = clamp(vertical, -cap, cap);
  const horizontal = integerSqrt(speed * speed - game.vy * game.vy);
  game.vx = side === 'player' ? horizontal : -horizontal;
  if (side === 'player') {
    game.hits += 1;
    game.score += C.pointsPerHit;
  }
}

function goal(game, side) {
  const key = side === 'player' ? 'playerGoals' : 'aiGoals';
  game[key] += 1;
  if (side === 'player') game.score += C.pointsPerGoal;
  game.rally = 0;
  game.ballSpeed = C.initialBallSpeed;
  game.ballX = game.ballY = game.vx = game.vy = 0;
  game.aiThinkTicks = 0;
  game.serveDirection = side === 'player' ? 1 : -1;
  if (game[key] === C.targetGoals) {
    game.alive = false;
    game.won = side === 'player';
    game.serveTicks = 0;
    if (game.won) game.score += C.winBonus;
  } else {
    game.serveTicks = C.serveTicks;
  }
}

// Mutates game and returns {playerHit, aiHit, wall, goal, ended}. Inputs are
// canonical 1-based tick changes. hits=player returns; rally/bestRally=both sides.
// Bad live targets are ignored. Replay validation rejects them instead.
export function advance(game, target = game.target) {
  const event = { playerHit: false, aiHit: false, wall: false, goal: null, ended: !game.alive };
  if (!game.alive) return event;
  game.steps += 1;
  if (Number.isInteger(target) && target >= -C.targetMax && target <= C.targetMax && target !== game.target) {
    game.target = target;
    game.inputs.push([game.steps, target]);
  }
  const playerBefore = game.playerY;
  const desired = truncDiv(game.target * C.paddleLimit, C.targetMax);
  game.playerY = moveTowards(playerBefore, desired, C.playerSpeed);
  const playerMotion = game.playerY - playerBefore;
  const aiMotion = moveAI(game);

  if (game.serveTicks > 0) {
    game.serveTicks -= 1;
    if (game.serveTicks === 0) launch(game);
  } else {
    const oldX = game.ballX;
    const oldY = game.ballY;
    const oldVX = game.vx;
    const oldVY = game.vy;
    game.ballX += oldVX;
    const rawY = oldY + oldVY;
    game.ballY = reflectY(rawY);
    if (rawY > BALL_LIMIT || rawY < -BALL_LIMIT) {
      game.vy = -oldVY;
      event.wall = true;
    }
    let side = null;
    let plane;
    let paddleY;
    let motion;
    if (oldVX < 0 && oldX >= -PADDLE_FACE && game.ballX <= -PADDLE_FACE) {
      side = 'player'; plane = -PADDLE_FACE; paddleY = game.playerY; motion = playerMotion;
    } else if (oldVX > 0 && oldX <= PADDLE_FACE && game.ballX >= PADDLE_FACE) {
      side = 'ai'; plane = PADDLE_FACE; paddleY = game.aiY; motion = aiMotion;
    }
    if (side !== null) {
      const contactY = reflectY(oldY + truncDiv(oldVY * (plane - oldX), oldVX));
      if (Math.abs(contactY - paddleY) <= C.paddleHalf + C.ballRadius) {
        game.ballX = 2 * plane - game.ballX;
        returnBall(game, side, contactY, motion);
        event[side === 'player' ? 'playerHit' : 'aiHit'] = true;
      }
    }
    if (game.ballX < -C.halfWidth - C.ballRadius) {
      event.goal = 'ai';
      goal(game, 'ai');
    } else if (game.ballX > C.halfWidth + C.ballRadius) {
      event.goal = 'player';
      goal(game, 'player');
    }
  }
  if (game.alive && game.steps >= C.maxSteps) {
    game.alive = false;
    game.won = false;
    game.endedByLimit = true;
  }
  event.ended = !game.alive;
  return event;
}

export function validateReplayShape(steps, inputs) {
  if (!Number.isInteger(steps) || steps < 1 || steps > C.maxSteps) {
    throw new RangeError(`steps must be an integer from 1 to ${C.maxSteps}.`);
  }
  if (!Array.isArray(inputs) || inputs.length > Math.min(C.maxInputs, steps)) {
    throw new RangeError(`inputs must be a list of at most ${C.maxInputs} target changes.`);
  }
  let lastTick = 0;
  let previousTarget = 0;
  for (const change of inputs) {
    if (!Array.isArray(change) || change.length !== 2) {
      throw new RangeError('Each input must contain exactly a tick and a target.');
    }
    const [tick, target] = change;
    if (!Number.isInteger(tick) || tick <= lastTick || tick > steps) {
      throw new RangeError('Input ticks must be unique, increasing integers within the run.');
    }
    if (!Number.isInteger(target) || target < -C.targetMax || target > C.targetMax) {
      throw new RangeError('Input targets must be integers from -1000 to 1000.');
    }
    if (target === previousTarget) {
      throw new RangeError('Record only target changes, not redundant targets.');
    }
    lastTick = tick;
    previousTarget = target;
  }
}

export function simulateReplay(seed, steps, inputs) {
  validateReplayShape(steps, inputs);
  const game = createGame(seed);
  let index = 0;
  for (let tick = 1; tick <= steps; tick += 1) {
    const target = index < inputs.length && inputs[index][0] === tick ? inputs[index++][1] : game.target;
    advance(game, target);
    if (!game.alive && tick !== steps) throw new RangeError('A replay cannot contain ticks after the match ends.');
  }
  if (game.alive) throw new RangeError('The final tick must be the seventh goal or the 14400-tick time limit.');
  return { game, durationMs: truncDiv(steps * 1000 + C.tickRate - 1, C.tickRate) };
}
