import { App } from "https://cdn.jsdelivr.net/npm/@modelcontextprotocol/ext-apps@2.0.0/dist/src/app-with-deps.js";

const canvas = document.querySelector("#board");
const ctx = canvas.getContext("2d");
const scoreEl = document.querySelector("#score");
const bestEl = document.querySelector("#best");
const overlay = document.querySelector("#overlay");
const overlayTitle = document.querySelector("#overlay-title");
const overlayCopy = document.querySelector("#overlay-copy");
const startBtn = document.querySelector("#start");
const pauseBtn = document.querySelector("#pause");
const announcer = document.querySelector("#announcer");
const saveScoreBtn = document.querySelector("#save-score");
const showScoresBtn = document.querySelector("#show-scores");
const leaderboardDialog = document.querySelector("#leaderboard-dialog");
const closeScoresBtn = document.querySelector("#close-scores");
const saveCard = document.querySelector("#save-card");
const finishedScoreEl = document.querySelector("#finished-score");
const playerIdentityEl = document.querySelector("#player-identity");
const confirmSaveBtn = document.querySelector("#confirm-save");
const leaderboardStatus = document.querySelector("#leaderboard-status");
const scoreList = document.querySelector("#score-list");

const GRID = 20;
const CELL = canvas.width / GRID;
const DIRECTIONS = {
  up: { x: 0, y: -1 },
  down: { x: 0, y: 1 },
  left: { x: -1, y: 0 },
  right: { x: 1, y: 0 },
};
const KEY_DIR = {
  ArrowUp: "up", w: "up", W: "up",
  ArrowDown: "down", s: "down", S: "down",
  ArrowLeft: "left", a: "left", A: "left",
  ArrowRight: "right", d: "right", D: "right",
};

let snake = [];
let berry = { x: 14, y: 10 };
let direction = DIRECTIONS.right;
let pendingDirection = DIRECTIONS.right;
let score = 0;
let best = Number(localStorage.getItem("snake-best") || 0);
let tickMs = 135;
let timer = null;
let state = "ready";
let touchStart = null;
let currentGameId = null;
let finishedGameId = null;
let finishedScore = 0;
let currentPlayer = null;
let bridgeReady = false;
bestEl.textContent = String(best);

function roundedRect(x, y, width, height, radius) {
  ctx.beginPath();
  ctx.roundRect(x, y, width, height, radius);
}

function drawBoard() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#0b1710";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.strokeStyle = "rgba(160, 255, 142, .045)";
  ctx.lineWidth = 1;
  for (let i = 1; i < GRID; i += 1) {
    ctx.beginPath();
    ctx.moveTo(i * CELL, 0);
    ctx.lineTo(i * CELL, canvas.height);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(0, i * CELL);
    ctx.lineTo(canvas.width, i * CELL);
    ctx.stroke();
  }

  const pulse = 1 + Math.sin(Date.now() / 180) * .04;
  const berrySize = CELL * .64 * pulse;
  const berryX = berry.x * CELL + CELL / 2;
  const berryY = berry.y * CELL + CELL / 2;
  ctx.save();
  ctx.shadowColor = "rgba(255, 79, 120, .6)";
  ctx.shadowBlur = 18;
  ctx.fillStyle = "#ff4f78";
  ctx.beginPath();
  ctx.arc(berryX, berryY, berrySize / 2, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
  ctx.fillStyle = "#b9ff88";
  ctx.beginPath();
  ctx.ellipse(berryX + 5, berryY - berrySize / 2 - 2, 5, 9, .7, 0, Math.PI * 2);
  ctx.fill();

  snake.forEach((part, index) => {
    const pad = index === 0 ? 2 : 3;
    const x = part.x * CELL + pad;
    const y = part.y * CELL + pad;
    const size = CELL - pad * 2;
    ctx.fillStyle = index === 0
      ? "#a2ff7e"
      : `hsl(${126 + Math.min(index, 30)}, 69%, ${58 - Math.min(index, 24) * .55}%)`;
    roundedRect(x, y, size, size, index === 0 ? 9 : 7);
    ctx.fill();

    if (index === 0) {
      const eyeOffsetX = direction.x === 0 ? 7 : (direction.x > 0 ? 19 : 8);
      const eyeY1 = direction.y > 0 ? 19 : 9;
      const eyeY2 = direction.y < 0 ? 9 : 19;
      ctx.fillStyle = "#102016";
      const eyes = direction.x === 0
        ? [[x + 8, y + (direction.y > 0 ? 19 : 8)], [x + 19, y + (direction.y > 0 ? 19 : 8)]]
        : [[x + eyeOffsetX, y + eyeY1], [x + eyeOffsetX, y + eyeY2]];
      for (const [eyeX, eyeY] of eyes) {
        ctx.beginPath();
        ctx.arc(eyeX, eyeY, 2.5, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  });
}

function placeBerry() {
  const open = [];
  for (let y = 0; y < GRID; y += 1) {
    for (let x = 0; x < GRID; x += 1) {
      if (!snake.some(part => part.x === x && part.y === y)) open.push({ x, y });
    }
  }
  berry = open[Math.floor(Math.random() * open.length)] || { x: 0, y: 0 };
}

function reset() {
  snake = [{ x: 6, y: 10 }, { x: 5, y: 10 }, { x: 4, y: 10 }];
  direction = DIRECTIONS.right;
  pendingDirection = DIRECTIONS.right;
  score = 0;
  tickMs = 135;
  scoreEl.textContent = "0";
  placeBerry();
  drawBoard();
}

function schedule() {
  clearTimeout(timer);
  if (state === "playing") timer = setTimeout(step, tickMs);
}

function step() {
  direction = pendingDirection;
  const head = snake[0];
  const next = { x: head.x + direction.x, y: head.y + direction.y };
  const hitWall = next.x < 0 || next.x >= GRID || next.y < 0 || next.y >= GRID;
  const willEat = next.x === berry.x && next.y === berry.y;
  const bodyToCheck = willEat ? snake : snake.slice(0, -1);
  const hitSelf = bodyToCheck.some(part => part.x === next.x && part.y === next.y);

  if (hitWall || hitSelf) {
    gameOver();
    return;
  }

  snake.unshift(next);
  if (willEat) {
    score += 10;
    scoreEl.textContent = String(score);
    if (score > best) {
      best = score;
      bestEl.textContent = String(best);
      localStorage.setItem("snake-best", String(best));
    }
    tickMs = Math.max(62, 135 - Math.floor(score / 40) * 8);
    placeBerry();
    announcer.textContent = `Berry eaten. Score ${score}.`;
  } else {
    snake.pop();
  }
  drawBoard();
  schedule();
}

function begin() {
  reset();
  currentGameId = globalThis.crypto?.randomUUID?.()
    || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  finishedGameId = null;
  finishedScore = 0;
  state = "playing";
  overlay.hidden = true;
  saveScoreBtn.hidden = true;
  saveScoreBtn.disabled = true;
  pauseBtn.textContent = "Pause";
  pauseBtn.setAttribute("aria-pressed", "false");
  canvas.focus();
  schedule();
}

function gameOver() {
  clearTimeout(timer);
  state = "over";
  finishedGameId = currentGameId;
  finishedScore = score;
  drawBoard();
  overlayTitle.textContent = score ? `${score} points!` : "Oops!";
  overlayCopy.textContent = score >= best && score > 0
    ? "New high score. That snake was moving!"
    : "The snake bumped into something. Ready for another run?";
  startBtn.textContent = "Play again";
  saveScoreBtn.hidden = score <= 0;
  saveScoreBtn.disabled = !bridgeReady || score <= 0;
  overlay.hidden = false;
  announcer.textContent = `Game over. Final score ${score}.`;
}

function togglePause() {
  if (state === "ready" || state === "over") return;
  if (state === "playing") {
    state = "paused";
    clearTimeout(timer);
    pauseBtn.textContent = "Resume";
    pauseBtn.setAttribute("aria-pressed", "true");
    overlayTitle.textContent = "Paused";
    overlayCopy.textContent = "Take a breath. Your snake will wait.";
    startBtn.textContent = "Resume";
    overlay.hidden = false;
  } else {
    state = "playing";
    pauseBtn.textContent = "Pause";
    pauseBtn.setAttribute("aria-pressed", "false");
    overlay.hidden = true;
    canvas.focus();
    schedule();
  }
}

function steer(name) {
  if (state !== "playing") return;
  const next = DIRECTIONS[name];
  if (!next) return;
  if (next.x === -direction.x && next.y === -direction.y) return;
  pendingDirection = next;
}

function resultData(result) {
  if (!result?.isError) return result?.structuredContent || {};
  const message = result.content
    ?.filter(item => item.type === "text")
    .map(item => item.text)
    .join(" ");
  throw new Error(message || "The leaderboard request failed.");
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "";
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function renderScores(scores) {
  scoreList.replaceChildren();
  if (!Array.isArray(scores) || scores.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.className = "empty-row";
    cell.colSpan = 4;
    cell.textContent = "No shared scores yet. Be the first!";
    row.append(cell);
    scoreList.append(row);
    return;
  }

  for (const entry of scores) {
    const row = document.createElement("tr");
    const rank = document.createElement("td");
    const player = document.createElement("td");
    const name = document.createElement("span");
    const email = document.createElement("span");
    const date = document.createElement("td");
    const points = document.createElement("td");

    rank.textContent = `#${entry.rank}`;
    name.textContent = entry.name;
    email.className = "player-email";
    email.textContent = entry.email;
    player.append(name, email);
    date.textContent = formatDate(entry.achieved_at);
    points.textContent = String(entry.score);
    row.append(rank, player, date, points);
    scoreList.append(row);
  }
}

function updateSaveCard() {
  const canSave = finishedScore > 0 && Boolean(finishedGameId);
  saveCard.hidden = !canSave;
  if (!canSave) return;

  finishedScoreEl.textContent = String(finishedScore);
  if (currentPlayer) {
    playerIdentityEl.textContent = `${currentPlayer.name} · ${currentPlayer.email}`;
    confirmSaveBtn.disabled = false;
  } else {
    playerIdentityEl.textContent = "Your Entra name and email are unavailable.";
    confirmSaveBtn.disabled = true;
  }
}

async function refreshLeaderboard() {
  leaderboardStatus.textContent = "Loading scores…";
  try {
    const result = await app.callServerTool({
      name: "get_snake_high_scores",
      arguments: {},
    });
    const data = resultData(result);
    currentPlayer = data.player || null;
    renderScores(data.scores);
    updateSaveCard();
    leaderboardStatus.textContent = data.scores?.length
      ? "Top shared scores"
      : "";
  } catch (error) {
    leaderboardStatus.textContent = String(error?.message || error);
    currentPlayer = null;
    updateSaveCard();
  }
}

async function openLeaderboard() {
  if (!bridgeReady) return;
  if (state === "playing") togglePause();
  if (!leaderboardDialog.open) leaderboardDialog.showModal();
  updateSaveCard();
  await refreshLeaderboard();
}

startBtn.addEventListener("click", () => {
  if (state === "paused") togglePause();
  else begin();
});
pauseBtn.addEventListener("click", togglePause);
showScoresBtn.addEventListener("click", openLeaderboard);
saveScoreBtn.addEventListener("click", openLeaderboard);
closeScoresBtn.addEventListener("click", () => leaderboardDialog.close());
leaderboardDialog.addEventListener("click", event => {
  if (event.target === leaderboardDialog) leaderboardDialog.close();
});
confirmSaveBtn.addEventListener("click", async () => {
  if (!finishedGameId || finishedScore <= 0 || !currentPlayer) return;
  confirmSaveBtn.disabled = true;
  leaderboardStatus.textContent = "Saving your score…";
  try {
    const result = await app.callServerTool({
      name: "save_snake_high_score",
      arguments: { score: finishedScore, game_id: finishedGameId },
    });
    const data = resultData(result);
    renderScores(data.scores);
    leaderboardStatus.textContent = data.saved
      ? `Saved ${data.score} points for ${data.player.name}.`
      : "This game was already saved.";
    finishedScore = 0;
    finishedGameId = null;
    saveCard.hidden = true;
    saveScoreBtn.hidden = true;
  } catch (error) {
    leaderboardStatus.textContent = String(error?.message || error);
    confirmSaveBtn.disabled = false;
  }
});
document.querySelectorAll("[data-dir]").forEach(button => {
  button.addEventListener("pointerdown", event => {
    event.preventDefault();
    steer(button.dataset.dir);
  });
});
window.addEventListener("keydown", event => {
  if (event.key === " ") {
    event.preventDefault();
    togglePause();
    return;
  }
  const name = KEY_DIR[event.key];
  if (name) {
    event.preventDefault();
    steer(name);
  }
});
canvas.addEventListener("pointerdown", event => {
  touchStart = { x: event.clientX, y: event.clientY };
});
canvas.addEventListener("pointerup", event => {
  if (!touchStart) return;
  const deltaX = event.clientX - touchStart.x;
  const deltaY = event.clientY - touchStart.y;
  touchStart = null;
  if (Math.max(Math.abs(deltaX), Math.abs(deltaY)) < 18) return;
  steer(Math.abs(deltaX) > Math.abs(deltaY)
    ? (deltaX > 0 ? "right" : "left")
    : (deltaY > 0 ? "down" : "up"));
});

reset();

const app = new App({ name: "Snake Game", version: "1.0.0" });
app.ontoolresult = result => {
  if (result?.structuredContent?.message) {
    overlayCopy.textContent = "Eat the berries, grow longer, and avoid the walls and your own tail.";
  }
};
try {
  await app.connect();
  bridgeReady = true;
  showScoresBtn.disabled = false;
  saveScoreBtn.disabled = finishedScore <= 0;
} catch (error) {
  console.warn("MCP app bridge unavailable; game remains playable.", error);
}
