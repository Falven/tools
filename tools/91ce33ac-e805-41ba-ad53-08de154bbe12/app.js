import { App } from "https://cdn.jsdelivr.net/npm/@modelcontextprotocol/ext-apps@2.0.0/dist/src/app-with-deps.js";

const COLS = 10;
const ROWS = 20;
const SCORE_TABLE = [0, 100, 300, 500, 800];
const COLORS = {
  I: "#43e8ff",
  J: "#668cff",
  L: "#ff9d4d",
  O: "#ffe66d",
  S: "#69f0a8",
  T: "#c875ff",
  Z: "#ff5a86",
};
const SHAPES = {
  I: [[0,0,0,0],[1,1,1,1],[0,0,0,0],[0,0,0,0]],
  J: [[1,0,0],[1,1,1],[0,0,0]],
  L: [[0,0,1],[1,1,1],[0,0,0]],
  O: [[1,1],[1,1]],
  S: [[0,1,1],[1,1,0],[0,0,0]],
  T: [[0,1,0],[1,1,1],[0,0,0]],
  Z: [[1,1,0],[0,1,1],[0,0,0]],
};

const boardCanvas = document.querySelector("#board");
const ctx = boardCanvas.getContext("2d");
const nextCanvas = document.querySelector("#next");
const nextCtx = nextCanvas.getContext("2d");
const overlay = document.querySelector("#overlay");
const overlayTitle = document.querySelector("#overlay-title");
const overlayEyebrow = document.querySelector("#overlay-eyebrow");
const overlayCopy = document.querySelector("#overlay-copy");
const overlayAction = document.querySelector("#overlay-action");
const pauseButton = document.querySelector("#pause");
const status = document.querySelector("#status");
const scoreNodes = document.querySelectorAll("[data-score]");
const bestNodes = document.querySelectorAll("[data-best]");
const linesNodes = document.querySelectorAll("[data-lines]");
const levelNodes = document.querySelectorAll("[data-level]");

let board;
let player;
let nextType;
let bag = [];
let score = 0;
let lines = 0;
let level = 1;
let best = Number(localStorage.getItem("neon-blocks-best") || 0);
let paused = false;
let gameOver = false;
let lastTime = 0;
let dropCounter = 0;
let animationId = 0;
let flashRows = [];
let shakeUntil = 0;
let appConnected = false;

const mcpApp = new App({ name: "Neon Blocks", version: "1.0.0" });
mcpApp.ontoolresult = () => {};

function emptyBoard() {
  return Array.from({ length: ROWS }, () => Array(COLS).fill(""));
}

function shuffle(values) {
  for (let i = values.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [values[i], values[j]] = [values[j], values[i]];
  }
  return values;
}

function drawFromBag() {
  if (!bag.length) bag = shuffle(Object.keys(SHAPES));
  return bag.pop();
}

function cloneMatrix(matrix) {
  return matrix.map((row) => [...row]);
}

function spawn() {
  const type = nextType || drawFromBag();
  nextType = drawFromBag();
  const matrix = cloneMatrix(SHAPES[type]);
  player = {
    type,
    matrix,
    x: Math.floor((COLS - matrix[0].length) / 2),
    y: type === "I" ? -1 : 0,
  };
  drawNext();
  if (collides(player.x, player.y, player.matrix)) endGame();
}

function collides(x, y, matrix) {
  for (let row = 0; row < matrix.length; row++) {
    for (let col = 0; col < matrix[row].length; col++) {
      if (!matrix[row][col]) continue;
      const bx = x + col;
      const by = y + row;
      if (bx < 0 || bx >= COLS || by >= ROWS) return true;
      if (by >= 0 && board[by][bx]) return true;
    }
  }
  return false;
}

function merge() {
  let aboveTop = false;
  player.matrix.forEach((row, y) => row.forEach((value, x) => {
    if (!value) return;
    const by = player.y + y;
    if (by < 0) aboveTop = true;
    else board[by][player.x + x] = player.type;
  }));
  if (aboveTop) endGame();
}

function rotateMatrix(matrix, clockwise = true) {
  const size = matrix.length;
  return Array.from({ length: size }, (_, y) =>
    Array.from({ length: size }, (_, x) =>
      clockwise ? matrix[size - 1 - x][y] : matrix[x][size - 1 - y]
    )
  );
}

function rotate(clockwise = true) {
  if (paused || gameOver) return;
  const rotated = rotateMatrix(player.matrix, clockwise);
  const originalX = player.x;
  for (const offset of [0, -1, 1, -2, 2]) {
    player.x = originalX + offset;
    if (!collides(player.x, player.y, rotated)) {
      player.matrix = rotated;
      return;
    }
  }
  player.x = originalX;
}

function move(direction) {
  if (paused || gameOver) return;
  if (!collides(player.x + direction, player.y, player.matrix)) player.x += direction;
}

function drop(manual = false) {
  if (paused || gameOver) return;
  if (!collides(player.x, player.y + 1, player.matrix)) {
    player.y++;
    if (manual) score += 1;
  } else {
    lockPiece();
  }
  dropCounter = 0;
  updateStats();
}

function hardDrop() {
  if (paused || gameOver) return;
  let distance = 0;
  while (!collides(player.x, player.y + 1, player.matrix)) {
    player.y++;
    distance++;
  }
  score += distance * 2;
  shakeUntil = performance.now() + 90;
  lockPiece();
}

function lockPiece() {
  merge();
  if (gameOver) return;
  clearLines();
  spawn();
  updateStats();
}

function clearLines() {
  const completed = [];
  for (let y = ROWS - 1; y >= 0; y--) {
    if (board[y].every(Boolean)) completed.push(y);
  }
  if (!completed.length) return;

  flashRows = completed.map((row) => ({ row, until: performance.now() + 130 }));
  completed.sort((a, b) => b - a).forEach((row) => {
    board.splice(row, 1);
    board.unshift(Array(COLS).fill(""));
  });
  const count = completed.length;
  lines += count;
  score += SCORE_TABLE[count] * level;
  level = Math.floor(lines / 10) + 1;
  status.textContent = count === 4 ? "TETRIS! +800 × level" : `${count} line${count > 1 ? "s" : ""} cleared`;
  window.setTimeout(() => {
    if (!gameOver && !paused) status.textContent = "Arrow keys to move · Space to drop";
  }, 1000);
}

function ghostY() {
  let y = player.y;
  while (!collides(player.x, y + 1, player.matrix)) y++;
  return y;
}

function cellPath(renderCtx, x, y, size, radius = 4) {
  const pad = Math.max(1, size * .055);
  const px = x * size + pad;
  const py = y * size + pad;
  const w = size - pad * 2;
  const r = Math.min(radius, w / 4);
  renderCtx.beginPath();
  renderCtx.roundRect(px, py, w, w, r);
}

function drawCell(renderCtx, x, y, size, color, ghost = false) {
  cellPath(renderCtx, x, y, size);
  if (ghost) {
    renderCtx.strokeStyle = color;
    renderCtx.globalAlpha = .33;
    renderCtx.lineWidth = Math.max(1, size * .07);
    renderCtx.stroke();
    renderCtx.globalAlpha = 1;
    return;
  }
  const gradient = renderCtx.createLinearGradient(x * size, y * size, (x + 1) * size, (y + 1) * size);
  gradient.addColorStop(0, color);
  gradient.addColorStop(1, shadeColor(color, -28));
  renderCtx.fillStyle = gradient;
  renderCtx.shadowColor = color;
  renderCtx.shadowBlur = size * .22;
  renderCtx.fill();
  renderCtx.shadowBlur = 0;
  renderCtx.globalAlpha = .25;
  renderCtx.fillStyle = "#ffffff";
  renderCtx.fillRect(x * size + size * .17, y * size + size * .14, size * .56, Math.max(1, size * .06));
  renderCtx.globalAlpha = 1;
}

function shadeColor(hex, amount) {
  const value = parseInt(hex.slice(1), 16);
  const r = Math.max(0, Math.min(255, (value >> 16) + amount));
  const g = Math.max(0, Math.min(255, ((value >> 8) & 255) + amount));
  const b = Math.max(0, Math.min(255, (value & 255) + amount));
  return `rgb(${r},${g},${b})`;
}

function resizeCanvas(canvas, context, cssWidth, cssHeight) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.round(cssWidth * dpr);
  const height = Math.round(cssHeight * dpr);
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function drawBoard(time = 0) {
  const rect = boardCanvas.getBoundingClientRect();
  resizeCanvas(boardCanvas, ctx, rect.width, rect.height);
  const size = rect.width / COLS;
  ctx.clearRect(0, 0, rect.width, rect.height);

  const background = ctx.createLinearGradient(0, 0, 0, rect.height);
  background.addColorStop(0, "#0c1022");
  background.addColorStop(1, "#070914");
  ctx.fillStyle = background;
  ctx.fillRect(0, 0, rect.width, rect.height);

  ctx.strokeStyle = "rgba(151, 167, 255, .065)";
  ctx.lineWidth = 1;
  for (let x = 1; x < COLS; x++) {
    ctx.beginPath();
    ctx.moveTo(x * size, 0);
    ctx.lineTo(x * size, rect.height);
    ctx.stroke();
  }
  for (let y = 1; y < ROWS; y++) {
    ctx.beginPath();
    ctx.moveTo(0, y * size);
    ctx.lineTo(rect.width, y * size);
    ctx.stroke();
  }

  board.forEach((row, y) => row.forEach((type, x) => {
    if (type) drawCell(ctx, x, y, size, COLORS[type]);
  }));

  if (player && !gameOver) {
    const gy = ghostY();
    player.matrix.forEach((row, y) => row.forEach((value, x) => {
      if (value && gy + y >= 0) drawCell(ctx, player.x + x, gy + y, size, COLORS[player.type], true);
    }));
    player.matrix.forEach((row, y) => row.forEach((value, x) => {
      if (value && player.y + y >= 0) drawCell(ctx, player.x + x, player.y + y, size, COLORS[player.type]);
    }));
  }

  flashRows = flashRows.filter((item) => item.until > time);
  flashRows.forEach((item) => {
    ctx.fillStyle = `rgba(255,255,255,${Math.max(0, (item.until - time) / 130) * .7})`;
    ctx.fillRect(0, item.row * size, rect.width, size);
  });

  const shell = boardCanvas.parentElement;
  shell.style.transform = time < shakeUntil
    ? `translateX(${Math.sin(time * .7) * 3}px)`
    : "";
}

function drawNext() {
  const rect = nextCanvas.getBoundingClientRect();
  if (!rect.width) return;
  resizeCanvas(nextCanvas, nextCtx, rect.width, rect.height);
  nextCtx.clearRect(0, 0, rect.width, rect.height);
  const matrix = SHAPES[nextType];
  const occupied = [];
  matrix.forEach((row, y) => row.forEach((value, x) => {
    if (value) occupied.push({ x, y });
  }));
  const minX = Math.min(...occupied.map((p) => p.x));
  const maxX = Math.max(...occupied.map((p) => p.x));
  const minY = Math.min(...occupied.map((p) => p.y));
  const maxY = Math.max(...occupied.map((p) => p.y));
  const pieceW = maxX - minX + 1;
  const pieceH = maxY - minY + 1;
  const size = Math.min(rect.width / 5.2, rect.height / 3.3);
  const offsetX = (rect.width - pieceW * size) / 2 - minX * size;
  const offsetY = (rect.height - pieceH * size) / 2 - minY * size;
  nextCtx.save();
  nextCtx.translate(offsetX, offsetY);
  occupied.forEach(({ x, y }) => drawCell(nextCtx, x, y, size, COLORS[nextType]));
  nextCtx.restore();
}

function updateStats() {
  if (score > best) {
    best = score;
    localStorage.setItem("neon-blocks-best", String(best));
  }
  scoreNodes.forEach((node) => { node.textContent = score.toLocaleString(); });
  bestNodes.forEach((node) => { node.textContent = best.toLocaleString(); });
  linesNodes.forEach((node) => { node.textContent = lines; });
  levelNodes.forEach((node) => { node.textContent = level; });
}

function resetGame() {
  board = emptyBoard();
  bag = [];
  score = 0;
  lines = 0;
  level = 1;
  paused = false;
  gameOver = false;
  nextType = drawFromBag();
  dropCounter = 0;
  lastTime = performance.now();
  overlay.classList.remove("show");
  pauseButton.textContent = "Ⅱ";
  pauseButton.setAttribute("aria-label", "Pause game");
  status.textContent = "Arrow keys to move · Space to drop";
  spawn();
  updateStats();
}

function showPause() {
  overlayEyebrow.textContent = "Game paused";
  overlayTitle.textContent = "Paused";
  overlayCopy.textContent = "Take a breath. Your stack will wait.";
  overlayAction.textContent = "Resume";
  overlay.classList.add("show");
}

function togglePause(force) {
  if (gameOver) return;
  paused = typeof force === "boolean" ? force : !paused;
  pauseButton.textContent = paused ? "▶" : "Ⅱ";
  pauseButton.setAttribute("aria-label", paused ? "Resume game" : "Pause game");
  if (paused) {
    showPause();
    status.textContent = "Paused";
  } else {
    overlay.classList.remove("show");
    status.textContent = "Arrow keys to move · Space to drop";
    lastTime = performance.now();
  }
}

function endGame() {
  gameOver = true;
  paused = false;
  if (score > best) {
    best = score;
    localStorage.setItem("neon-blocks-best", String(best));
  }
  updateStats();
  overlayEyebrow.textContent = score >= best && score > 0 ? "New high score" : "Stack reached the top";
  overlayTitle.textContent = "Game Over";
  overlayCopy.textContent = `${score.toLocaleString()} points · ${lines} line${lines === 1 ? "" : "s"} cleared`;
  overlayAction.textContent = "Play Again";
  overlay.classList.add("show");
  status.textContent = "Press R to restart";
  if (appConnected) {
    mcpApp.updateModelContext({
      structuredContent: { game: "Neon Blocks", score, lines, level, highScore: best },
    }).catch(() => {});
  }
}

function update(time = 0) {
  const delta = Math.min(time - lastTime, 100);
  lastTime = time;
  if (!paused && !gameOver) {
    dropCounter += delta;
    const interval = Math.max(90, 900 * Math.pow(.84, level - 1));
    if (dropCounter > interval) drop(false);
  }
  drawBoard(time);
  animationId = requestAnimationFrame(update);
}

function handleAction(action) {
  if (action === "left") move(-1);
  else if (action === "right") move(1);
  else if (action === "rotate") rotate(true);
  else if (action === "drop") hardDrop();
}

document.addEventListener("keydown", (event) => {
  const key = event.key.toLowerCase();
  const handled = ["arrowleft", "arrowright", "arrowdown", "arrowup", " ", "a", "d", "s", "w", "x", "z", "p", "r", "escape"];
  if (handled.includes(key)) event.preventDefault();
  if (key === "p" || key === "escape") togglePause();
  else if (key === "r") resetGame();
  else if (!paused && !gameOver) {
    if (key === "arrowleft" || key === "a") move(-1);
    else if (key === "arrowright" || key === "d") move(1);
    else if (key === "arrowdown" || key === "s") drop(true);
    else if (key === "arrowup" || key === "w" || key === "x") rotate(true);
    else if (key === "z") rotate(false);
    else if (key === " ") hardDrop();
  }
});

document.querySelectorAll("[data-action]").forEach((button) => {
  let repeatTimer;
  const start = (event) => {
    event.preventDefault();
    const action = button.dataset.action;
    handleAction(action);
    if (action === "left" || action === "right") {
      repeatTimer = window.setInterval(() => handleAction(action), 115);
    }
  };
  const stop = () => window.clearInterval(repeatTimer);
  button.addEventListener("pointerdown", start);
  button.addEventListener("pointerup", stop);
  button.addEventListener("pointercancel", stop);
  button.addEventListener("pointerleave", stop);
});

let touchStart = null;
document.querySelector("#touch-zone").addEventListener("pointerdown", (event) => {
  if (event.pointerType === "touch") touchStart = { x: event.clientX, y: event.clientY, time: performance.now() };
});
document.querySelector("#touch-zone").addEventListener("pointerup", (event) => {
  if (!touchStart || event.pointerType !== "touch" || paused || gameOver) return;
  const dx = event.clientX - touchStart.x;
  const dy = event.clientY - touchStart.y;
  const elapsed = performance.now() - touchStart.time;
  touchStart = null;
  if (Math.abs(dx) < 18 && Math.abs(dy) < 18) rotate(true);
  else if (Math.abs(dx) > Math.abs(dy)) move(dx > 0 ? 1 : -1);
  else if (dy > 70 && elapsed < 500) hardDrop();
  else if (dy > 15) drop(true);
});

pauseButton.addEventListener("click", () => togglePause());
overlayAction.addEventListener("click", () => {
  if (gameOver) resetGame();
  else togglePause(false);
});
window.addEventListener("resize", () => {
  drawBoard(performance.now());
  drawNext();
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden && !gameOver) togglePause(true);
});

bestNodes.forEach((node) => { node.textContent = best.toLocaleString(); });
resetGame();
cancelAnimationFrame(animationId);
animationId = requestAnimationFrame(update);

try {
  await mcpApp.connect();
  appConnected = true;
} catch (error) {
  console.warn("MCP app bridge unavailable; game remains playable.", error);
}
