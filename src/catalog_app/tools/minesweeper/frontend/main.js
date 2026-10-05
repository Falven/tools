import { App } from '@modelcontextprotocol/ext-apps';
import { RetroAudio } from './audio.js';

const $ = id => document.getElementById(id);
const levels = Object.freeze({
  beginner: { name: 'Beginner', rows: 9, cols: 9, mines: 10, multiplier: 1 },
  intermediate: { name: 'Intermediate', rows: 16, cols: 16, mines: 40, multiplier: 2 },
  expert: { name: 'Expert', rows: 16, cols: 30, mines: 99, multiplier: 3 },
});
const app = new App({ name: 'Minesweeper', version: '1.0.0' }, { availableDisplayModes: ['inline', 'fullscreen'] }, { autoResize: false });
const audio = new RetroAudio();
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
let connected = false, connecting = false, canPlay = false, disposed = false;
let game = null, difficulty = 'beginner', busy = false, flagMode = false, flat = reducedMotion.matches;
let player = null, scores = [], epoch = null, expired = false, receivedOverview = false;
let cells = [], focusIndex = 0, pendingDifficulty = 'beginner', pendingMove = null, retryAction = null;
let hubSequence = 0, appliedHubSequence = 0, generation = 0, gameReceivedAt = 0, lastResultRun = null;
let longPress = null, touchOrigin = null, suppressClick = null, resultTimer = null, particlesTimer = null;
const cleanupTimers = new Set();
const number = value => (Number(value) || 0).toLocaleString('en-US');
const icon = (name, size = 24) => `<svg width="${size}" height="${size}" viewBox="0 0 32 32" aria-hidden="true"><use href="#i-${name}"/></svg>`;

function announce(message) { $('announcer').textContent = message; }
function later(callback, delay) {
  const id = setTimeout(() => { cleanupTimers.delete(id); if (!disposed) callback(); }, delay);
  cleanupTimers.add(id);
  return id;
}
function status(message, state = '') {
  $('status-text').textContent = message;
  $('field-status').dataset.state = state;
}
function clearError() { $('error-banner').hidden = true; retryAction = null; }
function showError(message, retry = null, label = 'Try again') {
  $('error-text').textContent = message;
  $('error-banner').hidden = false;
  $('retry-button').hidden = !retry;
  $('retry-button').textContent = label;
  retryAction = retry;
  announce(message);
}
function unpack(result) {
  if (result?.isError) throw new Error(result.content?.filter(item => item.type === 'text').map(item => item.text).join(' ') || 'The game server could not complete this request.');
  let data = result?.structuredContent;
  if (!data && result?.content) {
    for (const item of result.content) {
      if (item.type === 'text') { try { data = JSON.parse(item.text); break; } catch { /* Ignore non-JSON fallback text. */ } }
    }
  }
  if (!data && result && ('epoch' in result || 'leaderboard' in result)) data = result;
  if (!data) throw new Error('The game server returned an unreadable response.');
  if (data.error) {
    const error = new Error(data.error.message || 'This move could not be completed.');
    error.code = data.error.code;
    error.data = data;
    throw error;
  }
  return data;
}
async function call(name, args = {}) {
  return unpack(await app.callServerTool({ name, arguments: args }, { timeout: 20000 }));
}
function mergeHub(data, sequence = ++hubSequence, resetting = false) {
  if (sequence < appliedHubSequence || disposed) return;
  appliedHubSequence = sequence;
  if (epoch && data.epoch && epoch !== data.epoch && game && !resetting) {
    expired = true;
    pendingMove = null;
    status('The server restarted. Time for a fresh field.', 'error');
    showError('The server memory was reset. This field can no longer be scored.', () => startGame(difficulty), 'New game');
  }
  if (data.player && player && data.player.id !== player.id && game && !resetting) {
    expired = true;
    pendingMove = null;
    showError('The signed-in player changed. Please start a new field.', () => startGame(difficulty), 'New game');
  }
  if (data.epoch) epoch = data.epoch;
  if ('player' in data) player = data.player;
  if ('canPlay' in data) canPlay = Boolean(data.canPlay);
  if (Array.isArray(data.leaderboard)) scores = data.leaderboard.slice();
  $('identity').textContent = player ? `Playing as ${player.name} · wins verified on the server` : 'Sign in with a user account to play a scored game';
  renderScores();
  syncAvailability();
}
function renderScores() {
  const ordered = scores.slice().sort((a, b) => b.score - a.score || a.elapsedMs - b.elapsedMs || a.rank - b.rank);
  const list = $('score-list');
  list.replaceChildren();
  for (const [index, entry] of ordered.entries()) {
    const row = document.createElement('li');
    row.className = `score-row${entry.isYou ? ' is-you' : ''}`;
    const rank = document.createElement('span'); rank.className = 'rank'; rank.textContent = String(entry.rank || index + 1).padStart(2, '0');
    const info = document.createElement('div');
    const name = document.createElement('div'); name.className = 'player-name'; name.textContent = entry.name || 'Player'; name.title = entry.name || 'Player';
    if (entry.isYou) { const badge = document.createElement('span'); badge.className = 'you-label'; badge.textContent = 'YOU'; name.append(badge); }
    const meta = document.createElement('span'); meta.className = 'player-meta'; meta.textContent = `${levels[entry.difficulty]?.name || 'Classic'} · ${Math.floor(entry.elapsedMs / 1000)}s`;
    info.append(name, meta);
    const points = document.createElement('strong'); points.className = 'player-points'; points.textContent = number(entry.score);
    row.setAttribute('aria-label', `Rank ${entry.rank || index + 1}, ${entry.name || 'Player'}${entry.isYou ? ', you' : ''}, ${number(entry.score)} points, ${meta.textContent}`);
    row.append(rank, info, points); list.append(row);
  }
  list.hidden = ordered.length === 0;
  $('empty-scores').hidden = ordered.length > 0;
  $('personal-best').textContent = player?.bestScore ? number(player.bestScore) : '—';
  if (!connected) {
    $('empty-title').textContent = 'The top spot is wide open.';
    $('empty-description').textContent = 'Connect to the game server to see this session’s scores.';
  } else if (ordered.length === 0) {
    $('empty-title').textContent = 'The top spot is wide open.';
    $('empty-description').replaceChildren(document.createTextNode('Clear a field.'), document.createElement('br'), document.createTextNode('Make a little history.'));
  }
}
async function refreshScores({ quiet = false } = {}) {
  if (!connected || disposed) return;
  const sequence = ++hubSequence;
  $('refresh-scores').disabled = true;
  $('refresh-scores').classList.add('loading');
  try {
    const data = await call('minesweeper_scores');
    mergeHub(data, sequence);
    if (!quiet) announce('High scores refreshed. Highest score first.');
  } catch (error) {
    if (!quiet) showError(`Scores could not refresh. ${error.message}`, () => refreshScores(), 'Refresh');
  } finally {
    $('refresh-scores').classList.remove('loading');
    $('refresh-scores').disabled = !connected;
  }
}

const segmentPaths = [
  'M3 1h12l-2 3H5z', 'M15 2l2 2v9l-3 1V5z', 'M14 16l3 1v9l-2 2-1-3z',
  'M5 26h8l2 3H3z', 'M1 17l3-1v9l-1 3-2-2z', 'M1 4l2-2 1 3v9l-3-1z', 'M5 13h8l2 2-2 2H5l-2-2z',
];
const digitSegments = ['abcdef', 'bc', 'abdeg', 'abcdg', 'bcfg', 'acdfg', 'acdefg', 'abc', 'abcdefg', 'abcdfg'];
function led(element, value, label) {
  const display = String(Math.max(0, Math.min(999, Math.floor(value)))).padStart(3, '0');
  if (element.dataset.display !== display) {
    element.innerHTML = [...display].map(digit => `<svg viewBox="0 0 18 30" aria-hidden="true">${segmentPaths.map((path, index) => `<path class="seg${digitSegments[Number(digit)].includes('abcdefg'[index]) ? ' on' : ''}" d="${path}"/>`).join('')}</svg>`).join('');
    element.dataset.display = display;
  }
  element.setAttribute('aria-label', label);
}
function elapsed() {
  if (!game) return 0;
  return Math.max(0, game.elapsedMs + (game.status === 'playing' && !expired ? performance.now() - gameReceivedAt : 0));
}
function renderTimer() {
  const seconds = Math.floor(elapsed() / 1000);
  led($('time-counter'), seconds, `${seconds} seconds elapsed${seconds > 999 ? '; display capped at 999' : ''}`);
}
function renderHUD() {
  const level = levels[difficulty];
  const remaining = game ? game.mineCount - game.flagsUsed : level.mines;
  led($('mine-counter'), remaining, `${remaining} mines left to flag`);
  renderTimer();
  const value = String(game?.score || 0).padStart(5, '0');
  const leadingCount = Math.min(value.match(/^0*/)?.[0].length || 0, value.length - 1);
  const leading = document.createElement('span'); leading.className = 'leading'; leading.textContent = value.slice(0, leadingCount);
  $('score').replaceChildren(leading, document.createTextNode(value.slice(leadingCount)));
  $('score').setAttribute('aria-label', `${game?.score || 0} points`);
  const total = level.rows * level.cols - level.mines;
  $('reveal-count').textContent = `${game?.revealedCount || 0} / ${total} SAFE TILES`;
  $('progress-fill').style.width = `${((game?.revealedCount || 0) / total) * 100}%`;
  $('multiplier').textContent = `${level.multiplier}× POINTS`;
  $('board-level').textContent = level.name.toUpperCase();
  $('field-spec').textContent = `${level.cols} × ${level.rows} · ${level.mines} MINES`;
  document.querySelectorAll('[data-difficulty]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.difficulty === difficulty)));
}
function face(state = game?.status || 'ready') {
  let features = '<path d="M10 11h4v5h-4zm12 0h4v5h-4z" fill="#3c3e2c"/><path d="M10 22v3h3v2h10v-2h3v-3" fill="none" stroke="#3c3e2c" stroke-width="2"/>';
  if (state === 'nervous') features = '<path d="M10 10h4v6h-4zm12 0h4v6h-4z" fill="#3c3e2c"/><ellipse cx="18" cy="24" rx="4" ry="5" fill="#3c3e2c"/>';
  if (state === 'lost') features = '<path d="m10 10 6 6m0-6-6 6m11-6 6 6m0-6-6 6M11 26v-3h3v-2h8v2h3v3" stroke="#3c3e2c" stroke-width="2" fill="none"/>';
  if (state === 'won') features = '<path d="M5 11h12v7H8v-3H5zm14 0h12v4h-3v3h-9z" fill="#293c36"/><path d="M16 12h5M11 22v3h3v2h8v-2h3v-3" stroke="#293c36" stroke-width="2" fill="none"/>';
  return `<svg viewBox="0 0 36 36" aria-hidden="true"><circle cx="18" cy="19" r="15" fill="#c99b3d"/><circle cx="18" cy="17" r="15" fill="#f4d35c" stroke="#a47d27" stroke-width="1.4"/><path d="M8 10a12 12 0 0 1 16-3" fill="none" stroke="#fff0a3" stroke-width="2"/>${features}</svg>`;
}
function setFace(state) { $('face-button').innerHTML = face(state); }
function boardShape() {
  const level = levels[difficulty];
  const board = $('board');
  board.style.setProperty('--cols', level.cols);
  if (difficulty !== 'beginner') board.style.setProperty('--cell', difficulty === 'expert' ? '27px' : '29px');
  else board.style.removeProperty('--cell');
  board.setAttribute('aria-rowcount', level.rows);
  board.setAttribute('aria-colcount', level.cols);
  if (cells.length === level.rows * level.cols && Number(board.dataset.cols) === level.cols) return;
  board.dataset.cols = level.cols;
  board.replaceChildren(); cells = []; focusIndex = 0;
  for (let rowIndex = 0; rowIndex < level.rows; rowIndex++) {
    const row = document.createElement('div'); row.className = 'board-row'; row.setAttribute('role', 'row'); row.setAttribute('aria-rowindex', rowIndex + 1);
    for (let colIndex = 0; colIndex < level.cols; colIndex++) {
      const cell = document.createElement('button'); cell.type = 'button'; cell.className = 'cell covered'; cell.setAttribute('role', 'gridcell');
      const index = rowIndex * level.cols + colIndex;
      cell.dataset.cell = index; cell.dataset.value = '-2'; cell.tabIndex = index === 0 ? 0 : -1;
      cell.setAttribute('aria-colindex', colIndex + 1); row.append(cell); cells.push(cell);
    }
    board.append(row);
  }
}
function measureBoard() {
  $('board-progress').classList.toggle('has-scroll', $('board-scroll').scrollWidth > $('board-scroll').clientWidth + 3);
}
function renderBoard(animate = false) {
  boardShape();
  const values = game?.cells || Array(cells.length).fill(-2);
  let revealOrder = 0;
  for (const [index, button] of cells.entries()) {
    const value = values[index], previous = Number(button.dataset.value);
    button.dataset.value = value;
    const covered = value === -2 || value === -3;
    button.className = `cell ${covered ? 'covered' : 'revealed'}${value === -4 ? ' exploded' : ''}${value === -5 ? ' wrong-flag' : ''}`;
    if (value === -3 || value === -5) button.innerHTML = icon('flag');
    else if (value === -1 || value === -4) button.innerHTML = icon('mine');
    else button.textContent = value > 0 ? value : '';
    if (animate && previous < 0 && value >= 0 && !reducedMotion.matches) {
      button.classList.add('new-reveal'); button.style.setProperty('--delay', `${Math.min(revealOrder++, 18) * 9}ms`);
    }
    const description = value === -2 ? 'covered' : value === -3 ? 'flagged' : value === -5 ? 'incorrect flag' : value === -4 ? 'exploded mine' : value === -1 ? 'mine' : value === 0 ? 'empty' : `${value} neighboring ${value === 1 ? 'mine' : 'mines'}`;
    button.setAttribute('aria-label', `Row ${Math.floor(index / levels[difficulty].cols) + 1}, column ${index % levels[difficulty].cols + 1}: ${description}`);
  }
  $('board-plinth').classList.toggle('flat', flat);
  renderHUD(); setFace(); syncAvailability(); requestAnimationFrame(measureBoard);
}
function syncAvailability() {
  const unavailable = !connected || !canPlay;
  $('board').classList.toggle('blocked', unavailable || expired || Boolean(pendingMove));
  $('board').setAttribute('aria-busy', String(busy));
  for (const id of ['new-game', 'face-button', 'play-again', 'confirm-restart']) $(id).disabled = busy || unavailable;
  document.querySelectorAll('[data-difficulty]').forEach(button => { button.disabled = busy; });
  for (const button of cells) button.setAttribute('aria-disabled', String(unavailable || busy || expired || Boolean(pendingMove) || ['won', 'lost'].includes(game?.status)));
  $('refresh-scores').disabled = !connected;
}
function setBusy(value) {
  busy = value; syncAvailability();
  if (!value) { for (const button of cells) button.classList.remove('pressing'); setFace(); }
}
function syncGame(next, animate = false) {
  game = next; gameReceivedAt = performance.now(); difficulty = game.difficulty; expired = false;
  renderBoard(animate);
  if (game.status === 'ready') status('Your first click is always safe.');
  else if (game.status === 'playing') status(flagMode ? 'Flag mode on. Mark a tile you suspect.' : 'Take your time. Trust the numbers.');
  else if (game.status === 'won') status('Field cleared. Nicely swept!', 'won');
  else status('One mine too many. Shall we try again?', 'lost');
}
async function issueGame(level, preserveMode = false) {
  const sequence = ++hubSequence;
  const data = await call('minesweeper_start', { difficulty: level });
  mergeHub(data, sequence, true);
  pendingMove = null; lastResultRun = null;
  if (!preserveMode) flagMode = false;
  updateInputMode();
  syncGame(data.game); $('board-scroll').scrollLeft = 0;
  audio.play('start');
  return data;
}
async function startGame(level = difficulty) {
  if (busy || !connected || !canPlay || disposed) return;
  const version = ++generation;
  clearTimeout(resultTimer); $('result-dialog').close(); $('restart-dialog').close();
  clearError(); setBusy(true); status('Setting out a fresh field…');
  void unlockAudio();
  try {
    await issueGame(level);
    if (version !== generation || disposed) return;
    announce(`${levels[level].name} field ready. Your first reveal is safe.`);
  } catch (error) {
    if (!disposed) { showError(error.message, () => startGame(level), 'New game'); status('Could not start the field. Please retry.', 'error'); }
  } finally { if (version === generation) setBusy(false); }
}
function requestNewGame(level = difficulty, force = false) {
  if (busy || disposed) return;
  if (!connected || !canPlay) {
    if (level !== difficulty && !game) { difficulty = level; renderBoard(); }
    showError(!connected ? 'Open this app in ToolForge to connect to the game server.' : 'A signed-in user account is needed to play scored games.');
    return;
  }
  if (!force && game?.status === 'playing' && !expired) {
    pendingDifficulty = level;
    $('restart-dialog').showModal(); $('cancel-restart').focus(); return;
  }
  void startGame(level);
}
function adjacent(index) {
  const { cols, rows } = levels[difficulty], row = Math.floor(index / cols), col = index % cols, neighbors = [];
  for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
    if ((!dx && !dy) || row + dy < 0 || row + dy >= rows || col + dx < 0 || col + dx >= cols) continue;
    neighbors.push((row + dy) * cols + col + dx);
  }
  return neighbors;
}
async function move(action, index) {
  if (busy || disposed || !connected || !canPlay || expired || ['won', 'lost'].includes(game?.status)) return;
  if (pendingMove) { showError('The previous move needs to be synchronized before continuing.', () => retryMove(), 'Retry move'); return; }
  void unlockAudio();
  clearError(); setBusy(true);
  const version = generation;
  try {
    if (!game) await issueGame(difficulty, true);
    if (disposed || version !== generation) return;
    if (action === 'reveal' && game.cells[index] === -3) return;
    if (action === 'reveal' && game.cells[index] >= 0) action = 'chord';
    if (action === 'chord') {
      const flags = adjacent(index).filter(cell => game.cells[cell] === -3).length;
      if (game.cells[index] < 0 || flags !== game.cells[index]) {
        if (game.cells[index] > 0) status(`Mark ${game.cells[index]} neighboring mines before clearing around this number.`);
        return;
      }
    }
    if (action === 'flag' && game.cells[index] === -2 && game.flagsUsed >= game.mineCount) { status('All flags are in use. Remove one to place another.'); return; }
    const request = { run_id: game.runId, action, cell: index, revision: game.revision };
    pendingMove = request;
    await sendMove(request);
  } catch (error) {
    handleMoveError(error);
  } finally { if (version === generation) setBusy(false); }
}
async function sendMove(request) {
  const sequence = ++hubSequence;
  const before = game, requestEpoch = epoch;
  let data;
  try { data = await call('minesweeper_move', request); }
  catch (error) { error.requestSequence = sequence; error.requestEpoch = requestEpoch; throw error; }
  if (disposed || request.run_id !== game?.runId) return;
  pendingMove = null;
  mergeHub(data, sequence);
  if (data.epoch !== epoch) return;
  syncGame(data.game, true); clearError();
  if (game.status === 'won' || game.status === 'lost') { finish(data); return; }
  const newlyRevealed = game.revealedCount - (before?.revealedCount || 0);
  if (newlyRevealed > 0) { audio.play(newlyRevealed > 2 ? 'flood' : 'reveal'); announce(`${newlyRevealed} safe ${newlyRevealed === 1 ? 'tile' : 'tiles'} revealed. ${game.revealedCount} of ${game.rows * game.cols - game.mineCount} clear.`); }
  else if (game.flagsUsed !== before.flagsUsed) {
    const flagged = game.flagsUsed > before.flagsUsed; audio.play(flagged ? 'flag' : 'unflag');
    announce(`${flagged ? 'Flag placed' : 'Flag removed'}. ${game.mineCount - game.flagsUsed} flags remaining.`);
  }
}
function handleMoveError(error) {
  if (disposed) return;
  // A delayed error is still a response from its original server epoch. Never
  // let it resurrect a field after a newer scores response observes a restart.
  if (error.requestEpoch && epoch && error.requestEpoch !== epoch && error.data?.epoch !== epoch) {
    pendingMove = null; expired = true;
    status('The server restarted. Time for a fresh field.', 'error');
    showError('This response belongs to an earlier server session. Please start a new field.', () => startGame(difficulty), 'New game');
    return;
  }
  if (error.code === 'stale_revision' && error.data?.game) {
    pendingMove = null; mergeHub(error.data, error.requestSequence); syncGame(error.data.game);
    showError('The field was synchronized with the server. Please try your move again.');
    if (['won', 'lost'].includes(game.status)) finish(error.data);
    return;
  }
  if (['unavailable_run', 'ineligible', 'expired_run'].includes(error.code) || (error.data?.epoch && epoch && error.data.epoch !== epoch)) {
    pendingMove = null; expired = true;
    if (error.data?.epoch && error.data.epoch !== epoch) { epoch = error.data.epoch; scores = []; player = player ? { ...player, bestScore: 0 } : null; renderScores(); }
    status('This field is no longer available.', 'error');
    showError(error.message, () => startGame(difficulty), 'New game');
    return;
  }
  showError(error.message, pendingMove ? () => retryMove() : () => startGame(difficulty), pendingMove ? 'Retry move' : 'New game');
}
async function retryMove() {
  if (busy || !pendingMove || disposed) return;
  setBusy(true); clearError();
  try { await sendMove(pendingMove); } catch (error) { handleMoveError(error); } finally { setBusy(false); }
}
function burst(won) {
  if (reducedMotion.matches) return;
  clearTimeout(particlesTimer);
  $('particles').replaceChildren();
  if (!won) {
    $('board-plinth').classList.remove('shake'); void $('board-plinth').offsetWidth; $('board-plinth').classList.add('shake');
    later(() => $('board-plinth').classList.remove('shake'), 380);
  }
  const colors = won ? ['#e9bb41', '#408b68', '#e98451', '#4c7796', '#f7ecd0'] : ['#ad5141', '#efba73', '#879375'];
  for (let index = 0; index < (won ? 32 : 16); index++) {
    const particle = document.createElement('i'); particle.className = 'particle';
    particle.style.setProperty('--color', colors[index % colors.length]);
    particle.style.setProperty('--x', `${(Math.random() - .5) * 390}px`);
    particle.style.setProperty('--y', `${Math.random() * 330 - 130}px`);
    particle.style.setProperty('--rot', `${Math.random() * 500 - 250}deg`);
    $('particles').append(particle);
  }
  particlesTimer = later(() => $('particles').replaceChildren(), 1200);
}
function finish(data) {
  if (!game || lastResultRun === game.runId) return;
  lastResultRun = game.runId;
  const won = game.status === 'won';
  audio.play(won ? 'win' : 'lose'); burst(won);
  $('result-window-title').textContent = won ? 'A Job Well Swept' : 'Field Report';
  $('result-icon').innerHTML = won ? icon('trophy', 40) : face('lost');
  $('result-title').textContent = won ? 'A clean sweep.' : 'Oh, there it was.';
  $('result-description').textContent = won ? 'Every safe tile. Every good decision.' : 'Some days you find the mines the hard way.';
  $('result-score').textContent = number(game.score);
  $('result-level').textContent = levels[difficulty].name.toUpperCase();
  $('result-time').textContent = `${Math.floor(game.elapsedMs / 1000)} SECONDS`;
  $('result-record').textContent = won
    ? data.personalBest ? `New session best! ${data.rank ? `You’re #${data.rank} in the Hall of Fame.` : 'Your score is on the board.'}`
      : 'Win verified. Your highest score stays in the Hall of Fame.'
    : `${game.revealedCount} safe tiles found. Only wins reach the Hall of Fame. You’ve got the next one.`;
  announce(`${won ? 'You won' : 'Game over'}. ${game.score} points. ${Math.floor(game.elapsedMs / 1000)} seconds.`);
  const runId = game.runId;
  resultTimer = later(() => {
    if (game?.runId !== runId || $('help-dialog').open || $('restart-dialog').open) return;
    $('result-dialog').showModal(); $('play-again').focus();
  }, won ? 800 : 700);
}
function updateInputMode() {
  $('reveal-mode').setAttribute('aria-pressed', String(!flagMode));
  $('flag-mode').setAttribute('aria-pressed', String(flagMode));
}
function chooseInputMode(flag) {
  flagMode = flag; updateInputMode();
  if (!['won', 'lost'].includes(game?.status)) status(flag ? 'Flag mode on. Tap a tile to mark it.' : game?.status === 'playing' ? 'Reveal mode on. Trust the numbers.' : 'Your first click is always safe.');
  void unlockAudio().then(() => audio.play('ui'));
}
function focusCell(index) {
  cells[focusIndex]?.setAttribute('tabindex', '-1'); focusIndex = index;
  cells[index]?.setAttribute('tabindex', '0'); cells[index]?.focus({ preventScroll: true });
  cells[index]?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}
function clearPointer() {
  clearTimeout(longPress); longPress = null; touchOrigin = null;
  for (const button of cells) button.classList.remove('pressing');
  if (!busy) setFace();
}
$('board').addEventListener('click', event => {
  const button = event.target.closest('[data-cell]'); if (!button) return;
  const index = Number(button.dataset.cell);
  if (suppressClick && suppressClick.index === index && performance.now() < suppressClick.until) { event.preventDefault(); suppressClick = null; return; }
  cells[focusIndex]?.setAttribute('tabindex', '-1'); focusIndex = index; button.tabIndex = 0;
  void move(flagMode || event.shiftKey ? 'flag' : 'reveal', index);
});
$('board').addEventListener('contextmenu', event => {
  event.preventDefault();
  const button = event.target.closest('[data-cell]'); if (!button) return;
  const index = Number(button.dataset.cell);
  if (suppressClick && suppressClick.index === index && performance.now() < suppressClick.until) return;
  clearPointer(); void move('flag', index);
});
$('board').addEventListener('pointerdown', event => {
  const button = event.target.closest('[data-cell]');
  if (!button || busy || !connected || !canPlay || expired || ['won', 'lost'].includes(game?.status)) return;
  void unlockAudio();
  if (event.button === 0 && Number(button.dataset.value) < 0) { button.classList.add('pressing'); setFace('nervous'); }
  if (event.pointerType === 'touch' && !flagMode) {
    const index = Number(button.dataset.cell); touchOrigin = { x: event.clientX, y: event.clientY };
    longPress = setTimeout(() => { suppressClick = { index, until: performance.now() + 1100 }; clearPointer(); void move('flag', index); }, 470);
  }
});
$('board').addEventListener('pointermove', event => {
  if (touchOrigin && Math.hypot(event.clientX - touchOrigin.x, event.clientY - touchOrigin.y) > 9) clearPointer();
});
window.addEventListener('pointerup', clearPointer);
window.addEventListener('pointercancel', clearPointer);
$('board').addEventListener('keydown', event => {
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  const target = event.target.closest('[data-cell]'); if (!target) return;
  const index = Number(target.dataset.cell), cols = levels[difficulty].cols;
  const directions = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -cols, ArrowDown: cols };
  if (event.key in directions) {
    event.preventDefault();
    const next = index + directions[event.key];
    if (next >= 0 && next < cells.length && !(event.key === 'ArrowLeft' && index % cols === 0) && !(event.key === 'ArrowRight' && index % cols === cols - 1)) focusCell(next);
  } else if (event.key === 'Home' || event.key === 'End') {
    event.preventDefault(); focusCell(Math.floor(index / cols) * cols + (event.key === 'End' ? cols - 1 : 0));
  } else if ([' ', 'Enter', 'f', 'F'].includes(event.key)) {
    event.preventDefault(); if (!event.repeat) void move(event.key.toLowerCase() === 'f' ? 'flag' : 'reveal', index);
  }
});

async function unlockAudio() {
  if (disposed) return;
  await audio.unlock();
  if (!audio.available) {
    $('music-button').disabled = true; $('sfx-button').disabled = true;
    $('audio-caption').textContent = 'Audio is unavailable in this browser. The field is still yours.';
  }
}
function updateAudio() {
  $('music-button').setAttribute('aria-pressed', String(audio.musicEnabled));
  $('music-button').setAttribute('aria-label', audio.musicEnabled ? 'Mute music' : 'Unmute music');
  $('music-state').textContent = audio.musicEnabled ? 'ON' : 'OFF';
  $('sfx-button').setAttribute('aria-pressed', String(audio.sfxEnabled));
  $('sfx-button').setAttribute('aria-label', audio.sfxEnabled ? 'Mute sound effects' : 'Unmute sound effects');
  $('sfx-state').textContent = audio.sfxEnabled ? 'ON' : 'OFF';
}
$('music-button').addEventListener('click', async () => { await unlockAudio(); if (!audio.available) return; audio.setMusic(!audio.musicEnabled); updateAudio(); audio.play('ui'); });
$('sfx-button').addEventListener('click', async () => { await unlockAudio(); if (!audio.available) return; audio.setSfx(!audio.sfxEnabled); updateAudio(); if (audio.sfxEnabled) audio.play('ui'); });
$('new-game').addEventListener('click', () => requestNewGame());
$('face-button').addEventListener('click', () => requestNewGame(difficulty, true));
$('play-again').addEventListener('click', () => requestNewGame(difficulty, true));
$('confirm-restart').addEventListener('click', () => requestNewGame(pendingDifficulty, true));
$('help-button').addEventListener('click', () => { void unlockAudio().then(() => audio.play('ui')); $('help-dialog').showModal(); });
$('scores-menu').addEventListener('click', () => { $('scoreboard').scrollIntoView({ behavior: reducedMotion.matches ? 'instant' : 'smooth', block: 'nearest' }); $('scoreboard').focus({ preventScroll: true }); void refreshScores(); });
$('refresh-scores').addEventListener('click', () => refreshScores());
$('retry-button').addEventListener('click', () => { const retry = retryAction; if (retry) void retry(); });
$('reveal-mode').addEventListener('click', () => chooseInputMode(false));
$('flag-mode').addEventListener('click', () => chooseInputMode(true));
$('view-button').addEventListener('click', () => {
  flat = !flat; $('board-plinth').classList.toggle('flat', flat); updateView();
  void unlockAudio().then(() => audio.play('ui'));
});
function updateView() {
  $('view-button').setAttribute('aria-pressed', String(!flat));
  $('view-button').setAttribute('aria-label', flat ? 'Enable the 2.5D view' : 'Flatten the 2.5D view');
  $('view-label').textContent = flat ? 'Flat view' : '2.5D view';
}
for (const button of document.querySelectorAll('[data-difficulty]')) button.addEventListener('click', () => {
  if (button.dataset.difficulty !== difficulty) requestNewGame(button.dataset.difficulty);
});
for (const button of document.querySelectorAll('[data-close]')) button.addEventListener('click', () => {
  $(button.dataset.close).close(); if (button.dataset.close === 'result-dialog') cells[focusIndex]?.focus({ preventScroll: true });
});
window.addEventListener('keydown', event => {
  if (event.ctrlKey || event.metaKey || event.altKey || event.repeat || document.querySelector('dialog[open]')) return;
  if (event.key.toLowerCase() === 'n') { event.preventDefault(); requestNewGame(); }
  if (event.key.toLowerCase() === 'h' && !event.target.closest('input,textarea,select')) { event.preventDefault(); $('help-dialog').showModal(); }
});
document.addEventListener('visibilitychange', () => {
  if (document.hidden) { clearPointer(); audio.suspend(); }
  else { audio.setActive(true); renderTimer(); if (connected) void refreshScores({ quiet: true }); }
});
const resizeObserver = new ResizeObserver(measureBoard); resizeObserver.observe($('board-scroll'));
const timer = setInterval(() => { if (!document.hidden && !disposed) renderTimer(); }, 250);
function dispose() {
  if (disposed) return;
  disposed = true; generation++; clearInterval(timer); clearPointer();
  clearTimeout(resultTimer); clearTimeout(particlesTimer);
  for (const id of cleanupTimers) clearTimeout(id); cleanupTimers.clear();
  resizeObserver.disconnect(); audio.dispose(); game = null; scores = []; pendingMove = null;
}
app.onteardown = async () => { dispose(); return {}; };
app.ontoolresult = result => {
  if (disposed || receivedOverview || connected) return;
  try { mergeHub(unpack(result)); receivedOverview = true; } catch (error) { showError(error.message); }
};
app.onhostcontextchanged = context => { if (context.displayMode) document.body.dataset.displayMode = context.displayMode; requestAnimationFrame(measureBoard); };
window.addEventListener('pagehide', dispose, { once: true });
// Diagnostics are read-only and contain ONLY the same visible tiles sent to the UI.
// No mine map, credentials, score injection, persistence, or hidden game controls.
Object.defineProperty(window, '__MINESWEEPER__', { value: Object.freeze({
  snapshot: () => ({ connected, canPlay, busy, expired, difficulty, status: game?.status || 'ready', runId: game?.runId || null, revision: game?.revision ?? null, cells: game?.cells?.slice() || [], score: game?.score || 0, revealed: game?.revealedCount || 0, flags: game?.flagsUsed || 0, elapsedMs: Math.floor(elapsed()), flagMode, flat, music: audio.musicEnabled, sfx: audio.sfxEnabled, audioUnlocked: audio.unlocked, pendingMove: Boolean(pendingMove), epoch, leaderboard: scores.map(row => ({ ...row })) }),
}), writable: false, configurable: false });
async function connect() {
  if (connecting || disposed) return;
  connecting = true;
  if (window.parent === window) {
    connecting = false; $('connection').textContent = 'OFFLINE PREVIEW';
    $('identity').textContent = 'Open this app through ToolForge to play'; renderScores(); syncAvailability();
    showError('This standalone preview is not connected. Open Minesweeper in ToolForge to play with shared scores.'); return;
  }
  try {
    await app.connect(undefined, { timeout: 15000 }); connected = true;
    $('connection').textContent = 'READY TO SWEEP'; $('connection').classList.add('live');
    const context = app.getHostContext(); if (context?.displayMode) document.body.dataset.displayMode = context.displayMode;
    const sequence = ++hubSequence; mergeHub(await call('minesweeper_scores'), sequence);
    clearError();
    if (!canPlay) showError('Sign in with a delegated user account to play. Everyone connected can view the scoreboard.');
    syncAvailability();
  } catch (error) {
    connected = false; $('connection').textContent = 'CONNECTION LOST';
    $('identity').textContent = 'Game server unavailable · no scores are saved locally'; syncAvailability();
    showError(`Could not connect to the game server. Reopen the app to try again. ${error.message}`);
  } finally { connecting = false; }
}
renderBoard(); renderScores(); updateAudio(); updateView(); void connect();
