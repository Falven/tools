// ISOLATED QA FIXTURE: synthetic identity, synthetic mines and synthetic scores.
// Never imported by production, registered with MCP, or served as an App resource.
// Generate: node tests/fixtures/minesweeper_ui_host.mjs
// Self-test (no bundle required): node tests/fixtures/minesweeper_ui_host.mjs --self-test
// Open artifacts/minesweeper-qa.html directly; no web server is started.
//
// Browser controls on window.fixture:
//   app().snapshot() / visible()     Production's read-only VISIBLE diagnostics.
//   mines(runId?)                   Private synthetic mine indices, host-only.
//   failNextMove = true             Lose the response AFTER committing a move.
//   forceStaleNextMove = true       Commit a harmless competing no-op first.
//   delayMove = true; releaseMoves() Hold already-processed responses/errors.
//   pending()                      Number of held move responses.
//   restartServer()                Clear games/scores/change epoch and player ID.
//                                  Keeps held old responses for race testing!
//   seedScores() / resetScores()    Optional synthetic scores; default is EMPTY.
//   serverMove(action, cell, rev?)  Change only the synthetic server for resync QA.
//   click(id), cell(index, action), key(key, index?), advanceTime(ms), result()
// After restart/reset/seed, use the App's Refresh button to observe the new hub.

import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const outputPath = resolve(root, 'artifacts/minesweeper-qa.html');

// This function is self-contained so the exact same implementation runs in the
// generated browser host and the Node self-tests. It is NOT the real backend.
export function createFixtureServer(clock = () => performance.now()) {
  const levels = {
    beginner: { name: 'Beginner', rows: 9, cols: 9, mineCount: 10, multiplier: 1 },
    intermediate: { name: 'Intermediate', rows: 16, cols: 16, mineCount: 40, multiplier: 2 },
    expert: { name: 'Expert', rows: 16, cols: 30, mineCount: 99, multiplier: 3 },
  };
  const runs = new Map(), players = new Map();
  let epochNumber = 1, serial = 0, achievement = 0;
  const copy = value => JSON.parse(JSON.stringify(value));
  const epoch = () => `qa-minesweeper-epoch-${epochNumber}`;
  const playerId = () => `qa-synthetic-player-${epochNumber}`;
  const callerName = 'QA Current User (synthetic)';
  const failure = (code, message, game) => ({ error: { code, message }, epoch: epoch(), ephemeral: true, ...(game ? { game } : {}) });
  const adjacent = (cell, rows, cols) => {
    const row = Math.floor(cell / cols), col = cell % cols, result = [];
    for (let y = Math.max(0, row - 1); y < Math.min(rows, row + 2); y++) {
      for (let x = Math.max(0, col - 1); x < Math.min(cols, col + 2); x++) {
        if (y !== row || x !== col) result.push(y * cols + x);
      }
    }
    return result;
  };
  const ordered = () => [...players.values()].sort((a, b) => b.score - a.score || a.elapsedMs - b.elapsedMs || a.achieved - b.achieved);
  const hub = () => ({
    epoch: epoch(), ephemeral: true, canPlay: true,
    player: { id: playerId(), name: callerName, bestScore: players.get(playerId())?.score || 0 },
    leaderboard: ordered().slice(0, 50).map((entry, index) => ({
      rank: index + 1, name: entry.name, score: entry.score, difficulty: entry.difficulty,
      elapsedMs: entry.elapsedMs, isYou: entry.id === playerId(),
    })),
    totalPlayers: players.size,
  });
  const elapsed = (game, now) => game.startedAt === null ? 0 : Math.max(0, Math.floor((game.finishedAt ?? now) - game.startedAt));
  const score = (game, now) => {
    const bonus = game.status === 'won' ? 1000 + Math.max(0, 1000 - Math.floor(elapsed(game, now) / 1000)) : 0;
    return (game.revealed.size * 10 + bonus) * game.spec.multiplier;
  };
  const visible = game => Array.from({ length: game.spec.rows * game.spec.cols }, (_, cell) => {
    if (cell === game.exploded) return -4;
    if (game.flags.has(cell)) return game.status === 'lost' && !game.mines.has(cell) ? -5 : -3;
    if (game.status === 'lost' && game.mines.has(cell)) return -1;
    return game.revealed.has(cell) ? game.numbers[cell] : -2;
  });
  const gameView = (game, now, changed = []) => ({
    runId: game.runId, revision: game.revision, difficulty: game.difficulty,
    rows: game.spec.rows, cols: game.spec.cols, mineCount: game.spec.mineCount,
    status: game.status, cells: visible(game), flagsUsed: game.flags.size,
    revealedCount: game.revealed.size, score: score(game, now), elapsedMs: elapsed(game, now), changed: [...changed],
  });
  const prune = now => { for (const [id, game] of runs) if (now >= game.expires) runs.delete(id); };
  const unavailable = () => failure('unavailable_run', 'Synthetic QA run unavailable. Start a new game.');
  function plant(game, first) {
    const { rows, cols, mineCount } = game.spec;
    const safe = new Set([first, ...adjacent(first, rows, cols)]);
    const candidates = Array.from({ length: rows * cols }, (_, index) => index).filter(index => !safe.has(index));
    // Deterministic private Fisher-Yates layout, never included in live views.
    let rng = game.seed >>> 0;
    for (let index = candidates.length - 1; index > 0; index--) {
      rng = (Math.imul(1664525, rng) + 1013904223) >>> 0;
      const other = rng % (index + 1);
      [candidates[index], candidates[other]] = [candidates[other], candidates[index]];
    }
    game.mines = new Set(candidates.slice(0, mineCount));
    game.numbers = Array.from({ length: rows * cols }, (_, cell) => adjacent(cell, rows, cols).filter(index => game.mines.has(index)).length);
  }
  function flood(game, targets) {
    const pending = [...targets];
    for (let head = 0; head < pending.length; head++) {
      const cell = pending[head];
      if (game.revealed.has(cell) || game.flags.has(cell) || game.mines.has(cell)) continue;
      game.revealed.add(cell);
      if (game.numbers[cell] === 0) pending.push(...adjacent(cell, game.spec.rows, game.spec.cols));
    }
  }
  function start(difficulty = 'beginner') {
    if (typeof difficulty !== 'string' || !Object.hasOwn(levels, difficulty)) return failure('invalid_difficulty', 'Choose beginner, intermediate, or expert.');
    const now = clock(); prune(now);
    const owned = [...runs.values()].filter(game => game.owner === playerId());
    const retire = owned.length >= 3 ? owned[0].runId : null;
    if (runs.size - Number(retire !== null) >= 1024) return failure('capacity', 'Synthetic QA run capacity reached.');
    if (retire) runs.delete(retire);
    const runId = `qa-minesweeper-run-${epochNumber}-${String(++serial).padStart(26, '0')}`;
    const game = {
      runId, owner: playerId(), difficulty, spec: levels[difficulty], seed: (0x4d535750 ^ serial) >>> 0,
      revision: 0, status: 'ready', issued: now, expires: now + 7200000,
      mines: null, numbers: null, revealed: new Set(), flags: new Set(), exploded: null,
      startedAt: null, finishedAt: null, lastRequest: null, lastResponse: null,
    };
    runs.set(runId, game);
    return { ...hub(), game: gameView(game, now) };
  }
  function move({ run_id: runId, action, cell, revision }) {
    if (typeof runId !== 'string' || runId.length < 20 || runId.length > 128) return unavailable();
    if (!['reveal', 'flag', 'chord'].includes(action)) return failure('invalid_action', 'action must be reveal, flag, or chord.');
    if (!Number.isSafeInteger(cell) || cell < 0 || cell >= 480) return failure('invalid_cell', 'cell must be a strict integer within the board.');
    if (!Number.isSafeInteger(revision) || revision < 0) return failure('invalid_revision', 'revision must be a strict nonnegative integer.');
    const now = clock(); prune(now);
    const game = runs.get(runId);
    if (!game || game.owner !== playerId()) return unavailable();
    if (cell >= game.spec.rows * game.spec.cols) return failure('invalid_cell', 'cell must be within this board.');
    const request = JSON.stringify([revision, action, cell]);
    if (request === game.lastRequest) return copy(game.lastResponse);
    if (revision !== game.revision) return failure('stale_revision', 'The field changed. Resynchronize from this game.', gameView(game, now));
    if (['won', 'lost'].includes(game.status)) return { ...hub(), game: gameView(game, now) };
    const before = visible(game);
    const lose = mine => { game.status = 'lost'; game.exploded = mine; game.finishedAt = now; };
    if (action === 'flag') {
      if (game.flags.has(cell)) game.flags.delete(cell);
      else if (!game.revealed.has(cell) && game.flags.size < game.spec.mineCount) game.flags.add(cell);
    } else if (action === 'reveal') {
      if (!game.flags.has(cell) && !game.revealed.has(cell)) {
        if (game.mines === null) { plant(game, cell); game.startedAt = now; game.status = 'playing'; }
        if (game.mines.has(cell)) lose(cell);
        else flood(game, [cell]);
      }
    } else if (game.revealed.has(cell)) {
      const neighbors = adjacent(cell, game.spec.rows, game.spec.cols);
      if (neighbors.filter(index => game.flags.has(index)).length === game.numbers[cell]) {
        const targets = neighbors.filter(index => !game.flags.has(index) && !game.revealed.has(index));
        const mine = targets.find(index => game.mines.has(index));
        if (mine !== undefined) lose(mine);
        else flood(game, targets);
      }
    }
    if (game.status === 'playing' && game.revealed.size === game.spec.rows * game.spec.cols - game.spec.mineCount) {
      game.status = 'won'; game.finishedAt = now; game.flags = new Set(game.mines);
    }
    game.revision++;
    let receipt = {};
    if (game.status === 'won') {
      const points = score(game, now), duration = elapsed(game, now), previous = players.get(playerId());
      const personalBest = !previous || points > previous.score || (points === previous.score && duration < previous.elapsedMs);
      if (personalBest) players.set(playerId(), {
        id: playerId(), name: callerName, score: points, elapsedMs: duration,
        difficulty: game.difficulty, achieved: ++achievement,
      });
      receipt = { recorded: true, personalBest, rank: ordered().findIndex(entry => entry.id === playerId()) + 1 };
    }
    const changed = visible(game).flatMap((value, index) => before[index] !== value ? [index] : []);
    const result = { ...hub(), game: gameView(game, now, changed), ...receipt };
    game.lastRequest = request; game.lastResponse = copy(result);
    return copy(result);
  }
  const overview = () => ({
    ...hub(), title: 'Minesweeper',
    description: 'ISOLATED QA FIXTURE: synthetic user, games and scores. Not the live MCP server.',
    rules: ['First reveal and its neighbors are safe.', 'Only synthetic wins enter this isolated in-memory scoreboard.'],
    difficulties: Object.entries(levels).map(([id, spec]) => ({ id, ...spec })),
  });
  function call(name, args = {}) {
    const fields = {
      minesweeper: [], minesweeper_scores: [], minesweeper_start: ['difficulty'],
      minesweeper_move: ['run_id', 'action', 'cell', 'revision'],
    };
    if (!Object.hasOwn(fields, name)) return failure('unknown_tool', 'Unknown isolated QA tool.');
    if (!args || typeof args !== 'object' || Array.isArray(args) || Object.keys(args).some(key => !fields[name].includes(key))) return failure('invalid_arguments', 'Unexpected or malformed tool arguments.');
    prune(clock());
    if (name === 'minesweeper_start') return start(Object.hasOwn(args, 'difficulty') ? args.difficulty : 'beginner');
    if (name === 'minesweeper_move') return move(args);
    return name === 'minesweeper' ? overview() : hub();
  }
  function seedScores(entries = [
    { name: 'QA Synthetic Ada', difficulty: 'beginner', score: 2695, elapsedMs: 15000 },
    { name: 'QA Synthetic Lin', difficulty: 'intermediate', score: 8260, elapsedMs: 30000 },
  ], { replace = true } = {}) {
    if (!Array.isArray(entries) || entries.length > 5000) throw new Error('QA seedScores expects at most 5000 synthetic records.');
    for (const entry of entries) {
      if (!entry || !Number.isSafeInteger(entry.score) || entry.score < 0 || !Number.isSafeInteger(entry.elapsedMs) || entry.elapsedMs < 0 || !Object.hasOwn(levels, entry.difficulty)) throw new Error('Invalid synthetic score row.');
    }
    if (replace) players.clear();
    for (const [index, entry] of entries.entries()) {
      const id = entry.isYou ? playerId() : `qa-seeded-${entry.id ?? index}`;
      players.set(id, {
        id, name: entry.isYou ? callerName : `QA ${String(entry.name || 'Synthetic Player').replace(/^QA\s+/, '')}`.slice(0, 48),
        score: entry.score, difficulty: entry.difficulty, elapsedMs: entry.elapsedMs, achieved: ++achievement,
      });
    }
    return hub();
  }
  return Object.freeze({
    call, start, move, scores: hub, overview,
    mines: runId => [...(runs.get(runId)?.mines || [])].sort((a, b) => a - b),
    game: runId => runs.has(runId) ? gameView(runs.get(runId), clock()) : null,
    latestRunId: () => [...runs.keys()].at(-1) || null,
    restartServer: () => { epochNumber++; runs.clear(); players.clear(); achievement = 0; return hub(); },
    resetScores: () => { players.clear(); return hub(); },
    seedScores,
    forceStale: (runId, avoidCell) => {
      const game = runs.get(runId);
      if (!game || ['won', 'lost'].includes(game.status)) return;
      // An unrevealed chord is a legal no-op. Use another cell so the incoming
      // request cannot accidentally match this synthetic competitor's retry key.
      const cell = visible(game).findIndex((value, index) => value < 0 && index !== avoidCell);
      move({ run_id: runId, action: 'chord', cell, revision: game.revision });
    },
  });
}

// Installs only the OUTER fixture bridge, never production globals or game hooks.
export function installFixture(frameHTML, env = window) {
  const iframe = env.document.getElementById('qa-app');
  let offsetMs = 0, moveWaiters = [], initialized = false;
  const server = createFixtureServer(() => env.performance.now() + offsetMs);
  const clone = value => JSON.parse(JSON.stringify(value));
  const fixture = env.fixture = {
    calls: [], errors: [], notifications: [], displayModes: [], modelContexts: [],
    failNextMove: false, forceStaleNextMove: false, delayMove: false,
  };
  const post = (target, data) => target.postMessage(data, '*');
  const reply = (target, id, result) => post(target, { jsonrpc: '2.0', id, result });
  const rpcError = (target, id, code, message) => post(target, { jsonrpc: '2.0', id, error: { code, message } });
  const toolResult = data => ({ content: [{ type: 'text', text: JSON.stringify(data) }], structuredContent: data });
  const notify = (method, params) => post(iframe.contentWindow, { jsonrpc: '2.0', method, params });
  fixture.app = () => iframe.contentWindow?.__MINESWEEPER__ || null;
  fixture.visible = () => fixture.app()?.snapshot() || null;
  const runId = () => fixture.visible()?.runId || server.latestRunId();
  fixture.mines = (id = runId()) => server.mines(id);
  fixture.serverSnapshot = (id = runId()) => ({ ...server.scores(), game: server.game(id) });
  fixture.restartServer = () => server.restartServer();
  fixture.resetScores = () => server.resetScores();
  fixture.seedScores = (...args) => server.seedScores(...args);
  fixture.pending = () => ({ moves: moveWaiters.length });
  fixture.releaseMoves = ({ reverse = false, keepDelaying = false } = {}) => {
    const waiters = moveWaiters; moveWaiters = []; fixture.delayMove = keepDelaying;
    if (reverse) waiters.reverse();
    for (const respond of waiters) respond();
    return waiters.length;
  };
  fixture.advanceTime = milliseconds => {
    if (!Number.isFinite(milliseconds) || milliseconds < 0) throw new Error('advanceTime requires nonnegative milliseconds.');
    offsetMs += milliseconds; return offsetMs;
  };
  fixture.serverMove = (action, cell, revision, id = runId()) => server.move({
    run_id: id, action, cell, revision: revision ?? server.game(id)?.revision,
  });
  fixture.click = id => iframe.contentDocument.getElementById(id)?.click();
  fixture.cell = (index, action = 'reveal') => {
    const button = iframe.contentDocument.querySelector(`[data-cell="${index}"]`);
    if (!button) throw new Error(`No visible QA cell ${index}.`);
    const child = iframe.contentWindow;
    if (action === 'flag') button.dispatchEvent(new child.MouseEvent('contextmenu', { bubbles: true, cancelable: true }));
    else { fixture.click('reveal-mode'); button.click(); }
  };
  fixture.key = (key, index) => {
    const target = Number.isInteger(index) ? iframe.contentDocument.querySelector(`[data-cell="${index}"]`) : iframe.contentDocument.activeElement;
    target?.dispatchEvent(new iframe.contentWindow.KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
  };
  fixture.result = () => ({
    initialized, app: fixture.visible(), server: fixture.serverSnapshot(),
    calls: clone(fixture.calls), pending: fixture.pending(), errors: [...fixture.errors],
    displayModes: [...fixture.displayModes],
  });
  iframe.addEventListener('load', () => {
    const child = iframe.contentWindow;
    child.addEventListener('error', event => fixture.errors.push(String(event.message || event.error)));
    child.addEventListener('unhandledrejection', event => fixture.errors.push(String(event.reason)));
  });
  env.addEventListener('message', event => {
    if (event.source !== iframe.contentWindow || event.data?.jsonrpc !== '2.0') return;
    const { id, method, params = {} } = event.data;
    if (id === undefined) {
      fixture.notifications.push({ method, params: clone(params) });
      if (method === 'ui/notifications/initialized' && !initialized) {
        initialized = true;
        notify('ui/notifications/tool-input', { arguments: {} });
        notify('ui/notifications/tool-result', toolResult(server.overview()));
      }
      if (method === 'notifications/message' && params.level === 'error') fixture.errors.push(String(params.data));
      return;
    }
    if (method === 'ui/initialize') {
      reply(event.source, id, {
        protocolVersion: params.protocolVersion,
        hostInfo: { name: 'Minesweeper isolated QA fixture', version: '1.0.0' },
        hostCapabilities: { serverTools: {}, logging: {}, sandbox: { csp: { resourceDomains: [], connectDomains: [] } } },
        hostContext: {
          theme: 'light', displayMode: 'inline', availableDisplayModes: ['inline', 'fullscreen'],
          locale: 'en-US', timeZone: 'UTC',
          deviceCapabilities: { touch: env.innerWidth < 721, hover: env.innerWidth >= 721 },
        },
      });
      return;
    }
    if (method === 'ui/request-display-mode') {
      const mode = params.mode === 'fullscreen' ? 'fullscreen' : 'inline';
      fixture.displayModes.push(mode); reply(event.source, id, { mode });
      notify('ui/notifications/host-context-changed', { displayMode: mode }); return;
    }
    if (method === 'ui/update-model-context') { fixture.modelContexts.push(clone(params)); reply(event.source, id, {}); return; }
    if (method === 'ping') { reply(event.source, id, {}); return; }
    if (method !== 'tools/call') { rpcError(event.source, id, -32601, `Unsupported isolated QA method: ${method}`); return; }
    const { name, arguments: args = {} } = params;
    const entry = { id, name, args: clone(args), epoch: server.scores().epoch, receivedAtMs: env.performance.now() };
    fixture.calls.push(entry);
    if (name === 'minesweeper_move' && fixture.forceStaleNextMove) {
      fixture.forceStaleNextMove = false; entry.forcedStale = true; server.forceStale(args.run_id, args.cell);
    }
    const result = server.call(name, args);
    entry.revision = result.game?.revision ?? null;
    entry.status = result.game?.status ?? null;
    entry.error = result.error?.code ?? null;
    const failedAfterApply = name === 'minesweeper_move' && fixture.failNextMove && !result.error;
    if (failedAfterApply) { fixture.failNextMove = false; entry.failedAfterApply = true; }
    const respond = () => {
      entry.respondedAtMs = env.performance.now();
      if (failedAfterApply) rpcError(event.source, id, -32001, 'Isolated QA: response intentionally lost AFTER the move committed. Retry the exact move.');
      else reply(event.source, id, toolResult(result));
    };
    if (name === 'minesweeper_move' && fixture.delayMove) { entry.delayed = true; moveWaiters.push(respond); }
    else respond();
  });
  iframe.srcdoc = frameHTML;
  return fixture;
}

async function generate() {
  const tool = resolve(root, 'src/catalog_app/tools/minesweeper');
  const [template, js] = await Promise.all([
    readFile(resolve(tool, 'app.html'), 'utf8'),
    readFile(resolve(tool, 'app.js'), 'utf8'),
  ]);
  if (template.split('<!-- app.js -->').length !== 2) throw new Error('Expected exactly one Minesweeper app.js insertion marker.');
  const csp = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src data:; img-src data:; connect-src 'none'; media-src 'none'; base-uri 'none'; form-action 'none'";
  const html = template
    .replace(/<head>/i, `<head><meta http-equiv="Content-Security-Policy" content="${csp}">`)
    .replace('<!-- app.js -->', () => `<script type="module">\n${js.replace(/<\/script/gi, '<\\/script')}\n</script>`);
  const frameData = JSON.stringify(html).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
  const host = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Minesweeper — isolated QA fixture</title>
<style>html,body{margin:0;height:100%;overflow:hidden;background:#092d30;color:#fff;font:11px monospace}#fixture-label{box-sizing:border-box;height:30px;display:flex;align-items:center;justify-content:center;padding:0 8px;color:#ffe5a6;background:#332719;font-size:10px;text-align:center}iframe{border:0;width:100%;height:calc(100% - 30px);display:block}</style>
</head><body><div id="fixture-label">ISOLATED QA FIXTURE · SYNTHETIC IDENTITY, MINES & SCORES · NOT THE LIVE MCP SERVER</div>
<iframe title="Minesweeper isolated QA app" id="qa-app" sandbox="allow-scripts allow-same-origin" allow="autoplay"></iframe>
<script>
${createFixtureServer.toString()}
${installFixture.toString()}
installFixture(${frameData});
</script></body></html>\n`;
  await mkdir(resolve(root, 'artifacts'), { recursive: true });
  await writeFile(outputPath, host, 'utf8');
  console.log('Generated artifacts/minesweeper-qa.html (isolated synthetic QA bridge; no server started).');
}

function selfTest() {
  let now = 1000;
  const server = createFixtureServer(() => now);
  let checks = 0;
  const check = callback => { callback(); checks++; };
  const start = (level = 'beginner') => server.start(level);
  const move = (game, action, cell) => server.move({ run_id: game.runId, revision: game.revision, action, cell });
  check(() => assert.equal(server.scores().totalPlayers, 0));
  for (const [difficulty, rows, cols, count] of [['beginner', 9, 9, 10], ['intermediate', 16, 16, 40], ['expert', 16, 30, 99]]) {
    for (const first of [0, cols - 1, rows * cols - 1, Math.floor(rows / 2) * cols + Math.floor(cols / 2)]) {
      const ready = start(difficulty).game;
      check(() => assert.equal(server.mines(ready.runId).length, 0));
      const result = move(ready, 'reveal', first);
      const mines = server.mines(ready.runId), row = Math.floor(first / cols), col = first % cols;
      check(() => assert.equal(mines.length, count));
      check(() => assert.ok(mines.every(cell => Math.abs(Math.floor(cell / cols) - row) > 1 || Math.abs(cell % cols - col) > 1)));
      check(() => assert.equal(result.game.cells[first], 0));
    }
  }
  server.restartServer();
  let game = start().game;
  const flagRequest = { run_id: game.runId, revision: 0, action: 'flag', cell: 40 };
  const flagged = server.move(flagRequest);
  now += 2000;
  check(() => assert.deepEqual(server.move(flagRequest), flagged));
  check(() => assert.equal(flagged.game.flagsUsed, 1));
  game = move(flagged.game, 'reveal', 40).game;
  check(() => assert.equal(game.elapsedMs, 0));
  check(() => assert.equal(server.mines(game.runId).length, 0));
  game = move(game, 'flag', 40).game;
  game = move(game, 'reveal', 40).game;
  check(() => assert.equal(game.elapsedMs, 0));
  check(() => assert.equal(server.scores().totalPlayers, 0));
  const mine = server.mines(game.runId)[0];
  game = move(game, 'reveal', mine).game;
  check(() => assert.equal(game.status, 'lost'));
  check(() => assert.equal(game.cells[mine], -4));
  check(() => assert.equal(server.scores().totalPlayers, 0));
  check(() => assert.deepEqual(move(game, 'flag', 0).game, { ...game, changed: [] }));
  game = start().game;
  game = move(game, 'reveal', 40).game;
  const map = new Set(server.mines(game.runId));
  now += 10250;
  let winningRequest, won;
  for (let cell = 0; cell < game.cells.length && game.status === 'playing'; cell++) {
    if (game.cells[cell] === -2 && !map.has(cell)) {
      winningRequest = { run_id: game.runId, revision: game.revision, action: 'reveal', cell };
      won = server.move(winningRequest); game = won.game;
    }
  }
  check(() => assert.equal(game.status, 'won'));
  check(() => assert.equal(game.score, 2700));
  check(() => assert.equal(game.cells.filter(value => value === -3).length, 10));
  check(() => assert.equal(won.recorded, true));
  check(() => assert.equal(won.personalBest, true));
  check(() => assert.deepEqual(server.move(winningRequest), won));
  won.game.cells[0] = 99;
  check(() => assert.notEqual(server.move(winningRequest).game.cells[0], 99));
  server.seedScores();
  check(() => assert.deepEqual(server.scores().leaderboard.map(entry => entry.score), [8260, 2695]));
  server.resetScores();
  check(() => assert.equal(server.scores().totalPlayers, 0));
  const oldEpoch = server.scores().epoch, oldId = server.scores().player.id;
  server.restartServer();
  check(() => assert.notEqual(server.scores().epoch, oldEpoch));
  check(() => assert.notEqual(server.scores().player.id, oldId));
  check(() => assert.equal(server.move(winningRequest).error.code, 'unavailable_run'));
  game = start().game;
  server.forceStale(game.runId, 40);
  check(() => assert.equal(move(game, 'reveal', 40).error.code, 'stale_revision'));
  for (const bad of [true, '0', 0.5, -1]) {
    check(() => assert.equal(server.move({ run_id: game.runId, action: 'flag', cell: bad, revision: 1 }).error.code, 'invalid_cell'));
  }
  check(() => assert.equal(server.call('minesweeper_start', { score: 999 }).error.code, 'invalid_arguments'));
  now += 7200000;
  check(() => assert.equal(server.move({ run_id: game.runId, action: 'flag', cell: 0, revision: 1 }).error.code, 'unavailable_run'));

  // Verify actual successful and wrong-flag chords against generated layouts.
  const neighbors = (view, cell) => {
    const row = Math.floor(cell / view.cols), col = cell % view.cols, values = [];
    for (let y = Math.max(0, row - 1); y < Math.min(view.rows, row + 2); y++) {
      for (let x = Math.max(0, col - 1); x < Math.min(view.cols, col + 2); x++) {
        if (y !== row || x !== col) values.push(y * view.cols + x);
      }
    }
    return values;
  };
  for (const wrongFlag of [false, true]) {
    server.restartServer();
    game = move(start().game, 'reveal', 40).game;
    const mines = new Set(server.mines(game.runId));
    const target = game.cells.findIndex((value, cell) => value > 0 && neighbors(game, cell).some(index => game.cells[index] === -2 && !mines.has(index)));
    check(() => assert.ok(target >= 0));
    const around = neighbors(game, target), actualMines = around.filter(index => mines.has(index));
    const safe = around.find(index => game.cells[index] === -2 && !mines.has(index));
    const noop = move(game, 'chord', target);
    check(() => assert.deepEqual(noop.game.changed, []));
    game = noop.game;
    const flags = wrongFlag ? [...actualMines.slice(1), safe] : actualMines;
    for (const cell of flags) game = move(game, 'flag', cell).game;
    const before = game.revealedCount;
    game = move(game, 'chord', target).game;
    if (wrongFlag) {
      check(() => assert.equal(game.status, 'lost'));
      check(() => assert.equal(game.cells[safe], -5));
      check(() => assert.equal(game.cells[actualMines[0]], -4));
      check(() => assert.equal(server.scores().totalPlayers, 0));
    } else {
      check(() => assert.notEqual(game.status, 'lost'));
      check(() => assert.ok(game.revealedCount > before));
    }
  }
  game = start().game;
  for (let cell = 0; cell < 10; cell++) game = move(game, 'flag', cell).game;
  const capped = move(game, 'flag', 10).game;
  check(() => assert.equal(capped.flagsUsed, 10));
  check(() => assert.equal(capped.revision, game.revision + 1));
  check(() => assert.deepEqual(capped.changed, []));
  const copies = [createFixtureServer(() => now), createFixtureServer(() => now)];
  const layouts = copies.map(store => {
    const ready = store.start('expert').game;
    store.move({ run_id: ready.runId, action: 'reveal', cell: 245, revision: 0 });
    return store.mines(ready.runId);
  });
  check(() => assert.deepEqual(layouts[0], layouts[1]));

  // Exercise the actual browser bridge without a browser/bundle: fake only its
  // outer DOM/transport, then send the official SDK handshake and tool calls.
  const messages = [], listeners = {};
  const child = { postMessage: data => messages.push(data), addEventListener() {} };
  const iframe = { contentWindow: child, addEventListener() {}, srcdoc: '' };
  const env = { document: { getElementById: () => iframe }, performance: { now: () => now }, innerWidth: 1000,
    addEventListener: (name, handler) => { listeners[name] = handler; } };
  const fixture = installFixture('<html>synthetic test</html>', env);
  let rpcId = 0;
  const rpc = (method, params = {}) => {
    const id = ++rpcId; listeners.message({ source: child, data: { jsonrpc: '2.0', id, method, params } });
    return { id, response: messages.find(message => message.id === id) };
  };
  check(() => assert.equal(rpc('ui/initialize', { protocolVersion: '2026-01-26' }).response.result.protocolVersion, '2026-01-26'));
  listeners.message({ source: child, data: { jsonrpc: '2.0', method: 'ui/notifications/initialized' } });
  check(() => assert.ok(messages.some(message => message.method === 'ui/notifications/tool-result')));
  const started = rpc('tools/call', { name: 'minesweeper_start', arguments: {} }).response.result.structuredContent;
  const args = { run_id: started.game.runId, action: 'flag', cell: 0, revision: 0 };
  fixture.failNextMove = true;
  check(() => assert.equal(rpc('tools/call', { name: 'minesweeper_move', arguments: args }).response.error.code, -32001));
  check(() => assert.equal(fixture.serverSnapshot().game.revision, 1));
  check(() => assert.equal(rpc('tools/call', { name: 'minesweeper_move', arguments: args }).response.result.structuredContent.game.flagsUsed, 1));
  fixture.forceStaleNextMove = true; fixture.delayMove = true;
  const delayed = rpc('tools/call', { name: 'minesweeper_move', arguments: { ...args, cell: 5, revision: 1 } });
  const previousEpoch = fixture.serverSnapshot().epoch;
  check(() => assert.equal(delayed.response, undefined));
  check(() => assert.equal(fixture.pending().moves, 1));
  fixture.restartServer();
  check(() => assert.notEqual(fixture.serverSnapshot().epoch, previousEpoch));
  check(() => assert.equal(fixture.releaseMoves(), 1));
  const oldError = messages.find(message => message.id === delayed.id).result.structuredContent;
  check(() => assert.equal(oldError.error.code, 'stale_revision'));
  check(() => assert.equal(oldError.epoch, previousEpoch));
  check(() => assert.equal(fixture.pending().moves, 0));
  console.log(`Minesweeper isolated fixture self-tests: ${checks} checks passed (no browser, bundle or server required).`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (process.argv.includes('--self-test')) selfTest();
  else await generate();
}
