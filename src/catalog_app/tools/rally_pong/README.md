# Rally — After Hours

An original, full-viewport **Three.js 2.5D Pong** MCP App: a raised midnight-green court, mint and coral paddles, a reactive house opponent, angled/spin returns, a warm ball trail, and a newly composed arcade soundtrack.

Call **`rally_pong()`** to open it or read a useful text/structured fallback. Opening never starts a ranked run or posts a score. Click **Take the court** to play ranked when eligible, or **Just warming up** for unranked practice. Play requests the host's native fullscreen display mode when supported; the App itself fills its available viewport, including inline/phone sizes. There is intentionally no competing in-App maximize control.

## Controls and scoring

| Action | Controls |
| --- | --- |
| Move the left/mint paddle | W/S, Up/Down, mouse position over the court, or touch-drag |
| Gamepad | Left stick or D-pad; Start pauses |
| Pause/resume | Space or P; Escape also pauses outside dialogs |
| Toggle music independently | M or the **Music** switch |
| Toggle effects independently | N or the **SFX** switch |

- First to **7 goals**, with a **120-second** simulation-time ceiling.
- A **0.75-second serve** begins the match and follows nonterminal goals. Countdown time is included in the ceiling; pause time is not.
- Player return: **10 points**. Player goal: **100 points**. Reaching seven goals: **250 bonus points**.
- At timeout, earned points remain but no victory/bonus is awarded, even when leading.
- A paddle-edge contact changes the return angle; paddle motion adds spin. The ball accelerates within bounded speeds. The AI has seeded error, reaction delay, and a lower movement speed than the player.
- `hits` counts player returns. `rally` and `bestRally` count consecutive contacts with either paddle.

Controls feed a local **120 Hz fixed-step integer engine**, without network requests inside the frame loop. Paddles are not visually eased. Position controls are ray-projected into court coordinates; keyboard release stops motion. The renderer interpolates only ball motion and the introductory camera. Blur, hidden pages, a long stalled frame, a modal opened during play, or lost graphics context pause the match rather than fast-forward it. Reduced-motion preference disables trails/particles and camera easing. Resolution adapts without changing physics; software WebGL uses a smaller vertex-lit shader instead of expensive per-pixel materials.

## Sound

**“Mint / Coral”** is an original 122 BPM, sixteen-bar D-dorian A/B theme composed for this game. Filtered chip melody, syncopated triangle bass, synthesized kick/snare/hats, and all nine game cues are generated locally with Web Audio. No songs, samples, media files, or audio services are downloaded.

- No AudioContext, voices, or music timer exists before a direct user interaction.
- Music and effects have separate gain buses, preferences, controls, and queued-voice cancellation. Muting one never mutes the other.
- Music has at most 18 voices; effects at most 16. One lookahead timer, cooldowns, declick envelopes, and a master limiter limit audio work and peaks.
- Hidden/paused/teardown states silence both buses without changing preferences. Failed permission requests remain retryable.
- Only `{musicEnabled, sfxEnabled}` booleans may be saved under `rally-pong-audio-v1` in browser localStorage. Storage denial is harmless. **No scores, replays, identity, tokens, or run IDs are stored there.**

## Identity, verification, and volatile state

The hosting server already verifies MCP authentication before Tool code runs. Ranked eligibility is derived only from `get_access_token().claims` in that verified invocation: a nonempty delegated `scp`, no application `idtyp`, and either tenant/object identity or issuer/subject identity. Application-only callers may read the rules and board, and the UI may play practice, but cannot start or submit ranked runs. No raw JWT is decoded in the Tool, and no name, score, or identity is accepted from the client.

Each ranked start issues a cryptographically random caller-bound run ID and a seed. The browser submits only its exact terminal tick and canonical integer `[tick, target]` changes. The server replays matching integer physics, enforces input/time bounds, requires the exact seventh-goal/time-limit terminal tick, checks minimum real elapsed duration, and derives the score. Python/JavaScript parity is tested at full-state, event, and checkpoint level. This is replay validation, **not anti-bot or proof of human play**: a determined client can still calculate a legal input sequence.

All records are **process-local memory only**, under a lock:

- One highest score per verified user; ties preserve first achievement order.
- Per-epoch salted HMAC public IDs and a cleaned display name; no raw identity IDs, emails, or bearer tokens are retained or shown.
- At most 2,048 active runs, four per user, 4,096 active-plus-completed records, and 10,000 distinct reserved players.
- Starting a fifth run retires only that user's oldest active run. Slots for eventual receipts/players are reserved at begin.
- Runs and immutable retry receipts expire **30 minutes after issue**. Finishing retries are caller-bound and idempotent. Verification runs outside the state lock, followed by a locked commit/recheck.
- Scores have no file/database/cache persistence and clear on process restart, alongside the epoch and public IDs. Multiple independent server processes would have separate boards; there is no durable distributed leaderboard.
- A restart/account change detected in an open App makes its existing match unranked. Stale receipts cannot restore an older epoch, overwrite a new run, or regress a personal best.

The App uses text nodes, not HTML interpolation, for returned names and messages. Scores are not copied into model context or browser storage by the App. A caller/client may independently retain ordinary MCP response history; the Tool's own game/leaderboard store is volatile.

## MCP surface

| Operation | Visibility | Purpose |
| --- | --- | --- |
| `rally_pong()` | Model + App | Read-only opening, controls, rules, top scores and caller summary |
| `rally_pong_begin()` | App only | Issue a caller-bound ranked run |
| `rally_pong_finish(run_id, steps, inputs)` | App only | Verify a complete replay and atomically update best |
| `rally_pong_scores(offset=0, limit=50)` | App only | Read paginated scores (maximum page 100) |

`ui://rally-pong/app.html` is lazy-loaded and contains all runtime scripts/fonts. The official MCP Apps SDK 2.0.0 is bundled, and all handlers are registered on the supplied server with the same resource URI and `visibility: ["app"]`. The resource CSP has empty `resourceDomains` and `connectDomains`: no runtime CDN/network dependencies. Gamepad/WebGL/Web Audio availability is browser-dependent; WebGL 2 is needed to play, and the scores UI remains available when graphics fail.

## Build and verification

Python uses the repository's existing locked environment; no new Python dependencies or credentials are required. Frontend dependencies are exact-pinned and accompanied by an npm lockfile.

```bash
uv sync --all-packages
cd src/catalog_app/tools/rally_pong/frontend
npm ci
npm run build
npm test
```

From the repository root:

```bash
uv run python -m unittest discover -s tests -p 'test_rally_pong.py' -v
node --test tests/test_rally_core.mjs tests/test_rally_audio.mjs tests/test_rally_renderer.mjs
node tests/fixtures/rally_ui_host.mjs
node tests/test_rally_browser.mjs
```

The repository also contains a pre-existing [Hello World test](<../../../../tests/test_hello_world_app.py#L9>) that imports a removed tool. Unrestricted unittest discovery therefore reports that unrelated missing-module error; it is not part of the Rally test commands above and was not removed or suppressed.

The browser runner uses the installed `agent-browser` CLI in its own named session and only an isolated local fixture. That fixture uses the real self-contained App and official SDK bridge under a restrictive CSP, with **explicitly synthetic identities/scores**. It never starts a replacement GUI/server, registers a production test handler, or posts synthetic scores to the live server. Generated QA artifacts are ignored by Git. Python tests separately exercise verified auth context, registration and strict schemas, foreign/expired runs, capacities, timing, exact-terminal replays, concurrency and idempotency.

## Provenance

Court design, UI, integer game engine, music, and effects were authored for this tool. Bundled third-party runtime dependencies are **Three.js 0.180.0**, **MCP Apps SDK 2.0.0** and its transitive code, and **Space Grotesk / Space Mono** fonts. The build collects the exact applicable upstream license/notice texts and both distributes them separately and embeds them in the browser bundle. No trademarked arcade branding, third-party game assets, or copyrighted music recordings are used.
