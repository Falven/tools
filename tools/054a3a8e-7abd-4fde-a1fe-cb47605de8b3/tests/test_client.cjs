/* No dependencies. Run: node tests/test_client.cjs
 * Parses ALL app.js, then tests its actual pure functions and save queue.
 * This does not emulate DOM rendering, pointer events, or the real MCP bridge.
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { webcrypto } = require("node:crypto");
const source = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");
new vm.Script(source, { filename: "app.js" });
function slice(start, end) {
  const a = source.indexOf(start), b = source.indexOf(end, a + start.length);
  assert(a >= 0 && b > a, `Test extraction marker missing: ${start}`);
  return source.slice(a, b);
}
const setup = `
const state = { viewport:{z:1}, selected:new Set(), undo:[], redo:[] };
const measure = null;
const byId = (board, id) => board.elements.find(e => e.id === id);
function visibleElements(){ return state.view.elements; }
function scheduleRender(){}
function status(){}
function queueContext(){}
function hideBanner(){}
function banner(){}
function toast(){}
function conflict(){ state.paused = "conflict"; }
let callImpl;
async function call(name, args){ return callImpl(name, args); }
`;
const pieces = [
  source.slice(0, source.indexOf("\nicons();")),
  setup,
  slice("function localApply(", "function visibleElements("),
  slice("function rotate(", "function screenPoint("),
  slice("function textLines(", "function selectionMarkup("),
  slice("function finalizeHistory(", "function enqueue("),
  slice("async function drain(", "async function poll("),
  slice("function exportedJSON(", "function exportDialog("),
  slice("function parseImport(", "function importDialog("),
  `globalThis.api={state,clone,clean,equal,localApply,capture,canRebase,difference,
    exportedJSON,exportedSVG,parseImport,nodeMarkup,wire,drain,finalizeHistory,
    setCall:fn=>{callImpl=fn;}};`,
];
const context = vm.createContext({ console, crypto: webcrypto, TextEncoder });
new vm.Script(pieces.join("\n"), { filename: "paperweave-pure-functions.js" }).runInContext(context);
const api = context.api;
const plain = data => JSON.parse(JSON.stringify(data));
const node = (id, text = id, x = 0) => ({
  id, kind: "card", x, y: 0, w: 200, h: 120, text, color: "sage", font_size: 22, angle: 0, badge: "",
});
const board = (elements = [node("a"), node("b", "b", 350)]) => ({
  id: "pw_0123456789abcdef0123456789abcdef", title: "A test board", revision: 0, elements, history: [],
});
function entry(before, ops) {
  const after = api.localApply(before, ops);
  return { ops, expected: api.capture(ops, before), inverse: api.difference(after, before), after, request: "request_0001", history: "edit" };
}
function prepare(before, edit) {
  Object.assign(api.state, {
    confirmed: api.clone(before), view: api.localApply(before, edit.ops),
    selected: new Set(), pending: [edit], undo: [], redo: [], saving: false,
    connected: true, paused: null, deferred: null, recovery: null,
  });
}
async function run() {
  const before = board();
  const ops = [{ op: "update", id: "a", changes: { text: "My idea" } }];
  const edit = entry(before, ops);
  const unrelated = api.localApply(before, [{ op: "update", id: "b", changes: { text: "Their idea" } }]);
  assert(api.canRebase(edit, unrelated), "disjoint edits must rebase");
  const overlap = api.localApply(before, [{ op: "update", id: "a", changes: { text: "A competing idea" } }]);
  assert(!api.canRebase(edit, overlap), "same-field edits must not overwrite");
  assert.deepEqual(plain(api.localApply(api.localApply(before, ops), edit.inverse).elements), before.elements);

  const linked = board([...before.elements, {
    id: "thread", kind: "connector", source: "a", target: "b", text: "", color: "ink",
    x: 0, y: 0, w: 200, h: 120, font_size: 13, badge: "", angle: 0, arrow: true, dashed: false,
  }]);
  const deleted = api.localApply(linked, [{ op: "delete", id: "a" }]);
  assert.deepEqual(plain(deleted.elements.map(e => e.id)), ["b"], "deletion cascades to threads");
  const restored = api.localApply(deleted, api.difference(deleted, linked));
  assert(api.equal(restored.elements.slice().sort((a,b)=>a.id.localeCompare(b.id)), linked.elements.slice().sort((a,b)=>a.id.localeCompare(b.id))));
  const deletion = entry(before, [{ op: "delete", id: "a" }]);
  assert(!api.canRebase(deletion, linked), "undo/delete must protect a newly attached collaborator thread");

  const roundTrip = api.parseImport(api.exportedJSON(linked));
  assert.deepEqual(plain(roundTrip.elements), linked.elements);
  assert(!api.exportedJSON(linked).includes(linked.id), "backups must not contain a board access code");
  const malicious = node("test", '<script>alert("x")</script> & a note');
  const markup = api.nodeMarkup(malicious, true);
  assert(!markup.includes('<script>'), "labels must be escaped");
  assert(markup.includes("&lt;script&gt;"));
  const svg = api.exportedSVG(linked);
  assert(svg.startsWith('<?xml'));
  assert(svg.includes('xmlns="http://www.w3.org/2000/svg"'));
  assert(!svg.includes("selection-handle"));
  assert(!svg.includes("var(--"), "SVG exports must be self-contained");
  const wireBefore = api.wire(linked.elements[2], linked.elements);
  const moved = api.localApply(linked, [{ op: "update", id: "a", changes: { x: 100, y: 170 } }]);
  assert.notEqual(api.wire(moved.elements[2], moved.elements).d, wireBefore.d);
  for (const invalid of [
    '{"format":"excalidraw","version":1,"elements":[]}',
    JSON.stringify({ format:"paperweave",version:1,title:"x",elements:[node("dup"),node("dup")] }),
    JSON.stringify({ format:"paperweave",version:1,title:"x",elements:[{...node("bad"),x:20001}] }),
    JSON.stringify({ format:"paperweave",version:1,title:"x",elements:[{...node("bad"),text:"\u0000"}] }),
  ]) assert.throws(() => api.parseImport(invalid));

  // A stale edit changing a DIFFERENT field is retried against the new revision.
  prepare(before, entry(before, ops));
  unrelated.revision = 1;
  let calls = 0;
  api.setCall(async (_, args) => {
    calls++;
    assert.equal(args.base_revision, calls - 1);
    if (calls === 1) return { ok:false,code:"conflict",board:api.clone(unrelated) };
    const saved = api.localApply(unrelated, ops); saved.revision = 2;
    return { ok:true,board:saved,applied_revision:2 };
  });
  await api.drain();
  assert.equal(calls, 2);
  assert.equal(api.state.pending.length, 0);
  assert.equal(api.state.confirmed.elements.find(e=>e.id==="b").text, "Their idea");

  // A stale edit changing the SAME field pauses for explicit recovery.
  prepare(before, entry(before, ops));
  calls = 0; overlap.revision = 1;
  api.setCall(async () => { calls++; return { ok:false,code:"conflict",board:api.clone(overlap) }; });
  await api.drain();
  assert.equal(calls, 1);
  assert.equal(api.state.paused, "conflict");
  assert.equal(api.state.recovery.elements.find(e=>e.id==="a").text, "My idea");

  // Lost response: retry the SAME base and request, even if a newer board arrives.
  // A later collaborator value must never become the authorization basis for undo.
  const empty = board([]);
  const addition = [{ op:"add",element:node("new", "My saved value") }];
  prepare(empty, entry(empty, addition));
  api.setCall(async () => { throw new Error("Simulated transport loss"); });
  await api.drain();
  assert.equal(api.state.paused, "network");
  const later = board([node("new", "Their later value")]); later.revision = 2;
  api.state.deferred = later; api.state.paused = null;
  api.setCall(async (_, args) => {
    assert.equal(args.base_revision, 0, "uncertain retries must retain original base");
    assert.equal(args.request_id, "request_0001");
    return { ok:true,replayed:true,applied_revision:1,board:api.clone(later) };
  });
  await api.drain();
  const undo = api.state.undo.at(-1);
  assert(!api.canRebase({ops:undo.undo,expected:undo.undoExpected}, later), "undo must not erase a later collaborator edit");
  console.log("PASS: full JavaScript syntax, pure diagram functions, escaping/import/export, conflict rebase, protected undo, and uncertain retry logic.");
}
run().catch(error => { console.error(error); process.exitCode = 1; });
