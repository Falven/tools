// BEGIN SNAKE ENGINE — pure rules, mirrored by _Game in tool.py.
const SNAKE_RULES = Object.freeze({
  version: 1, board_size: 18, points_per_food: 10, foods_per_level: 5,
  initial_tick_ms: 165, minimum_tick_ms: 75, level_tick_reduction_ms: 12,
  max_steps: 16000,
});
const DIRECTIONS = [[0, -1], [1, 0], [0, 1], [-1, 0]];
class SnakeEngine {
  constructor(seed) {
    this.rng = (seed >>> 0) || 1;
    this.snake = [[6, 9], [5, 9], [4, 9], [3, 9]];
    this.previous = this.snake.map(p => [...p]);
    this.direction = 1;
    this.apples = 0;
    this.steps = 0;
    this.durationMs = 0;
    this.over = "";
    this.food = this.spawnFood();
  }
  get score() { return this.apples * SNAKE_RULES.points_per_food; }
  get level() { return 1 + Math.floor(this.apples / SNAKE_RULES.foods_per_level); }
  get interval() {
    return Math.max(SNAKE_RULES.minimum_tick_ms,
      SNAKE_RULES.initial_tick_ms - (this.level - 1) * SNAKE_RULES.level_tick_reduction_ms);
  }
  spawnFood() {
    const occupied = new Set(this.snake.map(([x, y]) => `${x},${y}`));
    const free = [];
    for (let y = 0; y < SNAKE_RULES.board_size; y++) {
      for (let x = 0; x < SNAKE_RULES.board_size; x++) {
        if (!occupied.has(`${x},${y}`)) free.push([x, y]);
      }
    }
    if (!free.length) return null;
    let x = this.rng;
    x ^= x << 13;
    x ^= x >>> 17;
    x ^= x << 5;
    this.rng = x >>> 0;
    return free[this.rng % free.length];
  }
  step(direction) {
    if (this.over) throw new Error("Moves after game over.");
    if (!Number.isInteger(direction) || direction < 0 || direction > 3 ||
        (direction + 2) % 4 === this.direction) throw new Error("Invalid turn.");
    this.previous = this.snake.map(p => [...p]);
    this.direction = direction;
    this.steps++;
    this.durationMs += this.interval;
    const [dx, dy] = DIRECTIONS[direction];
    const head = [this.snake[0][0] + dx, this.snake[0][1] + dy];
    const eating = !!this.food && head[0] === this.food[0] && head[1] === this.food[1];
    const body = eating ? this.snake : this.snake.slice(0, -1);
    if (head.some(n => n < 0 || n >= SNAKE_RULES.board_size)) {
      this.over = "wall";
    } else if (body.some(p => p[0] === head[0] && p[1] === head[1])) {
      this.over = "self";
    } else {
      this.snake.unshift(head);
      if (eating) {
        this.apples++;
        this.food = this.spawnFood();
        if (!this.food) this.over = "win";
      } else {
        this.snake.pop();
      }
    }
    if (this.steps >= SNAKE_RULES.max_steps && !this.over) this.over = "limit";
    return eating && this.over !== "wall" && this.over !== "self";
  }
}
function bufferTurn(queue, direction, currentDirection) {
  const last = queue.length ? queue[queue.length - 1] : currentDirection;
  if (!Number.isInteger(direction) || direction < 0 || direction > 3 ||
      queue.length >= 2 || last === direction || (last + 2) % 4 === direction) return false;
  queue.push(direction);
  return true;
}
function movementAlpha(elapsed, interval, reducedMotion = false) {
  // A short transition rather than trailing the authoritative grid by a full
  // 75–165ms tick. Movement speed, collision rules and replay timing stay intact.
  return reducedMotion ? 1 : Math.min(1, Math.max(0, elapsed) / Math.min(50, interval * .35));
}
// END SNAKE ENGINE

const $ = id => document.getElementById(id);
const stage = $("stage");
const sceneContainer = $("scene");
const motion = matchMedia("(prefers-reduced-motion: reduce)");
const events = new AbortController();
const on = (target, name, handler, options = {}) =>
  target.addEventListener(name, handler, { ...options, signal: events.signal });
const pad = (value, width = 4) => String(value).padStart(width, "0");
const formatTime = ms => `${pad(Math.floor(ms / 60000), 2)}:${pad(Math.floor(ms / 1000) % 60, 2)}`;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

let app = null;
let connected = false;
let connectionFailed = false;
let disposed = false;
let snapshot = null;
let view = null;
let compatible = true;
let state = "ready";
let pausedFrom = "running";
let engine = previewGame();
let ranked = false;
let run = null;
let trace = "";
let queue = [];
let accumulator = 0;
let countdownMs = 2100;
let lastFrame = performance.now();
let lastRender = 0;
let frameId = 0;
let startBusy = false;
let profileStartsGame = true;
let boardScope = "all";
let boardRequest = 0;
let boardBusy = false;
let lastCompleted = null;
let sound = false;
let audio = null;
let activeDialog = null;
let resumeAfterDialog = false;
let host = { displayMode: "inline", availableDisplayModes: [] };
let displayBusy = false;
let fullscreenAttempted = false;
const pendingSaves = new Map();

function previewGame() {
  const preview = new SnakeEngine(2026);
  preview.snake = [
    [14, 14], [13, 14], [12, 14], [11, 14], [10, 14], [9, 14],
    [8, 14], [7, 14], [6, 14], [5, 14], [4, 14], [4, 13], [4, 12],
    [4, 11], [4, 10],
  ];
  preview.previous = preview.snake.map(p => [...p]);
  preview.food = [13, 4];
  return preview;
}

function notice(message) {
  $("banner-text").textContent = message;
  $("banner").hidden = !message;
}
function announce(message) { $("announcement").textContent = message; }

function showDialog(id) {
  const dialog = $(id);
  if (dialog.open || disposed) return;
  if (!activeDialog) {
    resumeAfterDialog = ["running", "countdown"].includes(state);
    pause("Paused while this panel is open.");
  }
  const previous = activeDialog;
  activeDialog = dialog;
  previous?.close();
  placeDialog(dialog);
}
function placeDialog(dialog) {
  // Auto-sized inline Apps can be taller than the phone's visible viewport.
  // Measure the clipped area without reading the cross-origin parent window.
  // Centering against the full iframe would strand form buttons off-screen.
  const observer = new IntersectionObserver(entries => open(entries[0]?.intersectionRect));
  const timer = setTimeout(() => open(null), 250);
  function open(rect) {
    observer.disconnect();
    clearTimeout(timer);
    if (disposed || activeDialog !== dialog) return;
    const height = rect?.height > 64 ? rect.height : Math.min(innerHeight, 640);
    const top = rect?.height > 64 ? Math.max(0, rect.top) : 0;
    dialog.style.setProperty("--dialog-top", `${top + 16}px`);
    dialog.style.setProperty("--dialog-height", `${Math.max(32, Math.min(640, height - 32))}px`);
    if (!dialog.open) dialog.showModal();
    // Center within the *visible* part of an inline iframe, not its full page.
    const offset = Math.max(16, (height - dialog.getBoundingClientRect().height) / 2);
    dialog.style.setProperty("--dialog-top", `${top + offset}px`);
  }
  observer.observe(document.querySelector(".shell"));
}

class ApiError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}
function unpack(result) {
  if (result?.isError) throw new ApiError("server_error", "The score service couldn't complete that action. Please retry.");
  let data = result?.structuredContent;
  if (!data) {
    for (const block of result?.content || []) {
      if (block.type !== "text") continue;
      try {
        const candidate = JSON.parse(block.text);
        if (candidate?.kind === "neon_snake") { data = candidate; break; }
      } catch { /* Not every fallback content block is JSON. */ }
    }
  }
  if (data?.kind !== "neon_snake" || data.protocol !== 1) {
    throw new ApiError("version_mismatch", "Reopen the App to load the current game version.");
  }
  if (!data.ok) throw new ApiError(data.error?.code || "server_error",
    data.error?.message || "The score service couldn't complete that action.");
  return data;
}
async function withTimeout(promise, ms) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new ApiError("connection",
        "The score service didn't respond. Keep this App open and try again.")), ms);
    })]);
  } finally { clearTimeout(timer); }
}
async function rpc(name, args = {}) {
  if (!connected || !app) throw new ApiError("connection",
    "Score recording needs the MCP App connection. Reopen the App or choose practice.");
  try {
    return unpack(await withTimeout(app.callServerTool({ name, arguments: args }), 15000));
  } catch (error) {
    if (error instanceof ApiError) throw error;
    // Do not display host transport exceptions, which can contain sensitive details.
    throw new ApiError("connection", "The score connection was interrupted. Keep this App open and retry.");
  }
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderBoard(data) {
  const list = $("leaderboard");
  list.replaceChildren();
  // The server is authoritative for ordering, tie-breaks, and rank.
  for (const row of data.leaderboard || []) {
    const item = element("li", `score-row${row.is_you ? " you" : ""}`);
    const person = element("div", "row-player");
    const name = element("div", "row-name");
    name.append(element("span", "", row.display_name));
    if (row.is_you) name.append(element("span", "you-tag", "YOU"));
    person.append(name, element("span", "row-email", row.email_hint));
    const score = element("div", "row-score", Number(row.score).toLocaleString());
    score.append(element("span", "row-time", formatTime(row.duration_ms)));
    item.append(element("span", "rank", pad(row.rank, 2)), person, score);
    item.title = `Rank ${row.rank} · ${row.score} points · ${formatTime(row.duration_ms)} active time`;
    list.append(item);
  }
  $("empty-board").hidden = list.children.length > 0;
  const signedIn = data.player?.authenticated;
  $("empty-title").textContent = !signedIn ? "Play now. Rank when signed in." :
    boardScope === "mine" ? "Your story starts here." : "Room at the top.";
  $("empty-copy").textContent = !signedIn ?
    "Practice is open to everyone. A signed-in account is needed for the shared scoreboard." :
    "Finish a ranked run. Your score will appear here automatically.";
  $("board-total").textContent = `${Number(data.total_runs || 0).toLocaleString()} RUN${data.total_runs === 1 ? "" : "S"}`;
  $("board-state").classList.toggle("loaded", !!signedIn && data.storage?.available !== false);
  $("board-state-text").textContent = signedIn ? "AUTO-SAVE READY" : "PRACTICE ONLY";
}

function applySnapshot(data, includeBoard = true) {
  if (!data?.player || disposed) return;
  snapshot = data;
  compatible = Object.entries(SNAKE_RULES).every(([key, value]) => data.rules?.[key] === value);
  if (!compatible) notice("The game rules changed. Reopen the App for ranked play; practice is still available.");
  const player = data.player;
  $("player-name").textContent = player.display_name || "Player";
  $("player-email").textContent = player.email_hint ||
    (player.authenticated ? "Complete your player details to rank" : "Practice mode · scores are not saved");
  $("avatar").textContent = player.authenticated ?
    (player.display_name || "P").split(/\s+/).slice(0, 2).map(p => p[0]).join("").toUpperCase() : "P";
  $("best").textContent = pad(player.best_score || 0);
  $("profile-best").textContent = String(player.best_score || 0);
  $("personal-rank").textContent = player.best_rank ? `#${player.best_rank}` : "—";
  $("personal-runs").textContent = String(player.total_runs || 0);
  $("complete-profile").hidden = !player.authenticated || player.ready;
  if (includeBoard && (data.scope || "all") === boardScope) renderBoard(data);
  if (data.storage?.available === false) {
    notice("Score storage is unavailable. Practice is still playable; ranked scores cannot be saved right now.");
    $("board-state-text").textContent = "STORAGE OFFLINE";
  }
  updateControls();
}

function canRank() {
  return connected && compatible && snapshot?.player?.authenticated && snapshot.storage?.available !== false;
}
function updateControls() {
  const known = snapshot !== null || connectionFailed;
  $("start").disabled = !view || startBusy || displayBusy || !known;
  $("practice").disabled = !view || startBusy || displayBusy;
  $("practice").hidden = known && !canRank();
  $("start-label").textContent = startBusy ? "Setting up your run…" :
    !known ? "Connecting player…" : canRank() ? "Start ranked run" : "Play practice";
  $("start-notice").textContent = canRank() ?
    "Scores save with your name and e-mail. Only a masked address is shown." :
    "Practice runs aren't saved. Open in a signed-in MCP App to join the leaderboard.";
  $("load-note").hidden = !!view && known && !startBusy;
  if (!view) $("load-note").textContent = "Loading the arcade…";
  else if (!known) $("load-note").textContent = "Connecting your player profile…";
  else if (startBusy) $("load-note").textContent = "Creating a ranked game session…";
  $("refresh").disabled = !connected || boardBusy;
  $("scope-all").disabled = !connected;
  $("scope-mine").disabled = !connected;
  $("scope-all").setAttribute("aria-pressed", String(boardScope === "all"));
  $("scope-mine").setAttribute("aria-pressed", String(boardScope === "mine"));
  $("pause-button").disabled = !["running", "paused", "countdown"].includes(state);
  $("pause-label").textContent = state === "paused" ? "Resume" : "Pause";
  $("pause-icon").setAttribute("href", state === "paused" ? "#i-play" : "#i-pause");
  $("again").disabled = startBusy;
  $("back-to-menu").disabled = startBusy;
  $("complete-profile").disabled = startBusy || !["ready", "over"].includes(state);
  $("delete-data").disabled = !canRank() || !["ready", "over"].includes(state) ||
    pendingSaves.size > 0 || startBusy;
  const fullscreen = host.displayMode === "fullscreen";
  const displayLabel = fullscreen ? "Exit fullscreen" : "Enter fullscreen";
  $("fullscreen-button").hidden = !fullscreen && !host.availableDisplayModes?.includes("fullscreen");
  $("fullscreen-button").disabled = displayBusy || !connected;
  $("fullscreen-button").setAttribute("aria-pressed", String(fullscreen));
  $("fullscreen-button").setAttribute("aria-label", displayLabel);
  $("fullscreen-button").title = displayLabel;
  $("fullscreen-icon").setAttribute("href", fullscreen ? "#i-collapse" : "#i-expand");
}

function setState(next) {
  state = next;
  stage.dataset.state = state;
  $("overlay").hidden = state === "running";
  $("ready-panel").hidden = state !== "ready";
  $("pause-panel").hidden = state !== "paused";
  $("over-panel").hidden = state !== "over";
  $("countdown").hidden = state !== "countdown";
  updateControls();
}
function focusBoard() { stage.focus({ preventScroll: true }); }
function pause(reason = "Your next move can wait.") {
  if (!["running", "countdown"].includes(state)) return;
  pausedFrom = state;
  $("pause-reason").textContent = reason;
  setState("paused");
  announce("Game paused.");
}
function resume() {
  if (state !== "paused" || document.hidden || activeDialog) return;
  lastFrame = performance.now();
  setState(pausedFrom);
  focusBoard();
  announce("Game resumed.");
}
function turn(direction) {
  if (activeDialog || !["running", "countdown"].includes(state)) return false;
  return bufferTurn(queue, direction, engine.direction);
}
function updateHud() {
  $("score").textContent = pad(engine.score);
  $("level").textContent = pad(engine.level, 2);
  $("timer").textContent = formatTime(engine.durationMs);
}
function launch(seed, session) {
  run = session;
  ranked = !!session;
  engine = new SnakeEngine(seed);
  queue = [];
  trace = "";
  accumulator = 0;
  countdownMs = 2100;
  lastFrame = performance.now();
  lastCompleted = null;
  $("mode-badge").classList.toggle("practice", !ranked);
  $("mode-text").textContent = ranked ? "RANKED RUN" : "PRACTICE · NOT SAVED";
  $("count-number").textContent = "3";
  $("retry-save").hidden = true;
  updateHud();
  setState("countdown");
  focusBoard();
  announce(`${ranked ? "Ranked" : "Practice"} run. Three, two, one.`);
}
function openProfile(startAfter = true) {
  if (!canRank()) return;
  profileStartsGame = startAfter;
  const missing = snapshot.player.missing_fields || [];
  $("profile-form").reset();
  for (const [key, labelId, inputId] of [
    ["display_name", "name-field", "profile-name"], ["email", "email-field", "profile-email"],
  ]) {
    const needed = missing.includes(key);
    $(labelId).hidden = !needed;
    $(inputId).disabled = !needed;
    $(inputId).required = needed;
  }
  $("save-profile").textContent = startAfter ? "Save profile & start" : "Save player profile";
  $("profile-error").hidden = true;
  showDialog("profile-dialog");
}
async function startGame(practice = false) {
  if (!view || startBusy || disposed) return;
  if (!practice && canRank() && !snapshot.player.ready) { openProfile(); return; }
  if (practice || !canRank()) {
    const seed = crypto.getRandomValues(new Uint32Array(1))[0] || 1;
    launch(seed, null);
    return;
  }
  startBusy = true;
  updateControls();
  try {
    const data = await rpc("neon_snake_begin");
    applySnapshot(data);
    if (!compatible || !data.run || !Number.isInteger(data.run.seed)) {
      throw new ApiError("version_mismatch", "Reopen the App to synchronize the game rules.");
    }
    launch(data.run.seed, data.run);
    if (!pendingSaves.size) notice("");
  } catch (error) {
    notice(error.message);
    if (error.code === "profile_required") {
      await refreshBoard(true);
      openProfile();
    }
  } finally {
    startBusy = false;
    updateControls();
  }
}
function backToMenu() {
  if (startBusy) return;
  engine = previewGame();
  run = null;
  queue = [];
  $("score").textContent = "0000";
  $("level").textContent = "01";
  $("timer").textContent = "00:00";
  $("mode-text").textContent = "CLASSIC MODE";
  $("mode-badge").classList.remove("practice");
  setState("ready");
  $("start").focus({ preventScroll: true });
}

async function refreshBoard(silent = false) {
  if (!connected || disposed) return;
  const request = ++boardRequest;
  const scope = boardScope;
  boardBusy = true;
  updateControls();
  try {
    const data = await rpc("neon_snake_board", { scope });
    if (request === boardRequest && scope === boardScope) {
      applySnapshot(data);
      if (!silent) announce("Leaderboard refreshed.");
    }
  } catch (error) {
    if (request === boardRequest) {
      $("board-state-text").textContent = "REFRESH FAILED";
      $("board-state").classList.remove("loaded");
      if (!silent) notice(error.message);
    }
  } finally {
    if (request === boardRequest) { boardBusy = false; updateControls(); }
  }
}

function showSaveState() {
  if (!lastCompleted) return;
  const completed = lastCompleted;
  $("save-state").classList.toggle("error", ["pending", "failed"].includes(completed.saveState));
  $("retry-save").hidden = completed.saveState !== "pending";
  if (completed.saveState === "practice") $("save-state").textContent = "Practice run · not saved to the leaderboard";
  else if (completed.saveState === "saving") $("save-state").textContent = "Verifying & saving your score…";
  else if (completed.saveState === "saved") {
    $("save-state").textContent = `✓ Saved automatically · rank #${completed.rank}`;
    if (completed.newBest) $("result-kicker").textContent = "A new personal best";
  } else if (completed.saveState === "pending") {
    $("save-state").textContent = "Not saved yet. Keep this App open and retry.";
  } else $("save-state").textContent = completed.error || "This run couldn't be saved.";
}
async function savePending(id) {
  const pending = pendingSaves.get(id);
  if (!pending || pending.saving || !connected || disposed) return;
  pending.saving = true;
  if (lastCompleted?.id === id) { lastCompleted.saveState = "saving"; showSaveState(); }
  updateControls();
  try {
    const result = await rpc("neon_snake_finish", {
      run_id: pending.run_id, directions: pending.directions,
    });
    if (!result.saved_run) throw new ApiError("server_error", "Score confirmation was incomplete. Please retry.");
    pendingSaves.delete(id);
    boardRequest++; // Invalidate reads started before this write.
    boardBusy = false;
    applySnapshot(result);
    if (boardScope !== "all") void refreshBoard(true);
    if (lastCompleted?.id === id) {
      lastCompleted.saveState = "saved";
      lastCompleted.rank = result.saved_run.rank;
      showSaveState();
    }
    announce(`Score saved: ${result.saved_run.score} points, rank ${result.saved_run.rank}.`);
    if (!pendingSaves.size) notice("");
    // No e-mail or identity details are added to model context.
    try {
      await app.updateModelContext({
        structuredContent: {
          game: "Neon Snake", score: result.saved_run.score,
          personalBest: result.player.best_score, rank: result.saved_run.rank,
        },
      });
    } catch { /* Saving succeeded even if the host doesn't support context updates. */ }
  } catch (error) {
    const terminal = ["invalid_run", "run_expired", "invalid_replay", "already_recorded"].includes(error.code);
    if (terminal) pendingSaves.delete(id);
    if (lastCompleted?.id === id) {
      lastCompleted.saveState = terminal ? "failed" : "pending";
      lastCompleted.error = error.message;
      showSaveState();
    }
    notice(terminal ? `Run not saved: ${error.message}` :
      `${pendingSaves.size} run${pendingSaves.size === 1 ? "" : "s"} waiting to save. Keep this App open. Refresh scores or use Retry; retries won't duplicate a run.`);
  } finally {
    pending.saving = false;
    updateControls();
  }
}
async function retryPending() {
  for (const id of [...pendingSaves.keys()]) await savePending(id);
}
function finishGame() {
  setState("over");
  const newBest = ranked && engine.score > (snapshot?.player?.best_score || 0);
  lastCompleted = {
    id: run?.run_id || null, saveState: ranked ? "saving" : "practice",
    newBest, rank: null, score: engine.score,
  };
  $("result-title").textContent = engine.over === "win" ? "Grid conquered." :
    engine.over === "limit" ? "What a marathon." : engine.score ? "Nice run." : "A fresh start?";
  $("result-kicker").textContent = engine.over === "win" ? "You filled the board" :
    engine.over === "self" ? "A little too close" : engine.over === "wall" ? "End of the line" : "Run complete";
  $("final-score").textContent = String(engine.score);
  $("final-apples").textContent = `${engine.apples} cell${engine.apples === 1 ? "" : "s"}`;
  $("final-time").textContent = formatTime(engine.durationMs);
  showSaveState();
  tone(engine.over === "win" ? 740 : 190, .18);
  announce(`Game over. ${engine.score} points. ${ranked ? "Saving your score." : "Practice score is not saved."}`);
  if (ranked) {
    pendingSaves.set(run.run_id, { run_id: run.run_id, directions: trace, saving: false });
    void savePending(run.run_id);
  }
}

function tone(frequency, duration = .09) {
  if (!sound || !audio || audio.state !== "running") return;
  const start = audio.currentTime;
  const oscillator = audio.createOscillator();
  const gain = audio.createGain();
  oscillator.type = "sine";
  oscillator.frequency.setValueAtTime(frequency, start);
  oscillator.frequency.exponentialRampToValueAtTime(Math.max(40, frequency * .65), start + duration);
  gain.gain.setValueAtTime(.0001, start);
  gain.gain.exponentialRampToValueAtTime(.045, start + .012);
  gain.gain.exponentialRampToValueAtTime(.0001, start + duration);
  oscillator.connect(gain).connect(audio.destination);
  oscillator.start(start);
  oscillator.stop(start + duration);
  oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
}

class ThreeBoard {
  constructor(THREE, RoundedBoxGeometry) {
    this.T = THREE;
    this.scene = new THREE.Scene();
    this.camera = new THREE.OrthographicCamera();
    this.camera.position.set(1.4, 25, 19);
    this.camera.lookAt(0, 0, 0);
    // Maximum-quality preset. Input handling never lowers rendering quality.
    this.renderer = new THREE.WebGLRenderer({
      antialias: true, alpha: true, precision: "highp", powerPreference: "high-performance",
    });
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.shadowMap.autoUpdate = true;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.15;
    this.renderer.setClearColor(0, 0);
    $("scene").replaceChildren(this.renderer.domElement);
    on(this.renderer.domElement, "webglcontextlost", event => {
      event.preventDefault();
      pause("The graphics context was interrupted. Your game is paused.");
      notice("Graphics were interrupted. If they don't recover, reopen the App.");
    });
    on(this.renderer.domElement, "webglcontextrestored", () => notice("Graphics restored. Resume when you're ready."));
    this.scene.add(new THREE.HemisphereLight(0xd7efca, 0x183b24, 2.1));
    const sun = new THREE.DirectionalLight(0xedffe4, 3);
    sun.position.set(-7, 17, 8);
    sun.castShadow = true;
    // Only the GPU's actual texture limit can constrain the 4K shadow map.
    const shadowSize = Math.min(4096, this.renderer.capabilities.maxTextureSize);
    sun.shadow.mapSize.set(shadowSize, shadowSize);
    Object.assign(sun.shadow.camera, { left: -13, right: 13, top: 13, bottom: -13, near: 1, far: 50 });
    sun.shadow.normalBias = .035;
    sun.shadow.bias = -.0004;
    this.scene.add(sun);
    const material = (color, other = {}) => new THREE.MeshStandardMaterial({ color, roughness: .7, ...other });
    const add = (geometry, mat, x = 0, y = 0, z = 0) => {
      const mesh = new THREE.Mesh(geometry, mat);
      mesh.position.set(x, y, z);
      mesh.receiveShadow = true;
      this.scene.add(mesh);
      return mesh;
    };
    const base = add(new RoundedBoxGeometry(19, .7, 19, 6, .22), material(0x263e2d), 0, -.52);
    base.castShadow = true;
    const floor = add(new THREE.PlaneGeometry(35, 35), new THREE.ShadowMaterial({ opacity: .25 }), 0, -.9);
    floor.rotation.x = -Math.PI / 2;
    this.dummy = new THREE.Object3D();
    this.color = new THREE.Color();
    const tiles = new THREE.InstancedMesh(new THREE.PlaneGeometry(.976, .976), material(0xffffff), 324);
    for (let y = 0; y < 18; y++) {
      for (let x = 0; x < 18; x++) {
        this.dummy.position.set(x - 8.5, -.145, y - 8.5);
        this.dummy.rotation.set(-Math.PI / 2, 0, 0);
        this.dummy.updateMatrix();
        tiles.setMatrixAt(y * 18 + x, this.dummy.matrix);
        tiles.setColorAt(y * 18 + x, this.color.set((x + y) % 2 ? 0x254333 : 0x213c2d));
      }
    }
    tiles.receiveShadow = true;
    this.scene.add(tiles);
    const railMaterial = material(0x4a6740);
    for (const [x, z, wide] of [[0, -9.12, true], [0, 9.12, true], [-9.12, 0, false], [9.12, 0, false]]) {
      add(new THREE.BoxGeometry(wide ? 18.5 : .14, .16, wide ? .14 : 18.5), railMaterial, x, -.08, z);
    }
    const accent = new THREE.MeshBasicMaterial({ color: 0x9abc62 });
    for (const x of [-8.5, 8.5]) {
      for (const z of [-9.15, 9.15]) add(new THREE.BoxGeometry(.75, .025, .16), accent, x, .012, z);
    }
    for (let i = 0; i < 6; i++) add(new THREE.BoxGeometry(.15, .1, .015), accent, -7.4 + i * .3, -.51, 9.505);
    this.body = new THREE.InstancedMesh(
      new RoundedBoxGeometry(.92, .64, .92, 6, .15),
      material(0xffffff, { roughness: .45, metalness: .05 }), 324,
    );
    this.body.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.body.frustumCulled = false;
    this.body.castShadow = true;
    this.body.receiveShadow = true;
    this.body.count = 0;
    this.scene.add(this.body);
    this.head = new THREE.Group();
    const headMesh = new THREE.Mesh(
      new RoundedBoxGeometry(.96, .72, .96, 6, .17),
      material(0xc6fa70, { emissive: 0x395812, emissiveIntensity: .12, roughness: .4 }),
    );
    headMesh.castShadow = true;
    this.head.add(headMesh);
    const white = material(0xf4ffe9);
    const pupil = material(0x162715);
    for (const z of [-.24, .24]) {
      const eye = new THREE.Mesh(new THREE.SphereGeometry(.12, 32, 24), white);
      eye.scale.y = .55;
      eye.position.set(.19, .365, z);
      const dot = new THREE.Mesh(new THREE.SphereGeometry(.051, 24, 16), pupil);
      dot.scale.y = .48;
      dot.position.set(.23, .422, z);
      this.head.add(eye, dot);
    }
    this.scene.add(this.head);
    this.food = add(new THREE.IcosahedronGeometry(.43, 0),
      material(0xff8b71, { emissive: 0xff5c3a, emissiveIntensity: .4, roughness: .34 }));
    this.food.castShadow = true;
    this.ring = add(new THREE.TorusGeometry(.53, .026, 16, 96),
      new THREE.MeshBasicMaterial({ color: 0xff997d, transparent: true, opacity: .62 }), 0, -.11);
    this.ring.rotation.x = Math.PI / 2;
    this.foodLight = new THREE.PointLight(0xff7c54, 4, 3.5, 2);
    this.scene.add(this.foodLight);
    const particleGeometry = new THREE.BoxGeometry(.12, .12, .12);
    const particleMaterial = new THREE.MeshBasicMaterial({ color: 0xffb990 });
    this.particles = Array.from({ length: 16 }, () => {
      const mesh = new THREE.Mesh(particleGeometry, particleMaterial);
      mesh.visible = false;
      this.scene.add(mesh);
      return { mesh, age: 1, velocity: new THREE.Vector3() };
    });
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(sceneContainer);
    this.resize();
  }
  resize() {
    const width = sceneContainer.clientWidth, height = sceneContainer.clientHeight;
    if (!width || !height) return;
    // Native display resolution, with no pixel budget or adaptive downscaling.
    this.renderer.setPixelRatio(devicePixelRatio || 1);
    this.renderer.setSize(width, height, false);
    const aspect = width / height, span = Math.max(16.7, 20.3 / aspect);
    Object.assign(this.camera, {
      left: -span * aspect / 2, right: span * aspect / 2,
      top: span / 2, bottom: -span / 2, near: .1, far: 100,
    });
    this.camera.updateProjectionMatrix();
    this.renderer.shadowMap.needsUpdate = true;
    lastRender = 0;
  }
  burst(position) {
    if (motion.matches || !position) return;
    this.particles.forEach((particle, index) => {
      const angle = index / this.particles.length * Math.PI * 2;
      particle.age = 0;
      particle.mesh.visible = true;
      particle.mesh.position.set(position[0] - 8.5, .5, position[1] - 8.5);
      particle.velocity.set(Math.cos(angle) * 2.6, 2 + Math.random(), Math.sin(angle) * 2.6);
    });
  }
  render(game, alpha, now, dt) {
    const time = motion.matches || state !== "running" ? 0 : now / 1000;
    this.dummy.rotation.set(0, 0, 0);
    this.body.count = game.snake.length - 1;
    game.snake.forEach((position, i) => {
      const previous = game.previous[Math.min(i, game.previous.length - 1)] || position;
      const x = previous[0] + (position[0] - previous[0]) * alpha - 8.5;
      const z = previous[1] + (position[1] - previous[1]) * alpha - 8.5;
      if (!i) {
        this.head.position.set(x, .3, z);
        this.head.rotation.y = [Math.PI / 2, 0, -Math.PI / 2, Math.PI][game.direction];
      } else {
        const scale = i === game.snake.length - 1 ? .83 : 1;
        this.dummy.position.set(x, .23, z);
        this.dummy.scale.set(scale, scale, scale);
        this.dummy.updateMatrix();
        this.body.setMatrixAt(i - 1, this.dummy.matrix);
        if (this.lastLength !== game.snake.length) {
          this.color.setHSL(.22 + .025 * i / game.snake.length, .68, .51 - .14 * i / game.snake.length);
          this.body.setColorAt(i - 1, this.color);
        }
      }
    });
    this.body.instanceMatrix.needsUpdate = true;
    if (this.body.instanceColor && this.lastLength !== game.snake.length) this.body.instanceColor.needsUpdate = true;
    this.lastLength = game.snake.length;
    this.food.visible = this.ring.visible = this.foodLight.visible = !!game.food;
    if (game.food) {
      const [x, z] = game.food.map(n => n - 8.5);
      this.food.position.set(x, .55 + Math.sin(time * 3) * .09, z);
      this.food.rotation.set(.25, time * .65, .15);
      this.foodLight.position.set(x, .8, z);
      this.ring.position.set(x, -.105, z);
      this.ring.scale.setScalar(1 + Math.sin(time * 3) * .1);
    }
    for (const particle of this.particles) {
      if (!particle.mesh.visible) continue;
      particle.age += dt;
      if (particle.age >= .6 || motion.matches) { particle.mesh.visible = false; continue; }
      particle.velocity.y -= dt * 7;
      particle.mesh.position.addScaledVector(particle.velocity, dt);
      particle.mesh.scale.setScalar(1 - particle.age / .6);
      particle.mesh.rotation.x += dt * 3;
    }
    this.renderer.render(this.scene, this.camera);
  }
  dispose() {
    this.observer.disconnect();
    const geometries = new Set(), materials = new Set();
    this.scene.traverse(object => {
      if (object.geometry) geometries.add(object.geometry);
      if (object.material) {
        for (const mat of Array.isArray(object.material) ? object.material : [object.material]) materials.add(mat);
      }
      if (object.shadow) object.shadow.dispose();
    });
    geometries.forEach(g => g.dispose());
    materials.forEach(m => m.dispose());
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}

class CompatibilityBoard {
  // A clearly labelled fallback keeps the game usable on WebGL-disabled hosts.
  constructor() {
    this.canvas = document.createElement("canvas");
    this.ctx = this.canvas.getContext("2d");
    if (!this.ctx) throw new Error("Canvas unavailable");
    $("scene").replaceChildren(this.canvas);
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(sceneContainer);
    this.resize();
  }
  resize() {
    this.ratio = devicePixelRatio || 1;
    this.canvas.width = sceneContainer.clientWidth * this.ratio;
    this.canvas.height = sceneContainer.clientHeight * this.ratio;
    lastRender = 0;
  }
  burst() {}
  render(game, alpha) {
    const ctx = this.ctx, w = sceneContainer.clientWidth, h = sceneContainer.clientHeight;
    ctx.setTransform(this.ratio, 0, 0, this.ratio, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const cell = Math.min((w - 30) / 18, (h - 75) / 14.4), dy = cell * .8;
    const left = (w - 18 * cell) / 2, top = (h - 18 * dy) / 2;
    ctx.fillStyle = "#1a2c20";
    ctx.fillRect(left - 4, top - 4, 18 * cell + 8, 18 * dy + 16);
    ctx.strokeStyle = "#597244";
    ctx.strokeRect(left - 4, top - 4, 18 * cell + 8, 18 * dy + 16);
    for (let y = 0; y < 18; y++) {
      for (let x = 0; x < 18; x++) {
        ctx.fillStyle = (x + y) % 2 ? "#254333" : "#213c2d";
        ctx.fillRect(left + x * cell, top + y * dy, cell - 1, dy - 1);
      }
    }
    for (let i = game.snake.length - 1; i >= 0; i--) {
      const p = game.snake[i], old = game.previous[Math.min(i, game.previous.length - 1)] || p;
      const x = left + (old[0] + (p[0] - old[0]) * alpha) * cell;
      const y = top + (old[1] + (p[1] - old[1]) * alpha) * dy;
      ctx.fillStyle = "#587c2c";
      ctx.fillRect(x + 1, y - cell * .1, cell - 2, dy);
      ctx.fillStyle = i === 0 ? "#ceff79" : "#a7d753";
      ctx.fillRect(x + 1, y - cell * .23, cell - 2, dy - 1);
      if (!i) {
        ctx.fillStyle = "#17311d";
        const [dx, dz] = DIRECTIONS[game.direction];
        for (const sign of [-1, 1]) {
          ctx.beginPath();
          ctx.arc(x + cell * (.5 + dx * .23 + dz * sign * .2),
            y - cell * .23 + dy * (.5 + dz * .23 - dx * sign * .2), cell * .075, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
    if (game.food) {
      ctx.save();
      ctx.translate(left + (game.food[0] + .5) * cell, top + (game.food[1] + .35) * dy);
      ctx.rotate(Math.PI / 4);
      ctx.fillStyle = "#ff987d";
      ctx.fillRect(-cell * .28, -cell * .28, cell * .56, cell * .56);
      ctx.restore();
    }
  }
  dispose() { this.observer.disconnect(); this.canvas.remove(); }
}

async function loadView() {
  try {
    const [THREE, rounded] = await withTimeout(Promise.all([
      import("three"), import("three/addons/geometries/RoundedBoxGeometry.js"),
    ]), 12000);
    if (disposed) return;
    view = new ThreeBoard(THREE, rounded.RoundedBoxGeometry);
    stage.dataset.renderer = "three";
  } catch {
    if (disposed) return;
    try {
      view = new CompatibilityBoard();
      $("renderer-label").textContent = "2D COMPATIBILITY";
      stage.dataset.renderer = "compatibility";
      notice("3D graphics aren't available in this host. You're playing in 2D compatibility mode.");
    } catch {
      $("load-note").textContent = "This host doesn't support game graphics. Try a browser with canvas/WebGL enabled.";
      $("start").disabled = $("practice").disabled = true;
      return;
    }
  }
  updateControls();
  frameId = requestAnimationFrame(animate);
}

function animate(now) {
  if (disposed) return;
  const rawDelta = now - lastFrame;
  lastFrame = now;
  const dt = Math.min(rawDelta, 100);
  if (rawDelta > 500 && ["running", "countdown"].includes(state)) {
    pause("Paused automatically while the App was away or the display was busy.");
  }
  if (state === "countdown") {
    countdownMs -= dt;
    const count = Math.max(1, Math.ceil(countdownMs / 700));
    if ($("count-number").textContent !== String(count)) tone(390 + (3 - count) * 100, .06);
    $("count-number").textContent = String(count);
    if (countdownMs <= 0) {
      accumulator = 0;
      setState("running");
      tone(690, .1);
    }
  } else if (state === "running") {
    accumulator += dt;
    while (state === "running" && accumulator >= engine.interval) {
      accumulator -= engine.interval;
      const next = queue.length ? queue.shift() : engine.direction;
      const food = engine.food;
      const ate = engine.step(next);
      trace += String(next);
      if (ate) {
        view.burst(food);
        tone(engine.apples % 5 === 0 ? 930 : 610, .1);
        if (!motion.matches) {
          $("score").classList.remove("pulse");
          void $("score").offsetWidth;
          $("score").classList.add("pulse");
        }
        announce(`${engine.score} points. Level ${engine.level}.`);
      }
      updateHud();
      if (engine.over) finishGame();
    }
  }
  const alpha = state === "running" ? movementAlpha(accumulator, engine.interval, motion.matches) : 1;
  // Render every animation frame during play, including high-refresh displays.
  // Idle screens stay static; this does not change resolution or effects.
  const cadence = state === "running" ? 0 : 200;
  if (!document.hidden && now - lastRender >= cadence) {
    view.render(engine, alpha, now, Math.min((now - lastRender) / 1000, .1));
    lastRender = now;
  }
  frameId = requestAnimationFrame(animate);
}

function hostContext(context) {
  const previousMode = host.displayMode;
  host = { ...host, ...context };
  const root = document.documentElement;
  root.dataset.displayMode = host.displayMode || "inline";
  for (const edge of ["top", "bottom"]) {
    const inset = host.safeAreaInsets?.[edge];
    if (typeof inset === "number" && Number.isFinite(inset)) {
      root.style.setProperty(`--safe-${edge}`, `${Math.max(0, Math.min(inset, 100))}px`);
    }
  }
  for (const [key, property] of [["height", "--app-height"], ["maxHeight", "--app-max-height"]]) {
    const value = host.containerDimensions?.[key];
    if (typeof value === "number" && Number.isFinite(value) && value > 0) {
      root.style.setProperty(property, `${value}px`);
    } else root.style.removeProperty(property);
  }
  if (previousMode !== host.displayMode) pause("Display size changed. Resume when you're ready.");
  updateControls();
  if (connected && !fullscreenAttempted && host.availableDisplayModes?.includes("fullscreen")) {
    fullscreenAttempted = true;
    if (host.displayMode !== "fullscreen") void changeDisplay("fullscreen", true);
  }
}
async function changeDisplay(mode, automatic = false) {
  if (!connected || displayBusy || !host.availableDisplayModes?.includes(mode)) return;
  displayBusy = true;
  pause("Changing display size. Resume when you're ready.");
  updateControls();
  try {
    // The host owns fullscreen. Respect its actual response, including refusal.
    const result = await app.requestDisplayMode({ mode }, { timeout: 5000 });
    if (disposed) return;
    hostContext({ displayMode: result.mode });
    if (result.mode !== mode && !automatic) notice("This host kept the game inline. The board still fills the available App area.");
  } catch {
    if (!automatic) notice("Fullscreen isn't available in this host. You can keep playing inline.");
  } finally {
    displayBusy = false;
    updateControls();
  }
}
function guest(message) {
  connectionFailed = true;
  if (!snapshot) {
    $("player-name").textContent = "Guest player";
    $("avatar").textContent = "P";
    $("player-email").textContent = "Practice mode · scores are not saved";
    $("board-state-text").textContent = "PRACTICE ONLY";
    $("empty-title").textContent = "Play now. Rank when signed in.";
    $("empty-copy").textContent = "Open in a signed-in MCP App to record scores automatically.";
  }
  if (message) notice(message);
  updateControls();
}
async function connectHost() {
  if (window.parent === window) {
    document.documentElement.dataset.standalone = "true";
    guest();
    return;
  }
  const delayed = setTimeout(() => guest("Player connection is taking a while. You can practice now; ranked play needs the MCP connection."), 10000);
  try {
    const { App } = await import("https://cdn.jsdelivr.net/npm/@modelcontextprotocol/ext-apps@2.0.0/dist/src/app-with-deps.js");
    if (disposed) return;
    app = new App({ name: "Neon Snake", version: "1.2.0" });
    // Register notification handlers BEFORE the bridge handshake.
    app.ontoolresult = result => {
      try { applySnapshot(unpack(result)); }
      catch (error) { notice(error.message); }
    };
    app.onhostcontextchanged = hostContext;
    app.onteardown = async () => { dispose(); return {}; };
    await app.connect();
    if (disposed) return;
    connected = true;
    connectionFailed = false;
    clearTimeout(delayed);
    hostContext(app.getHostContext());
    updateControls();
    await sleep(250); // Hosts deliver the initial tool result just after initialization.
    if (!snapshot) applySnapshot(await rpc("new_tool"));
  } catch {
    clearTimeout(delayed);
    guest("The score connection isn't available. Practice works without it; reopen the App to reconnect.");
  }
}

on($("start"), "click", () => void startGame());
on($("practice"), "click", () => void startGame(true));
on($("again"), "click", () => void startGame(!ranked));
on($("back-to-menu"), "click", backToMenu);
on($("resume"), "click", resume);
on($("pause-button"), "click", () => {
  if (state === "paused") resume(); else { pause(); focusBoard(); }
});
on($("fullscreen-button"), "click", () =>
  void changeDisplay(host.displayMode === "fullscreen" ? "inline" : "fullscreen"));
on($("leaderboard-button"), "click", () => {
  showDialog("leaderboard-dialog");
  void refreshBoard(true);
});
on($("dismiss-banner"), "click", () => notice(""));
on($("retry-save"), "click", () => { if (lastCompleted?.id) void savePending(lastCompleted.id); });
on($("refresh"), "click", async () => { await retryPending(); await refreshBoard(); });
for (const scope of ["all", "mine"]) {
  on($(`scope-${scope}`), "click", () => {
    boardScope = scope;
    updateControls();
    void refreshBoard();
  });
}
on($("complete-profile"), "click", () => openProfile(false));
async function saveProfile(event) {
  event.preventDefault();
  if ($("save-profile").disabled || !$("profile-form").reportValidity()) return;
  $("save-profile").disabled = true;
  $("profile-error").hidden = true;
  try {
    const data = await rpc("neon_snake_profile", {
      display_name: $("profile-name").disabled ? "" : $("profile-name").value.trim(),
      email: $("profile-email").disabled ? "" : $("profile-email").value.trim(),
    });
    applySnapshot(data);
    $("profile-form").reset();
    $("profile-dialog").close();
    if (profileStartsGame) await startGame();
  } catch (error) {
    $("profile-error").textContent = error.message;
    $("profile-error").hidden = false;
  } finally { $("save-profile").disabled = false; }
}
// Handle clicks directly: MCP sandboxes may intentionally disallow native
// form submission. Validation still runs, and all data uses the MCP bridge.
on($("profile-form"), "submit", saveProfile);
on($("save-profile"), "click", saveProfile);
on($("profile-form"), "keydown", event => {
  if (event.key === "Enter" && event.target.matches("input")) {
    event.preventDefault();
    $("save-profile").click();
  }
});
on($("help-button"), "click", () => {
  showDialog("help-dialog");
});
on($("data-button"), "click", () => {
  $("delete-form").reset();
  $("delete-error").hidden = true;
  updateControls();
  showDialog("data-dialog");
});
document.querySelectorAll("[data-close]").forEach(button =>
  on(button, "click", () => $(button.dataset.close).close()));
document.querySelectorAll("dialog").forEach(dialog => {
  on(dialog, "close", () => {
    if (activeDialog !== dialog) return; // Switching from scores to privacy/profile.
    activeDialog = null;
    const shouldResume = resumeAfterDialog;
    resumeAfterDialog = false;
    if (shouldResume) resume();
    else if (["paused", "running", "countdown"].includes(state)) focusBoard();
  });
  on(dialog, "click", event => {
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right ||
        event.clientY < box.top || event.clientY > box.bottom) dialog.close();
  });
});
async function deleteData(event) {
  event.preventDefault();
  if ($("delete-data").disabled || !$("delete-form").reportValidity()) return;
  $("delete-data").disabled = true;
  try {
    const data = await rpc("neon_snake_forget", { confirm: true });
    boardRequest++;
    boardBusy = false;
    boardScope = "all";
    applySnapshot(data);
    $("data-dialog").close();
    backToMenu();
    notice("Your profile and all runs were deleted from the active database.");
    announce("Your score data was deleted.");
  } catch (error) {
    $("delete-error").textContent = error.message;
    $("delete-error").hidden = false;
  } finally { updateControls(); }
}
on($("delete-form"), "submit", deleteData);
on($("delete-data"), "click", deleteData);
on($("sound-button"), "click", async () => {
  try {
    if (!audio) {
      const Audio = window.AudioContext || window.webkitAudioContext;
      if (!Audio) throw new Error("Audio unavailable");
      audio = new Audio();
    }
    if (audio.state === "suspended") await audio.resume();
    sound = !sound;
    $("sound-button").setAttribute("aria-pressed", String(sound));
    const label = sound ? "Mute game sounds" : "Enable game sounds";
    $("sound-button").setAttribute("aria-label", label);
    $("sound-button").title = label;
    $("sound-icon").setAttribute("href", sound ? "#i-sound" : "#i-mute");
    if (sound) tone(550);
  } catch { notice("Game sounds aren't available in this host. You can keep playing silently."); }
});

const keyDirections = { ArrowUp: 0, ArrowRight: 1, ArrowDown: 2, ArrowLeft: 3, w: 0, d: 1, s: 2, a: 3 };
on(document, "keydown", event => {
  if (activeDialog || event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey ||
      event.target.closest?.("input, textarea, select, [contenteditable='true']")) return;
  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
  if (key in keyDirections && ["running", "countdown"].includes(state)) {
    event.preventDefault();
    // OS key repeat must not add stale turns behind a fresh direction.
    if (!event.repeat) turn(keyDirections[key]);
  } else if ([" ", "p", "Escape"].includes(key) && ["running", "countdown", "paused"].includes(state)) {
    if (key === " " && event.target.closest?.("button")) return; // Native keyboard activation.
    event.preventDefault();
    if (event.repeat) return;
    if (state === "paused" && key !== "Escape") resume(); else pause();
  }
}, { capture: true });
document.querySelectorAll("[data-direction]").forEach(button => {
  on(button, "pointerdown", event => {
    if (!event.isPrimary || event.button !== 0) return;
    event.preventDefault();
    button.setPointerCapture(event.pointerId);
    button.classList.add("held");
    turn(Number(button.dataset.direction)); // Act on contact, not release/click.
    focusBoard();
  });
  for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) {
    on(button, type, () => button.classList.remove("held"));
  }
  on(button, "click", event => {
    if (event.detail !== 0) return; // Pointer input was already handled above.
    turn(Number(button.dataset.direction)); // Keyboard and assistive activation.
    focusBoard();
  });
});
let pointer = null;
on(stage, "pointerdown", event => {
  if (activeDialog || !event.isPrimary || event.button !== 0 ||
      event.target.closest("button, .overlay-card") || !["running", "countdown"].includes(state)) return;
  event.preventDefault();
  focusBoard();
  pointer = { id: event.pointerId, x: event.clientX, y: event.clientY };
  stage.setPointerCapture(event.pointerId);
}, { passive: false });
on(stage, "pointermove", event => {
  if (!pointer || pointer.id !== event.pointerId) return;
  const dx = event.clientX - pointer.x, dy = event.clientY - pointer.y;
  if (Math.max(Math.abs(dx), Math.abs(dy)) < 8) return;
  event.preventDefault();
  turn(Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 1 : 3) : (dy > 0 ? 2 : 0));
  pointer.x = event.clientX;
  pointer.y = event.clientY;
}, { passive: false });
on(stage, "pointerup", () => { pointer = null; });
on(stage, "pointercancel", () => { pointer = null; });
on(stage, "lostpointercapture", () => { pointer = null; });
on(window, "blur", () => pause("Paused automatically when you left the App."));
on(document, "visibilitychange", () => {
  if (document.hidden) pause("Paused automatically while the App was hidden.");
  lastFrame = performance.now();
});
on(window, "online", () => void retryPending());
on(window, "resize", () => {
  if (activeDialog?.open) placeDialog(activeDialog);
});
const visibleObserver = new IntersectionObserver(entries => {
  if (entries[0] && !entries[0].isIntersecting) pause("Paused while the board was out of view.");
});
visibleObserver.observe(stage);
const poll = setInterval(() => {
  if (document.hidden || disposed || !connected) return;
  void retryPending();
  if ($("leaderboard-dialog").open && !boardBusy && !startBusy) void refreshBoard(true);
}, 20000);
function dispose() {
  if (disposed) return;
  disposed = true;
  cancelAnimationFrame(frameId);
  clearInterval(poll);
  visibleObserver.disconnect();
  events.abort();
  view?.dispose();
  if (audio) void audio.close().catch(() => {});
}
on(window, "pagehide", dispose);

setState("ready");
void loadView();
void connectHost();