// Sample-free pocket synth. Only unlock(), called from a user gesture, creates audio.
const STORAGE_KEY = 'minesweeper-audio-v1';
const BPM = 104;
const STEP = 60 / BPM / 2; // Eighth notes, with a very small paired swing.
const LOOKAHEAD = 0.18;
const TICK_MS = 60;
const FLOOR = 0.0001;
const MUSIC_LEVEL = 0.42;
const SFX_LEVEL = 0.62;
const LIMITS = { music: 12, sfx: 16 };
const hz = (note) => 440 * 2 ** ((note - 69) / 12);

// Original eight-bar "Lantern Walk" theme, composed for this game, not a cover.
// G6 / Em7 / Cmaj7 / Dadd9 / Bm7 / Em7 / Am7 / D7; zeroes are breathing spaces.
const THEME = [
  { bass: 43, lead: [74, 0, 71, 69, 0, 67, 69, 0] },
  { bass: 40, lead: [71, 74, 76, 0, 74, 71, 0, 69] },
  { bass: 36, lead: [72, 0, 76, 74, 0, 71, 69, 0] },
  { bass: 38, lead: [69, 74, 0, 76, 78, 0, 74, 0] },
  { bass: 47, lead: [74, 71, 0, 78, 76, 0, 74, 71] },
  { bass: 40, lead: [76, 0, 79, 78, 0, 76, 74, 0] },
  { bass: 45, lead: [72, 76, 0, 74, 71, 0, 69, 0] },
  { bass: 38, lead: [74, 0, 71, 69, 66, 0, 67, 0] },
];
const COOLDOWN = {
  ui: 0.045, reveal: 0.045, flood: 0.14, flag: 0.07, unflag: 0.07,
  start: 0.2, win: 0.7, lose: 0.7,
};

function disconnect(node) {
  try { node?.disconnect(); } catch { /* Already detached or closed. */ }
}

export class RetroAudio {
  constructor() {
    this._Context = globalThis.AudioContext || globalThis.webkitAudioContext;
    this._available = typeof this._Context === 'function';
    this._musicEnabled = false;
    this._sfxEnabled = true;
    this._unlocked = false;
    this._active = true;
    this._suspended = false;
    this._disposed = false;
    this._generation = 0;
    this._context = null;
    this._nodes = [];
    this._voices = { music: new Set(), sfx: new Set() };
    this._lastSfx = Object.create(null);
    this._timer = null;
    this._step = 0;
    this._nextStep = 0;
    this._document = globalThis.document;
    this._tick = () => this._schedule();
    this._onState = () => this._contextChanged();
    this._onVisibility = () => {
      if (this._hidden()) this.suspend();
      else if (this._active && this._unlocked) void this._wake(false);
    };
    this._loadPreferences();
  }

  get available() { return this._available && !this._disposed; }
  get musicEnabled() { return this._musicEnabled; }
  get sfxEnabled() { return this._sfxEnabled; }
  get unlocked() { return this._unlocked; }

  // Invoke directly in a pointer/key handler, before any unrelated await.
  // Permission denial is retryable on the next gesture; nothing autoplays first.
  async unlock() {
    if (!this.available || !this._active || this._hidden()) return false;
    if (!this._context) {
      try { this._init(); }
      catch { this.dispose(); return false; }
    }
    return this._wake(true);
  }

  setMusic(enabled) {
    if (this._disposed) return;
    this._musicEnabled = Boolean(enabled);
    this._savePreferences();
    if (this._musicEnabled && this._ready()) this._startMusic();
    else this._stopMusic();
  }

  setSfx(enabled) {
    if (this._disposed) return;
    this._sfxEnabled = Boolean(enabled);
    this._savePreferences();
    this._level(this._sfxBus, this._sfxEnabled && this._ready() ? SFX_LEVEL : 0);
    if (!this._sfxEnabled) {
      this._stopVoices('sfx');
      this._lastSfx = Object.create(null);
    }
  }

  // Visibility/host lifecycle control, not a preference. Never unlocks audio.
  setActive(active) {
    if (this._disposed) return;
    this._active = Boolean(active);
    if (!this._active || this._hidden()) this.suspend();
    else if (this._unlocked) void this._wake(false);
  }

  play(name) {
    if (!this._sfxEnabled || !this._ready() || typeof name !== 'string'
      || !Object.prototype.hasOwnProperty.call(COOLDOWN, name)) return;
    const t = this._context.currentTime + 0.006;
    if (t - (this._lastSfx[name] ?? -Infinity) < COOLDOWN[name]) return;
    this._lastSfx[name] = t;
    // End-of-board cues replace queued clicks rather than making a loud pileup.
    if (name === 'win' || name === 'lose') this._stopVoices('sfx');
    switch (name) {
      case 'ui':
        this._tone('sfx', t, hz(81), 0.045, 0.07, 'triangle', hz(83));
        break;
      case 'reveal':
        this._tone('sfx', t, hz(71), 0.075, 0.07, 'square', hz(74));
        break;
      case 'flood':
        [67, 71, 74, 81].forEach((note, i) => {
          this._tone('sfx', t + i * 0.04, hz(note), 0.14, 0.065, 'triangle');
        });
        break;
      case 'flag':
        this._tone('sfx', t, hz(67), 0.085, 0.085, 'square');
        this._tone('sfx', t + 0.055, hz(74), 0.13, 0.08, 'triangle');
        break;
      case 'unflag':
        this._tone('sfx', t, hz(74), 0.065, 0.075, 'triangle');
        this._tone('sfx', t + 0.045, hz(67), 0.10, 0.075, 'triangle');
        break;
      case 'start':
        [67, 71, 74, 79].forEach((note, i) => {
          this._tone('sfx', t + i * 0.075, hz(note), i === 3 ? 0.28 : 0.14,
            0.085, 'square');
        });
        this._tone('sfx', t, hz(55), 0.24, 0.11, 'triangle');
        break;
      case 'win': {
        const notes = [74, 79, 78, 83, 81, 79, 86];
        const times = [0, 0.085, 0.17, 0.28, 0.36, 0.45, 0.62];
        notes.forEach((note, i) => {
          this._tone('sfx', t + times[i], hz(note), i === 6 ? 0.38 : 0.15,
            0.085, 'square');
        });
        [55, 59, 62].forEach((note) => {
          this._tone('sfx', t + 0.62, hz(note), 0.38, 0.05, 'triangle');
        });
        break;
      }
      case 'lose':
        // A soft descending arcade sigh, not a startling explosion.
        this._tone('sfx', t, hz(55), 0.34, 0.13, 'triangle', hz(43));
        this._tone('sfx', t, hz(74), 0.25, 0.065, 'square', hz(62));
        this._noise('sfx', t, 0.10, 0.025, 'bandpass', 950);
        break;
    }
  }

  suspend() {
    if (this._disposed) return;
    this._suspended = true;
    this._generation += 1; // Invalidate a resume awaiting the browser's permission.
    this._silence();
    this._sleepContext();
  }

  dispose() {
    if (this._disposed) return;
    this._disposed = true;
    this._available = false;
    this._unlocked = false;
    this._suspended = true;
    this._generation += 1;
    this._silence();
    this._document?.removeEventListener?.('visibilitychange', this._onVisibility);
    const context = this._context;
    context?.removeEventListener?.('statechange', this._onState);
    for (const node of this._nodes) disconnect(node);
    this._nodes.length = 0;
    this._noiseBuffer = null;
    this._musicBus = this._sfxBus = this._leadFilter = null;
    this._context = null;
    if (context && context.state !== 'closed') {
      try { Promise.resolve(context.close()).catch(() => {}); } catch { /* Best effort. */ }
    }
  }

  _loadPreferences() {
    try {
      const saved = JSON.parse(globalThis.localStorage?.getItem(STORAGE_KEY) ?? 'null');
      if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return;
      if (typeof saved.musicEnabled === 'boolean') this._musicEnabled = saved.musicEnabled;
      if (typeof saved.sfxEnabled === 'boolean') this._sfxEnabled = saved.sfxEnabled;
    } catch { /* Sandboxed storage and malformed JSON keep the safe defaults. */ }
  }

  _savePreferences() {
    try {
      globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify({
        musicEnabled: this._musicEnabled, sfxEnabled: this._sfxEnabled,
      }));
    } catch { /* In-memory preferences still work in private/sandboxed sessions. */ }
  }

  _hidden() { return Boolean(this._document?.hidden); }

  _ready() {
    return this.available && this._unlocked && this._active && !this._suspended
      && !this._hidden() && this._context?.state === 'running';
  }

  async _wake(fromGesture) {
    if (!this.available || !this._context || !this._active || this._hidden()
      || (!fromGesture && !this._unlocked)) return false;
    const context = this._context;
    const generation = this._generation;
    this._suspended = false;
    try {
      // Call synchronously even when running: this queues behind a pending suspend
      // and keeps gesture permission intact. Concurrent wakes share one scheduler.
      await context.resume();
      if (this._disposed || this._context !== context || generation !== this._generation
        || this._suspended || !this._active || this._hidden() || context.state !== 'running') {
        return false;
      }
      if (fromGesture) this._unlocked = true;
      this._sync();
      return true;
    } catch { return false; }
  }

  _sleepContext() {
    const context = this._context;
    if (!context || context.state !== 'running') return;
    try { Promise.resolve(context.suspend()).catch(() => {}); } catch { /* Already silent. */ }
  }

  _init() {
    const c = new this._Context({ latencyHint: 'interactive' });
    this._context = c;
    const keep = (node) => { this._nodes.push(node); return node; };
    this._musicBus = keep(c.createGain());
    this._sfxBus = keep(c.createGain());
    const master = keep(c.createGain());
    this._leadFilter = keep(c.createBiquadFilter());
    this._musicBus.gain.value = this._sfxBus.gain.value = 0;
    master.gain.value = 0.8; // Conservative levels leave headroom without a limiter.
    this._leadFilter.type = 'lowpass';
    this._leadFilter.frequency.value = 3000;
    this._leadFilter.Q.value = 0.45;
    this._leadFilter.connect(this._musicBus);
    this._musicBus.connect(master);
    this._sfxBus.connect(master);
    master.connect(c.destination);

    // One short deterministic noise buffer for brushes/hats; no fetched samples.
    this._noiseBuffer = c.createBuffer(1, Math.ceil(c.sampleRate * 0.3), c.sampleRate);
    const data = this._noiseBuffer.getChannelData(0);
    let seed = 0x4c414e54;
    for (let i = 0; i < data.length; i += 1) {
      seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5;
      data[i] = (seed >>> 0) / 2147483648 - 1;
    }
    c.addEventListener?.('statechange', this._onState);
    this._document?.addEventListener?.('visibilitychange', this._onVisibility);
  }

  _contextChanged() {
    const context = this._context;
    if (!context || this._disposed) return;
    if (context.state === 'closed') { this.dispose(); return; }
    if (this._ready()) this._sync();
    else {
      this._silence();
      // A pending gesture resume can complete after hiding: keep it asleep.
      if (this._suspended || !this._active || this._hidden()) this._sleepContext();
    }
  }

  _sync() {
    if (!this._ready()) { this._silence(); return; }
    this._level(this._sfxBus, this._sfxEnabled ? SFX_LEVEL : 0);
    if (this._musicEnabled) this._startMusic();
    else this._stopMusic();
  }

  _level(bus, value) {
    if (!bus || !this._context) return;
    try {
      const now = this._context.currentTime;
      bus.gain.cancelScheduledValues(now);
      bus.gain.setValueAtTime(value, now); // Immediate gating, including future notes.
    } catch {
      try { bus.gain.value = value; } catch { /* Context was closed externally. */ }
    }
  }

  _startMusic() {
    if (!this._ready() || !this._musicEnabled || this._timer !== null) return;
    this._level(this._musicBus, MUSIC_LEVEL);
    this._nextStep = this._context.currentTime + 0.02;
    this._step = (Math.ceil(this._step / 8) * 8) % (THEME.length * 8);
    try {
      this._timer = setInterval(this._tick, TICK_MS);
      this._schedule();
    } catch { this._stopMusic(); }
  }

  _stopMusic() {
    if (this._timer !== null) clearInterval(this._timer);
    this._timer = null;
    this._level(this._musicBus, 0);
    this._stopVoices('music');
  }

  _silence() {
    this._stopMusic();
    this._level(this._sfxBus, 0);
    this._stopVoices('sfx');
    this._lastSfx = Object.create(null);
  }

  _schedule() {
    if (!this._ready() || !this._musicEnabled) { this._stopMusic(); return; }
    const now = this._context.currentTime;
    this._prune(now);
    if (this._nextStep < now) {
      // Never burst a backlog after a throttled tab/timer. Rejoin at a bar.
      this._nextStep = now + 0.02;
      this._step = (Math.ceil(this._step / 8) * 8) % (THEME.length * 8);
    }
    let count = 0;
    while (this._nextStep < now + LOOKAHEAD && count++ < 3) {
      this._musicStep(this._step, this._nextStep);
      this._nextStep += STEP + (this._step % 2 === 0 ? 0.008 : -0.008);
      this._step = (this._step + 1) % (THEME.length * 8);
    }
  }

  _musicStep(step, t) {
    const bar = THEME[Math.floor(step / 8)];
    const eighth = step % 8;
    const note = bar.lead[eighth];
    if (note) {
      const duration = STEP * (bar.lead[(eighth + 1) % 8] ? 0.8 : 1.7);
      this._tone('music', t, hz(note), duration, 0.075, 'square');
    }
    if (eighth === 0 || eighth === 4) {
      this._tone('music', t, hz(bar.bass), STEP * 1.65, 0.115, 'triangle');
      this._tone('music', t, 110, 0.11, 0.09, 'sine', 48);
    } else if (eighth === 3 || eighth === 7) {
      this._tone('music', t, hz(bar.bass + 7), STEP * 0.75, 0.08, 'triangle');
    }
    if (eighth === 2 || eighth === 6) {
      this._noise('music', t, 0.075, 0.035, 'bandpass', 1650);
    }
    if (eighth % 2 === 1) {
      this._noise('music', t, 0.035, eighth === 7 ? 0.013 : 0.009, 'highpass', 5200);
    }
  }

  _tone(group, t, frequency, duration, peak, shape, slideTo = 0) {
    if (!this._room(group)) return;
    const voice = this._track(group, t + duration + 0.012);
    try {
      const c = this._context;
      const source = voice.source = c.createOscillator();
      voice.nodes.push(source);
      const gain = c.createGain();
      voice.nodes.push(gain);
      source.type = shape;
      source.frequency.setValueAtTime(frequency, t);
      if (slideTo) source.frequency.exponentialRampToValueAtTime(slideTo, t + duration * 0.9);
      this._envelope(gain.gain, t, duration, peak);
      source.connect(gain);
      gain.connect(group === 'music' && shape === 'square'
        ? this._leadFilter : group === 'music' ? this._musicBus : this._sfxBus);
      source.onended = () => this._release(voice);
      source.start(t);
      source.stop(voice.end);
    } catch { this._release(voice); }
  }

  _noise(group, t, duration, peak, type, frequency) {
    if (!this._room(group)) return;
    const voice = this._track(group, t + duration + 0.012);
    try {
      const c = this._context;
      const source = voice.source = c.createBufferSource();
      voice.nodes.push(source);
      const filter = c.createBiquadFilter();
      voice.nodes.push(filter);
      const gain = c.createGain();
      voice.nodes.push(gain);
      source.buffer = this._noiseBuffer;
      filter.type = type;
      filter.frequency.value = Math.min(frequency, c.sampleRate * 0.45);
      filter.Q.value = 0.7;
      this._envelope(gain.gain, t, duration, peak);
      source.connect(filter).connect(gain);
      gain.connect(group === 'music' ? this._musicBus : this._sfxBus);
      source.onended = () => this._release(voice);
      source.start(t);
      source.stop(voice.end);
    } catch { this._release(voice); }
  }

  _envelope(param, t, duration, peak) {
    param.setValueAtTime(0, t);
    param.linearRampToValueAtTime(peak, t + Math.min(0.006, duration * 0.15));
    param.exponentialRampToValueAtTime(peak * 0.5, t + duration * 0.35);
    param.exponentialRampToValueAtTime(FLOOR, t + duration);
    param.linearRampToValueAtTime(0, t + duration + 0.008);
  }

  _room(group) {
    if (!this._ready()) return false;
    this._prune(this._context.currentTime);
    return this._voices[group].size < LIMITS[group];
  }

  _track(group, end) {
    const voice = { group, end, source: null, nodes: [] };
    this._voices[group].add(voice);
    return voice;
  }

  _release(voice) {
    if (!this._voices[voice.group].delete(voice)) return;
    if (voice.source) {
      voice.source.onended = null;
      try { voice.source.stop(); } catch { /* Not started, already ended, or closed. */ }
    }
    for (const node of voice.nodes) disconnect(node);
  }

  _stopVoices(group) {
    for (const voice of this._voices[group]) this._release(voice);
  }

  _prune(now) {
    for (const group of ['music', 'sfx']) {
      for (const voice of this._voices[group]) {
        if (voice.end <= now) this._release(voice);
      }
    }
  }
}
