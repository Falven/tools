import assert from 'node:assert/strict';
import test from 'node:test';
import { RetroAudio } from '../src/catalog_app/tools/minesweeper/frontend/audio.js';

const KEY = 'minesweeper-audio-v1';
const NAMES = ['ui', 'reveal', 'flood', 'flag', 'unflag', 'start', 'win', 'lose'];
const flush = async () => { await Promise.resolve(); await Promise.resolve(); };

class FakeEvents {
  listeners = new Map();
  addEventListener(name, callback) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set());
    this.listeners.get(name).add(callback);
  }
  removeEventListener(name, callback) { this.listeners.get(name)?.delete(callback); }
  dispatch(name) { for (const callback of [...(this.listeners.get(name) ?? [])]) callback(); }
  listenerCount(name) { return this.listeners.get(name)?.size ?? 0; }
}

class FakeParam {
  value = 1;
  events = [];
  setValueAtTime(value, time) { this.value = value; this.events.push(['set', value, time]); }
  linearRampToValueAtTime(value, time) { this.value = value; this.events.push(['linear', value, time]); }
  exponentialRampToValueAtTime(value, time) {
    assert.ok(value > 0, 'exponential ramps must not target zero');
    this.value = value;
    this.events.push(['exponential', value, time]);
  }
  cancelScheduledValues(time) { this.events.push(['cancel', time]); }
}

class FakeNode {
  constructor(context, kind) {
    this.context = context;
    this.kind = kind;
    this.connections = [];
    this.disconnected = false;
    if (kind === 'gain') this.gain = new FakeParam();
    if (kind === 'oscillator' || kind === 'filter') this.frequency = new FakeParam();
    if (kind === 'filter') this.Q = new FakeParam();
  }
  connect(destination) { this.connections.push(destination); return destination; }
  disconnect() { this.disconnected = true; this.connections.length = 0; }
}

class FakeSource extends FakeNode {
  startAt = null;
  stopAt = Infinity;
  stopTimes = [];
  ended = false;
  onended = null;
  start(time) { this.startAt = time; }
  stop(time = this.context.currentTime) {
    this.stopTimes.push(time);
    if (this.startAt === null) throw new Error('source not started');
    this.stopAt = time;
  }
}

class FakeContext extends FakeEvents {
  constructor(behavior) {
    super();
    if (behavior.constructError) throw new Error('context unavailable');
    this.behavior = behavior;
    this.state = behavior.initialState ?? 'suspended';
    this.currentTime = 0;
    this.sampleRate = 24000;
    this.nodes = [];
    this.sources = [];
    this.destination = new FakeNode(this, 'destination');
    this.resumeCalls = this.suspendCalls = this.closeCalls = 0;
  }
  setState(state) {
    if (this.state === state) return;
    this.state = state;
    this.dispatch('statechange');
  }
  resume() {
    this.resumeCalls += 1;
    if (this.behavior.resume) return this.behavior.resume(this);
    this.setState('running');
    return Promise.resolve();
  }
  suspend() {
    this.suspendCalls += 1;
    if (this.behavior.suspend) return this.behavior.suspend(this);
    this.setState('suspended');
    return Promise.resolve();
  }
  close() {
    this.closeCalls += 1;
    if (this.behavior.close) return this.behavior.close(this);
    this.setState('closed');
    return Promise.resolve();
  }
  makeNode(kind) {
    const node = kind === 'oscillator' || kind === 'bufferSource'
      ? new FakeSource(this, kind) : new FakeNode(this, kind);
    this.nodes.push(node);
    if (node instanceof FakeSource) this.sources.push(node);
    return node;
  }
  createGain() {
    if (this.failNextGain) { this.failNextGain = false; throw new Error('gain creation failed'); }
    return this.makeNode('gain');
  }
  createBiquadFilter() { return this.makeNode('filter'); }
  createOscillator() { return this.makeNode('oscillator'); }
  createBufferSource() { return this.makeNode('bufferSource'); }
  createBuffer(channels, length, sampleRate) {
    if (this.behavior.initError) throw new Error('buffer creation failed');
    const data = new Float32Array(length);
    return { length, sampleRate, numberOfChannels: channels, getChannelData: () => data };
  }
  advance(seconds) {
    if (this.state !== 'running') return;
    this.currentTime += seconds;
    for (const source of this.sources) {
      if (!source.ended && source.startAt !== null && source.stopAt <= this.currentTime) {
        source.ended = true;
        source.onended?.();
      }
    }
  }
}

class MemoryStorage {
  data = new Map();
  writes = [];
  getItem(key) {
    if (this.readError) throw new Error('storage blocked');
    return this.data.get(key) ?? null;
  }
  setItem(key, value) {
    if (this.writeError) throw new Error('quota exceeded');
    this.data.set(key, value);
    this.writes.push([key, value]);
  }
}

// No DOM, real AudioContext, actual timers, network, samples, or dependencies.
function harness(t, options = {}) {
  const behavior = options.behavior ?? {};
  const contexts = [];
  const racks = [];
  const storage = new MemoryStorage();
  const document = new FakeEvents();
  document.hidden = Boolean(options.hidden);
  const timers = new Map();
  let nextTimer = 0; // Exercise timer id zero: truthiness is not a safe timer guard.
  let peakTimers = 0;
  const restore = [];
  const install = (name, descriptor) => {
    const previous = Object.getOwnPropertyDescriptor(globalThis, name);
    Object.defineProperty(globalThis, name, { configurable: true, ...descriptor });
    restore.push(() => {
      if (previous) Object.defineProperty(globalThis, name, previous);
      else delete globalThis[name];
    });
  };
  class Context extends FakeContext {
    constructor() { super(behavior); contexts.push(this); }
  }
  install('AudioContext', { value: options.unsupported || options.webkit ? undefined : Context });
  install('webkitAudioContext', { value: options.webkit ? Context : undefined });
  install('document', { value: document });
  install('localStorage', options.blockStorage
    ? { get() { throw new Error('SecurityError'); } }
    : { value: options.noStorage ? undefined : storage });
  install('setInterval', { value: (callback, ms) => {
    assert.ok(ms >= 20, 'do not busy-poll the audio clock');
    const id = nextTimer++;
    timers.set(id, callback);
    peakTimers = Math.max(peakTimers, timers.size);
    return id;
  } });
  install('clearInterval', { value: (id) => timers.delete(id) });
  t.after(() => {
    for (const audio of racks) audio.dispose();
    assert.equal(timers.size, 0, 'all intervals must be released');
    for (const undo of restore.reverse()) undo();
  });
  return {
    behavior, contexts, storage, document, timers,
    get peakTimers() { return peakTimers; },
    get timerStarts() { return nextTimer; },
    create() { const audio = new RetroAudio(); racks.push(audio); return audio; },
    tick() { for (const callback of [...timers.values()]) callback(); },
  };
}

function assertReleased(voices) {
  for (const voice of voices) {
    assert.equal(voice.source.onended, null);
    assert.ok(voice.source.stopTimes.at(-1) <= voice.source.context.currentTime);
    assert.ok(voice.nodes.every((node) => node.disconnected), 'disconnect every voice node');
  }
}

function assertSilent(audio, h) {
  assert.equal(h.timers.size, 0);
  assert.equal(audio._voices.music.size, 0);
  assert.equal(audio._voices.sfx.size, 0);
  if (audio._musicBus) assert.equal(audio._musicBus.gain.value, 0);
  if (audio._sfxBus) assert.equal(audio._sfxBus.gain.value, 0);
}

test('defaults are music off/SFX on, with no context or sound before a gesture', async (t) => {
  const h = harness(t);
  const audio = h.create();
  assert.equal(audio.available, true);
  assert.equal(audio.musicEnabled, false);
  assert.equal(audio.sfxEnabled, true);
  assert.equal(audio.unlocked, false);
  audio.setMusic(true);
  audio.setActive(true);
  for (const name of NAMES) audio.play(name);
  assert.equal(h.contexts.length, 0);
  assert.equal(h.timers.size, 0);
  assert.equal(await audio.unlock(), true);
  assert.equal(audio.unlocked, true);
  assert.equal(h.contexts.length, 1);
  assert.equal(h.timers.size, 1);
});

test('saved preferences never persist permission, activity, or autoplay', async (t) => {
  const h = harness(t);
  h.storage.data.set(KEY, JSON.stringify({
    musicEnabled: true, sfxEnabled: false, unlocked: true, active: true, score: 999,
  }));
  const audio = h.create();
  assert.equal(audio.musicEnabled, true);
  assert.equal(audio.sfxEnabled, false);
  assert.equal(audio.unlocked, false);
  audio.setActive(true);
  audio.play('start');
  assert.equal(h.contexts.length, 0);
  assert.equal(h.storage.writes.length, 0);
  audio.setMusic(false);
  audio.setSfx(true);
  assert.deepEqual(JSON.parse(h.storage.data.get(KEY)), { musicEnabled: false, sfxEnabled: true });
  const writes = h.storage.writes.length;
  await audio.unlock();
  audio.play('reveal');
  audio.suspend();
  audio.setActive(false);
  audio.setActive(true);
  await flush();
  assert.equal(h.storage.writes.length, writes, 'lifecycle operations must not persist anything');
  assert.ok(h.storage.writes.every(([key]) => key === KEY));
  const restored = h.create();
  assert.equal(restored.musicEnabled, false);
  assert.equal(restored.sfxEnabled, true);
  assert.equal(restored.unlocked, false);
});

test('malformed storage and non-boolean preference values retain defaults', (t) => {
  const h = harness(t);
  for (const value of ['', '{broken', 'null', '[]', 'false', '42', '"on"',
    '{"musicEnabled":"true","sfxEnabled":0}']) {
    h.storage.data.set(KEY, value);
    const audio = h.create();
    assert.equal(audio.musicEnabled, false, value);
    assert.equal(audio.sfxEnabled, true, value);
  }
  h.storage.data.set(KEY, '{"musicEnabled":true,"sfxEnabled":"bad"}');
  const partial = h.create();
  assert.equal(partial.musicEnabled, true);
  assert.equal(partial.sfxEnabled, true);
});

for (const mode of ['getter throws', 'methods throw', 'absent']) {
  test(`storage ${mode} does not break preference changes or unlocking`, async (t) => {
    const h = harness(t, { blockStorage: mode === 'getter throws', noStorage: mode === 'absent' });
    if (mode === 'methods throw') h.storage.readError = h.storage.writeError = true;
    const audio = h.create();
    assert.equal(audio.musicEnabled, false);
    assert.equal(audio.sfxEnabled, true);
    assert.doesNotThrow(() => { audio.setMusic(true); audio.setSfx(false); });
    assert.equal(await audio.unlock(), true);
    assert.equal(audio.musicEnabled, true);
    assert.equal(audio.sfxEnabled, false);
    assert.equal(audio._sfxBus.gain.value, 0);
  });
}

test('SFX mute cancels sounding and future effects without changing music', async (t) => {
  const h = harness(t);
  const audio = h.create();
  audio.setMusic(true);
  await audio.unlock();
  audio.play('win');
  const voices = [...audio._voices.sfx];
  const music = [...audio._voices.music];
  const timer = audio._timer;
  assert.ok(voices.some((voice) => voice.source.startAt > h.contexts[0].currentTime + 0.5));
  audio.setSfx(false);
  assert.equal(audio.sfxEnabled, false);
  assert.equal(audio.musicEnabled, true);
  assert.equal(audio._sfxBus.gain.value, 0);
  assert.ok(audio._musicBus.gain.value > 0);
  assert.equal(audio._timer, timer);
  assert.equal(audio._voices.sfx.size, 0);
  assert.deepEqual([...audio._voices.music], music);
  assertReleased(voices);
  assert.deepEqual(audio._sfxBus.gain.events.slice(-2), [['cancel', 0], ['set', 0, 0]]);
  audio.play('ui');
  assert.equal(audio._voices.sfx.size, 0);
  audio.setSfx(true);
  assert.ok(audio._sfxBus.gain.value > 0);
  assert.equal(audio._voices.sfx.size, 0, 'unmuting must not revive a queued fanfare');
  audio.play('ui');
  assert.equal(audio._voices.sfx.size, 1);
});

test('music mute cancels scheduled notes while SFX stay enabled and audible', async (t) => {
  const h = harness(t);
  const audio = h.create();
  audio.setMusic(true);
  await audio.unlock();
  audio.play('flag');
  const music = [...audio._voices.music];
  const effects = [...audio._voices.sfx];
  audio.setMusic(false);
  assert.equal(audio.musicEnabled, false);
  assert.equal(audio.sfxEnabled, true);
  assert.equal(audio._musicBus.gain.value, 0);
  assert.ok(audio._sfxBus.gain.value > 0);
  assert.equal(h.timers.size, 0);
  assertReleased(music);
  assert.deepEqual([...audio._voices.sfx], effects);
  assert.ok(effects.every((voice) => !voice.source.disconnected));
  audio.setMusic(true);
  audio.setMusic(true);
  assert.equal(h.timers.size, 1);
  assert.equal(h.peakTimers, 1);
});

test('each named effect is synthesized, bounded, and cleans up after ending', async (t) => {
  const h = harness(t);
  const audio = h.create();
  await audio.unlock();
  const c = h.contexts[0];
  for (const name of NAMES) {
    audio.play(name);
    const voices = [...audio._voices.sfx];
    assert.ok(voices.length > 0, `${name} must synthesize audio`);
    assert.ok(voices.every((voice) => Number.isFinite(voice.source.stopAt)));
    assert.ok(voices.every((voice) => voice.end - c.currentTime < 1.1));
    c.advance(2);
    assertReleased(voices);
    assert.equal(audio._voices.sfx.size, 0);
  }
  for (const name of ['unknown', '__proto__', 'constructor', null, {}, 42]) audio.play(name);
  assert.equal(audio._voices.sfx.size, 0);
  for (let i = 0; i < 100; i += 1) audio.play('reveal');
  assert.equal(audio._voices.sfx.size, 1, 'rapid clicks are rate-limited');
  for (let i = 0; i < 100; i += 1) {
    c.currentTime += 0.051; // No onended delivery: pruning must still bound voices.
    audio.play('flood');
    audio.play('flag');
    audio.play('reveal');
    assert.ok(audio._voices.sfx.size <= 16);
  }
});

test('the original 104 BPM loop has square lead, triangle bass, quiet local percussion', async (t) => {
  const h = harness(t);
  const audio = h.create();
  audio.setMusic(true);
  await audio.unlock();
  const c = h.contexts[0];
  for (let i = 0; i < 750; i += 1) {
    c.advance(0.05);
    h.tick();
    assert.ok(audio._voices.music.size <= 12);
    assert.equal(h.timers.size, 1);
  }
  const leads = c.sources.filter((source) => source.type === 'square');
  const bass = c.sources.filter((source) => source.type === 'triangle');
  const percussion = c.sources.filter((source) => source.kind === 'bufferSource');
  assert.ok(leads.length > 80 && bass.length > 60 && percussion.length > 60);
  assert.ok(Math.abs(leads[1].startAt - leads[0].startAt - 60 / 104) < 1e-8);
  const loopSeconds = 8 * 4 * 60 / 104;
  const repeated = leads.find((source) => Math.abs(source.startAt - leads[0].startAt - loopSeconds) < 1e-8);
  assert.ok(repeated, 'the complete eight-bar phrase loops at its musical boundary');
  assert.equal(repeated.frequency.events[0][1], leads[0].frequency.events[0][1]);
  assert.equal(new Set(percussion.map((source) => source.buffer)).size, 1, 'reuse synthesized noise');
  assert.ok(audio._noiseBuffer.getChannelData(0).some((sample) => sample !== 0));
  assert.ok(audio._noiseBuffer.getChannelData(0).every((sample) => Math.abs(sample) <= 1));
  const before = c.sources.length;
  c.advance(300);
  h.tick();
  assert.ok(c.sources.length - before <= 5, 'a delayed timer must not replay its backlog');
  assert.ok(c.sources.slice(before).every((source) => source.startAt >= c.currentTime));
  assert.equal(h.peakTimers, 1);
});

test('active/hidden lifecycle immediately silences both buses and never stacks timers', async (t) => {
  const h = harness(t);
  const audio = h.create();
  audio.setMusic(true);
  await Promise.all([audio.unlock(), audio.unlock(), audio.unlock()]);
  const c = h.contexts[0];
  assert.equal(h.contexts.length, 1);
  assert.equal(h.timerStarts, 1);
  audio.play('win');
  const voices = [...audio._voices.music, ...audio._voices.sfx];
  audio.setActive(false);
  assertSilent(audio, h);
  assertReleased(voices);
  assert.equal(c.state, 'suspended');
  assert.equal(audio.unlocked, true, 'suspension is not a permission preference');
  h.document.hidden = true;
  h.document.dispatch('visibilitychange');
  assert.equal(await audio.unlock(), false);
  h.document.hidden = false;
  h.document.dispatch('visibilitychange');
  await flush();
  assertSilent(audio, h); // Explicit inactive state wins over visible state.
  for (let i = 0; i < 5; i += 1) audio.setActive(true);
  await flush();
  assert.equal(h.timers.size, 1);
  assert.equal(h.timerStarts, 2);
  assert.equal(audio._voices.sfx.size, 0);
  assert.ok(audio._sfxBus.gain.value > 0);
  for (let cycle = 0; cycle < 5; cycle += 1) {
    audio.suspend();
    audio.suspend();
    assertSilent(audio, h);
    audio.setActive(true);
    await audio.unlock();
    assert.equal(h.timers.size, 1);
  }
  assert.equal(h.peakTimers, 1);
  h.document.hidden = true;
  h.document.dispatch('visibilitychange');
  assertSilent(audio, h);
  h.document.hidden = false;
  h.document.dispatch('visibilitychange');
  await flush();
  assert.equal(h.timers.size, 1, 'visibility can resume previously unlocked audio');
});

test('a hidden initial app cannot create or unlock an AudioContext', async (t) => {
  const h = harness(t, { hidden: true });
  const audio = h.create();
  audio.setMusic(true);
  assert.equal(await audio.unlock(), false);
  assert.equal(h.contexts.length, 0);
  h.document.hidden = false;
  audio.setActive(true);
  assert.equal(h.contexts.length, 0);
  assert.equal(await audio.unlock(), true);
});

test('browser suspension/interruption clears voices and restarts with only one timer', async (t) => {
  const h = harness(t);
  const audio = h.create();
  audio.setMusic(true);
  await audio.unlock();
  const c = h.contexts[0];
  for (const state of ['suspended', 'interrupted']) {
    audio.play('start');
    const voices = [...audio._voices.music, ...audio._voices.sfx];
    c.setState(state);
    assertSilent(audio, h);
    assertReleased(voices);
    audio.play('ui');
    assert.equal(audio._voices.sfx.size, 0);
    audio.setActive(true);
    await flush();
    assert.equal(h.timers.size, 1);
    assert.equal(audio.unlocked, true);
  }
  c.setState('closed');
  assert.equal(audio.available, false);
  assert.equal(audio.unlocked, false);
  assertSilent(audio, h);
  assert.ok(c.nodes.every((node) => node.disconnected));
  assert.equal(c.closeCalls, 0, 'do not close an already-closed context');
});

test('unsupported Web Audio remains inert and every lifecycle method is safe', async (t) => {
  const h = harness(t, { unsupported: true });
  const audio = h.create();
  assert.equal(audio.available, false);
  audio.setMusic(true);
  audio.setSfx(false);
  audio.setActive(false);
  audio.suspend();
  audio.setActive(true);
  for (const name of NAMES) audio.play(name);
  assert.equal(await audio.unlock(), false);
  audio.dispose();
  audio.dispose();
  audio.setMusic(false);
  audio.setSfx(true);
  assert.equal(await audio.unlock(), false);
  assert.equal(h.contexts.length, 0);
  assert.equal(h.timers.size, 0);
});

test('the webkitAudioContext fallback can unlock without starting default music', async (t) => {
  const h = harness(t, { webkit: true });
  const audio = h.create();
  assert.equal(audio.available, true);
  assert.equal(await audio.unlock(), true);
  assert.equal(h.contexts.length, 1);
  assert.equal(h.timers.size, 0);
  audio.play('ui');
  assert.equal(audio._voices.sfx.size, 1);
});

for (const failure of ['constructError', 'initError']) {
  test(`${failure} is contained and partially-created nodes are cleaned up`, async (t) => {
    const h = harness(t, { behavior: { [failure]: true } });
    const audio = h.create();
    audio.setMusic(true);
    assert.equal(await audio.unlock(), false);
    assert.equal(audio.available, false);
    assert.equal(audio.unlocked, false);
    assertSilent(audio, h);
    for (const c of h.contexts) {
      assert.equal(c.closeCalls, 1);
      assert.ok(c.nodes.every((node) => node.disconnected));
    }
  });
}

test('resume rejection/throw is retryable, without setting unlocked or scheduling audio', async (t) => {
  const h = harness(t, { behavior: { resume: () => Promise.reject(new Error('NotAllowedError')) } });
  const audio = h.create();
  audio.setMusic(true);
  assert.equal(await audio.unlock(), false);
  assert.equal(audio.available, true);
  assert.equal(audio.unlocked, false);
  assertSilent(audio, h);
  h.behavior.resume = () => { throw new Error('interrupted'); };
  assert.equal(await audio.unlock(), false);
  assertSilent(audio, h);
  delete h.behavior.resume;
  assert.equal(await audio.unlock(), true);
  assert.equal(h.contexts.length, 1);
  assert.equal(h.timers.size, 1);
});

test('suspend/close rejection or synchronous throw cannot leave audible nodes', async (t) => {
  const h = harness(t, { behavior: {
    suspend: () => Promise.reject(new Error('suspend denied')),
    close: () => Promise.reject(new Error('close denied')),
  } });
  const audio = h.create();
  audio.setMusic(true);
  await audio.unlock();
  audio.play('win');
  audio.setActive(false);
  await flush();
  assertSilent(audio, h);
  assert.equal(h.contexts[0].state, 'running', 'rejection simulates a still-running browser context');
  h.behavior.suspend = () => { throw new Error('suspend threw'); };
  audio.suspend();
  assertSilent(audio, h);
  audio.setActive(true);
  await flush();
  assert.equal(h.timers.size, 1);
  audio.dispose();
  await flush();
  assert.ok(h.contexts[0].nodes.every((node) => node.disconnected));
  h.behavior.close = () => { throw new Error('close threw'); };
  const second = h.create();
  await second.unlock();
  assert.doesNotThrow(() => second.dispose());
});

test('hiding during a pending gesture resume does not unlock or revive audio', async (t) => {
  let resolve;
  const pending = new Promise((done) => { resolve = done; });
  const h = harness(t, { behavior: { resume: (c) => pending.then(() => c.setState('running')) } });
  const audio = h.create();
  audio.setMusic(true);
  const unlocking = audio.unlock();
  audio.setActive(false);
  resolve();
  assert.equal(await unlocking, false);
  assert.equal(audio.unlocked, false);
  assert.equal(h.contexts[0].state, 'suspended');
  assertSilent(audio, h);
  delete h.behavior.resume;
  audio.setActive(true);
  assertSilent(audio, h);
  assert.equal(await audio.unlock(), true, 'a fresh deliberate gesture can retry');
});

test('dispose cancels pending unlocks, disconnects every node, and removes listeners', async (t) => {
  let resolve;
  const pending = new Promise((done) => { resolve = done; });
  const h = harness(t, { behavior: { resume: () => pending } });
  const audio = h.create();
  audio.setMusic(true);
  const unlocking = audio.unlock();
  const c = h.contexts[0];
  assert.equal(c.listenerCount('statechange'), 1);
  assert.equal(h.document.listenerCount('visibilitychange'), 1);
  audio.dispose();
  resolve();
  assert.equal(await unlocking, false);
  assert.equal(await audio.unlock(), false);
  assert.equal(audio.available, false);
  assert.equal(audio.unlocked, false);
  assert.equal(c.closeCalls, 1);
  assert.equal(c.listenerCount('statechange'), 0);
  assert.equal(h.document.listenerCount('visibilitychange'), 0);
  assert.ok(c.nodes.every((node) => node.disconnected));
  assert.equal(audio._noiseBuffer, null);
  assertSilent(audio, h);
  audio.setActive(true);
  audio.play('win');
  audio.dispose();
  assert.equal(c.closeCalls, 1);
});

test('dispose during playback cleans music, queued effects, gains, and interval', async (t) => {
  const h = harness(t);
  const audio = h.create();
  audio.setMusic(true);
  await audio.unlock();
  audio.play('win');
  const c = h.contexts[0];
  const voices = [...audio._voices.music, ...audio._voices.sfx];
  audio.dispose();
  assertReleased(voices);
  assertSilent(audio, h);
  assert.equal(c.closeCalls, 1);
  assert.ok(c.nodes.every((node) => node.disconnected));
  assert.equal(audio._context, null);
  assert.equal(h.document.listenerCount('visibilitychange'), 0);
});

test('a synthesis failure cleans partially-created oscillators without interrupting play', async (t) => {
  const h = harness(t);
  const audio = h.create();
  await audio.unlock();
  const c = h.contexts[0];
  c.failNextGain = true;
  assert.doesNotThrow(() => audio.play('reveal'));
  assert.equal(audio._voices.sfx.size, 0);
  assert.equal(c.sources.at(-1).disconnected, true);
  audio.play('flag');
  assert.equal(audio._voices.sfx.size, 2, 'a later sound can still play');
});
