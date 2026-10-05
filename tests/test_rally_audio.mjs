import assert from 'node:assert/strict';
import test from 'node:test';
import { RallyAudio } from '../src/catalog_app/tools/rally_pong/frontend/audio.js';

const KEY = 'rally-pong-audio-v1';
const NAMES = ['ui', 'serve', 'paddle', 'rival', 'wall', 'goal', 'miss', 'win', 'lose'];
const flush = async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); };
const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

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
  record(kind, value, time) {
    assert.ok(Number.isFinite(value), 'all audio parameter values must be finite');
    assert.ok(Number.isFinite(time) && time >= 0, 'all audio times must be nonnegative and finite');
    this.value = value;
    this.events.push([kind, value, time]);
  }
  setValueAtTime(value, time) { this.record('set', value, time); }
  linearRampToValueAtTime(value, time) { this.record('linear', value, time); }
  exponentialRampToValueAtTime(value, time) {
    assert.ok(value > 0, 'exponential envelopes cannot target zero');
    this.record('exponential', value, time);
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
    if (kind === 'compressor') {
      for (const name of ['threshold', 'knee', 'ratio', 'attack', 'release']) this[name] = new FakeParam();
    }
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
  start(time) {
    assert.ok(time >= this.context.currentTime, 'no source should be scheduled in the past');
    assert.equal(this.context.state, 'running', 'only schedule while the context runs');
    this.startAt = time;
  }
  stop(time = this.context.currentTime) {
    this.stopTimes.push(time);
    if (this.startAt === null) throw new Error('source not started');
    this.stopAt = time;
  }
}

class FakeContext extends FakeEvents {
  constructor(behavior, options) {
    super();
    if (behavior.constructError) throw new Error('context unavailable');
    this.behavior = behavior;
    this.options = options;
    this.state = behavior.initialState ?? 'suspended';
    this.currentTime = 0;
    this.sampleRate = 24000;
    this.nodes = [];
    this.sources = [];
    this.destination = new FakeNode(this, 'destination');
    this.resumeCalls = this.suspendCalls = this.closeCalls = 0;
    if (behavior.noLimiter) this.createDynamicsCompressor = undefined;
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
    if (this.failNextGain || this.behavior.gainError) {
      this.failNextGain = false;
      throw new Error('gain creation failed');
    }
    return this.makeNode('gain');
  }
  createBiquadFilter() {
    if (this.failNextFilter) { this.failNextFilter = false; throw new Error('filter creation failed'); }
    return this.makeNode('filter');
  }
  createDynamicsCompressor() { return this.makeNode('compressor'); }
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
  reads = [];
  writes = [];
  getItem(key) {
    if (this.readError) throw new Error('storage blocked');
    this.reads.push(key);
    return this.data.get(key) ?? null;
  }
  setItem(key, value) {
    if (this.writeError) throw new Error('quota exceeded');
    this.data.set(key, value);
    this.writes.push([key, value]);
  }
}

// No real audio, browser, network, timers, assets, or third-party test dependencies.
function harness(t, options = {}) {
  const behavior = options.behavior ?? {};
  const contexts = [];
  const racks = [];
  const storage = new MemoryStorage();
  const document = new FakeEvents();
  document.hidden = Boolean(options.hidden);
  const timers = new Map();
  let nextTimer = 0; // Timer id zero must be cleaned up too.
  let peakTimers = 0;
  let inGesture = false;
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
    constructor(settings) {
      super(behavior, settings);
      this.createdInGesture = inGesture;
      this.resumeGestures = [];
      contexts.push(this);
    }
    resume() { this.resumeGestures.push(inGesture); return super.resume(); }
  }
  install('AudioContext', options.contextGetterThrows
    ? { get() { throw new Error('AudioContext access denied'); } }
    : { value: options.unsupported || options.webkit ? undefined : Context });
  install('webkitAudioContext', { value: options.webkit ? Context : undefined });
  install('document', { value: options.noDocument ? undefined : document });
  install('localStorage', options.blockStorage
    ? { get() { throw new Error('SecurityError'); } }
    : { value: options.noStorage ? undefined : storage });
  install('fetch', { value: () => assert.fail('the synth must never use the network') });
  install('setInterval', { value: (callback, ms) => {
    if (behavior.timerError) throw new Error('timer unavailable');
    assert.ok(ms >= 20, 'do not busy-poll the audio clock');
    const id = nextTimer++;
    timers.set(id, callback);
    peakTimers = Math.max(peakTimers, timers.size);
    return id;
  } });
  install('clearInterval', { value: (id) => timers.delete(id) });
  t.after(() => {
    for (const audio of racks) audio.dispose();
    assert.equal(timers.size, 0, 'dispose must clear every scheduler');
    assert.equal(document.listenerCount('visibilitychange'), 0, 'dispose must remove listeners');
    for (const undo of restore.reverse()) undo();
  });
  return {
    behavior, contexts, storage, document, timers,
    get peakTimers() { return peakTimers; },
    get timerStarts() { return nextTimer; },
    create() { const audio = new RallyAudio(); racks.push(audio); return audio; },
    tick() { for (const callback of [...timers.values()]) callback(); },
    gesture(callback) {
      inGesture = true;
      try { return callback(); } finally { inGesture = false; }
    },
  };
}

function assertReleased(voices) {
  for (const voice of voices) {
    if (voice.source) {
      assert.equal(voice.source.onended, null);
      assert.ok(voice.source.stopTimes.at(-1) <= voice.source.context.currentTime);
    }
    assert.ok(voice.nodes.every((node) => node.disconnected), 'disconnect every voice node');
  }
}

function assertSilent(audio, h) {
  assert.equal(h.timers.size, 0);
  assert.deepEqual(audio.diagnostics().voices, { music: 0, sfx: 0 });
  if (audio._musicBus) assert.equal(audio._musicBus.gain.value, 0);
  if (audio._sfxBus) assert.equal(audio._sfxBus.gain.value, 0);
}

function assertBounded(audio) {
  const { voices, voiceLimits, timers } = audio.diagnostics();
  assert.ok(voices.music <= voiceLimits.music && voices.sfx <= voiceLimits.sfx);
  assert.ok(timers <= 1);
}

test('defaults are music on/SFX on but initialization and controls cannot create audio', async (t) => {
  const h = harness(t);
  const audio = h.create();
  assert.equal(audio.available, true);
  assert.equal(audio.musicEnabled, true);
  assert.equal(audio.sfxEnabled, true);
  assert.equal(audio.unlocked, false);
  assert.equal(h.document.listenerCount('visibilitychange'), 0);
  audio.setMusic(false);
  audio.setSfx(false);
  audio.setMusic(true);
  audio.setSfx(true);
  audio.setActive(false);
  audio.suspend();
  audio.setActive(true);
  h.document.dispatch('visibilitychange');
  for (const name of NAMES) assert.equal(audio.play(name), false);
  await flush();
  assert.equal(h.contexts.length, 0);
  assertSilent(audio, h);
  assert.equal(audio.diagnostics().contextState, 'none');
});

test('unlock creates and resumes synchronously inside the gesture, before any await', async (t) => {
  const ready = deferred();
  const h = harness(t, { behavior: { resume: (c) => ready.promise.then(() => c.setState('running')) } });
  const audio = h.create();
  const unlocking = h.gesture(() => audio.unlock());
  assert.equal(h.contexts.length, 1, 'construction must not defer beyond the gesture');
  const c = h.contexts[0];
  assert.equal(c.createdInGesture, true);
  assert.deepEqual(c.resumeGestures, [true], 'resume must be invoked before the gesture returns');
  assert.deepEqual(c.options, { latencyHint: 'interactive' });
  assert.equal(audio.unlocked, false);
  assert.equal(audio.play('serve'), false);
  assertSilent(audio, h);
  ready.resolve();
  assert.equal(await unlocking, true);
  assert.equal(audio.unlocked, true);
  assert.equal(h.timers.size, 1);
  assert.equal(audio.play('serve'), true);
});

test('an initially running browser context is still silent until unlock succeeds', async (t) => {
  const ready = deferred();
  const h = harness(t, { behavior: { initialState: 'running', resume: () => ready.promise } });
  const audio = h.create();
  const unlocking = audio.unlock();
  assertSilent(audio, h);
  h.contexts[0].dispatch('statechange');
  assertSilent(audio, h);
  ready.resolve();
  assert.equal(await unlocking, true);
  assert.equal(h.timers.size, 1);
});

test('concurrent unlocks use one context and one scheduler, including timer id zero', async (t) => {
  const h = harness(t);
  const audio = h.create();
  assert.deepEqual(await Promise.all([audio.unlock(), audio.unlock(), audio.unlock()]), [true, true, true]);
  assert.equal(h.contexts.length, 1);
  assert.equal(audio._timer, 0);
  assert.equal(h.timerStarts, 1);
  const calls = h.contexts[0].resumeCalls;
  for (let i = 0; i < 10; i += 1) {
    audio.setActive(true);
    audio.setMusic(true);
    assert.equal(await audio.unlock(), true);
  }
  assert.equal(h.contexts[0].resumeCalls, calls, 'do not issue repeated resumes while ready');
  assert.equal(h.peakTimers, 1);
  audio.setMusic(false);
  assert.equal(h.timers.size, 0);
});

test('preferences restore only booleans, never permission, identity, scores, or autoplay', async (t) => {
  const h = harness(t);
  h.storage.data.set(KEY, JSON.stringify({
    musicEnabled: false, sfxEnabled: true, unlocked: true, active: true,
    score: 100, auth: 'do-not-copy', player: 'do-not-copy',
  }));
  const audio = h.create();
  assert.equal(audio.musicEnabled, false);
  assert.equal(audio.sfxEnabled, true);
  assert.equal(audio.unlocked, false);
  audio.setActive(true);
  audio.play('win');
  assert.equal(h.contexts.length, 0);
  assert.equal(h.storage.writes.length, 0);
  audio.setMusic(true);
  audio.setSfx(false);
  assert.deepEqual(JSON.parse(h.storage.data.get(KEY)), { musicEnabled: true, sfxEnabled: false });
  const writes = h.storage.writes.length;
  await audio.unlock();
  audio.play('serve');
  audio.suspend();
  audio.setActive(false);
  audio.setActive(true);
  await flush();
  audio.diagnostics();
  assert.equal(h.storage.writes.length, writes, 'lifecycle and diagnostics never write storage');
  assert.ok(h.storage.reads.every((key) => key === KEY));
  assert.ok(h.storage.writes.every(([key]) => key === KEY));
  const restored = h.create();
  assert.equal(restored.musicEnabled, true);
  assert.equal(restored.sfxEnabled, false);
  assert.equal(restored.unlocked, false);
});

test('malformed JSON, arrays, and nonboolean values preserve the independent defaults', (t) => {
  const h = harness(t);
  for (const value of ['', '{broken', 'null', '[]', 'false', '42', '"on"',
    '{"musicEnabled":"false","sfxEnabled":0}']) {
    h.storage.data.set(KEY, value);
    const audio = h.create();
    assert.equal(audio.musicEnabled, true, value);
    assert.equal(audio.sfxEnabled, true, value);
  }
  h.storage.data.set(KEY, '{"musicEnabled":false,"sfxEnabled":"bad"}');
  const first = h.create();
  assert.equal(first.musicEnabled, false);
  assert.equal(first.sfxEnabled, true);
  h.storage.data.set(KEY, '{"musicEnabled":null,"sfxEnabled":false}');
  const second = h.create();
  assert.equal(second.musicEnabled, true);
  assert.equal(second.sfxEnabled, false);
});

for (const mode of ['getter throws', 'methods throw', 'absent']) {
  test(`storage ${mode} cannot break controls or gesture unlocking`, async (t) => {
    const h = harness(t, { blockStorage: mode === 'getter throws', noStorage: mode === 'absent' });
    if (mode === 'methods throw') h.storage.readError = h.storage.writeError = true;
    const audio = h.create();
    assert.equal(audio.musicEnabled, true);
    assert.equal(audio.sfxEnabled, true);
    assert.doesNotThrow(() => { audio.setMusic(false); audio.setSfx(false); audio.setSfx(true); });
    assert.equal(await audio.unlock(), true);
    assert.equal(audio.musicEnabled, false);
    assert.equal(audio.sfxEnabled, true);
    assert.equal(h.timers.size, 0);
    assert.equal(audio.play('paddle'), true);
  });
}

test('SFX mute kills playing and future voices without touching the music bus or timer', async (t) => {
  const h = harness(t);
  const audio = h.create();
  await audio.unlock();
  audio.play('win');
  const voices = [...audio._voices.sfx];
  const music = [...audio._voices.music];
  const timer = audio._timer;
  assert.ok(voices.some((voice) => voice.start > 0.4), 'the cue contains genuinely queued notes');
  audio.setSfx(false);
  assert.equal(audio.musicEnabled, true);
  assert.equal(audio.sfxEnabled, false);
  assert.equal(audio._sfxBus.gain.value, 0);
  assert.ok(audio._musicBus.gain.value > 0);
  assert.equal(audio._timer, timer);
  assert.deepEqual([...audio._voices.music], music);
  assert.equal(audio._voices.sfx.size, 0);
  assertReleased(voices);
  assert.deepEqual(audio._sfxBus.gain.events.slice(-2), [['cancel', 0], ['set', 0, 0]]);
  audio.setSfx(true);
  assert.equal(audio._voices.sfx.size, 0, 'unmuting must not resurrect a fanfare');
  assert.ok(audio._sfxBus.gain.value > 0);
  assert.equal(audio.play('paddle'), true, 'mute also clears stale cue suppression/cooldown');
});

test('music mute cancels queued notes and its timer without silencing a queued SFX fanfare', async (t) => {
  const h = harness(t);
  const audio = h.create();
  await audio.unlock();
  audio.play('win');
  const music = [...audio._voices.music];
  const sfx = [...audio._voices.sfx];
  assert.ok(music.some((voice) => voice.start > h.contexts[0].currentTime));
  audio.setMusic(false);
  assert.equal(audio.sfxEnabled, true);
  assert.equal(audio._musicBus.gain.value, 0);
  assert.ok(audio._sfxBus.gain.value > 0);
  assert.equal(h.timers.size, 0);
  assertReleased(music);
  assert.deepEqual([...audio._voices.sfx], sfx);
  assert.ok(sfx.every((voice) => !voice.source.disconnected));
  audio.setMusic(true);
  audio.setMusic(true);
  assert.equal(h.timers.size, 1);
  assert.equal(h.peakTimers, 1);
});

test('both muted buses stay silent after unlocking and can be reenabled independently', async (t) => {
  const h = harness(t);
  h.storage.data.set(KEY, '{"musicEnabled":false,"sfxEnabled":false}');
  const audio = h.create();
  assert.equal(await audio.unlock(), true);
  assertSilent(audio, h);
  audio.setSfx(true);
  assert.equal(h.timers.size, 0);
  assert.equal(audio.play('serve'), true);
  audio.setMusic(true);
  assert.equal(h.timers.size, 1);
  audio.setSfx(false);
  assert.equal(audio._voices.sfx.size, 0);
  assert.equal(h.timers.size, 1);
});

test('preference changes during a pending unlock are honored when it resolves', async (t) => {
  const ready = deferred();
  const h = harness(t, { behavior: { resume: (c) => ready.promise.then(() => c.setState('running')) } });
  const audio = h.create();
  const unlocking = audio.unlock();
  audio.setMusic(false);
  audio.setSfx(false);
  ready.resolve();
  assert.equal(await unlocking, true);
  assertSilent(audio, h);
  audio.setSfx(true);
  audio.play('serve');
  assert.equal(h.timers.size, 0);
  assert.ok(audio._voices.sfx.size > 0);
});

test('all nine events synthesize short bounded sounds and naturally release every node', async (t) => {
  const h = harness(t);
  const audio = h.create();
  audio.setMusic(false);
  await audio.unlock();
  const c = h.contexts[0];
  for (const name of NAMES) {
    assert.equal(audio.play(name, { rally: 12 }), true, name);
    const voices = [...audio._voices.sfx];
    assert.ok(voices.length > 0, `${name} must synthesize audio`);
    assert.ok(voices.every((voice) => Number.isFinite(voice.source.stopAt)));
    assert.ok(voices.every((voice) => voice.end - c.currentTime < 1));
    c.advance(2);
    assertReleased(voices);
    assert.equal(audio._voices.sfx.size, 0);
    assert.equal(h.timers.size, 0, 'SFX never need a JavaScript cleanup timer');
  }
  for (const name of ['unknown', '__proto__', 'constructor', null, {}, 42]) {
    assert.equal(audio.play(name), false);
  }
  assert.equal(audio._voices.sfx.size, 0);
});

test('rally intensity raises impact pitch musically, stays clamped, and never raises gain', async (t) => {
  const h = harness(t);
  const audio = h.create();
  audio.setMusic(false);
  await audio.unlock();
  const c = h.contexts[0];
  const hit = (rally) => {
    audio.play('paddle', { rally });
    const voice = [...audio._voices.sfx].find((item) => item.source.type === 'triangle');
    const pitch = voice.source.frequency.events[0][1];
    const peak = voice.nodes[1].gain.events.find(([kind]) => kind === 'linear')[1];
    c.advance(1);
    return { pitch, peak };
  };
  const low = hit(0);
  const high = hit(99);
  assert.ok(high.pitch > low.pitch && high.pitch < 1500);
  assert.equal(high.peak, low.peak);
  assert.deepEqual(hit(Number.MAX_VALUE), high);
  for (const value of [undefined, -100, NaN, Infinity, 'loud', {}, null]) {
    assert.deepEqual(hit(value), low);
  }
  assert.doesNotThrow(() => audio.play('ui', null));
});

test('per-event and shared impact cooldowns prevent collision spam and cue cacophony', async (t) => {
  const h = harness(t);
  const audio = h.create();
  audio.setMusic(false);
  await audio.unlock();
  const c = h.contexts[0];
  for (let i = 0; i < 100; i += 1) audio.play('paddle');
  assert.equal(audio._voices.sfx.size, 3);
  assert.equal(audio.play('rival'), false, 'same-frame collision pairs share a small cooldown');
  assert.equal(audio.play('wall'), false);
  c.advance(0.03);
  assert.equal(audio.play('rival'), true);
  audio.play('win');
  const fanfare = [...audio._voices.sfx];
  c.advance(0.04);
  assert.equal(audio.play('paddle'), false, 'a terminal cue leaves room for its phrase');
  audio.play('lose');
  assertReleased(fanfare);
  assertBounded(audio);
});

test('polyphony remains bounded even when onended delivery is missing and clocks jump', async (t) => {
  const h = harness(t);
  const audio = h.create();
  await audio.unlock();
  const c = h.contexts[0];
  let peakSfx = 0;
  for (let i = 0; i < 1500; i += 1) {
    c.currentTime += 0.025; // Deliberately skip natural onended callbacks.
    for (const name of ['ui', 'serve', 'paddle', 'rival', 'wall']) audio.play(name, { rally: i });
    h.tick();
    assertBounded(audio);
    peakSfx = Math.max(peakSfx, audio._voices.sfx.size);
  }
  assert.ok(peakSfx >= 10, 'exercise the voice ceiling, not only an idle rack');
  assert.equal(h.peakTimers, 1);
  c.currentTime += 4;
  h.tick();
  assert.equal(audio._voices.sfx.size, 0, 'pruning is a fallback for missed ended events');
  const voices = [...audio._voices.music];
  audio.suspend();
  assertSilent(audio, h);
  assertReleased(voices);
});

test('the original 122 BPM theme alternates mint/coral melodies with bass and percussion', async (t) => {
  const h = harness(t);
  const audio = h.create();
  await audio.unlock();
  const c = h.contexts[0];
  const sections = new Set();
  for (let i = 0; i < 850; i += 1) {
    c.advance(0.04);
    h.tick();
    sections.add(audio.diagnostics().section);
    assertBounded(audio);
    assert.equal(h.timers.size, 1);
  }
  assert.deepEqual(sections, new Set(['mint', 'coral']));
  const leads = c.sources.filter((source) => source.type === 'square');
  const bass = c.sources.filter((source) => source.type === 'triangle');
  const kicks = c.sources.filter((source) => source.type === 'sine' && source.frequency.events[0][1] === 138);
  const percussion = c.sources.filter((source) => source.kind === 'bufferSource');
  assert.ok(leads.length > 80 && bass.length > 75 && kicks.length > 32 && percussion.length > 95);
  assert.ok(Math.abs(leads[1].startAt - leads[0].startAt - 60 / 122) < 1e-8);
  const half = 8 * 4 * 60 / 122;
  const second = leads.find((source) => Math.abs(source.startAt - leads[0].startAt - half) < 1e-8);
  const repeat = leads.find((source) => Math.abs(source.startAt - leads[0].startAt - 2 * half) < 1e-8);
  assert.ok(second && repeat, 'both full eight-bar sections and the loop boundary are scheduled');
  assert.notEqual(second.frequency.events[0][1], leads[0].frequency.events[0][1]);
  assert.equal(repeat.frequency.events[0][1], leads[0].frequency.events[0][1]);
  assert.equal(audio.diagnostics().bpm, 122);
  assert.equal(new Set(percussion.map((source) => source.buffer)).size, 1, 'reuse one local noise buffer');
  const samples = audio._noiseBuffer.getChannelData(0);
  assert.ok(samples.some((sample) => sample < -0.5) && samples.some((sample) => sample > 0.5));
  assert.ok(samples.every((sample) => Math.abs(sample) <= 1));
  const filters = c.nodes.filter((node) => node.kind === 'filter');
  assert.ok(filters.some((node) => node.type === 'bandpass'));
  assert.ok(filters.some((node) => node.type === 'highpass'));
});

test('a throttled scheduler skips stale music instead of replaying a backlog', async (t) => {
  const h = harness(t);
  const audio = h.create();
  await audio.unlock();
  const c = h.contexts[0];
  const before = c.sources.length;
  c.advance(300);
  h.tick();
  const fresh = c.sources.slice(before);
  assert.ok(fresh.length > 0 && fresh.length <= 9);
  assert.ok(fresh.every((source) => source.startAt >= c.currentTime));
  assertBounded(audio);
  assert.equal(h.peakTimers, 1);
});

test('all voices have declick envelopes, independent routes, and a conservative master limiter', async (t) => {
  const h = harness(t);
  const audio = h.create();
  await audio.unlock();
  audio.play('win');
  const c = h.contexts[0];
  const limiter = c.nodes.find((node) => node.kind === 'compressor');
  assert.ok(limiter.threshold.value <= -6 && limiter.ratio.value >= 12);
  assert.ok(limiter.attack.value > 0 && limiter.attack.value < 0.01);
  assert.deepEqual(limiter.connections, [c.destination]);
  assert.notEqual(audio._musicBus, audio._sfxBus);
  assert.ok(audio._musicBus.gain.value < 0.65 && audio._sfxBus.gain.value < 0.85);
  for (const voice of [...audio._voices.music, ...audio._voices.sfx]) {
    const gain = voice.nodes.find((node) => node.kind === 'gain');
    assert.deepEqual(gain.gain.events[0], ['set', 0, voice.start]);
    assert.equal(gain.gain.events.at(-1)[1], 0);
    const peak = gain.gain.events.find(([kind]) => kind === 'linear')[1];
    assert.ok(peak > 0 && peak <= 0.25);
    assert.ok(gain.gain.events.at(-1)[2] < voice.end);
    const route = gain.connections[0];
    assert.ok(voice.group === 'music'
      ? route === audio._musicBus || route === audio._leadFilter
      : route === audio._sfxBus || route === audio._sfxFilter);
  }
});

test('active and hidden lifecycle immediately silences both buses and never stacks timers', async (t) => {
  const h = harness(t);
  const audio = h.create();
  await audio.unlock();
  const c = h.contexts[0];
  audio.play('win');
  const voices = [...audio._voices.music, ...audio._voices.sfx];
  audio.setActive(false);
  assertSilent(audio, h);
  assertReleased(voices);
  assert.equal(c.state, 'suspended');
  assert.equal(audio.unlocked, true);
  h.document.hidden = true;
  h.document.dispatch('visibilitychange');
  assert.equal(await audio.unlock(), false);
  h.document.hidden = false;
  h.document.dispatch('visibilitychange');
  await flush();
  assertSilent(audio, h, 'visibility must not override explicit inactivity');
  for (let cycle = 0; cycle < 8; cycle += 1) {
    audio.setActive(true);
    await audio.unlock();
    assert.equal(h.timers.size, 1);
    audio.suspend();
    audio.suspend();
    assertSilent(audio, h);
    audio.setActive(true);
    await audio.unlock();
    assert.equal(h.timers.size, 1);
    h.document.hidden = true;
    h.document.dispatch('visibilitychange');
    assertSilent(audio, h);
    h.document.hidden = false;
    h.document.dispatch('visibilitychange');
    await flush();
    assert.equal(h.timers.size, 1, 'visible may resume already-authorized audio');
    assert.equal(audio._voices.sfx.size, 0, 'never replay old effects after a pause');
  }
  assert.equal(h.peakTimers, 1);
});

for (const mode of ['hidden', 'inactive']) {
  test(`${mode} initial apps cannot create or authorize a context`, async (t) => {
    const h = harness(t, { hidden: mode === 'hidden' });
    const audio = h.create();
    if (mode === 'inactive') audio.setActive(false);
    assert.equal(await audio.unlock(), false);
    assert.equal(h.contexts.length, 0);
    h.document.hidden = false;
    audio.setActive(true);
    assert.equal(h.contexts.length, 0);
    assert.equal(await audio.unlock(), true);
  });
}

test('browser interruption/suspension clears queues and may resume only a previously unlocked rack', async (t) => {
  const h = harness(t);
  const audio = h.create();
  await audio.unlock();
  const c = h.contexts[0];
  for (const state of ['suspended', 'interrupted']) {
    audio.play('serve');
    const voices = [...audio._voices.music, ...audio._voices.sfx];
    c.setState(state);
    assertSilent(audio, h);
    assertReleased(voices);
    assert.equal(audio.play('ui'), false);
    audio.setActive(true);
    await flush();
    assert.equal(h.timers.size, 1);
    assert.equal(audio.unlocked, true);
  }
  c.setState('interrupted');
  c.setState('running');
  assert.equal(h.timers.size, 1, 'browser recovery may continue an already authorized song');
  assert.equal(h.peakTimers, 1);
});

test('externally closed contexts dispose their graph, buffers, callbacks, and listeners', async (t) => {
  const h = harness(t);
  const audio = h.create();
  await audio.unlock();
  audio.play('win');
  const c = h.contexts[0];
  c.setState('closed');
  assert.equal(audio.available, false);
  assert.equal(audio.unlocked, false);
  assert.equal(audio.diagnostics().error, 'context-closed');
  assertSilent(audio, h);
  assert.ok(c.nodes.every((node) => node.disconnected));
  assert.equal(c.closeCalls, 0);
  assert.equal(c.listenerCount('statechange'), 0);
  assert.equal(h.document.listenerCount('visibilitychange'), 0);
  assert.equal(await audio.unlock(), false);
});

for (const option of ['unsupported', 'contextGetterThrows']) {
  test(`${option} Web Audio stays inert with safe methods and preferences`, async (t) => {
    const h = harness(t, { [option]: true });
    const audio = h.create();
    assert.equal(audio.available, false);
    audio.setMusic(false);
    audio.setSfx(false);
    audio.setActive(false);
    audio.suspend();
    audio.setActive(true);
    for (const name of NAMES) audio.play(name);
    assert.equal(await audio.unlock(), false);
    assert.equal(h.contexts.length, 0);
    assertSilent(audio, h);
    audio.dispose();
    audio.dispose();
    audio.setMusic(true);
    audio.setSfx(true);
    assert.equal(await audio.unlock(), false);
  });
}

test('webkitAudioContext and a missing document are supported without autoplay', async (t) => {
  const h = harness(t, { webkit: true, noDocument: true });
  const audio = h.create();
  assert.equal(audio.available, true);
  assert.equal(h.contexts.length, 0);
  assert.equal(await audio.unlock(), true);
  assert.equal(h.contexts.length, 1);
  assert.equal(h.timers.size, 1);
  audio.play('paddle');
  assert.equal(audio._voices.sfx.size, 3);
});

test('an incomplete context without a compressor retains extra headroom', async (t) => {
  const h = harness(t, { behavior: { noLimiter: true } });
  const audio = h.create();
  assert.equal(await audio.unlock(), true);
  const master = audio._musicBus.connections[0];
  assert.ok(master.gain.value <= 0.65);
  assert.deepEqual(master.connections, [h.contexts[0].destination]);
});

for (const failure of ['constructError', 'gainError', 'initError']) {
  test(`${failure} is contained and all partially created resources are released`, async (t) => {
    const h = harness(t, { behavior: { [failure]: true } });
    const audio = h.create();
    assert.equal(await audio.unlock(), false);
    assert.equal(audio.available, false);
    assert.equal(audio.unlocked, false);
    assertSilent(audio, h);
    for (const c of h.contexts) {
      assert.equal(c.closeCalls, 1);
      assert.ok(c.nodes.every((node) => node.disconnected));
    }
    assert.equal(audio.diagnostics().error, 'initialization-failed');
  });
}

test('resume denial or synchronous throw is retryable, not a persisted permission', async (t) => {
  const h = harness(t, { behavior: { resume: () => Promise.reject(new Error('NotAllowedError: secret detail')) } });
  const audio = h.create();
  assert.equal(await audio.unlock(), false);
  assert.equal(audio.available, true);
  assert.equal(audio.unlocked, false);
  assert.equal(audio.diagnostics().error, 'resume-failed');
  assertSilent(audio, h);
  audio.setActive(true);
  assert.equal(h.contexts[0].resumeCalls, 1, 'inactivity controls cannot retry a never-authorized rack');
  h.behavior.resume = () => { throw new Error('browser interrupted'); };
  assert.equal(await audio.unlock(), false);
  assertSilent(audio, h);
  delete h.behavior.resume;
  assert.equal(await audio.unlock(), true);
  assert.equal(h.contexts.length, 1);
  assert.equal(h.timers.size, 1);
  assert.equal(audio.diagnostics().error, null);
  assert.ok(!JSON.stringify(audio.diagnostics()).includes('secret'));
});

test('suspend and close failures cannot leave audible sources or unhandled rejections', async (t) => {
  const h = harness(t, { behavior: {
    suspend: () => Promise.reject(new Error('suspend denied')),
    close: () => Promise.reject(new Error('close denied')),
  } });
  const audio = h.create();
  await audio.unlock();
  audio.play('win');
  audio.setActive(false);
  await flush();
  assertSilent(audio, h);
  assert.equal(h.contexts[0].state, 'running');
  h.behavior.suspend = () => { throw new Error('suspend threw'); };
  audio.suspend();
  await flush();
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

for (const cancellation of ['pause', 'hidden']) {
  test(`${cancellation} during a pending gesture cancels permission and any late audio`, async (t) => {
    const ready = deferred();
    const h = harness(t, { behavior: { resume: (c) => ready.promise.then(() => c.setState('running')) } });
    const audio = h.create();
    const unlocking = audio.unlock();
    if (cancellation === 'pause') audio.setActive(false);
    else { h.document.hidden = true; h.document.dispatch('visibilitychange'); }
    ready.resolve();
    assert.equal(await unlocking, false);
    await flush();
    assert.equal(audio.unlocked, false);
    assert.equal(h.contexts[0].state, 'suspended');
    assertSilent(audio, h);
    delete h.behavior.resume;
    h.document.hidden = false;
    audio.setActive(true);
    assertSilent(audio, h);
    assert.equal(await audio.unlock(), true, 'only a fresh explicit unlock may authorize');
  });
}

test('a stale first unlock cannot authorize after an inactive/active cycle without a new gesture', async (t) => {
  const ready = deferred();
  const h = harness(t, { behavior: { resume: (c) => ready.promise.then(() => c.setState('running')) } });
  const audio = h.create();
  const first = audio.unlock();
  audio.setActive(false);
  audio.setActive(true);
  ready.resolve();
  assert.equal(await first, false);
  await flush();
  assert.equal(audio.unlocked, false);
  assertSilent(audio, h);
});

test('a stale resume resolving after a newer valid gesture cannot undo that legitimate wake', async (t) => {
  const old = deferred();
  const h = harness(t, { behavior: { resume: (c) => old.promise.then(() => c.setState('running')) } });
  const audio = h.create();
  const first = audio.unlock();
  audio.setActive(false);
  await flush();
  audio.setActive(true);
  delete h.behavior.resume;
  assert.equal(await audio.unlock(), true);
  old.resolve();
  assert.equal(await first, false);
  await flush();
  assert.equal(audio.unlocked, true);
  assert.equal(h.contexts[0].state, 'running');
  assert.equal(h.timers.size, 1);
});

test('resume is called synchronously even while a queued suspend still reports running', async (t) => {
  const h = harness(t);
  const audio = h.create();
  await audio.unlock();
  const c = h.contexts[0];
  const sleeping = deferred();
  const waking = deferred();
  h.behavior.suspend = (context) => sleeping.promise.then(() => context.setState('suspended'));
  h.behavior.resume = (context) => waking.promise.then(() => context.setState('running'));
  audio.suspend();
  assert.equal(c.state, 'running');
  assertSilent(audio, h);
  const before = c.resumeCalls;
  audio.setActive(true);
  const resume = h.gesture(() => audio.unlock());
  assert.ok(c.resumeCalls > before);
  assert.equal(c.resumeGestures.at(-1), true);
  sleeping.resolve();
  await flush();
  assertSilent(audio, h);
  waking.resolve();
  assert.equal(await resume, true);
  await flush();
  assert.equal(h.timers.size, 1);
  assert.equal(c.state, 'running');
});

test('a suspend resolving after a successful newer resume is repaired without a stuck timer', async (t) => {
  const h = harness(t);
  const audio = h.create();
  await audio.unlock();
  const c = h.contexts[0];
  const sleeping = deferred();
  h.behavior.suspend = (context) => sleeping.promise.then(() => context.setState('suspended'));
  audio.suspend();
  audio.setActive(true);
  await audio.unlock();
  assertSilent(audio, h, 'output remains gated while suspension is pending');
  const before = c.resumeCalls;
  sleeping.resolve();
  await flush();
  assert.equal(c.state, 'running');
  assert.equal(c.resumeCalls, before + 1, 'one legitimate repair resume, not a retry loop');
  assert.equal(h.timers.size, 1);
  assert.equal(h.peakTimers, 1);
});

test('same-microtask suspend/resume settlement cannot strand an unlocked active rack', async (t) => {
  const h = harness(t);
  const audio = h.create();
  await audio.unlock();
  const c = h.contexts[0];
  const sleeping = deferred();
  h.behavior.suspend = () => sleeping.promise;
  audio.suspend();
  audio.setActive(true); // Its resolved resume promise still has a continuation pending.
  c.setState('suspended');
  sleeping.resolve();
  await flush();
  assert.equal(c.state, 'running');
  assert.equal(h.timers.size, 1);
  assert.equal(audio.diagnostics().pendingSuspend, false);
  assert.equal(audio.diagnostics().pendingResume, false);
  assert.equal(h.peakTimers, 1);
});

test('repeated lifecycle wakes coalesce, but a fresh gesture can rescue a pending resume', async (t) => {
  const h = harness(t);
  const audio = h.create();
  await audio.unlock();
  audio.suspend();
  await flush();
  const old = deferred();
  const c = h.contexts[0];
  h.behavior.resume = (context) => old.promise.then(() => context.setState('running'));
  const before = c.resumeCalls;
  for (let i = 0; i < 50; i += 1) audio.setActive(true);
  assert.equal(c.resumeCalls, before + 1);
  delete h.behavior.resume;
  assert.equal(await h.gesture(() => audio.unlock()), true);
  old.resolve();
  await flush();
  assert.equal(h.timers.size, 1);
  assert.equal(h.peakTimers, 1);
});

test('dispose invalidates a pending unlock and releases all graph references and listeners', async (t) => {
  const ready = deferred();
  const h = harness(t, { behavior: { resume: () => ready.promise } });
  const audio = h.create();
  const unlocking = audio.unlock();
  const c = h.contexts[0];
  assert.equal(c.listenerCount('statechange'), 1);
  assert.equal(h.document.listenerCount('visibilitychange'), 1);
  audio.dispose();
  ready.resolve();
  assert.equal(await unlocking, false);
  assert.equal(await audio.unlock(), false);
  assert.equal(audio.available, false);
  assert.equal(audio.unlocked, false);
  assert.equal(c.closeCalls, 1);
  assert.equal(c.listenerCount('statechange'), 0);
  assert.equal(h.document.listenerCount('visibilitychange'), 0);
  assert.ok(c.nodes.every((node) => node.disconnected));
  assert.equal(audio._noiseBuffer, null);
  assert.equal(audio._context, null);
  assertSilent(audio, h);
  audio.setActive(true);
  audio.play('win');
  audio.dispose();
  assert.equal(c.closeCalls, 1);
});

test('dispose during a pending suspend cannot be reversed by late completion or visibility', async (t) => {
  const h = harness(t);
  const audio = h.create();
  await audio.unlock();
  const sleeping = deferred();
  h.behavior.suspend = () => sleeping.promise;
  audio.play('win');
  const voices = [...audio._voices.music, ...audio._voices.sfx];
  audio.suspend();
  audio.dispose();
  sleeping.resolve();
  h.document.dispatch('visibilitychange');
  await flush();
  assertSilent(audio, h);
  assertReleased(voices);
  assert.equal(h.contexts[0].closeCalls, 1);
  assert.equal(h.contexts[0].state, 'closed');
  assert.equal(audio.diagnostics().graphNodes, 0);
});

test('dispose during playback stops queued SFX, music, all nodes, and the sole interval exactly once', async (t) => {
  const h = harness(t);
  const audio = h.create();
  await audio.unlock();
  audio.play('win');
  const c = h.contexts[0];
  const voices = [...audio._voices.music, ...audio._voices.sfx];
  audio.dispose();
  assertReleased(voices);
  assertSilent(audio, h);
  assert.ok(c.nodes.every((node) => node.disconnected));
  audio.dispose();
  audio.setMusic(false);
  audio.setSfx(false);
  assert.equal(c.closeCalls, 1);
  assert.equal(audio._context, null);
});

test('synthesis failures release partially created sources without breaking later sounds', async (t) => {
  const h = harness(t);
  const audio = h.create();
  audio.setMusic(false);
  await audio.unlock();
  const c = h.contexts[0];
  c.failNextGain = true;
  assert.doesNotThrow(() => audio.play('ui'));
  assert.equal(audio._voices.sfx.size, 0);
  assert.equal(c.sources.at(-1).disconnected, true);
  c.failNextFilter = true;
  assert.doesNotThrow(() => audio.play('paddle'));
  assert.equal(c.sources.at(-1).disconnected, true, 'a failed noise filter also releases its source');
  c.advance(1);
  audio.play('serve');
  assert.equal(audio._voices.sfx.size, 4);
});

test('scheduler creation failure mutes music cleanly while leaving independent SFX usable', async (t) => {
  const h = harness(t, { behavior: { timerError: true } });
  const audio = h.create();
  assert.equal(await audio.unlock(), true);
  assert.equal(h.timers.size, 0);
  assert.equal(audio._voices.music.size, 0);
  assert.equal(audio._musicBus.gain.value, 0);
  assert.equal(audio.play('ui'), true);
  delete h.behavior.timerError;
  audio.setMusic(true);
  assert.equal(h.timers.size, 1);
});

test('diagnostics are harmless detached state/count snapshots with no persisted or live objects', async (t) => {
  const h = harness(t);
  const audio = h.create();
  const initial = audio.diagnostics();
  assert.deepEqual(initial.voices, { music: 0, sfx: 0 });
  assert.equal(initial.timers, 0);
  assert.equal(initial.graphNodes, 0);
  assert.equal(h.contexts.length, 0);
  await audio.unlock();
  audio.play('win');
  const report = audio.diagnostics();
  assert.deepEqual(JSON.parse(JSON.stringify(report)), report);
  assert.ok(report.queuedVoices.sfx > 0);
  assert.equal(report.timers, 1);
  report.voices.sfx = 999;
  report.voiceLimits.sfx = 999;
  assert.notEqual(audio.diagnostics().voices.sfx, 999);
  assert.equal(audio.diagnostics().voiceLimits.sfx, 16);
  assert.equal(h.storage.writes.length, 0);
  audio.dispose();
  const end = audio.diagnostics();
  assert.equal(end.disposed, true);
  assert.equal(end.contextState, 'none');
  assert.equal(end.graphNodes, 0);
  assert.equal(end.pendingResume, false);
  assert.equal(end.pendingSuspend, false);
  assert.deepEqual(end.voices, { music: 0, sfx: 0 });
  assert.equal(end.timers, 0);
});
