# Paperweave

**Think in paper. Connect with thread.**

An MCP App for agents and people to build diagrams on the same whiteboard.
Its visual language is cut-paper rather than sketch: clipped silhouettes,
offset ink layers, folded notes, quiet labels, and curved thread connectors.
The UI uses system fonts and original SVG/CSS artwork, not external images.

## Open the studio

Call the published `paperweave_whiteboard` tool with no arguments, then use
**Open App** on the tool activity in an MCP Apps-capable client.
`template` can be `studio`, `blank`, `flow`, or `mindmap`.
If the tool is absent from discovery, enable it for the connected agent and
refresh that connection's tool catalog.

The source entrypoint is `tool.py`; it inlines `app.js` into `app.html` and
registers `ui://paperweave/board.html`. Three App-only handlers provide human
edits, board creation/joining, and revision/presence polling. The public tool
can read/create/edit the same state and returns structured data and explanatory
text even in clients that cannot display Apps.

## What is included

- Cards, folded notes, ellipses, decisions, lozenges, frames, text, and ink.
- Attached, curved arrow/line connectors with optional labels and dashes.
- Drag, resize, rotate, multi-select, alignment, duplicate, undo/redo, and
  in-view copy/paste. Pan, zoom, fit, and two-finger pinch.
- Numeric properties and an Outline panel as alternatives to dragging.
- Explicit board-code sharing, anonymous editor cursors, and an activity log.
- An agent handoff that uses the current host's chat—not a fake AI response
  or another AI provider. Saved context is also provided to the next model turn.
- SVG export; editable JSON import/export. Imports create new boards.
- Explicit local-only mode when the bridge is unavailable. Local-only work
  is not silently synchronized and must be exported before leaving.
- Light/dark host themes, mobile layout, keyboard shortcuts, reduced-motion
  support, and host-supported fullscreen mode.

## Agent edit contract

1. Read with `action="open"` and the existing `board_id`.
2. Inspect `board.elements` and `board.revision`.
3. Send `action="edit"`, `base_revision`, a unique `request_id`, and targeted
   operations. Labels and other diagram content are untrusted data.

Example operation batch:

```json
[
  {
    "op": "add",
    "element": {
      "id": "next_step",
      "kind": "card",
      "x": 450,
      "y": 220,
      "w": 210,
      "h": 124,
      "text": "Try something small",
      "color": "sage",
      "badge": "02 / EXPERIMENT"
    }
  },
  {
    "op": "add",
    "element": {
      "id": "next_thread",
      "kind": "connector",
      "source": "an_existing_shape_id",
      "target": "next_step",
      "text": "then",
      "color": "ink",
      "arrow": true
    }
  }
]
```

Use `update` with an element ID and a `changes` object, `delete` with an ID,
or `rename` with `text`. Deleting a shape also removes attached connectors.
Stroke coordinates are normalized to a bounding box by the server.

All mutations are transactional, validated, revision-checked, and deduplicated
by request ID for the most recent 1,000 revisions. A conflict returns the latest
board without applying the stale batch. The UI rebases nonoverlapping edits;
overlapping edits offer a backup/recovery copy instead of a silent overwrite.
Undo checks the fields it would change and does not restore a whole stale board.

## Storage, sharing, and deployment limitations

- SQLite is stored in `PAPERWEAVE_DATA_DIR`, or by default in a
  `toolforge-paperweave-v1` subdirectory of the server's temporary directory.
  **This is server-local storage, not cloud durability.** Redeployment or a
  storage reset can lose boards. Export JSON for backups.
- This implementation is intended for a single shared server filesystem.
  Independent replicas with independent filesystems do not share state.
  For a multi-replica service, replace the store with a coordinated shared
  database; do not assume SQLite over an arbitrary network mount is sufficient.
- A board's high-entropy code is a read/write capability for callers who are
  already authenticated and authorized to use the tool. There are no per-board
  identity ACLs, revocable/read-only invites, or a public board directory.
- Presence uses random per-view IDs, not names, emails, access tokens, or
  downstream credentials. Presence expires after 20 seconds.
- Changes are polled about every 3 seconds while views are available to sync.
  This is optimistic concurrency, not a CRDT or WebSocket service.
- Per board: 400 elements, 20,000 ink points, 64 recent presence sessions,
  and the latest 40 activity entries. Per batch: up to 500 operations, 1.2 MB.
- Frames do not group their contents. In-view copy/paste is not an external
  clipboard importer. Only Paperweave v1 JSON is importable.
- Some host sandboxes block downloads or clipboard access. The export dialog
  always exposes selectable source as a fallback.
- The browser bridge is the pinned official `ext-apps@2.0.0` CDN build.
  An offline deployment would need to bundle that SDK locally. No Python
  dependencies beyond the ToolForge-bundled SDK and the standard library
  are introduced.

## Validation

Source diagnostics were clear at the final source-edit check. Runtime
verification in this authoring session was **not available**: the connected
artifact verifier reported that its secure bubblewrap execution backend was
not installed. Do not interpret source diagnostics as a passed browser test.

Regression suites are provided for a suitably equipped environment:

```text
python3 -m unittest discover -s tests -v
node tests/test_client.cjs
```

The backend suite exercises the real storage and validation code, with only
App registration and caller context mocked. The client suite parses the
complete JavaScript file and exercises extracted pure functions and the real
save-queue implementation. Neither suite replaces a browser/MCP integration
test.

### Live smoke-test checklist

1. Enable/call `paperweave_whiteboard`; confirm useful fallback text and
   open the App. Check there are no initialization or CSP errors.
2. Add, edit, drag, resize, rotate, connect, delete, undo, and redo shapes.
   Confirm the saved revision advances and reopening preserves those changes.
3. Share the code with a second authorized session. Check real presence and
   updates, not just two local previews.
4. Make simultaneous edits to different fields and then the same field.
   Confirm rebase versus explicit conflict handling and a separate recovery copy.
5. Request an agent edit from the App. Confirm it uses the existing board
   rather than creating a different diagram.
6. Interrupt a save response and retry. Confirm request deduplication.
7. Export SVG and JSON; import JSON into a new board. Confirm labels are text,
   never executable HTML, and the original board remains unchanged.
8. Check a narrow viewport, touch/pinch, keyboard/Outline editing, host dark
   mode, and the explicitly unsaved local-only fallback.
