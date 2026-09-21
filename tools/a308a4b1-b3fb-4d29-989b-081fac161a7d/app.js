import { App } from "https://cdn.jsdelivr.net/npm/@modelcontextprotocol/ext-apps@2.0.0/dist/src/app-with-deps.js";

const app = new App({ name: "Laya Plays Pokémon", version: "1.0.0" });
const byId = (id) => document.getElementById(id);
const state = {
  tab: crypto.randomUUID(), view: null, timer: null, inFlight: false,
  connected: false, leaving: false, needView: true, calls: 0,
  started: performance.now(), latency: null, lastFrame: null,
  frameAt: null, cadence: null, retired: new Set(), visibilityPending: false,
};

// Rendering consumes only the documented detached view contract.
function duration(value) {
  if (!Number.isFinite(value)) return "—";
  const s = Math.floor(Math.max(0, value));
  return `${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
function list(id, values, empty, format) {
  const target = byId(id);
  target.replaceChildren();
  for (const value of values.length ? values : [null]) {
    const li = document.createElement("li");
    li.textContent = value === null ? empty : format(value);
    target.append(li);
  }
}
function render(view) {
  byId("status").textContent = view.status.replaceAll("_", " ");
  byId("message").textContent = view.message;
  byId("run").textContent = view.run_number || "—";
  byId("active").textContent = duration(view.timing.active_seconds);
  byId("viewers").textContent = String(view.presence.operators);
  byId("runtime").textContent = `Runtime ${view.runtime_id} · revision ${view.revision}`;
  byId("empty-title").textContent = view.status === "setup_required" ? "Setup required" : view.status.replaceAll("_", " ");
  byId("requirements").replaceChildren(...view.requirements.map((text) => {
    const li = document.createElement("li"); li.textContent = text; return li;
  }));
  const frame = byId("frame");
  if (view.frame && view.frame.id !== state.lastFrame) {
    frame.src = `data:image/png;base64,${view.frame.png}`;
    const now = performance.now();
    state.cadence = state.frameAt === null ? null : now - state.frameAt;
    state.frameAt = now;
    state.lastFrame = view.frame.id;
  }
  frame.hidden = !view.frame;
  byId("screen-empty").hidden = Boolean(view.frame);
  byId("game-summary").textContent = view.game?.summary || "";
  list("decisions", view.decisions.slice(-4).reverse(), "No decisions yet.",
       (d) => `${d.action} · ${d.objective} · ${Math.round(d.inference_ms)} ms · ${d.input_tokens} tokens${d.stalled ? " · no observed progress" : ""}`);
  list("fastest", view.fastest_runs, "No verified completions this session.",
       (r) => `Run ${r.run_number} — ${duration(r.active_seconds)}`);
  list("watch", view.watch_leaders, "No watch time recorded yet.",
       (r) => `${r.label} — ${duration(r.watch_seconds)}`);
  byId("own-watch").textContent = `Your watch time: ${duration(view.you.watch_seconds)}`;
  byId("reconnect").hidden = true;
  renderTransport();
}
function renderTransport() {
  const perMinute = state.calls * 60000 / Math.max(1000, performance.now() - state.started);
  byId("transport").textContent = `${state.calls} App calls here · ${perMinute.toFixed(1)}/min observed · last round trip ${state.latency === null ? "—" : Math.round(state.latency) + " ms"} · last frame interval ${state.cadence === null ? "—" : (state.cadence / 1000).toFixed(1) + " s"}. Server cadence is shared; call volume is per viewer.`;
}
function showError(message) {
  byId("status").textContent = "Reconnecting";
  byId("message").textContent = message;
  byId("reconnect").hidden = false;
}
function accept(result) {
  if (result.isError) throw new Error(result.content?.find((c) => c.type === "text")?.text || "Viewer request rejected.");
  const view = result._meta?.view;
  if (!view || view.schema !== 1) throw new Error("The host did not forward the display metadata. Playback stopped; check the MCP App response contract.");
  if (state.retired.has(view.runtime_id)) return;
  if (state.view && state.view.runtime_id !== view.runtime_id) {
    state.retired.add(state.view.runtime_id);
    if (state.retired.size > 8) state.retired.delete(state.retired.values().next().value);
    state.lastFrame = null; state.frameAt = null; state.cadence = null;
    byId("frame").removeAttribute("src");
  } else if (state.view && view.revision < state.view.revision) return;
  state.view = view;
  render(view);
}

// Transport/lifecycle: one request in flight, no per-turn chat/model invocation.
function visible() { return !state.leaving && document.visibilityState === "visible"; }
function schedule(delay) {
  clearTimeout(state.timer);
  if (state.connected && visible()) state.timer = setTimeout(poll, Math.max(1500, delay));
}
async function poll() {
  if (!state.connected || state.inFlight) return;
  clearTimeout(state.timer);
  state.inFlight = true;
  const isVisible = visible();
  const read = state.needView || !isVisible || !state.view;
  const args = { tab_id: state.tab, visible: isVisible,
    runtime_id: state.view?.runtime_id ?? null,
    run_id: state.view?.run_id ?? null, revision: state.view?.revision ?? null };
  const start = performance.now();
  let delay = 15000;
  try {
    state.calls++;
    const result = await app.callServerTool({
      name: read ? "laya_pokemon_view" : "laya_pokemon_playback", arguments: args,
    });
    state.latency = performance.now() - start;
    accept(result);
    state.needView = false;
    delay = state.view?.timing.retry_after_ms ?? 15000;
  } catch (error) {
    state.needView = true;
    showError(error instanceof Error ? error.message : "Connection lost. Reconnecting to the same shared game.");
  } finally {
    state.inFlight = false;
    if (state.visibilityPending) {
      state.visibilityPending = false; state.needView = true;
      void poll();
    } else schedule(delay);
  }
}
function visibilityChanged() {
  clearTimeout(state.timer);
  state.needView = true;
  if (state.inFlight) { state.visibilityPending = true; return; }
  void poll();
}

app.ontoolresult = () => { /* The launch result is not live state. */ };
app.ontoolinput = () => {};
app.onhostcontextchanged = (context) => {
  if (context.theme) document.documentElement.style.colorScheme = context.theme;
};
app.onteardown = async () => {
  state.leaving = true;
  clearTimeout(state.timer);
  if (!state.inFlight && state.connected) { state.needView = true; await poll(); }
  state.connected = false;
  return {};
};
document.addEventListener("visibilitychange", visibilityChanged);
window.addEventListener("pagehide", () => { state.leaving = true; visibilityChanged(); });
window.addEventListener("pageshow", () => { state.leaving = false; visibilityChanged(); });
byId("reconnect").addEventListener("click", () => { state.needView = true; void poll(); });
try {
  await app.connect();
  state.connected = true;
  await poll();
} catch {
  showError("Could not connect to the MCP App host. Reopen the App to try again.");
}
