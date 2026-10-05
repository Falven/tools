# Neon Coil

A fullscreen-friendly, self-contained Three.js MCP App: a beveled 2.5D Snake arcade with original synthesized music, independent music/SFX muting, touch controls, and an authenticated leaderboard.

## Play

Invoke `neon_coil` and choose **Open App**. The app fills the host viewport and requests the standard `fullscreen` display mode when supported. The host’s native Fullscreen control remains available; the app does not add competing maximize controls.

- **Arrow keys / WASD:** steer; two distinct turns can be buffered.
- **Space / P:** pause or resume. **Escape:** pause while playing.
- **M:** toggle sound effects. **N:** toggle music.
- **Touch:** swipe with a 12-pixel threshold, or use the directional pad.
- Eat an orange energy cube for **100 points** and one extra segment.
- Avoid the walls and your body. The departing tail cell remains legal.
- Every five bites increases speed: 150 ms per grid step down to 70 ms.
- Fill all 432 cells to win. A run also ends at the 18,000-step limit.
- Opening the leaderboard or leaving the app pauses the game. Resuming is explicit.

A verified, delegated user account is required for ranked runs. Application-only identities may view the scoreboard and play clearly labeled, unranked practice. A standalone HTML preview is also unranked and never posts scores.

## Ephemeral state and identity

All run tickets, replay receipts, player identifiers and high scores are held in bounded dictionaries in **one MCP server process’s memory**. Restarting or redeploying that process resets them. There is no database, filesystem save, browser storage, cookie, analytics, or downstream service. The browser necessarily holds the current rendering and game simulation in temporary RAM. Source code and compiled assets are deployment artifacts, not saved games.

The app does not send gameplay or scores into model context. Host/platform logging and transcript retention remain host-controlled; the app cannot erase records retained by an MCP client.

Player identity comes exclusively from verified MCP access-token claims. Public player IDs are HMAC-derived with a fresh in-memory salt; raw tokens, tenant IDs, object IDs, email addresses and subjects are not stored or published. Display names are sanitized verified `name` claims, not caller-supplied text.

Each authenticated user has one highest score. Ranking is descending, with equal scores ordered by first achievement. The scoreboard loads 50 rows at a time and can page through every player.

## Verification and bounds

`neon_coil_begin` issues a caller-bound random run ID and deterministic seed. `neon_coil_finish` accepts only the run ID, tick count, and committed direction changes—not a claimed name or score. The server reconstructs the game, validates collisions and completion, checks minimum possible elapsed time, and atomically updates the best score. This rejects arbitrary score submission; it is not a claim to detect bots playing valid replays in real time.

- 2-hour run and idempotent receipt TTL.
- 4 active runs per user; a fifth replaces only that user’s oldest active ticket.
- 2,048 active runs and 4,096 combined active/receipt records.
- 10,000 leaderboard players per server epoch.
- 18,000 maximum replay steps/turns; strict integer validation.
- Unavailable, foreign, retired and expired tickets share the same error shape.
- Shared memory is lock-protected; bounded simulation occurs outside the lock.

A scaled deployment with multiple independent MCP processes would have one leaderboard per process. Use a single serving process if all users must share one volatile scoreboard.

## Rendering and audio

The browser runs a fixed-step simulation with interpolated visuals; gameplay never makes per-frame or per-turn server calls. Geometry is instanced/batched. The camera stays fixed during play. There are no expensive bloom passes or real-time shadow maps; baked glows and shaded geometry provide the arcade look. Resolution adapts before and during play. Software graphics drivers use cheaper shaded materials. Paused and finished scenes stop unnecessary continuous rendering, and hidden tabs stop the animation loop entirely. A severely stalled frame pauses rather than fast-forwarding the snake.

Audio is original Web Audio synthesis, created only after a user gesture. Independent music/SFX buses, an output limiter, an 80 ms scheduler with 150 ms lookahead, and a hard 24-source cap keep it bounded. Music and effects require no samples or network downloads. Mute preferences are deliberately not persisted.

The built resource bundles Three.js, the official MCP Apps SDK, fonts, styles and audio. Its `resourceDomains` and `connectDomains` CSP lists are empty. Rendering performance still depends on the client’s GPU and browser; no implementation can guarantee a particular frame rate on all hardware.

## Build and tests

From the repository root:

```sh
cd src/catalog_app/tools/neon_coil/frontend
npm ci
npm run build
```

The compiled app is committed so publication does not need a Node build step. To test from the repository root:

```sh
uv run python -m unittest discover -s tests -p 'test_neon_coil.py' -v
node --test tests/test_neon_core.mjs
```

The 49 Python and 14 JavaScript tests cover the MCP contract, authenticated multi-user isolation, schema strictness, pagination, deterministic engine parity, collisions, victory, timing, limits, expiry, and concurrent/idempotent completion. The repository also contains an unrelated legacy Hello World test whose referenced tool is absent; it is not part of this suite.

## MCP contract

| Operation | Visibility | Purpose |
| --- | --- | --- |
| `neon_coil()` | Model | Open the app; return useful rules and a score snapshot |
| `neon_coil_begin()` | App only | Issue an authenticated run |
| `neon_coil_finish(run_id, steps, turns)` | App only | Validate a completed run and update the best |
| `neon_coil_scores(offset=0, limit=50)` | App only | Read highest-first score pages (maximum 100 rows) |

Resource URI: `ui://neon-coil/app.html`.

Successful operations return structured data including an opaque server `epoch` and `ephemeral: true`. Domain failures return `{error: {code, message}, epoch, ephemeral: true}`. The score app renders names with `textContent`, not HTML.
