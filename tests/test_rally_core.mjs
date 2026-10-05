import assert from 'node:assert/strict';
import test from 'node:test';
import {
  CONSTANTS as C, createGame, advance, truncDiv, validateReplayShape, simulateReplay,
} from '../src/catalog_app/tools/rally_pong/frontend/core.js';

const noEvent = { playerHit: false, aiHit: false, wall: false, goal: null, ended: false };
const bound = (value, limit) => Math.min(limit, Math.max(-limit, value));
const live = (overrides = {}) => Object.assign(createGame(0), {
  serveTicks: 0, vx: 100, vy: 0, aiThinkTicks: 1000,
}, overrides);

// Controllers are test fixtures, not shipped UI or an automated score poster.
function play(seed, mode = 'idle') {
  const game = createGame(seed);
  const initial = structuredClone(game);
  const events = [];
  const checkpoints = [];
  while (game.alive) {
    let target = game.target;
    if (mode === 'idle') target = 0;
    else if (mode === 'follow' || game.steps % 12 === 0) {
      let desired = game.ballY;
      if (mode === 'aim' && game.vx < 0) desired += game.aiY > 0 ? 950 : -950;
      target = bound(truncDiv(desired * 1000, C.paddleLimit), 1000);
    }
    const event = advance(game, target);
    if (event.playerHit || event.aiHit || event.wall || event.goal || event.ended) {
      events.push({ tick: game.steps, ...event });
    }
    if (game.steps % 137 === 0 || !game.alive) {
      const { inputs, ...snapshot } = game;
      checkpoints.push({ ...snapshot });
    }
  }
  return { seed, mode, initial, game, events, checkpoints, durationMs: Math.ceil(game.steps * 1000 / C.tickRate) };
}

if (process.argv.includes('--fixtures')) {
  // Python compares complete authoritative games, all events and checkpoints.
  // Emit JSON only here so unittest can consume it without parsing Node TAP.
  console.log(JSON.stringify({
    constants: C,
    fixtures: [[0, 'idle'], [0xffffffff, 'idle'], [0, 'reactive'], [1, 'reactive'],
      [0x12345678, 'reactive'], [0x12345678, 'aim'], [7, 'follow']].map(([seed, mode]) => play(seed, mode)),
  }));
} else {
  test('constant and initial state contract is fixed and independent', () => {
    assert.equal(C.tickRate, 120);
    assert.equal(C.maxSteps, 14400);
    assert.equal(C.width, 20000);
    assert.equal(C.height, 12000);
    assert.equal(C.paddleLimit, C.halfHeight - C.paddleHalf);
    assert.ok(Object.isFrozen(C));
    assert.deepEqual(createGame(0), {
      steps: 0, rng: 0, target: 0, playerY: 0, aiY: 0, ballX: 0, ballY: 0,
      vx: 0, vy: 0, playerGoals: 0, aiGoals: 0, score: 0, hits: 0,
      rally: 0, bestRally: 0, alive: true, won: false, serveTicks: 90,
      inputs: [], ballSpeed: 100, serveDirection: -1, aiTarget: 0,
      aiThinkTicks: 0, endedByLimit: false,
    });
    const first = createGame(0);
    first.inputs.push([1, 2]);
    assert.deepEqual(createGame(0).inputs, []);
    assert.deepEqual(createGame(-1), createGame(0xffffffff));
    assert.deepEqual(createGame(2 ** 32), createGame(0));
    assert.deepEqual(createGame(2 ** 32 + 1), createGame(1));
  });

  test('truncation is towards zero for both signs and produces no negative zero', () => {
    for (const [n, d, result] of [[9, 4, 2], [-9, 4, -2], [9, -4, -2], [-9, -4, 2], [-1, 4, 0]]) {
      assert.equal(truncDiv(n, d), result);
      assert.equal(Object.is(truncDiv(n, d), -0), false);
    }
  });

  test('initial 90 tick serve counts time and movement starts on tick91', () => {
    const game = createGame(0);
    for (let tick = 1; tick < 90; tick += 1) {
      assert.deepEqual(advance(game), noEvent);
      assert.equal(game.vx, 0);
      assert.equal(game.ballX, 0);
      assert.equal(game.rng, 0);
    }
    advance(game);
    assert.equal(game.steps, 90);
    assert.equal(game.serveTicks, 0);
    assert.equal(game.rng, 1013904223);
    assert.ok(game.vx < 0 && Math.abs(game.vy) >= 18);
    assert.equal(game.ballX, 0);
    const { vx, vy } = game;
    advance(game);
    assert.equal(game.ballX, vx);
    assert.equal(game.ballY, vy);
  });

  test('target inputs are bounded, rate limited and recorded only on change', () => {
    const game = createGame(0);
    advance(game, -1000);
    assert.equal(game.playerY, -250);
    advance(game, -1000);
    assert.deepEqual(game.inputs, [[1, -1000]]);
    for (let i = 0; i < 38; i += 1) advance(game, -1000);
    assert.equal(game.playerY, -4900);
    for (let i = 0; i < 40; i += 1) advance(game, 1000);
    assert.equal(game.playerY, 4900);
    assert.deepEqual(game.inputs, [[1, -1000], [41, 1000]]);
    const tiny = createGame(0);
    advance(tiny, -1);
    assert.equal(tiny.playerY, -4);
  });

  test('bad live targets cannot corrupt or enter canonical input history', () => {
    for (const target of [-1001, 1001, NaN, Infinity, -Infinity, 1.1, true, false, '1', null, {}]) {
      const game = createGame(0);
      advance(game, target);
      assert.equal(game.target, 0);
      assert.equal(game.playerY, 0);
      assert.deepEqual(game.inputs, []);
    }
  });

  test('center player return sweeps paddle plane, reflects x and scores ten', () => {
    const game = live({ ballX: -8800, vx: -100 });
    assert.deepEqual(advance(game), { ...noEvent, playerHit: true });
    assert.equal(game.ballX, -8740);
    assert.equal(game.vx, 105);
    assert.equal(game.vy, 0);
    assert.equal(game.score, 10);
    assert.equal(game.hits, 1);
    assert.equal(game.rally, 1);
    assert.equal(game.bestRally, 1);
    assert.equal(game.ballSpeed, 105);
  });

  test('AI contacts extend rally but do not award player return points', () => {
    const game = live({ ballX: 8800 });
    assert.deepEqual(advance(game), { ...noEvent, aiHit: true });
    assert.equal(game.vx, -105);
    assert.equal(game.score, 0);
    assert.equal(game.hits, 0);
    assert.equal(game.rally, 1);
  });

  test('paddle radius is inclusive, contact is swept, and missed paddles cannot hit from behind', () => {
    for (const [y, expected] of [[1280, true], [1281, false], [-1280, true], [-1281, false]]) {
      const game = live({ ballX: -8800, ballY: y, vx: -100 });
      assert.equal(advance(game).playerHit, expected);
    }
    const swept = live({ ballX: -8800, ballY: 1250, vx: -100, vy: 100 });
    assert.equal(advance(swept).playerHit, true); // contact1270, final1350
    assert.equal(advance(live({ ballX: -8900, vx: -100 })).playerHit, false);
    assert.equal(advance(live({ ballX: -8900, vx: 100 })).playerHit, false);
  });

  test('edge angle and moving paddle spin use exact integer deflection', () => {
    for (const sign of [-1, 1]) {
      const game = live({ ballX: -8800, ballY: 1100 * sign, vx: -100 });
      advance(game);
      assert.equal(game.vy, 78 * sign);
      assert.equal(game.vx, 70);
    }
    const stationary = live({ ballX: -8800, vx: -100, playerY: 245, target: 50 });
    const moving = live({ ballX: -8800, vx: -100, playerY: -5, target: 50 });
    advance(stationary);
    advance(moving);
    assert.equal(stationary.playerY, moving.playerY);
    assert.equal(stationary.vy, -17);
    assert.equal(moving.vy, 9);
    const capped = live({ ballX: -8800, ballY: 1350, vx: -100 });
    advance(capped, 1000);
    assert.equal(capped.vy, 89);
    assert.equal(capped.vx, 55);
  });

  test('wall bounces reflect overshoot and corner contact remains in court', () => {
    for (const sign of [-1, 1]) {
      const game = live({ ballY: sign * 5800, vy: sign * 80 });
      assert.equal(advance(game).wall, true);
      assert.equal(game.ballY, sign * 5760);
      assert.equal(game.vy, -sign * 80);
    }
    const corner = live({ ballX: -8800, ballY: 5810, vx: -100, vy: 50, playerY: 4900, target: 1000 });
    const event = advance(corner);
    assert.equal(event.wall, true);
    assert.equal(event.playerHit, true);
    assert.ok(Math.abs(corner.ballY) <= 5820);
  });

  test('ball speed is capped and AI movement cannot exceed65 units per tick', () => {
    const game = live({ ballX: -8800, ballY: 1000, vx: -180, rally: 300, aiTarget: 4900 });
    const before = game.aiY;
    advance(game);
    assert.equal(game.ballSpeed, 180);
    assert.ok(game.vx * game.vx + game.vy * game.vy <= 180 * 180);
    assert.ok(Math.abs(game.vx) >= 90);
    assert.equal(game.aiY - before, 65);
  });

  test('a goal awards100, resets rally and schedules a90 tick serve towards conceding side', () => {
    const game = live({ ballX: 10170, rally: 4, bestRally: 4 });
    assert.deepEqual(advance(game), { ...noEvent, goal: 'player' });
    assert.equal(game.playerGoals, 1);
    assert.equal(game.score, 100);
    assert.equal(game.rally, 0);
    assert.equal(game.bestRally, 4);
    assert.equal(game.serveTicks, 90);
    assert.equal(game.ballX, 0);
    for (let i = 0; i < 90; i += 1) advance(game);
    assert.ok(game.vx > 0);
    assert.equal(game.ballX, 0);
    const loss = live({ ballX: -10170, vx: -100, score: 40 });
    assert.equal(advance(loss).goal, 'ai');
    assert.equal(loss.aiGoals, 1);
    assert.equal(loss.score, 40);
    assert.equal(loss.serveDirection, -1);
  });

  test('seventh player goal adds250 exactly once and terminal steps are immutable', () => {
    const game = live({ ballX: 10170, playerGoals: 6, score: 600 });
    assert.deepEqual(advance(game), { ...noEvent, goal: 'player', ended: true });
    assert.equal(game.score, 950);
    assert.equal(game.won, true);
    assert.equal(game.alive, false);
    assert.equal(game.serveTicks, 0);
    assert.equal(game.endedByLimit, false);
    const ended = structuredClone(game);
    assert.deepEqual(advance(game, -1000), { ...noEvent, ended: true });
    assert.deepEqual(game, ended);
    const loss = live({ ballX: -10170, vx: -100, aiGoals: 6 });
    assert.equal(advance(loss).ended, true);
    assert.equal(loss.won, false);
    assert.equal(loss.score, 0);
  });

  test('timeout terminates on14400, preserves points and never awards a leading bonus', () => {
    const game = live({ steps: 14399, playerGoals: 6, aiGoals: 1, score: 750 });
    assert.equal(advance(game).ended, true);
    assert.equal(game.steps, 14400);
    assert.equal(game.score, 750);
    assert.equal(game.won, false);
    assert.equal(game.endedByLimit, true);
    const seventh = live({ steps: 14399, ballX: 10170, playerGoals: 6, score: 600 });
    advance(seventh);
    assert.equal(seventh.won, true); // seventh goal wins even on final tick
    assert.equal(seventh.endedByLimit, false);
  });

  test('canonical validation rejects malformed, redundant, duplicate and out-of-range input', () => {
    const invalid = [
      [0, []], [14401, []], [true, []], [1.1, []], [20, null], [20, {}],
      [20, [[0, 1]]], [20, [[21, 1]]], [20, [[1, 0]]],
      [20, [[1, 3], [1, 4]]], [20, [[2, 3], [1, 4]]], [20, [[1, 3], [2, 3]]],
      [20, [[1, -1001]]], [20, [[1, 1001]]], [20, [[true, 1]]], [20, [[1, false]]],
      [20, [[1, 1.1]]], [20, [[1]]], [20, [[1, 1, 1]]], [1, [[1, 1], [2, 2]]],
    ];
    for (const [steps, inputs] of invalid) assert.throws(() => validateReplayShape(steps, inputs));
    validateReplayShape(20, [[1, -1000], [2, 1000], [20, 0]]);
    const maximum = Array.from({ length: C.maxSteps }, (_, index) => [index + 1, index % 2 ? -1 : 1]);
    validateReplayShape(C.maxSteps, maximum);
  });

  test('seed0 idle golden replay ends on exact tick1387 and rounds duration upwards', () => {
    const result = simulateReplay(0, 1387, []);
    assert.equal(result.durationMs, 11559);
    assert.equal(result.game.aiGoals, 7);
    assert.equal(result.game.playerGoals, 0);
    assert.equal(result.game.score, 0);
    for (const steps of [1, 1386, 1388, 14400]) assert.throws(() => simulateReplay(0, steps, []));
  });

  test('simple100ms reaction fixture wins and canonical replay exactly reproduces it', () => {
    const fixture = play(0, 'reactive');
    assert.equal(fixture.game.steps, 11207);
    assert.equal(fixture.game.won, true);
    assert.equal(fixture.game.score, 1270);
    assert.equal(fixture.game.hits, 32);
    assert.equal(fixture.game.playerGoals, 7);
    assert.deepEqual(simulateReplay(0, fixture.game.steps, fixture.game.inputs).game, fixture.game);
    assert.deepEqual(play(0, 'reactive'), fixture);
  });

  test('edge aiming produces an attainable51.5 second win against the seeded AI', () => {
    const fixture = play(0, 'aim');
    assert.equal(fixture.game.steps, 6180);
    assert.equal(fixture.game.won, true);
    assert.equal(fixture.game.playerGoals, 7);
    assert.equal(fixture.game.aiGoals, 1);
    assert.equal(fixture.game.hits, 13);
    assert.equal(fixture.game.score, 1080);
    assert.deepEqual(simulateReplay(0, fixture.game.steps, fixture.game.inputs).game, fixture.game);
  });

  test('timeout fixture is accepted only at exact maxSteps with no win bonus', () => {
    const fixture = play(7, 'follow');
    assert.equal(fixture.game.steps, C.maxSteps);
    assert.equal(fixture.game.endedByLimit, true);
    assert.equal(fixture.game.won, false);
    assert.deepEqual(simulateReplay(7, C.maxSteps, fixture.game.inputs).game, fixture.game);
    assert.equal(fixture.game.score, fixture.game.hits * 10 + fixture.game.playerGoals * 100);
  });

  test('seeded matches keep every value integer and court, motion and score bounds hold', () => {
    for (let seed = 0; seed < 12; seed += 1) {
      const game = createGame(seed * 123456789);
      let inputRng = seed >>> 0;
      let previousPlayer = 0;
      let previousAI = 0;
      while (game.alive) {
        inputRng = (Math.imul(1664525, inputRng) + 1013904223) >>> 0;
        const target = inputRng % 2001 - 1000;
        advance(game, target);
        for (const value of Object.values(game)) {
          if (typeof value === 'number') assert.ok(Number.isSafeInteger(value));
        }
        assert.ok(Math.abs(game.playerY) <= 4900);
        assert.ok(Math.abs(game.aiY) <= 4900);
        assert.ok(Math.abs(game.playerY - previousPlayer) <= 250);
        assert.ok(Math.abs(game.aiY - previousAI) <= 65);
        assert.ok(Math.abs(game.ballY) <= 5820);
        assert.ok(Math.abs(game.ballX) <= 10180);
        assert.ok(Math.abs(game.vx) <= 180 && Math.abs(game.vy) <= 180);
        assert.equal(game.score, game.hits * 10 + game.playerGoals * 100 + (game.won ? 250 : 0));
        previousPlayer = game.playerY;
        previousAI = game.aiY;
      }
      assert.ok(game.steps <= C.maxSteps);
      assert.ok(game.inputs.length <= C.maxInputs);
      assert.deepEqual(simulateReplay(seed * 123456789, game.steps, game.inputs).game, game);
    }
  });
}
