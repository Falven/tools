# Neon Snake

A playable 2.5D Three.js arcade game in an MCP App, with automatic,
account-linked score recording.

## Play

Call the existing Tool **`new_tool`**, then choose **Open App** in its activity.
The existing MCP operation name is intentionally preserved.

- **Arrow keys / WASD:** steer anywhere within the active App, including after
  using a toolbar control. Text fields and open dialogs never steer the snake.
- **Swipe / direction pad:** short swipes or immediate touch-down controls.
- **Space / P:** pause and resume. Leaving the App also pauses the game.
- **Trophy / Scores:** open the leaderboard modal. Opening a panel pauses play;
  closing it resumes only if that panel interrupted a running game.
- **Expand / collapse:** toggle host-supported fullscreen.
- **Ranked run:** completed scores save automatically.
- **Practice:** no profile or score is written.
- **Scores → Score privacy:** explains visibility and offers explicitly confirmed deletion.

The board fills the game screen with a compact HUD—no permanent leaderboard,
profile sidebar, instruction cards, or surrounding page. The App requests
fullscreen once on connection if the host advertises it, and respects refusal.
Inline-only hosts get the same game-first layout within their available area.
Phone portrait/landscape, host size limits, and safe-area insets are supported.
Browser-native fullscreen is not forced outside the host's sandbox.

Input changes preserve the existing game speed, replay protocol, and scores:
two quick valid corners can be buffered, held-key repeats are ignored, touch
controls act on **pointer-down** rather than click/release, and swipe slop is
8 CSS pixels. Grid-transition animation is capped at 50ms instead of trailing
by an entire 75–165ms game tick. This is an animation duration, not an
end-to-end latency guarantee. Fullscreen rendering caps pixel density, reuses
stationary shadow maps, and removes drifting background particles to reduce
rendering overhead. Repeated slow frames lower rendering resolution and, on
very slow devices, disable shadows without changing the game or score rules.

Eat coral energy cells for 10 points and one extra segment. Speed increases
every five cells. Walls and body collisions end the game; entering a cell the
tail is leaving is allowed. Filling the 18×18 board wins. Runs are capped at
16,000 moves.

The leaderboard shows the top ten completed runs, **score descending**, then
shorter active game time, then earlier finish. “My runs” retains the overall
ranks. Your personal best and run count update automatically. There is no
fabricated leaderboard data.

## Identity and privacy

Every server entrypoint reads ToolForge's authenticated caller context.
Name and e-mail come from the verified sign-in claims when available; a
one-time form requests only missing details. A supplied e-mail is a contact
label, not proof of mailbox ownership.

An immutable, tenant-scoped account identifier links the scores—not the
mutable e-mail or display name. App-only handlers cannot nominate a different
account. Scores are visible only within the same sign-in tenant.

The database stores names and full e-mails alongside runs. Responses display
only a masked e-mail address. No bearer tokens, raw identity claims, or full
e-mails are returned on the leaderboard. Model context updates contain score,
personal best, and rank only. There are no analytics, e-mail delivery, browser
storage of personal details, or downstream credential/scope requirements.

Choosing **Start ranked run** records the profile and a game session.
Finishing sends a direction replay: the server calculates the score itself,
checks collisions, ownership, expiry, and plausible elapsed time. Exact retries
are idempotent. This prevents arbitrary submitted score values; it is not
bot-proof, competitive anti-cheat.

If saving fails, the App keeps the replay in memory, displays a retry control,
and retries periodically while open. **Keep the App open until saving is
confirmed.** Closing/reloading loses unsent replays. Abandoned or unfinished
runs do not appear on the leaderboard; active sessions expire after six hours.

## Storage deployment

No additional production Python dependency or external service is required.
The default SQLite file is outside the source checkout:

```text
~/.local/share/toolforge/neon-snake/scores.sqlite3
```

For a durable deployment, configure the shared Tool Environment variable
**`NEON_SNAKE_DB_PATH`** with an absolute file path on an administrator-managed
persistent volume. The directory must be writable by the Tool runtime.
New database files use mode `0600`; newly created parent directories use `0700`.

**The default is server-local storage, not a managed cloud database.**
It survives process restarts on the same filesystem, but redeployment or
replacement of that filesystem may remove the scores. A persistent volume has
not been provisioned by this Tool. Use one runtime/database owner or a
SQLite-compatible shared deployment; this implementation does not synchronize
independent replicas. Administrators manage encrypted storage, access controls,
retention, and backups. The in-App delete action removes records only from the
active database, not administrator backups.

Database files, caches, and test artifacts are excluded from publishing by
`.gitignore`.

## MCP interface

Resource: `ui://neon-snake-70c8ba87/app.html`

| Operation | Visibility | Purpose |
| --- | --- | --- |
| `new_tool()` | Model / App | Open game; read rules, profile summary, and scores |
| `neon_snake_board(scope)` | App only | Read everyone’s or personal top ten |
| `neon_snake_profile(display_name, email)` | App only | Complete missing profile fields |
| `neon_snake_begin()` | App only | Create an owner-bound ranked session |
| `neon_snake_finish(run_id, directions)` | App only | Verify replay and record score |
| `neon_snake_forget(confirm)` | App only | Delete the caller’s own score data |

`tool.py` inlines `app.js` into `app.html` when registering the resource.
The browser uses pinned Three.js `0.180.0` and the official MCP App SDK
`2.0.0` from the CSP-allowed jsDelivr origin. External network access is needed
for those modules. If 3D cannot initialize, a visibly labelled 2D compatibility
renderer remains playable. A host without the MCP bridge can play practice
but cannot record scores.

## Development checks

Run from the workspace directory containing `pyproject.toml`, using its uv
environment and ToolForge's bundled MCP SDK:

```sh
uv run --no-sync python tools/70c8ba87-e289-4a8c-af79-1da1952db1ac/test_tool.py
```

Optional browser-test setup (development only; not production dependencies):

```sh
uv pip install --python .venv/bin/python playwright==1.63.0
uv run --no-sync playwright install --with-deps chromium
uv run --no-sync python -u tools/70c8ba87-e289-4a8c-af79-1da1952db1ac/test_browser.py
```

Browser suites can also be selected individually: append `desktop`, `mobile`,
`inputs`, or `compatibility`. They use the real official App/host bridge and Python SDK,
with synthetic middleware identities and a disposable SQLite database.
They do not contact a production score store. Screenshots go in ignored
`.test-artifacts/`. Low-memory Chromium flags are test-only; the harness uses
the real Resume button if software graphics trigger the game's stall pause.
Checks cover fullscreen negotiation/refusal, viewport sizing, modal pause and
resume, pointer-down before release, short swipes, rapid corners, toolbar focus,
held-key repeat, score persistence, and save retries.

The unit suite covers replay rules, Python/JavaScript parity, sorting,
identity isolation, privacy, rate limits, expiry, concurrent retries, deletion,
MCP metadata, the inline resource, and non-UI fallback output.