// Sample-free, original arcade synth. Only unlock(), called in a gesture, creates audio.
const STORAGE_KEY = 'rally-pong-audio-v1';
const BPM = 122;
const STEP = 60 / BPM / 4;
const LOOKAHEAD = 0.15;
const TICK_MS = 40;
const FLOOR = 0.0001;
const MUSIC_LEVEL = 0.56;
const SFX_LEVEL = 0.78;
const LIMITS = Object.freeze({ music: 18, sfx: 16 });
const hz = (note) => 440 * 2 ** ((note - 69) / 12);

// "Mint / Coral", composed for Rally — After Hours. A sixteen-bar D-dorian groove:
// eight bars of a low, syncopated mint hook, then a higher coral call-and-response.
// Dm9 / G6 / Cmaj9 / Am7 / Dm9 / Fmaj7 / G6 / A7sus; the second half opens on F.
// These are eighth-note melodies over a lightly swung sixteenth-note rhythm rack.
// Zeroes leave space for the ball; this is a tune, not an unbroken random arpeggio.
const THEME = [
  { bass: 38, lead: [74, 0, 77, 81, 0, 79, 76, 0] },
  { bass: 43, lead: [74, 71, 0, 69, 0, 74, 76, 0] },
  { bass: 36, lead: [76, 0, 79, 83, 81, 0, 79, 0] },
  { bass: 45, lead: [76, 72, 0, 69, 72, 0, 74, 0] },
  { bass: 38, lead: [74, 0, 77, 81, 84, 81, 0, 79] },
  { bass: 41, lead: [77, 0, 76, 72, 0, 69, 72, 0] },
  { bass: 43, lead: [74, 76, 0, 79, 0, 81, 79, 76] },
  { bass: 45, lead: [76, 0, 74, 72, 69, 0, 73, 0] },
  { bass: 41, lead: [81, 0, 84, 88, 0, 86, 84, 0] },
  { bass: 43, lead: [83, 79, 0, 81, 0, 86, 83, 0] },
  { bass: 40, lead: [79, 0, 83, 86, 88, 0, 83, 0] },
  { bass: 45, lead: [84, 81, 0, 79, 76, 0, 79, 0] },
  { bass: 38, lead: [81, 0, 77, 74, 0, 76, 81, 0] },
  { bass: 43, lead: [83, 0, 81, 79, 74, 0, 76, 79] },
  { bass: 36, lead: [84, 0, 83, 79, 81, 0, 76, 0] },
  { bass: 45, lead: [81, 79, 0, 76, 73, 0, 74, 0] },
];
const PING_NOTES = [74, 76, 77, 79, 81, 84, 86];
const COOLDOWN = Object.freeze({
  ui: 0.045, serve: 0.2, paddle: 0.024, rival: 0.024, wall: 0.035,
  goal: 0.3, miss: 0.3, win: 0.8, lose: 0.8,
});

function disconnect(node) {
  try { node?.disconnect(); } catch { /* Already detached or closed. */ }
}

export class RallyAudio {
  constructor() {
    // Construction, preference changes, play(), and visibility cannot grant permission.
    try { this._Context = globalThis.AudioContext || globalThis.webkitAudioContext; }
    catch { this._Context = null; }
    this._available = typeof this._Context === 'function';
    this._musicEnabled = true;
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
    this._lastImpact = -Infinity;
    this._impactQuietUntil = 0;
    this._musicBus = this._sfxBus = null;
    this._leadFilter = this._sfxFilter = null;
    this._noiseBuffer = null;
    this._timer = null;
    this._step = 0;
    this._nextStep = 0;
    this._wakeRequest = null;
    this._sleepRequest = null;
    this._error = null;
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
  get unlocked() { return this._unlocked; }
  get musicEnabled() { return this._musicEnabled; }
  get sfxEnabled() { return this._sfxEnabled; }

  // Call directly in a pointer/key handler BEFORE any await. _init() and resume()
  // both execute synchronously in that gesture; denial returns false and is retryable.
  async unlock() {
    if (!this.available || !this._active || this._hidden()) return false;
    if (!this._context) {
      try { this._init(); }
      catch { this._error = 'initialization-failed'; this.dispose(); return false; }
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
      this._resetEffects();
    }
  }

  // Activity is ephemeral, not a preference. A previously unlocked rack may wake;
  // a locked rack still needs unlock(). Inactive/hidden always wins over a late resume.
  setActive(active) {
    if (this._disposed) return;
    this._active = Boolean(active);
    if (!this._active || this._hidden()) this.suspend();
    else if (this._unlocked) void this._wake(false);
  }

  play(name, options = {}) {
    if (!this._sfxEnabled || !this._ready() || typeof name !== 'string'
      || !Object.prototype.hasOwnProperty.call(COOLDOWN, name)) return false;
    const t = this._context.currentTime + 0.004;
    if (t - (this._lastSfx[name] ?? -Infinity) < COOLDOWN[name]) return false;
    const impact = name === 'paddle' || name === 'rival' || name === 'wall';
    if (impact && (t < this._impactQuietUntil || t - this._lastImpact < 0.014)) return false;
    this._lastSfx[name] = t;
    if (impact) this._lastImpact = t;
    const rally = Number.isFinite(options?.rally) ? Math.max(0, Math.floor(options.rally)) : 0;
    const ping = PING_NOTES[Math.min(PING_NOTES.length - 1, Math.floor(rally / 4))];
    // Native audio scheduling, not timeouts. A score/final cue replaces queued impacts.
    if (name === 'goal' || name === 'miss' || name === 'win' || name === 'lose') {
      this._stopVoices('sfx');
      this._impactQuietUntil = t + (name === 'win' || name === 'lose' ? 0.75 : 0.24);
    }
    switch (name) {
      case 'ui':
        this._tone('sfx', t, hz(81), 0.045, 0.065, 'sine', hz(86));
        break;
      case 'serve':
        [62, 69, 74].forEach((note, i) => {
          this._tone('sfx', t + i * 0.055, hz(note), i === 2 ? 0.19 : 0.09, 0.09, 'triangle');
        });
        this._tone('sfx', t, 110, 0.16, 0.075, 'sine', 220);
        break;
      case 'paddle':
        // Rounded glass/rubber ping: its pitch rises with the rally, not its loudness.
        this._tone('sfx', t, hz(ping), 0.085, 0.14, 'triangle', hz(ping - 1));
        this._tone('sfx', t, hz(ping + 12), 0.035, 0.038, 'sine');
        this._noise('sfx', t, 0.018, 0.015, 'bandpass', 3100);
        break;
      case 'rival':
        this._tone('sfx', t, hz(ping - 5), 0.08, 0.13, 'triangle', hz(ping - 6));
        this._tone('sfx', t, hz(ping + 7), 0.03, 0.03, 'sine');
        this._noise('sfx', t, 0.018, 0.012, 'bandpass', 2300);
        break;
      case 'wall':
        this._tone('sfx', t, hz(81), 0.035, 0.052, 'sine', hz(79));
        break;
      case 'goal':
        [74, 77, 81, 88].forEach((note, i) => {
          this._tone('sfx', t + i * 0.06, hz(note), i === 3 ? 0.24 : 0.11, 0.105, 'triangle');
        });
        this._tone('sfx', t, hz(50), 0.2, 0.13, 'sine');
        break;
      case 'miss':
        this._tone('sfx', t, hz(62), 0.24, 0.12, 'sine', hz(57));
        this._tone('sfx', t + 0.045, hz(65), 0.18, 0.07, 'triangle', hz(62));
        this._noise('sfx', t, 0.035, 0.018, 'bandpass', 1100);
        break;
      case 'win': {
        const notes = [74, 77, 81, 84, 88, 86];
        const times = [0, 0.07, 0.14, 0.245, 0.315, 0.46];
        notes.forEach((note, i) => {
          this._tone('sfx', t + times[i], hz(note), i === 5 ? 0.4 : 0.13, 0.095, 'square');
        });
        [62, 65, 69].forEach((note) => {
          this._tone('sfx', t + 0.46, hz(note), 0.4, 0.042, 'triangle');
        });
        this._tone('sfx', t, hz(50), 0.3, 0.12, 'sine');
        break;
      }
      case 'lose':
        // A short, encouraging descending tag, never an explosive punishment.
        [77, 76, 74, 69].forEach((note, i) => {
          this._tone('sfx', t + i * 0.09, hz(note), i === 3 ? 0.28 : 0.13, 0.08, 'triangle');
        });
        this._tone('sfx', t, hz(50), 0.38, 0.12, 'sine', hz(38));
        break;
    }
    return true;
  }

  suspend() {
    if (this._disposed) return;
    this._suspended = true;
    this._generation += 1;
    this._wakeRequest = null; // Old resume promises may finish, but cannot unlock us.
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
    this._wakeRequest = this._sleepRequest = null;
    this._silence();
    this._document?.removeEventListener?.('visibilitychange', this._onVisibility);
    const context = this._context;
    context?.removeEventListener?.('statechange', this._onState);
    for (const node of this._nodes) disconnect(node);
    this._nodes.length = 0;
    this._noiseBuffer = null;
    this._musicBus = this._sfxBus = this._leadFilter = this._sfxFilter = null;
    this._context = null;
    if (context && context.state !== 'closed') {
      try { Promise.resolve(context.close()).catch(() => {}); } catch { /* Output is disconnected. */ }
    }
  }

  diagnostics() {
    const now = this._context?.currentTime ?? 0;
    const queued = (group) => [...this._voices[group]].filter((voice) => voice.start > now).length;
    // Only counts, booleans, and fixed labels. No nodes, buffers, identity, score, or storage.
    return {
      available: this.available, unlocked: this.unlocked, disposed: this._disposed,
      musicEnabled: this.musicEnabled, sfxEnabled: this.sfxEnabled,
      active: this._active, suspended: this._suspended, hidden: this._hidden(),
      contextState: this._context?.state ?? 'none', musicRunning: this._timer !== null,
      timers: this._timer === null ? 0 : 1,
      voices: { music: this._voices.music.size, sfx: this._voices.sfx.size },
      queuedVoices: { music: queued('music'), sfx: queued('sfx') },
      voiceLimits: { ...LIMITS }, graphNodes: this._nodes.length,
      pendingResume: Boolean(this._wakeRequest), pendingSuspend: Boolean(this._sleepRequest),
      bpm: BPM, section: this._step < 8 * 16 ? 'mint' : 'coral', error: this._error,
    };
  }

  _loadPreferences() {
    try {
      const saved = JSON.parse(globalThis.localStorage?.getItem(STORAGE_KEY) ?? 'null');
      if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return;
      if (typeof saved.musicEnabled === 'boolean') this._musicEnabled = saved.musicEnabled;
      if (typeof saved.sfxEnabled === 'boolean') this._sfxEnabled = saved.sfxEnabled;
    } catch { /* Denied storage / malformed JSON keeps the in-memory defaults. */ }
  }

  _savePreferences() {
    try {
      globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify({
        musicEnabled: this._musicEnabled, sfxEnabled: this._sfxEnabled,
      }));
    } catch { /* Sound controls still work with blocked or full storage. */ }
  }

  _hidden() { return Boolean(this._document?.hidden); }

  _ready() {
    return this.available && this._unlocked && this._active && !this._suspended
      && !this._sleepRequest && !this._hidden() && this._context?.state === 'running';
  }

  _wake(fromGesture) {
    if (!this.available || !this._context || !this._active || this._hidden()
      || (!fromGesture && !this._unlocked)) return Promise.resolve(false);
    if (this._ready()) return Promise.resolve(true);
    // Coalesce lifecycle wakes, but a new gesture must be allowed to retry a browser
    // resume that is still pending. Never defer resume() into a Promise callback.
    if (!fromGesture && this._wakeRequest?.generation === this._generation) {
      return this._wakeRequest.promise;
    }
    const context = this._context;
    const request = { context, generation: this._generation, promise: null };
    this._wakeRequest = request;
    this._suspended = false;
    let resumed;
    try { resumed = context.resume(); }
    catch { resumed = Promise.reject(new Error('resume-failed')); }
    request.promise = Promise.resolve(resumed).then(() => {
      if (this._disposed || this._context !== context || request.generation !== this._generation
        || this._suspended || !this._active || this._hidden() || context.state !== 'running') {
        if (this._context === context && (this._suspended || !this._active || this._hidden())) {
          this._silence();
          this._sleepContext();
        }
        return false;
      }
      if (fromGesture) this._unlocked = true;
      this._error = null;
      this._sync();
      return true;
    }, () => {
      if (this._context === context && request.generation === this._generation) {
        this._error = 'resume-failed';
        if (!this._ready()) this._silence();
      }
      return false;
    }).finally(() => {
      if (this._wakeRequest === request) this._wakeRequest = null;
    });
    return request.promise;
  }

  _sleepContext() {
    const context = this._context;
    if (!context || context.state === 'closed' || this._sleepRequest) return;
    const request = { context };
    this._sleepRequest = request;
    // Queue suspend even if state still says suspended: an earlier resume may be
    // in flight. Bus gates and stopped sources provide immediate silence either way.
    let sleeping;
    try { sleeping = context.suspend(); }
    catch { sleeping = Promise.reject(new Error('suspend-failed')); }
    const settled = () => {
      if (this._sleepRequest !== request) return;
      this._sleepRequest = null;
      if (this._disposed || this._context !== context) return;
      if (!this._suspended && this._active && this._unlocked && !this._hidden()) {
        if (context.state === 'running') this._sync();
        // A late suspend must not win over a newer legitimate resume. Let a
        // current resume settle first, then repair once if it lost the race.
        else if (this._wakeRequest?.promise) {
          void this._wakeRequest.promise.then(() => {
            if (this._context === context && !this._suspended && this._active
              && this._unlocked && !this._hidden() && !this._sleepRequest && !this._wakeRequest) {
              if (context.state === 'running') this._sync();
              else void this._wake(false);
            }
          });
        } else void this._wake(false);
      }
    };
    Promise.resolve(sleeping).then(settled, () => {
      if (this._sleepRequest === request) this._error = 'suspend-failed';
      settled();
    });
  }

  _init() {
    const c = new this._Context({ latencyHint: 'interactive' });
    this._context = c;
    const keep = (node) => { this._nodes.push(node); return node; };
    this._musicBus = keep(c.createGain());
    this._sfxBus = keep(c.createGain());
    this._musicBus.gain.value = this._sfxBus.gain.value = 0;
    this._leadFilter = keep(c.createBiquadFilter());
    this._sfxFilter = keep(c.createBiquadFilter());
    for (const [filter, cutoff] of [[this._leadFilter, 2900], [this._sfxFilter, 4400]]) {
      filter.type = 'lowpass';
      filter.frequency.value = Math.min(cutoff, c.sampleRate * 0.45);
      filter.Q.value = 0.45;
    }
    this._leadFilter.connect(this._musicBus);
    this._sfxFilter.connect(this._sfxBus);
    const master = keep(c.createGain());
    master.gain.value = 0.82; // Headroom comes first; the limiter only catches pileups.
    this._musicBus.connect(master);
    this._sfxBus.connect(master);
    if (typeof c.createDynamicsCompressor === 'function') {
      const limiter = keep(c.createDynamicsCompressor());
      limiter.threshold.value = -9;
      limiter.knee.value = 3;
      limiter.ratio.value = 16;
      limiter.attack.value = 0.002;
      limiter.release.value = 0.12;
      master.connect(limiter).connect(c.destination);
    } else {
      master.gain.value = 0.62; // Conservative fallback for incomplete Web Audio implementations.
      master.connect(c.destination);
    }
    this._noiseBuffer = c.createBuffer(1, Math.ceil(c.sampleRate * 0.3), c.sampleRate);
    const data = this._noiseBuffer.getChannelData(0);
    let seed = 0x52414c4c;
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
    if (context.state === 'closed') { this._error = 'context-closed'; this.dispose(); return; }
    if (this._ready()) this._sync();
    else {
      this._silence();
      if (context.state === 'running' && (this._suspended || !this._active || this._hidden())) {
        this._sleepContext();
      }
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
      bus.gain.setValueAtTime(value, now); // Gate immediately, including queued notes.
    } catch {
      try { bus.gain.value = value; } catch { /* Context was closed externally. */ }
    }
  }

  _startMusic() {
    if (!this._ready() || !this._musicEnabled || this._timer !== null) return;
    this._level(this._musicBus, MUSIC_LEVEL);
    this._nextStep = this._context.currentTime + 0.018;
    this._step = (Math.ceil(this._step / 16) * 16) % (THEME.length * 16);
    try {
      this._timer = setInterval(this._tick, TICK_MS);
      this._schedule();
    } catch { this._error = 'scheduler-failed'; this._stopMusic(); }
  }

  _stopMusic() {
    if (this._timer !== null) clearInterval(this._timer);
    this._timer = null;
    this._level(this._musicBus, 0);
    this._stopVoices('music');
  }

  _resetEffects() {
    this._lastSfx = Object.create(null);
    this._lastImpact = -Infinity;
    this._impactQuietUntil = 0;
  }

  _silence() {
    this._stopMusic();
    this._level(this._sfxBus, 0);
    this._stopVoices('sfx');
    this._resetEffects();
  }

  _schedule() {
    if (!this._ready() || !this._musicEnabled) { this._stopMusic(); return; }
    const now = this._context.currentTime;
    this._prune(now);
    if (this._nextStep < now) {
      // Drop throttled-tab backlog and rejoin a bar; never fire hundreds of late notes.
      this._nextStep = now + 0.018;
      this._step = (Math.ceil(this._step / 16) * 16) % (THEME.length * 16);
    }
    let count = 0;
    while (this._nextStep < now + LOOKAHEAD && count++ < 3) {
      this._musicStep(this._step, this._nextStep);
      this._nextStep += STEP + (this._step % 2 === 0 ? 0.005 : -0.005);
      this._step = (this._step + 1) % (THEME.length * 16);
    }
  }

  _musicStep(step, t) {
    const barIndex = Math.floor(step / 16);
    const bar = THEME[barIndex];
    const beat = step % 16;
    const coral = barIndex >= 8;
    if (beat % 2 === 0) {
      const eighth = beat / 2;
      const note = bar.lead[eighth];
      if (note) {
        const duration = STEP * (bar.lead[(eighth + 1) % 8] ? 1.35 : 2.65);
        this._tone('music', t, hz(note), duration, coral ? 0.06 : 0.072, 'square');
      }
    }
    if (beat === 0 || beat === 8) {
      this._tone('music', t, hz(bar.bass), STEP * 2.3, 0.15, 'triangle');
    } else if (beat === 6 || beat === 11 || beat === 14) {
      const jump = beat === 11 ? 7 : beat === 6 ? 12 : 0;
      this._tone('music', t, hz(bar.bass + jump), STEP * 0.9, 0.115, 'triangle');
    }
    if (beat === 0 || beat === 8 || (coral && barIndex % 2 === 1 && beat === 6)) {
      this._tone('music', t, 138, 0.135, 0.25, 'sine', 46);
    }
    if (beat === 4 || beat === 12) {
      this._noise('music', t, 0.09, 0.085, 'bandpass', 1900);
      this._tone('music', t, 185, 0.055, 0.042, 'sine', 145);
    }
    if (beat % 4 === 2) {
      this._noise('music', t, beat === 14 ? 0.07 : 0.028,
        beat === 14 ? 0.017 : 0.02, 'highpass', 6100);
    } else if (coral && (beat === 7 || beat === 15)) {
      this._noise('music', t, 0.023, 0.009, 'highpass', 6900);
    }
  }

  _tone(group, t, frequency, duration, peak, shape, slideTo = 0) {
    if (!this._room(group)) return;
    const voice = this._track(group, t, t + duration + 0.012);
    try {
      const c = this._context;
      const source = voice.source = c.createOscillator();
      voice.nodes.push(source);
      const gain = c.createGain();
      voice.nodes.push(gain);
      source.type = shape;
      source.frequency.setValueAtTime(frequency, t);
      if (slideTo) source.frequency.exponentialRampToValueAtTime(slideTo, t + duration * 0.8);
      this._envelope(gain.gain, t, duration, peak);
      source.connect(gain);
      const bus = group === 'music' ? this._musicBus : this._sfxBus;
      gain.connect(shape === 'square' ? (group === 'music' ? this._leadFilter : this._sfxFilter) : bus);
      source.onended = () => this._release(voice);
      source.start(t);
      source.stop(voice.end);
    } catch { this._error = 'voice-failed'; this._release(voice); }
  }

  _noise(group, t, duration, peak, type, frequency) {
    if (!this._room(group)) return;
    const voice = this._track(group, t, t + duration + 0.012);
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
    } catch { this._error = 'voice-failed'; this._release(voice); }
  }

  _envelope(param, t, duration, peak) {
    param.setValueAtTime(0, t);
    param.linearRampToValueAtTime(peak, t + Math.min(0.004, duration * 0.15));
    param.exponentialRampToValueAtTime(peak * 0.46, t + duration * 0.32);
    param.exponentialRampToValueAtTime(FLOOR, t + duration);
    param.linearRampToValueAtTime(0, t + duration + 0.008);
  }

  _room(group) {
    if (!this._ready() || !(group === 'music' ? this._musicEnabled : this._sfxEnabled)) return false;
    this._prune(this._context.currentTime);
    return this._voices[group].size < LIMITS[group];
  }

  _track(group, start, end) {
    const voice = { group, start, end, source: null, nodes: [] };
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
