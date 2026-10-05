# Minesweeper · Desktop Classics

A self-contained MCP App with a teal desktop, classic Windows-inspired beveled tiles, red seven-segment counters, a smiley reset button, and a gently tilted 2.5D board. No image, font, music, or CDN requests are made at runtime.

## Play

Open the **Minesweeper** Tool, then use the host's **Open App / View App** controls. The host's native fullscreen control gives large fields more room.

- **Beginner:** 9 × 9, 10 mines, 1× points.
- **Intermediate:** 16 × 16, 40 mines, 2× points.
- **Expert:** 30 × 16, 99 mines, 3× points. Scroll horizontally on narrow screens.
- Click / tap to reveal. The first revealed tile and its eight neighbors are safe.
- Right-click, long-press, use **Flag** mode, or press **F** to toggle a flag.
- Arrow keys move focus; **Enter / Space** reveal; **Home / End** move to row edges.
- Click a revealed number to clear its remaining neighbors once its adjacent flag count matches. A wrong flag can make this move fatal.
- The smiley resets immediately. **New game / N** and difficulty changes ask before abandoning an active game. **H** opens help.
- Use **2.5D view** to flatten the board. Reduced-motion preferences disable animation.

## Scores and lifecycle

The Python server owns mine placement, all moves, and elapsed time. Live responses contain only the visible board; hidden mine locations and covered-cell values are never sent to the App.

```text
base points = revealed safe tiles × 10 × difficulty multiplier
win bonus  = (1,000 + max(0, 1,000 − floor(elapsed seconds))) × multiplier
```

**Only wins are posted.** Each verified delegated user retains one personal best across all difficulties. The shared top 50 are sorted by score descending, then server elapsed milliseconds ascending, then first achieved. Equal-score faster runs replace that user's best; exact ties retain the original achievement.

Scores and active games are **process-local, in-memory, and ephemeral**. There is no database, score file, browser score storage, or score copied into the conversation. A server restart clears them. Games expire two hours after issuance; only the newest three games per player are retained, including terminal receipts. Shared memory is bounded to 1,024 runs and 5,000 scored players. Active games reserve a player slot so a valid issued win can always be recorded.

The timer starts on the first actual reveal, not opening the App or placing a flag. It keeps running while the tab is hidden or help is open. The nostalgic display caps at 999 seconds; the server and accessible label retain actual elapsed time.

MCP's verified delegated claims bind each game to its player. Application-only callers can view rules/scores but cannot play. Names come only from the verified display-name claim, with private identifiers and email-like labels replaced by `Player`. Public player IDs are process-salted opaque HMAC values. Other players' IDs are not included in leaderboard rows.

Moves use a revision and retain the last complete response. Retrying the identical last request cannot toggle a flag twice or post a duplicate win. The App offers **Retry move** after an uncertain response and resynchronizes stale revisions. A new server epoch invalidates the old field visibly.

## Music and effects

Original, gentle chiptune music and short arcade effects are synthesized with Web Audio. Music defaults **off**; effects default **on**. They have separate buses and independent mute buttons, including immediate silencing of scheduled audio. Audio starts only following user interaction, suspends when hidden, and is disposed on teardown. Only audio preferences use browser storage (when available), under `minesweeper-audio-v1`; scores never do.

## MCP contract

- Model-facing Tool: `minesweeper()` — useful rules/score fallback; no start or score side effect.
- App-only: `minesweeper_start(difficulty="beginner")`.
- App-only: `minesweeper_move(run_id, action, cell, revision)`; `action` is `reveal`, `flag`, or `chord`.
- App-only: `minesweeper_scores()`.
- Resource: `ui://minesweeper/app.html`; bundled official MCP Apps SDK 2.0.0; no external CSP domains.

Cell codes: `-2` covered, `-3` flag, `0…8` revealed numbers, `-1` mine after loss, `-4` exploded mine, `-5` incorrect flag after loss. Wins automatically flag all remaining mines.

## Build and test

From this tool's `frontend` directory:

```sh
npm ci
npm run build
npm test
```

From the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_minesweeper.py' -v
node --test tests/test_minesweeper_audio.mjs
node tests/fixtures/minesweeper_ui_host.mjs
node tests/test_minesweeper_browser.mjs
```

The browser fixture is explicitly synthetic, isolated, and never part of the MCP resource. It writes an ignored local HTML artifact and starts no server. It supports deterministic fields, winning/losing, independent audio toggles, network-response loss/retry, delayed replies, stale revision, and server-restart checks.

Source changes go in the readable [HTML](<src/catalog_app/tools/minesweeper/app.html>), [engine](<src/catalog_app/tools/minesweeper/engine.py>), [state](<src/catalog_app/tools/minesweeper/state.py>), [main.js](<src/catalog_app/tools/minesweeper/frontend/main.js>), or [audio.js](<src/catalog_app/tools/minesweeper/frontend/audio.js>). Rebuild the adjacent [app.js](<src/catalog_app/tools/minesweeper/app.js>) bundle before publication. The build preserves upstream bundled dependency notices in [THIRD_PARTY_NOTICES.txt](<src/catalog_app/tools/minesweeper/THIRD_PARTY_NOTICES.txt>) and in the resource itself. Commit and push to publish, then verify Tool activation and resource delivery separately.
