// A small, sample-free synth rack. Nothing touches Web Audio before unlock().
const BPM = 112;
const STEP = 60 / BPM / 4;
const LOOKAHEAD = 0.15;
const TICK_MS = 80;
const FLOOR = 0.0001;
const MUSIC_LIMIT = 14;
const SFX_LIMIT = 12;
const VOICE_LIMIT = 24;
const HZ = Array.from({ length: 128 }, (_, n) => 440 * 2 ** ((n - 69) / 12));

// Original eight-bar F# minor / Dmaj9 / Aadd9 / Eadd9 theme.
const CHORDS = [
  { bass: 42, notes: [66, 69, 73, 80], answer: [76, 73, 71] },
  { bass: 38, notes: [66, 69, 73, 76], answer: [74, 73, 69] },
  { bass: 45, notes: [64, 69, 71, 73], answer: [76, 73, 71] },
  { bass: 40, notes: [64, 68, 71, 78], answer: [76, 71, 68] },
];
const ARP = [0, 2, 1, 3, 2, 1, 3, 2, 0, 2, 1, 3, 2, 3, 1, 2];
const EAT_ROOTS = [73, 76, 78, 81];
const LEVEL_NOTES = [78, 81, 85, 90, 88, 90];
const LEVEL_TIMES = [0, 0.065, 0.13, 0.23, 0.31, 0.4];
const COOLDOWN = { start: 0.15, turn: 0.055, eat: 0.055, level: 0.45,
  death: 0.35, pause: 0.16, resume: 0.16, ui: 0.045 };

function disconnect(node) {
  try { node?.disconnect(); } catch { /* Already detached by the browser. */ }
}

export class ArcadeAudio {
  constructor() {
    this._Context = globalThis.AudioContext || globalThis.webkitAudioContext;
    this._available = typeof this._Context === 'function';
    this._musicEnabled = true;
    this._sfxEnabled = true;
    this._playing = false;
    this._unlocked = false;
    this._suspended = false;
    this._disposed = false;
    this._context = null;
    this._nodes = [];
    this._echo = [];
    this._voices = { music: new Set(), sfx: new Set() };
    this._lastSfx = Object.create(null);
    this._eatIndex = 0;
    this._step = 0;
    this._nextStep = 0;
    this._timer = null;
    this._suspendTimer = null;
    this._tick = () => this._schedule();
    this._onBlur = () => this.suspend();
    this._onFocus = () => { void this.resume(); };
    this._onVisibility = () => {
      if (this._hidden()) this.suspend();
      else void this.resume();
    };
    this._onState = () => this._contextChanged();
  }

  get musicEnabled() { return this._musicEnabled; }
  get sfxEnabled() { return this._sfxEnabled; }
  get available() { return this._available && !this._disposed; }

  // Call directly from a pointer/key gesture; resume() never creates a context.
  async unlock() {
    if (!this.available || this._hidden()) return false;
    if (!this._context) {
      try { this._init(); }
      catch { this.dispose(); return false; }
    }
    return this._wake(true);
  }

  async resume() {
    if (!this.available || !this._unlocked || !this._context || this._hidden()) return false;
    return this._wake(false);
  }

  setMusic(enabled) {
    this._musicEnabled = Boolean(enabled);
    if (!this._context || this._disposed) return;
    if (this._musicEnabled && this._ready()) this._startMusic();
    else this._stopMusic();
  }

  setSfx(enabled) {
    this._sfxEnabled = Boolean(enabled);
    if (!this._context || this._disposed) return;
    this._fade(this._sfxBus.gain, this._sfxEnabled && this._ready() ? 0.62 : 0);
    if (!this._sfxEnabled) this._stopVoices('sfx');
  }

  setPlaying(playing) {
    this._playing = Boolean(playing);
    if (!this._context || this._disposed) return;
    this._fade(this._musicFilter.frequency, this._playing ? 6200 : 3800, 0.18);
    if (this._musicEnabled && this._ready()) {
      this._fade(this._musicBus.gain, this._playing ? 0.48 : 0.29, 0.16);
    }
  }

  play(name) {
    if (!this._sfxEnabled || !this._ready() || typeof name !== 'string'
      || !Object.prototype.hasOwnProperty.call(COOLDOWN, name)) return;
    const t = this._context.currentTime + 0.006;
    if (t - (this._lastSfx[name] ?? -Infinity) < COOLDOWN[name]) return;
    this._lastSfx[name] = t;
    try {
      switch (name) {
        case 'turn':
          this._tone('sfx', t, 700, 0.032, 0.045, 'triangle', 510);
          break;
        case 'ui':
          this._tone('sfx', t, HZ[81], 0.055, 0.09, 'sine', HZ[83]);
          break;
        case 'start':
          this._tone('sfx', t, HZ[66], 0.13, 0.14, 'chip');
          this._tone('sfx', t + 0.065, HZ[73], 0.16, 0.12, 'chip');
          this._tone('sfx', t + 0.13, HZ[78], 0.25, 0.12, 'sine');
          break;
        case 'eat': {
          const root = EAT_ROOTS[this._eatIndex++ % EAT_ROOTS.length];
          this._tone('sfx', t, HZ[root - 4], 0.09, 0.17, 'chip', HZ[root]);
          this._tone('sfx', t + 0.06, HZ[root + 7], 0.12, 0.14, 'chip');
          this._tone('sfx', t + 0.125, HZ[root + 12], 0.21, 0.13, 'sine');
          break;
        }
        case 'level':
          for (let i = 0; i < LEVEL_NOTES.length; i++) {
            this._tone('sfx', t + LEVEL_TIMES[i], HZ[LEVEL_NOTES[i]],
              i === 5 ? 0.36 : 0.17, 0.15, 'chip');
          }
          this._tone('sfx', t, HZ[42], 0.35, 0.15, 'triangle');
          this._tone('sfx', t + 0.4, HZ[78], 0.36, 0.085, 'sine');
          break;
        case 'death':
          // Prioritize the descending arcade crash over queued little bleeps.
          this._stopVoices('sfx', true);
          this._tone('sfx', t, HZ[54], 0.62, 0.23, 'triangle', HZ[24]);
          this._tone('sfx', t + 0.015, HZ[78], 0.46, 0.18, 'chip', HZ[42]);
          this._tone('sfx', t + 0.12, HZ[66], 0.26, 0.10, 'chip', HZ[54]);
          this._noise('sfx', t, 0.2, 0.105, 'bandpass', 2300, 420);
          break;
        case 'pause':
          this._tone('sfx', t, HZ[73], 0.11, 0.11, 'triangle');
          this._tone('sfx', t + 0.075, HZ[66], 0.15, 0.09, 'triangle');
          break;
        case 'resume':
          this._tone('sfx', t, HZ[66], 0.11, 0.10, 'triangle');
          this._tone('sfx', t + 0.075, HZ[73], 0.16, 0.11, 'triangle');
          break;
      }
    } catch { /* Audio failure must never interrupt the game. */ }
  }

  suspend() {
    if (this._disposed) return;
    this._suspended = true;
    this._clearSuspendTimer();
    this._stopMusic();
    if (!this._context) return;
    this._fade(this._sfxBus.gain, 0, 0.018);
    this._stopVoices('sfx');
    const context = this._context;
    // Let the short anti-click fades finish before freezing the audio clock.
    if (context.state === 'running') {
      this._suspendTimer = setTimeout(() => {
        this._suspendTimer = null;
        if (!this._suspended || this._context !== context || this._disposed) return;
        try {
          Promise.resolve(context.suspend()).then(() => {
            if (this._suspended && this._context === context) this._clearVoices();
          }).catch(() => {});
        } catch { /* Output is already muted even if suspension is denied. */ }
      }, 28);
    } else this._clearVoices();
  }

  dispose() {
    if (this._disposed) return;
    this._disposed = true;
    this._available = false;
    this._unlocked = false;
    this._suspended = true;
    this._clearSuspendTimer();
    this._stopMusic(true);
    this._clearVoices();
    globalThis.window?.removeEventListener('blur', this._onBlur);
    globalThis.window?.removeEventListener('focus', this._onFocus);
    globalThis.document?.removeEventListener('visibilitychange', this._onVisibility);
    const context = this._context;
    context?.removeEventListener?.('statechange', this._onState);
    for (const node of this._nodes) disconnect(node);
    this._nodes.length = 0;
    this._noiseBuffer = null;
    this._chipWave = null;
    this._musicBus = null;
    this._sfxBus = null;
    this._musicFilter = null;
    this._leadInputs = null;
    this._echoInput = null;
    this._context = null;
    if (context && context.state !== 'closed') {
      try { Promise.resolve(context.close()).catch(() => {}); } catch { /* Best effort. */ }
    }
  }

  _hidden() { return Boolean(globalThis.document?.hidden); }

  _ready() {
    return this.available && this._unlocked && !this._suspended
      && this._context?.state === 'running';
  }

  async _wake(fromGesture) {
    this._clearSuspendTimer();
    this._suspended = false;
    const context = this._context;
    try {
      if (context.state !== 'running') await context.resume();
      if (this._disposed || this._suspended || this._context !== context || this._hidden()
        || context.state !== 'running') return false;
      if (fromGesture) this._unlocked = true;
      this._activate();
      return true;
    } catch {
      // Autoplay denial/interruption is retryable on the next real gesture.
      return false;
    }
  }

  _init() {
    const c = new this._Context({ latencyHint: 'interactive' });
    this._context = c;
    const keep = (node) => { this._nodes.push(node); return node; };
    this._musicBus = keep(c.createGain());
    this._sfxBus = keep(c.createGain());
    this._musicFilter = keep(c.createBiquadFilter());
    const limiter = keep(c.createDynamicsCompressor());
    const master = keep(c.createGain());
    this._musicBus.gain.value = 0;
    this._sfxBus.gain.value = 0;
    this._musicFilter.type = 'lowpass';
    this._musicFilter.frequency.value = this._playing ? 6200 : 3800;
    this._musicFilter.Q.value = 0.45;
    // Conservative buses plus a soft-knee limiter leave comfortable headroom.
    limiter.threshold.value = -12;
    limiter.knee.value = 12;
    limiter.ratio.value = 6;
    limiter.attack.value = 0.003;
    limiter.release.value = 0.15;
    master.gain.value = 0.78;
    this._musicBus.connect(this._musicFilter).connect(limiter);
    this._sfxBus.connect(limiter);
    limiter.connect(master).connect(c.destination);

    this._echoInput = keep(c.createGain());
    this._echoInput.gain.value = 0.13;
    this._leadInputs = [-0.22, 0.22].map((pan) => {
      const node = keep(c.createStereoPanner ? c.createStereoPanner() : c.createGain());
      if (node.pan) node.pan.value = pan;
      node.connect(this._musicBus);
      node.connect(this._echoInput);
      return node;
    });
    const real = new Float32Array(10);
    const imaginary = new Float32Array(10);
    imaginary[1] = 1;
    imaginary[3] = 0.20;
    imaginary[5] = 0.085;
    imaginary[7] = 0.025;
    imaginary[9] = 0.008;
    this._chipWave = c.createPeriodicWave(real, imaginary);

    // One reusable, locally synthesized noise buffer; no samples or downloads.
    this._noiseBuffer = c.createBuffer(1, Math.ceil(c.sampleRate * 0.5), c.sampleRate);
    const data = this._noiseBuffer.getChannelData(0);
    let seed = 0x4e434f49;
    for (let i = 0; i < data.length; i++) {
      seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5;
      data[i] = (seed >>> 0) / 2147483648 - 1;
    }
    c.addEventListener?.('statechange', this._onState);
    globalThis.window?.addEventListener('blur', this._onBlur);
    globalThis.window?.addEventListener('focus', this._onFocus);
    globalThis.document?.addEventListener('visibilitychange', this._onVisibility);
  }

  _activate() {
    this._fade(this._sfxBus.gain, this._sfxEnabled ? 0.62 : 0);
    if (this._musicEnabled) this._startMusic();
  }

  _contextChanged() {
    if (this._disposed || !this._context) return;
    if (this._context.state === 'closed') { this.dispose(); return; }
    if (this._context.state !== 'running') {
      this._stopMusic(true);
      this._fade(this._sfxBus.gain, 0, 0);
      this._clearVoices();
    } else if (this._suspended) {
      // A pending unlock can resolve after blur; keep that race silent/asleep.
      try { Promise.resolve(this._context.suspend()).catch(() => {}); } catch { /* Muted. */ }
    } else if (this._ready()) this._activate();
  }

  _startMusic() {
    if (!this._ready() || !this._musicEnabled || this._timer !== null) return;
    try {
      this._resetEcho();
      this._fade(this._musicBus.gain, this._playing ? 0.48 : 0.29, 0.10);
      this._nextStep = this._context.currentTime + 0.018;
      // Resume at a bar boundary, never replay a throttled timer's backlog.
      this._step = (Math.ceil(this._step / 16) * 16) % 128;
      this._timer = setInterval(this._tick, TICK_MS);
      this._schedule();
    } catch { this._stopMusic(true); }
  }

  _stopMusic(immediate = false) {
    if (this._timer !== null) clearInterval(this._timer);
    this._timer = null;
    if (!this._context) return;
    if (this._musicBus) this._fade(this._musicBus.gain, 0, immediate ? 0 : 0.024);
    this._stopVoices('music', immediate);
    if (immediate) this._disconnectEcho();
  }

  _schedule() {
    if (!this._ready() || !this._musicEnabled) { this._stopMusic(); return; }
    const now = this._context.currentTime;
    this._prune(now);
    if (this._nextStep < now + 0.004) this._nextStep = now + 0.012;
    const horizon = now + LOOKAHEAD;
    let count = 0;
    try {
      while (this._nextStep < horizon && count++ < 3) {
        this._musicStep(this._step, this._nextStep);
        // A tiny sixteenth-note swing; paired intervals still equal 112 BPM.
        this._nextStep += STEP + (this._step % 2 === 0 ? 0.006 : -0.006);
        this._step = (this._step + 1) % 128;
      }
    } catch { this._stopMusic(true); }
  }

  _musicStep(step, t) {
    const bar = Math.floor(step / 16);
    const beat = step % 16;
    const chord = CHORDS[Math.floor(bar / 2)];
    const active = this._playing;
    if (beat % (active ? 2 : 4) === 0 || (active && beat % 8 === 7)) {
      const answer = active && bar % 2 === 1 && beat >= 10 && beat % 2 === 0;
      const note = answer ? chord.answer[(beat - 10) / 2] : chord.notes[ARP[beat]];
      this._tone('music', t, HZ[note], active ? 0.20 : 0.28,
        beat % 4 === 0 ? 0.105 : 0.078, 'chip', 0, beat % 4 < 2 ? -1 : 1);
    }
    if (beat === 0 || beat === 8) {
      this._tone('music', t, HZ[chord.notes[0] - 12], 0.88, 0.032, 'pad', 0, -1);
      this._tone('music', t, HZ[chord.notes[2] - 12], 0.88, 0.029, 'pad', 0, 1);
    }
    if (beat === 0 || beat === 8 || (active && (beat === 3 || beat === 6 || beat === 11 || beat === 14))) {
      const octave = active && (beat === 6 || beat === 14) ? 12 : 0;
      this._tone('music', t, HZ[chord.bass + octave], active ? 0.21 : 0.38,
        active ? 0.19 : 0.14, 'triangle');
    }
    if (beat === 0 || (active && (beat === 8 || (bar % 2 === 1 && beat === 10)))) {
      this._tone('music', t, 146, 0.19, active ? 0.37 : 0.18, 'sine', 43);
    }
    if ((active && (beat === 4 || beat === 12)) || (!active && beat === 12)) {
      this._noise('music', t, 0.115, active ? 0.16 : 0.055, 'bandpass', 1750);
      this._tone('music', t, 185, 0.085, active ? 0.08 : 0.025, 'sine', 125);
    }
    if ((active && beat % 2 === 0) || (!active && (beat === 6 || beat === 14))) {
      this._noise('music', t, beat === 14 && active ? 0.085 : 0.035,
        active ? (beat % 4 === 2 ? 0.047 : 0.029) : 0.013, 'highpass', 6800);
    }
  }

  _resetEcho() {
    this._disconnectEcho();
    const c = this._context;
    const delay = c.createDelay(1);
    this._echo.push(delay);
    const filter = c.createBiquadFilter();
    this._echo.push(filter);
    const feedback = c.createGain();
    this._echo.push(feedback);
    delay.delayTime.value = 60 / BPM * 0.75;
    filter.type = 'lowpass';
    filter.frequency.value = 2500;
    filter.Q.value = 0.4;
    feedback.gain.value = 0.20;
    this._echoInput.connect(delay).connect(filter);
    filter.connect(this._musicBus);
    filter.connect(feedback).connect(delay);
  }

  _disconnectEcho() {
    disconnect(this._echoInput);
    for (const node of this._echo) disconnect(node);
    this._echo.length = 0;
  }

  _tone(group, t, frequency, duration, peak, shape = 'triangle', slideTo = 0, pan = 0) {
    if (!this._room(group)) return;
    const c = this._context;
    let source, gain, voice;
    try {
      source = c.createOscillator();
      gain = c.createGain();
      voice = this._track(group, source, gain, null, t + duration + 0.012);
      if (shape === 'chip') source.setPeriodicWave(this._chipWave);
      else source.type = shape === 'pad' ? 'sine' : shape;
      source.frequency.setValueAtTime(frequency, t);
      if (slideTo) source.frequency.exponentialRampToValueAtTime(slideTo, t + duration * 0.9);
      this._envelope(gain.gain, t, duration, peak, shape === 'pad');
      source.connect(gain);
      gain.connect(group === 'sfx' ? this._sfxBus
        : pan ? this._leadInputs[pan < 0 ? 0 : 1] : this._musicBus);
      source.start(t);
      source.stop(voice.end);
    } catch {
      if (voice) this._release(voice);
      else { disconnect(source); disconnect(gain); }
    }
  }

  _noise(group, t, duration, peak, type, frequency, slideTo = 0) {
    if (!this._room(group)) return;
    const c = this._context;
    let source, filter, gain, voice;
    try {
      source = c.createBufferSource();
      gain = c.createGain();
      filter = c.createBiquadFilter();
      voice = this._track(group, source, gain, filter, t + duration + 0.01);
      source.buffer = this._noiseBuffer;
      filter.type = type;
      filter.frequency.setValueAtTime(Math.min(frequency, c.sampleRate * 0.45), t);
      filter.Q.value = 0.7;
      if (slideTo) filter.frequency.exponentialRampToValueAtTime(slideTo, t + duration);
      this._envelope(gain.gain, t, duration, peak, false, 0.001);
      source.connect(filter).connect(gain);
      gain.connect(group === 'music' ? this._musicBus : this._sfxBus);
      source.start(t);
      source.stop(voice.end);
    } catch {
      if (voice) this._release(voice);
      else { disconnect(source); disconnect(gain); disconnect(filter); }
    }
  }

  _envelope(param, t, duration, peak, pad, attack = 0.004) {
    const rise = pad ? 0.085 : Math.min(attack, duration * 0.2);
    param.setValueAtTime(0, t);
    param.linearRampToValueAtTime(peak, t + rise);
    param.exponentialRampToValueAtTime(peak * (pad ? 0.75 : 0.38),
      t + duration * (pad ? 0.68 : 0.3));
    param.exponentialRampToValueAtTime(FLOOR, t + duration);
    param.linearRampToValueAtTime(0, t + duration + 0.008);
  }

  _room(group) {
    this._prune(this._context.currentTime);
    return this._voices[group].size < (group === 'music' ? MUSIC_LIMIT : SFX_LIMIT)
      && this._voices.music.size + this._voices.sfx.size < VOICE_LIMIT;
  }

  _track(group, source, gain, filter, end) {
    const voice = { group, source, gain, filter, end, stopping: false };
    this._voices[group].add(voice);
    source.onended = () => this._release(voice);
    return voice;
  }

  _release(voice) {
    if (!this._voices[voice.group].delete(voice)) return;
    voice.source.onended = null;
    try { voice.source.stop(); } catch { /* It may already have ended. */ }
    disconnect(voice.source);
    disconnect(voice.gain);
    disconnect(voice.filter);
  }

  _prune(now) {
    for (const group of ['music', 'sfx']) {
      for (const voice of this._voices[group]) {
        if (voice.end <= now) this._release(voice);
      }
    }
  }

  _stopVoices(group, immediate = false) {
    if (!this._context) return;
    const now = this._context.currentTime;
    for (const voice of this._voices[group]) {
      if (immediate || this._context.state !== 'running') { this._release(voice); continue; }
      if (voice.stopping) continue;
      voice.stopping = true;
      voice.end = Math.min(voice.end, now + 0.019);
      this._fade(voice.gain.gain, 0, 0.016);
      try { voice.source.stop(voice.end); } catch { this._release(voice); }
    }
  }

  _clearVoices() {
    this._stopVoices('music', true);
    this._stopVoices('sfx', true);
    this._disconnectEcho();
  }

  _fade(param, value, seconds = 0.024) {
    if (!this._context) return;
    const now = this._context.currentTime;
    try {
      if (param.cancelAndHoldAtTime) param.cancelAndHoldAtTime(now);
      else {
        const current = param.value;
        param.cancelScheduledValues(now);
        param.setValueAtTime(current, now);
      }
      if (seconds > 0) param.linearRampToValueAtTime(value, now + seconds);
      else param.setValueAtTime(value, now);
    } catch { /* Ignore automation on a context closed by the browser. */ }
  }

  _clearSuspendTimer() {
    if (this._suspendTimer !== null) clearTimeout(this._suspendTimer);
    this._suspendTimer = null;
  }
}
