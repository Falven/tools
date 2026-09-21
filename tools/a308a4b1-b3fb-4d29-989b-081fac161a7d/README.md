# Laya Plays Pokémon

A watch-only Pokémon Red MCP App. One shared game and two leaderboards live in
one Python process. **Progress and scores last for this server session.**
The preserved chat operation is `new_tool`; it only returns status and an App
binding. Chat launches do not load assets, register presence, or advance play.

## Setup

Use **exactly one ToolForge replica**. Multiple processes would have independent
games; this design does not synchronize them.

These three names are App-specific configuration conventions, not built-in
ToolForge mount facilities:

| Setting | Required value |
| --- | --- |
| `POKEMON_RED_ROM_PATH` | Absolute, readable approved deployment location of a lawfully provisioned English Red ROM. |
| `POKEMON_RED_ROM_SHA256` | Its 64-digit SHA-256. The App independently requires a 1 MiB image with the pret Red SHA-1 `ea9bcae617fdf159b045185467ae58b2e4a48b9a`. A filename or arbitrary configured hash does not establish mapping compatibility. |
| `LAYA_MODEL_PATH` | Local root-English Hub snapshot, ending in `snapshots/1c5edc17a7acd8701df6fc341c0d179f1c62c982`, provisioned from `convaiinnovations/laya`. |

The model snapshot needs `rl_agent_config.json`, `encoder/config.json`,
`model.safetensors`, `tokenizer/tokenizer.json`, and
`tokenizer/tokenizer_config.json`. Provision the complete pinned snapshot,
including tokenizer ancillary files, outside playback. The App checks layout,
configuration and plausible weight size, but the operator is responsible for
the snapshot's provenance/integrity; a directory name is not cryptographic
proof of its tensor contents. Do not use specialized checkpoint subdirectories.

ToolForge has no private per-tool ROM mount. **Do not upload ROMs, weights or saves
into Tool Directory/catalog Git, encode them in secrets, or add them to source.**
An operator must arrange an approved read-only location accessible to the
existing Python process. No ROM or weights are distributed/downloaded by this
App. No downstream credentials, scopes, inference service or database is used.

Dependencies are pinned in the shared `pyproject.toml`. Python stays `>=3.14`.
Torch is a direct **2.10.0 CPU-only CPython 3.14/Linux x86_64 wheel**, matching
the established runtime. The initial CUDA installation exhausted disk; this
CPU-only replacement restored the connected launch operation. If the platform
architecture/interpreter changes, select its compatible CPU wheel explicitly.
No deployment-wide timeout or interpreter downgrade was made.

Initialization is request-driven in four phases: validate assets, import SDK,
load one CPU model, and power on the emulator. No phase runs while requests stop.
Each request has a 20-second cooperative work budget below the platform's
30-second deadline. **Native import/load/inference cannot be forcibly interrupted
inside this design.** Operators must establish RAM headroom and that each cold
phase/prediction fits the real deployment budget before claiming readiness.
An overlong native call can still cause the host deadline to terminate the
shared Tool Server. No detached preloader or automatic timeout increase hides
this risk. Setup failures remain explicit; correcting the same asset paths
requires reload/republish to recheck, which resets this ephemeral session.

## Modules and small contracts

* `tool.py`: `Apps`, unique `ui://` resource, relative asset inlining, one cheap
  session, verified delegated caller extraction and response serialization.
* `game/session.py`: one lock, exclusive request-owned gameplay admission,
  due times, lifecycle, union-of-tabs accounting, immutable published views,
  one-shot score finalization and rollover. Heartbeats can renew during native
  work, but no other request can touch emulator/model state.
* `game/emulator.py`: headless PyBoy, file-like ROM and explicit blank in-memory
  cartridge RAM, bounded press/release/tick, memory reads and PNG capture.
* `game/pokemon_red.py`: fingerprint/mappings, ROM-derived names and move data,
  visible text/menu/cursor, party/bag/battle/map decoding, finite legal macros
  and Hall-of-Fame record validation. No game-memory writes.
* `game/controller.py`: pinned local Laya, compact observations, goal/action
  decisions and bounded per-run memory. No MCP, emulator access or reset logic.
* `app.html`, `app.js`, `styles.css`: semantic viewer, official MCP bridge,
  single-flight polling, visibility, rendering, host theme and pixel scaling.
* `game/__init__.py`: package marker with no initialization side effects.

Dependency direction: tool → session → controller/emulator/pokemon_red;
controller also consumes pokemon_red's immutable records. No circular imports,
global mutable caches in helpers, plugin framework, or schema framework.

**Observation:** frozen mode, location/position/facing, visible text and cursor,
own party/HP/status/moves/PP, bag/money/badges, visible neighboring terrain and
sprites. Enemy observations contain displayed species/level and HP-bar
granularity, not hidden moves, stats, PP or unrevealed trainer parties.

**Legal action:** short ID/description, bounded ordinary button pulses, and an
optional menu target. The session rechecks mode, cursor and target text before
confirmation. Movement is a short chosen direction, not a scripted route.
Menu actions cover battle commands/moves, party/item targets, yes/no,
inventory/PC/shop/field-move entries, quantity and naming controls. Unknown
screens stay explicit; dynamic screens, obscure menus and puzzles can stall.
Terrain is local collision guidance, not a complete world/warp navigator.
Observed disable announcements and obvious PP/HP/item restrictions are filtered;
unobserved/transient restrictions can still be rejected by the game.

**Decision:** legal ID, selected objective, measured inference time, SDK-rendered
input tokens (at most 512 per model call), retained/omitted state tokens and option
concentration. Goals are reselected periodically, on map changes and stalls.
Visits (4096 positions), recent dialogue/travel and observed milestone labels
remain outside the prompt. The head is checked against its 192-token budget.
No alternative-model, random-action or scripted-policy fallback exists. A deterministic
animation wait is labeled as such, not as a Laya decision. Model confidence is
concentration among supplied choices, **not strategic certainty**.

**Viewer:** verified delegated `scp` plus `(tid, oid)`, extracted in the App
handler; only the small identity record reaches the session. No retained tokens,
browser names, claimed identities or client-reported durations/scores.
Random memory-only tab UUIDs are bound to the operator. Active records expire
and are pruned. Up to 128 active tabs and 4096 bounded binding tombstones prevent
cross-operator reuse; each operator has one cumulative watch counter and a
session-local pseudonym, not a published email address.

**Display snapshot v1 (`_meta.view`):** `schema`, `runtime_id`, `run_id`,
`run_number`, `revision`, `status`, `busy`, `admission`, `message`,
`requirements`, `frame`, `game`, `timing`, `presence`, `decisions`,
`fastest_runs`, `watch_leaders`, `you`, `completion`.
Frame is null or `{id, width:160, height:144, format:"png", emulator_frame, png}`.
`timing` includes active seconds, retry delay, last/mean batch time, initialization
phases, step count and budgets. Score rows contain actual run/time/team evidence;
watch rows contain pseudonym and server-accounted seconds. Views are detached.

App-only `laya_pokemon_view` updates presence/read state without game work.
`laya_pokemon_playback` supplies tab UUID, visibility/display signal and last
runtime/run/revision. The latter can admit **one** batch, never a queued loop.
Both handlers use exactly `visibility=["app"]`. Fresh reads are required after
stale/expired presence. Busy, stale, hidden or not-due requests do not advance.
An admitted request awaits completion, including cancellation; the lock grants
exclusive ownership, then commits its result once. Busy heartbeat calls only
touch accounting and detached displays.

## Pause, scoring and transport

No requests means no new gameplay. One already admitted batch may finish.
All buttons are released before a batch settles. The emulator is retained in RAM
while paused; returning viewers resume that exact state with no wall-clock
catch-up. Closing an App alone does not reset anything. Process loss, restart,
reload or republish discards game, model run memory, frames, presence and scores.
There is no manual input, speed setting, disruptive reset or saved-state endpoint.

Presence expires after **12 seconds**, evaluated on requests. Watch time is the
union of fresh visible/displaying intervals per operator, not the sum of tabs.
The browser reports document visibility and at least 25% screen intersection;
this is a practical signal, not proof of attention. A frame must have decoded
before the browser reports it as displayed. Missing close events can overcount
by up to the expiry; missing/delayed heartbeats can undercount. Setup without a
frame earns no watch time. Busy heartbeats are accepted without game admission.

**Fastest runs — active play time** includes inference, admitted work and normal
connected pacing, excluding setup/error/completion display/no-viewer intervals,
subject to presence expiry. These are current-session demo scores, not
conventional speedrun records. The best ten completions are retained.

Completion requires a pristine-run zero-counter witness, counter one in the
Hall-of-Fame map outside battle with eight badges, and every party member's
species/level/terminated nickname matching the first SRAM team (plus unused-slot
terminator). The complete 96-byte record must differ from the baseline and remain
unchanged at least two **emulated** frames apart after a candidate appears.
The counter increment alone never scores. This derives from the synchronous
Hall-of-Fame copy; a real terminal-state replay is still needed to validate the
implemented addresses/record interpretation end-to-end.

Finalization is once per run under the session lock. The actual completion frame
and result remain for at least six server seconds. The next eligible request
creates a fresh blank-RAM game and clears only per-run controller memory; the
model and both leaderboards survive. A subsequent eligible request begins play.
With no requests, the completed game remains untouched.

Each batch advances at most **120 actual emulator frames** and returns one real
PNG, encoded once and cached for all viewers. No fabricated intermediate frames,
video endpoint or browser-side simulation. The minimum post-batch gap is 2.5 s.
Nominal steady polling is about 24 calls/min/viewer before latency; stale reads
and visibility/reconnect calls add overhead. The App displays **observed**
per-viewer call rate/round-trip/frame cadence and server timings, not promised
60-fps playback.

Ordinary MCP content/structuredContent is a small status receipt, never a base64
frame. Display data is exclusively in `_meta`. This relies on the specified host
behavior that fresh App-handler metadata is forwarded but omitted from Tool
Activity. **End-to-end forwarding/recording exclusion has not been independently
verified here.** The browser stops playback if metadata or image decoding fails.
Normal ToolForge activity remains enabled; metadata is not a credentials channel.

## Validation evidence and remaining limits

* Published coherent package slices and called `new_tool` through connected MCP:
  relative imports/cheap session construction succeeded; the real fallback was
  `setup_required`, run zero, with fresh runtime IDs after replacement.
* Dependency installation initially failed on CUDA disk use. Published the
  CPU-only repair and observed connected launch recovery.
* Authoring type/lint diagnostics were used to repair MCP SDK v2 response field
  names and Python issues. Executable verifier checks were attempted but marked
  **untested**: bubblewrap was unavailable. No test files, diagnostic endpoints,
  fake controllers, terminal flags or seeded scores were added.
* Final entrypoint/viewer artifact check: **12 static criteria passed, zero
  failed**. JavaScript parsing was untested because the secure command backend
  was unavailable; the overall verifier outcome was **incomplete**, not a full
  App acceptance pass. Evidence ID:
  `36e329bd7f4f843905e89a36a3807438acea584564113540df3ea996c07bd467`.
* No approved ROM/model-backed playback was exercised. **Furthest real
  autonomous milestone: none.** No starter, parcel, Pokédex, Brock, next-region
  or full-campaign achievement has been observed.
* Two authenticated operators, concurrent game batches, pause/resume, watch
  unions, native cold-load/inference performance, terminal scoring/rollover,
  actual narrow/wide browser rendering and activity metadata exclusion are
  **unverified in deployment**, not passed tests. Their mechanisms have only
  source review/static checks plus package/launch evidence.

The next acceptance run must provision the assets and observe these paths through
the actual App: two tabs/identities, idle/reconnect, one action per due slot,
small retained receipts, then genuine campaign milestones and terminal evidence.
Laya is a general 421M typed-choice model, not a vision model or demonstrated
Pokémon policy. A working viewer, implemented controller mechanisms, a
source-reviewed score branch and an autonomous completion are different evidence.

## Upstream basis / notices

Memory/input knowledge references **NousResearch/pokemon-agent** (MIT), revision
`f8a03e4a8bc58f1d9dda6d677a7436cc832a57a9`, particularly
`pokemon_agent/memory/red.py`. This decoder is independently written; no FastAPI
server, persistent session system, Hermes autopilot or dashboard was copied.
Upstream copyright and MIT license remain with that project:
`https://github.com/NousResearch/pokemon-agent/blob/f8a03e4a8bc58f1d9dda6d677a7436cc832a57a9/LICENSE`

ROM identity/layout/record basis: pret/pokered
`a1a22aaf84d1675bcdbaeb194592379d586d838e`, `ram/wram.asm`,
`ram/sram.asm`, `engine/movie/hall_of_fame.asm`, `engine/menus/save.asm`.
PyBoy is pinned to 2.7.0; inspected reference
`f2a8bed61a81c827d8c46669a2f3ef4be4d15e5f` documents explicit ticks/memory/input
and `stop(save=False)`. Laya SDK is pinned to
`42626c348753fbb17572a813127df2278a1ec527` (0.3.4), `laya/agent.py` and
`laya/common.py`; model pin is listed above. Installed dependencies retain their
own licenses. Some full pinned source pages were unavailable to the authoring
browser; source-derived mappings and guards must not be confused with runtime
ROM/model validation.
