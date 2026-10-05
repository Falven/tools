// Browser regression suite against the explicitly synthetic, isolated QA host.
// Generate the fixture first, then run: node tests/test_minesweeper_browser.mjs
// Requires agent-browser. No web server, production scores, or credentials used.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { resolve, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const session = execFileSync('agent-browser', ['session', 'id', '--scope', 'worktree', '--prefix', 'minesweeper-regression'], { cwd: root, encoding: 'utf8' }).trim();
const env = { ...process.env, AGENT_BROWSER_SESSION: session };
let passed = 0;
function browser(args, input) {
  const text = execFileSync('agent-browser', [...args, '--json'], { cwd: root, env, encoding: 'utf8', input, timeout: 30000, maxBuffer: 8 * 1024 * 1024 });
  const output = JSON.parse(text);
  if (!output.success) throw new Error(JSON.stringify(output.error));
  return output.data;
}
function evaluate(script) { return browser(['eval', '--stdin'], script).result; }
function test(label, script) {
  const result = evaluate(`(async () => {
    const check = (value, message) => { if (!value) throw new Error(message); };
    const state = () => fixture.visible();
    const doc = document.getElementById('qa-app').contentDocument;
    const wait = async (predicate, label = 'condition') => {
      const until = performance.now() + 8000;
      while (!predicate()) { if (performance.now() > until) throw new Error('Timed out: ' + label); await new Promise(requestAnimationFrame); }
    };
    const settled = () => wait(() => !state().busy, 'move response');
    const fresh = async () => { if (doc.getElementById('result-dialog').open) doc.querySelector('[data-close="result-dialog"]').click(); fixture.click('face-button'); await settled(); check(state().status === 'ready', 'new field is ready'); };
    ${script}
    return { ok: true, status: state().status, revision: state().revision };
  })()`);
  assert.equal(result.ok, true);
  console.log(`PASS ${++passed}: ${label}`);
}
try {
  browser(['set', 'viewport', '1280', '1040']);
  browser(['open', pathToFileURL(resolve(root, 'artifacts/minesweeper-qa.html')).href]);
  browser(['wait', '--fn', 'window.fixture?.visible()?.connected === true']);
  test('connected initial state has no invented scores', `
    check(state().canPlay && state().status === 'ready', 'ready authenticated fixture');
    check(state().leaderboard.length === 0, 'empty session scoreboard');
    check(doc.querySelectorAll('[data-cell]').length === 81, '81 beginner tiles');
    check(state().music === false && state().sfx === true, 'independent default audio settings');
    check(fixture.errors.length === 0, 'no startup errors');
  `);
  // Trusted clicks unlock Web Audio; synthetic element.click() is not an audio gesture.
  browser(['frame', '#qa-app']);
  browser(['click', '#music-button']);
  browser(['click', '#sfx-button']);
  browser(['frame', 'main']);
  test('music remains on when sound effects are muted', `
    await wait(() => state().music && !state().sfx, 'audio settings');
    check(state().audioUnlocked, 'audio context unlocked after a real click');
    check(doc.getElementById('music-state').textContent === 'ON', 'music UI on');
    check(doc.getElementById('sfx-state').textContent === 'OFF', 'effects UI off');
  `);
  browser(['frame', '#qa-app']);
  browser(['click', '#music-button']);
  browser(['click', '#sfx-button']);
  browser(['frame', 'main']);
  test('effects remain on when music is muted', `
    await wait(() => !state().music && state().sfx, 'independent reverse toggles');
    check(doc.getElementById('music-button').getAttribute('aria-label') === 'Unmute music', 'music mute accessible label');
    check(doc.getElementById('sfx-button').getAttribute('aria-label') === 'Mute sound effects', 'effects mute accessible label');
  `);
  test('first flag preserves touch mode and does not start the timer', `
    fixture.click('flag-mode'); doc.querySelector('[data-cell="40"]').click(); await settled();
    check(state().flags === 1 && state().flagMode, 'flag mode preserved through implicit start');
    check(state().status === 'ready' && state().elapsedMs === 0, 'flag does not start clock');
    check(fixture.mines().length === 0, 'no mine map exists before reveal');
    fixture.cell(40, 'flag'); await settled(); check(state().flags === 0, 'right-click removes flag');
  `);
  test('first reveal is safe, floods, and supports keyboard flags', `
    fixture.cell(40); await settled();
    check(state().status === 'playing' && state().cells[40] === 0, 'safe first reveal');
    check(state().revealed > 1 && state().score === state().revealed * 10, 'flood and score');
    check(fixture.mines().every(i => Math.abs(Math.floor(i / 9) - 4) > 1 || Math.abs(i % 9 - 4) > 1), 'first ring safe');
    check(!state().cells.some(value => value === -1 || value === -4), 'no live mine leakage');
    const index = state().cells.findIndex(value => value === -2);
    fixture.key('f', index); await settled(); check(state().cells[index] === -3, 'F plants flag');
    fixture.key('F', index); await settled(); check(state().cells[index] === -2, 'F removes flag');
    doc.querySelector('[data-cell="40"]').focus(); fixture.key('ArrowRight', 40);
    check(doc.activeElement.dataset.cell === '41', 'arrow moves keyboard focus');
  `);
  test('help and restart confirmation preserve an active field', `
    const run = state().runId, revision = state().revision;
    fixture.click('new-game'); check(doc.getElementById('restart-dialog').open, 'restart asks during play');
    fixture.click('cancel-restart'); check(!doc.getElementById('restart-dialog').open, 'cancel closes confirmation');
    fixture.click('help-button'); check(doc.getElementById('help-dialog').open, 'help opens');
    doc.querySelector('[data-close="help-dialog"]').click();
    check(state().runId === run && state().revision === revision && state().status === 'playing', 'current field preserved');
  `);
  test('correctly flagged number chords reveal neighbors', `
    const mines = new Set(fixture.mines());
    const adjacent = i => { const out = [], r = Math.floor(i / 9), c = i % 9; for (let y = Math.max(0,r-1);y<=Math.min(8,r+1);y++) for(let x=Math.max(0,c-1);x<=Math.min(8,c+1);x++) if(y!==r||x!==c)out.push(y*9+x); return out; };
    const target = state().cells.findIndex((v,i) => v > 0 && adjacent(i).some(j => state().cells[j] === -2 && !mines.has(j)));
    check(target >= 0, 'fixture has a chord opportunity');
    for (const index of adjacent(target).filter(index => mines.has(index))) { fixture.cell(index, 'flag'); await settled(); }
    const before = state().revealed; fixture.cell(target); await settled();
    check(state().revealed > before && state().status !== 'lost', 'chord reveals safely');
  `);
  test('complete win automatically records one verified score', `
    const mines = new Set(fixture.mines());
    for (let i = 0; i < 81 && state().status === 'playing'; i++) {
      if (!mines.has(i) && state().cells[i] === -2) { fixture.cell(i); await settled(); }
    }
    check(state().status === 'won' && state().revealed === 71 && state().flags === 10, 'complete win and auto flags');
    check(state().leaderboard.length === 1 && state().leaderboard[0].isYou, 'one own score');
    check(state().score > 2000 && state().score <= 2710, 'score contains server time/win bonus');
    await wait(() => doc.getElementById('result-dialog').open, 'win dialog');
    check(doc.getElementById('result-title').textContent === 'A clean sweep.', 'win presentation');
  `);
  test('scores sort highest first; losses never add a score', `
    doc.querySelector('[data-close="result-dialog"]').click();
    fixture.seedScores(undefined, { replace: false }); fixture.click('refresh-scores');
    await wait(() => state().leaderboard.length >= 3, 'score refresh');
    check(state().leaderboard.every((entry,i,all) => i === 0 || all[i-1].score >= entry.score), 'descending score order');
    const count = fixture.serverSnapshot().totalPlayers;
    await fresh(); fixture.cell(40); await settled(); fixture.cell(fixture.mines()[0]); await settled();
    check(state().status === 'lost' && state().cells.includes(-4), 'loss shows exploded mine');
    check(fixture.serverSnapshot().totalPlayers === count, 'loss did not post');
    await wait(() => doc.getElementById('result-dialog').open, 'loss dialog');
    check(doc.getElementById('result-title').textContent === 'Oh, there it was.', 'loss presentation');
  `);
  test('a lost move response retries exactly once without double toggling', `
    await fresh(); fixture.failNextMove = true; fixture.cell(5, 'flag'); await settled();
    check(state().pendingMove && state().flags === 0, 'UI retains uncertain move');
    check(!doc.getElementById('error-banner').hidden, 'recoverable error visible');
    fixture.click('retry-button'); await settled();
    check(!state().pendingMove && state().flags === 1 && state().revision === 1, 'same receipt restored, flag not toggled twice');
    check(doc.getElementById('error-banner').hidden, 'retry error cleared');
  `);
  test('stale revision resynchronizes without replaying the user action', `
    fixture.forceStaleNextMove = true; fixture.cell(6, 'flag'); await settled();
    check(!state().pendingMove && !state().expired, 'stale resync remains playable');
    check(state().flags === 1 && state().revision === 2, 'competing no-op synced, rejected flag not applied');
  `);
  test('delayed old-epoch error cannot resurrect a restarted field', `
    await fresh(); fixture.delayMove = true; fixture.forceStaleNextMove = true;
    fixture.cell(7, 'flag'); await wait(() => fixture.pending().moves === 1, 'held stale error');
    const oldEpoch = state().epoch; fixture.restartServer(); fixture.click('refresh-scores');
    await wait(() => state().epoch !== oldEpoch, 'new epoch scores');
    const newEpoch = state().epoch; fixture.delayMove = false; fixture.releaseMoves(); await settled();
    check(state().epoch === newEpoch && state().expired, 'old error did not revert epoch or revive game');
    check(state().leaderboard.length === 0 && !state().pendingMove, 'server restart clears standings');
    await fresh(); check(!state().expired, 'fresh game recovers');
  `);
  test('difficulty switching and both view modes work', `
    doc.querySelector('[data-difficulty="intermediate"]').click(); await settled();
    check(state().difficulty === 'intermediate' && state().cells.length === 256, 'intermediate 16 by 16');
    doc.querySelector('[data-difficulty="expert"]').click(); await settled();
    check(state().difficulty === 'expert' && state().cells.length === 480, 'expert 30 by 16');
    fixture.click('view-button'); check(state().flat, 'flat view selected');
    fixture.click('view-button'); check(!state().flat, '2.5D restored');
    doc.querySelector('[data-difficulty="beginner"]').click(); await settled();
  `);
  test('touch long-press flags once and suppresses the following click', `
    await fresh();
    const win = document.getElementById('qa-app').contentWindow;
    const tile = doc.querySelector('[data-cell="7"]');
    tile.dispatchEvent(new win.PointerEvent('pointerdown', { bubbles: true, pointerType: 'touch', button: 0, clientX: 100, clientY: 100 }));
    await wait(() => state().flags === 1, 'long-press flag'); await settled();
    tile.dispatchEvent(new win.PointerEvent('pointerup', { bubbles: true, pointerType: 'touch', button: 0 }));
    tile.click(); await settled();
    check(state().flags === 1 && state().revision === 1 && state().status === 'ready', 'no duplicate flag or accidental reveal');
  `);
  for (const width of [768, 414, 375, 320]) {
    browser(['set', 'viewport', String(width), '1000']);
    test(`responsive beginner field at ${width}px`, `
      await new Promise(requestAnimationFrame);
      const win = document.getElementById('qa-app').contentWindow;
      check(doc.documentElement.scrollWidth <= win.innerWidth + 1, 'no full-page horizontal overflow');
      const scroller = doc.getElementById('board-scroll');
      check(scroller.scrollWidth <= scroller.clientWidth + 3, 'beginner fits without sideways scrolling');
    `);
  }
  test('expert stays contained and scrollable on a small screen', `
    doc.querySelector('[data-difficulty="expert"]').click(); await settled();
    await new Promise(requestAnimationFrame);
    const win = document.getElementById('qa-app').contentWindow;
    check(doc.documentElement.scrollWidth <= win.innerWidth + 1, 'expert does not widen page');
    const scroller = doc.getElementById('board-scroll');
    check(scroller.scrollWidth > scroller.clientWidth, 'expert has deliberate horizontal board scroll');
    check(doc.getElementById('board-progress').classList.contains('has-scroll'), 'scroll hint present');
    fixture.click('help-button'); check(doc.getElementById('help-dialog').open, 'help accessible on mobile');
    doc.querySelector('[data-close="help-dialog"]').click();
    check(fixture.errors.length === 0, 'no unhandled UI errors');
    check(fixture.modelContexts.length === 0, 'scores not copied into model context');
  `);
  console.log(`\nAll ${passed} Minesweeper browser regression groups passed.`);
} finally {
  try { browser(['close']); } catch (error) { console.error('Browser cleanup:', error.message); }
}
