from mcp.server.apps import Apps, ResourceCsp  # noqa: I001


apps = Apps()
__all__ = ["snake_game"]

RESOURCE_URI = "ui://snake-game/app.html"

HTML = r"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Snake</title>
    <style>
      :root {
        color-scheme: dark;
        --ink: #f7fff4;
        --muted: #a8b8a3;
        --panel: rgba(12, 24, 17, .88);
        --line: rgba(171, 255, 144, .16);
        --green: #83f267;
        --green-2: #3ecf5c;
        --berry: #ff4f78;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100vh;
        overflow-x: hidden;
        color: var(--ink);
        font-family: ui-rounded, "SF Pro Rounded", "Segoe UI", system-ui, sans-serif;
        background:
          radial-gradient(circle at 15% 10%, rgba(62, 207, 92, .18), transparent 34%),
          radial-gradient(circle at 85% 90%, rgba(131, 242, 103, .12), transparent 36%),
          #07100b;
      }
      .shell {
        width: min(100%, 700px);
        margin: 0 auto;
        padding: 18px 16px 24px;
      }
      header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        margin-bottom: 12px;
      }
      h1 {
        margin: 0;
        font-size: clamp(28px, 7vw, 44px);
        letter-spacing: -.06em;
        line-height: .95;
      }
      .leaf { color: var(--green); }
      .stats { display: flex; gap: 8px; }
      .stat {
        min-width: 74px;
        padding: 7px 10px;
        border: 1px solid var(--line);
        border-radius: 13px;
        background: var(--panel);
        text-align: center;
        box-shadow: 0 10px 30px rgba(0, 0, 0, .2);
      }
      .stat span {
        display: block;
        color: var(--muted);
        font-size: 10px;
        font-weight: 800;
        letter-spacing: .12em;
        text-transform: uppercase;
      }
      .stat strong { font-size: 21px; font-variant-numeric: tabular-nums; }
      .board-wrap {
        position: relative;
        overflow: hidden;
        border: 1px solid rgba(171, 255, 144, .22);
        border-radius: 24px;
        padding: 10px;
        background: linear-gradient(145deg, rgba(27, 50, 34, .95), rgba(8, 18, 12, .96));
        box-shadow: 0 24px 70px rgba(0, 0, 0, .42), inset 0 1px rgba(255,255,255,.05);
      }
      canvas {
        display: block;
        width: 100%;
        aspect-ratio: 1;
        border-radius: 16px;
        background: #0b1710;
        touch-action: none;
      }
      .overlay {
        position: absolute;
        inset: 10px;
        display: grid;
        place-items: center;
        padding: 24px;
        border-radius: 16px;
        text-align: center;
        background: rgba(5, 14, 9, .72);
        backdrop-filter: blur(7px);
        transition: opacity .18s ease;
      }
      .overlay[hidden] { display: none; }
      .overlay-card { max-width: 330px; }
      .overlay h2 { margin: 0 0 6px; font-size: 34px; letter-spacing: -.04em; }
      .overlay p { margin: 0 0 18px; color: #c8d8c4; line-height: 1.45; }
      button {
        border: 0;
        border-radius: 14px;
        color: #07100b;
        background: linear-gradient(180deg, #a5ff89, #66e75f);
        box-shadow: 0 8px 24px rgba(82, 222, 94, .22);
        padding: 11px 18px;
        font: inherit;
        font-weight: 850;
        cursor: pointer;
        transition: transform .1s ease, filter .1s ease;
      }
      button:hover { filter: brightness(1.08); }
      button:active { transform: translateY(1px) scale(.98); }
      button:focus-visible { outline: 3px solid white; outline-offset: 3px; }
      .toolbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-top: 12px;
      }
      .toolbar button {
        color: var(--ink);
        background: var(--panel);
        border: 1px solid var(--line);
        box-shadow: none;
      }
      .hint { color: var(--muted); font-size: 12px; text-align: right; }
      .dpad {
        display: none;
        width: 192px;
        margin: 16px auto 0;
        grid-template-columns: repeat(3, 56px);
        grid-template-rows: repeat(2, 48px);
        justify-content: center;
        gap: 7px;
      }
      .dpad button {
        padding: 0;
        color: var(--ink);
        background: rgba(25, 44, 31, .96);
        border: 1px solid var(--line);
        box-shadow: none;
        font-size: 23px;
      }
      .up { grid-column: 2; }
      .left { grid-column: 1; grid-row: 2; }
      .down { grid-column: 2; grid-row: 2; }
      .right { grid-column: 3; grid-row: 2; }
      .sr-only {
        position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
        overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
      }
      @media (pointer: coarse), (max-width: 600px) {
        .dpad { display: grid; }
        .hint { display: none; }
      }
      @media (max-width: 430px) {
        .shell { padding: 12px 10px 18px; }
        .stat { min-width: 62px; padding: 6px 8px; }
        .stat strong { font-size: 18px; }
        .board-wrap { border-radius: 20px; padding: 7px; }
        .overlay { inset: 7px; }
      }
      @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; }
      }
    </style>
  </head>
  <body>
    <main class="shell">
      <header>
        <h1>SNAKE<span class="leaf">.</span></h1>
        <div class="stats" aria-label="Game scores">
          <div class="stat"><span>Score</span><strong id="score">0</strong></div>
          <div class="stat"><span>Best</span><strong id="best">0</strong></div>
        </div>
      </header>

      <section class="board-wrap" aria-label="Snake game">
        <canvas id="board" width="600" height="600" tabindex="0"
          aria-label="Snake game board. Use arrow keys or WASD to steer."></canvas>
        <div class="overlay" id="overlay">
          <div class="overlay-card">
            <h2 id="overlay-title">Ready?</h2>
            <p id="overlay-copy">Eat the berries, grow longer, and avoid the walls and your own tail.</p>
            <button id="start" type="button">Start game</button>
          </div>
        </div>
      </section>

      <div class="toolbar">
        <button id="pause" type="button" aria-pressed="false">Pause</button>
        <div class="hint">Arrow keys / WASD · Space to pause</div>
      </div>

      <div class="dpad" aria-label="Touch controls">
        <button class="up" data-dir="up" type="button" aria-label="Move up">↑</button>
        <button class="left" data-dir="left" type="button" aria-label="Move left">←</button>
        <button class="down" data-dir="down" type="button" aria-label="Move down">↓</button>
        <button class="right" data-dir="right" type="button" aria-label="Move right">→</button>
      </div>
      <div id="announcer" class="sr-only" aria-live="polite"></div>
    </main>

    <script type="module">
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
      bestEl.textContent = String(best);

      function roundedRect(x, y, w, h, r) {
        ctx.beginPath();
        ctx.roundRect(x, y, w, h, r);
      }

      function drawBoard() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = "#0b1710";
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.strokeStyle = "rgba(160, 255, 142, .045)";
        ctx.lineWidth = 1;
        for (let i = 1; i < GRID; i++) {
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
        const bx = berry.x * CELL + CELL / 2;
        const by = berry.y * CELL + CELL / 2;
        ctx.save();
        ctx.shadowColor = "rgba(255, 79, 120, .6)";
        ctx.shadowBlur = 18;
        ctx.fillStyle = "#ff4f78";
        ctx.beginPath();
        ctx.arc(bx, by, berrySize / 2, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
        ctx.fillStyle = "#b9ff88";
        ctx.beginPath();
        ctx.ellipse(bx + 5, by - berrySize / 2 - 2, 5, 9, .7, 0, Math.PI * 2);
        ctx.fill();

        snake.forEach((part, index) => {
          const pad = index === 0 ? 2 : 3;
          const x = part.x * CELL + pad;
          const y = part.y * CELL + pad;
          const size = CELL - pad * 2;
          ctx.fillStyle = index === 0 ? "#a2ff7e" : `hsl(${126 + Math.min(index, 30)}, 69%, ${58 - Math.min(index, 24) * .55}%)`;
          roundedRect(x, y, size, size, index === 0 ? 9 : 7);
          ctx.fill();

          if (index === 0) {
            const eyeOffsetX = direction.x === 0 ? 7 : (direction.x > 0 ? 19 : 8);
            const eyeY1 = direction.y > 0 ? 19 : 9;
            const eyeY2 = direction.y < 0 ? 9 : 19;
            ctx.fillStyle = "#102016";
            for (const [ex, ey] of direction.x === 0
              ? [[x + 8, y + (direction.y > 0 ? 19 : 8)], [x + 19, y + (direction.y > 0 ? 19 : 8)]]
              : [[x + eyeOffsetX, y + eyeY1], [x + eyeOffsetX, y + eyeY2]]) {
              ctx.beginPath();
              ctx.arc(ex, ey, 2.5, 0, Math.PI * 2);
              ctx.fill();
            }
          }
        });
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

      function placeBerry() {
        const open = [];
        for (let y = 0; y < GRID; y++) {
          for (let x = 0; x < GRID; x++) {
            if (!snake.some(part => part.x === x && part.y === y)) open.push({ x, y });
          }
        }
        berry = open[Math.floor(Math.random() * open.length)] || { x: 0, y: 0 };
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
        state = "playing";
        overlay.hidden = true;
        pauseBtn.textContent = "Pause";
        pauseBtn.setAttribute("aria-pressed", "false");
        canvas.focus();
        schedule();
      }

      function gameOver() {
        clearTimeout(timer);
        state = "over";
        drawBoard();
        overlayTitle.textContent = score ? `${score} points!` : "Oops!";
        overlayCopy.textContent = score >= best && score > 0
          ? "New high score. That snake was moving!"
          : "The snake bumped into something. Ready for another run?";
        startBtn.textContent = "Play again";
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

      startBtn.addEventListener("click", () => {
        if (state === "paused") togglePause();
        else begin();
      });
      pauseBtn.addEventListener("click", togglePause);
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
        const dx = event.clientX - touchStart.x;
        const dy = event.clientY - touchStart.y;
        touchStart = null;
        if (Math.max(Math.abs(dx), Math.abs(dy)) < 18) return;
        steer(Math.abs(dx) > Math.abs(dy)
          ? (dx > 0 ? "right" : "left")
          : (dy > 0 ? "down" : "up"));
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
      } catch (error) {
        console.warn("MCP app bridge unavailable; game remains playable.", error);
      }
    </script>
  </body>
</html>
"""


@apps.tool(resource_uri=RESOURCE_URI)
def snake_game() -> dict[str, object]:
    """Launch an interactive Snake arcade game.

    The app supports arrow keys, WASD, swipe gestures, and on-screen direction
    controls, with pause/restart actions and a locally saved high score. Returns
    a short launch confirmation and control summary for clients that cannot
    render the interactive app. The game has no server-side effects.
    """
    return {
        "message": "Snake is ready to play.",
        "controls": {
            "desktop": "Arrow keys or WASD to steer; Space to pause.",
            "touch": "Swipe on the board or use the on-screen arrow buttons.",
        },
        "objective": "Eat berries to grow and score points. Avoid walls and your own tail.",
    }


apps.add_html_resource(
    RESOURCE_URI,
    HTML,
    title="Snake Game",
    csp=ResourceCsp(resource_domains=["https://cdn.jsdelivr.net"]),
)
