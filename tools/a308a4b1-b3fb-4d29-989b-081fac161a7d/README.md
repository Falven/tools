# Laya Plays Pokémon

A watch-only, single-process Pokémon Red MCP App. The existing MCP operation
`new_tool` is preserved. Opening the chat Tool does not register a viewer, load
assets, or advance gameplay.

## Small contracts (v1)

These contracts are intentionally plain Python records / JSON, not a schema layer.

* **Observation:** immutable mode, map/position/facing, visible screen text and
  menu/cursor, own party/moves/PP, bag, badges, public enemy species/level/HP bar,
  and locally visible navigation. No hidden opponent moves or trainer team.
* **Legal action:** unique short ID, short player-facing description, and a bounded
  ordinary-button macro. Strategic options are selected by Laya; execution only
  handles timing and menu traversal. No memory writes, warps, grants, or fallback
  policy. Unknown screens remain explicit, not guessed campaign progress.
* **Decision:** chosen legal ID, objective, measured inference milliseconds and
  input-token count, option-concentration confidence (not correctness), and
  concise observed progress/stall metadata. Per-run memory stays outside prompts.
* **Viewer:** verified delegated `(tid, oid)` supplied by the transport; random
  browser tab ID in memory, bound to that operator. Browser names, durations,
  scores and identity claims are never accepted. Visibility is a practical signal,
  not proof of attention.
* **Display snapshot:** `schema`, `runtime_id`, `run_id`, `run_number`, `revision`,
  `status`, `message`, `requirements`, `frame` (null or PNG at 160×144 with ID),
  `game`, `timing`, `presence`, `decisions`, `fastest_runs`, `watch_leaders`,
  `you`, `completion`. Revisions order complete views within one runtime.
  Snapshots are detached values. Only `_meta.view` contains display data.
  Ordinary content/structuredContent contain a small nonsecret receipt.

App-only view/presence calls never advance the emulator. Playback supplies the
last runtime/run/revision; stale, busy, hidden, expired or early calls return the
current view without queueing another action. The browser has at most one call
in flight, fetches a live view after connecting, and clears old-runtime state.
Setup/error calls back off; no autoplay worker or timer exists on the server.

## Ownership

`tool.py` owns Apps registration, relative asset inlining, verified authentication,
the lightweight session, and serialization. `game/session.py` owns the single
nonblocking lock, lifecycle, due times, presence, clocks, snapshots and scores.
`game/emulator.py` owns PyBoy and RAM-only cartridge lifecycle.
`game/pokemon_red.py` owns revision validation, decoding, legal macros and terminal
evidence. `game/controller.py` owns local Laya loading, prompts and run memory.
The browser owns transport, visibility and rendering, never gameplay or scores.
Dependency direction is tool → session → controller/emulator/pokemon_red;
lower modules never import the session or MCP. Imports/constructors are cheap.

## Operator prerequisites

Exactly **one ToolForge replica** is required. Nothing coordinates two processes.
These configuration names are conventions introduced by this App:

* `POKEMON_RED_ROM_PATH`: approved deployment-local, readable lawful Red ROM.
* `POKEMON_RED_ROM_SHA256`: expected SHA-256 for that file. An independent known
  ROM fingerprint is also required by the decoder.
* `LAYA_MODEL_PATH`: approved deployment-local root English checkpoint snapshot
  of `convaiinnovations/laya` at
  `1c5edc17a7acd8701df6fc341c0d179f1c62c982`, not the specialized subdirectories.

Provision static assets outside Tool Directory/catalog Git. Do not upload ROMs,
weights, save games or credentials here. The Tool never downloads weights. The
30-second Tool-call deadline is not increased; cold load and CPU inference must
be measured on the deployment before claiming readiness.

## Operating contract

All mutable state is RAM-only and shared by every conversation/tab in this
Python process. Closing an App does not dispose the paused emulator. No requests
means no new gameplay; one admitted batch may finish. Returning viewers resume
the exact state, with no idle-time catch-up. Restart, reload or republish loses
the current run and both leaderboards. Normal ToolForge activity stays enabled.

Presence expires after 12 seconds, accounted lazily on requests. Watch totals
credit the union of an operator's fresh visible tabs, never tab count. Crashes
or missed visibility notifications can overcount by at most this expiry per
interval. Setup without a game frame does not accrue watch time.

Fastest runs use server monotonic **active play time**, including inference and
ordinary connected pacing, excluding setup, errors, completion display and
no-viewer intervals (subject to the same expiry precision). These are ephemeral
demo scores, not conventional speedrun records. A run scores only once, after a
verified complete first Hall-of-Fame recording. The actual terminal frame is
shown before a fresh emulator is created; the loaded model/watch totals/top ten
are retained. No manual controls, speed selector or disruptive reset are exposed.

## Evidence and limits

Implementation is being built in vertical slices. No real ROM, model, browser
or terminal-state validation has yet been performed. Empty tables are deliberate.
Laya is a typed-choice model, not a demonstrated full-campaign Pokémon policy.
Do not equate a functioning viewer, a verified score predicate, a moving sprite
and an autonomously completed campaign.
