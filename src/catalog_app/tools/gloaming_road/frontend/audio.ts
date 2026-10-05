import { AUDIO_ASSETS, AUDIO_COMPRESSED_BYTES, type AudioAsset } from './assets/audio/catalog';

/** Original rendered audio only. No oscillator, sequencer, reference recording, or CDN. */
export type AudioPosition = { x: number; y: number; z: number };
export type AudioLevels = { master: number; music: number; ambience: number; effects: number };
export type AudioWorldState = { biome: string; night: boolean; blood: boolean; inside: boolean; threat: boolean; royal: boolean };
export const SOUND_NAMES = [...new Set(AUDIO_ASSETS.filter(a => a.kind === 'effect').map(a => a.group))] as readonly string[];

const CACHE_BYTES = 8 * 1024 * 1024;
const CACHE_COUNT = 40;
const MAX_VOICES = 24;
const MAX_PENDING_PLAYS = 12;
const DECODE_CONCURRENCY = 2;
const MAX_DECODE_QUEUE = 32;
const SAMPLE_RATE = 24000;
const DEFAULT_LEVELS: AudioLevels = { master: .8, music: .7, ambience: .65, effects: .85 };
const DEFAULT_STATE: AudioWorldState = { biome: 'meadow', night: false, blood: false, inside: false, threat: false, royal: false };
const assets = new Map(AUDIO_ASSETS.map(asset => [asset.id, asset]));
const groups = new Map<string, AudioAsset[]>();
for (const asset of AUDIO_ASSETS) {
  if (asset.kind === 'effect') groups.set(asset.group, [...(groups.get(asset.group) ?? []), asset]);
}
const aliases: Record<string, string> = {
  dirt: 'step_dirt', grass: 'step_grass', stone: 'step_stone', wood: 'step_wood',
  footstep_dirt: 'step_dirt', footstep_grass: 'step_grass', footstep_stone: 'step_stone', footstep_wood: 'step_wood',
  step: 'step_dirt', swing: 'whoosh_light', light: 'whoosh_light', heavy: 'whoosh_heavy',
  swing_light: 'whoosh_light', swing_heavy: 'whoosh_heavy', impact_stone: 'arrow_stone', impact_wood: 'arrow_wood',
  death_enemy: 'enemy_death',
  hit: 'flesh', hit_flesh: 'flesh', hit_armor: 'armor', hit_shield: 'shield', armor_rustle: 'armor',
  arrow_hit: 'arrow_impact', arrow_release: 'bow_release', fire_hit: 'fire_impact',
  fire_cast: 'fire_release', fire_loop: 'fire_linger', cloth_move: 'cloth',
  select: 'ui', confirm: 'ui_confirm', cancel: 'ui_cancel', door_open: 'door',
  knight_death: 'enemy_death', player_death: 'death', leaf: 'leaves', birds: 'bird',
};

// Deliberately selective: footsteps, cloth, UI clicks and ambience must not flood captions.
const SOUND_CAPTIONS: Readonly<Record<string, string>> = {
  bow_draw: 'Bowstring draws taut', bow_release: 'Arrow released',
  fire_charge: 'Fire gathers', fire_release: 'Fire released', fire_impact: 'Fire bursts',
  parry: 'Steel rings — parry', block: 'Blow blocked', shield: 'Shield struck',
  armor: 'Armor struck', flesh: 'Hit lands', arrow_flesh: 'Hit lands',
  door: 'Door creaks', latch: 'Latch clicks', rest: 'Rest chimes',
};

type Cached = { buffer: AudioBuffer; bytes: number; used: number };
type DecodeTask = { asset: AudioAsset; resolve: (buffer: AudioBuffer | undefined) => void };
type Voice = { source: AudioBufferSourceNode; gain: GainNode; panner?: PannerNode; position?: AudioPosition; ended: boolean };
type MediaSlot = {
  element: HTMLAudioElement; source: MediaElementAudioSourceNode; gain: GainNode;
  asset?: AudioAsset; target: number; serial: number; retireTimer?: number;
  playing: boolean; playPromise?: Promise<boolean>; cancelPlay?: () => void;
};
type Activation = { epoch: number; cancel: () => void };
const CONTACT_CAPTIONS = new Set(['parry', 'block', 'shield', 'armor', 'flesh', 'arrow_flesh']);
const PLAY_TIMEOUT_MS = 10000;

function finite(n: number, fallback = 0): number { return Number.isFinite(n) ? n : fallback; }
function clamp(n: number, low = 0, high = 1): number { return Math.max(low, Math.min(high, finite(n))); }
function point(p: AudioPosition): AudioPosition { return { x: finite(p.x), y: finite(p.y), z: finite(p.z) }; }

/**
 * Parent contract:
 *  - await load() at boot; it decodes a small useful SFX set, never plays anything.
 *  - call unlock() synchronously from a real click/touch/key event (before any await).
 *  - cue('title') in the menu; mix(state, dt) only during active gameplay.
 *  - pause() on menu/blur, resume() after play resumes, clear() at new game/death.
 *  - rebase(dx,dz) subtracts the same origin shift that the world subtracts.
 *
 * Four reusable, gesture-primed HTMLAudio elements stream two music and two ambience
 * voices during crossfades. Long files NEVER enter the decoded-buffer cache. Effects
 * use a two-job decoder, a 40-entry / 8 MiB LRU, and at most 24 live source nodes.
 */
export class GameAudio {
  /** Optional sound-event accessibility feed; independent of mute/unlock. The UI gates display. */
  onCaption?: (text: string) => void;
  private lastCaptionText = '';
  private lastCaptionPriority = 0;
  private lastCaptionAt = -Infinity;
  private ctx?: AudioContext;
  private decoder?: OfflineAudioContext;
  private masterBus?: GainNode;
  private musicBus?: GainNode;
  private ambienceBus?: GainNode;
  private effectsBus?: GainNode;
  private musicFilter?: BiquadFilterNode;
  private limiter?: DynamicsCompressorNode;
  private ceiling?: WaveShaperNode;
  private convolver?: ConvolverNode;
  private wetBus?: GainNode;
  private impulse?: AudioBuffer;
  private reverbImpulse?: AudioBuffer;
  private resamplingImpulse?: Promise<void>;
  private musicSlots: MediaSlot[] = [];
  private ambientSlots: MediaSlot[] = [];
  private levels = { ...DEFAULT_LEVELS };
  private state = { ...DEFAULT_STATE };
  private cueName?: 'title' | 'rescue';
  private started = false;
  private paused = false;
  private disposed = false;
  private unlocking?: Promise<boolean>;
  private activation?: Activation;
  private mediaEpoch = 0;
  private retryRequired = false;
  private playbackError = '';
  private loading?: Promise<void>;
  private format: 'ogg' | 'mp3' = 'ogg';
  private lastError = '';
  private lastGesture = -Infinity;
  private generation = 0;
  private voices = new Set<Voice>();
  private pendingPlays = 0;
  private cache = new Map<string, Cached>();
  private cacheBytes = 0;
  private clock = 0;
  private pendingDecodes = new Map<string, Promise<AudioBuffer | undefined>>();
  private decodeQueue: DecodeTask[] = [];
  private decoding = 0;
  private variation = new Map<string, number>();
  private cooldown = new Map<string, number>();
  private currentMusic = '';
  private currentAmbience = '';
  private zoneKey = '';
  private listenerPosition: AudioPosition = { x: 0, y: 1.65, z: 0 };
  private listenerForward: AudioPosition = { x: 0, y: 0, z: -1 };
  private originX = 0;
  private originZ = 0;
  private deathUntil = 0;
  private accentIn = 18;

  private readonly gesture = (event: Event): void => {
    if (event.isTrusted) this.lastGesture = performance.now();
  };
  private readonly visibility = (): void => {
    // Do not resume automatically: the parent should resume the game, not just sound.
    if (document.hidden) this.pause();
  };

  constructor() {
    if (typeof document !== 'undefined') {
      const probe = document.createElement('audio');
      this.format = probe.canPlayType('audio/ogg; codecs="vorbis"') ? 'ogg' : 'mp3';
      for (const name of ['pointerdown', 'click', 'touchend', 'keydown']) document.addEventListener(name, this.gesture, true);
      document.addEventListener('visibilitychange', this.visibility);
    }
  }

  /** Safe on the loading screen: no live AudioContext or media playback is created. */
  async load(progress?: (label: string) => void): Promise<void> {
    if (this.disposed) return;
    if (this.loading) return this.loading;
    this.loading = (async () => {
      const warm = ['room_ir', 'step_dirt_1', 'step_grass_1', 'step_stone_1', 'step_wood_1',
        'cloth_1', 'whoosh_light_1', 'whoosh_heavy_1', 'parry_1', 'block_1', 'shield_1',
        'armor_1', 'flesh_1', 'bow_draw_1', 'bow_release_1', 'fire_charge_1', 'fire_release_1',
        'ui_1', 'death_1', 'respawn_1'];
      let done = 0;
      const failed: string[] = [];
      progress?.('Preparing local audio · music remains silent until a gesture');
      await Promise.all(warm.map(async id => {
        const asset = assets.get(id);
        const buffer = asset ? await this.buffer(asset) : undefined;
        if (!buffer && !this.disposed) failed.push(id);
        if (id === 'room_ir' && buffer && !this.disposed) {
          this.impulse = buffer;
          this.prepareImpulse();
        }
        progress?.(`Local sounds ${++done}/${warm.length}`);
      }));
      if (failed.length) {
        this.lastError = `Local audio preload failed (${failed.slice(0, 3).join(', ')}${failed.length > 3 ? ', …' : ''}). Reload the App; if it persists, mute audio and report this message.`;
        progress?.('Some local sounds could not load · see audio warning');
      } else progress?.('Local audio ready · click or press a key to enable');
    })();
    return this.loading;
  }

  /** First activation/retry requires a gesture; an already ready transport is a no-op. */
  async unlock(): Promise<boolean> {
    if (this.disposed || typeof window === 'undefined') return false;
    if (this.unlocking) return this.unlocking;
    if (this.playbackReady) return true;
    const activeGesture = navigator.userActivation
      ? navigator.userActivation.isActive
      : performance.now() - this.lastGesture < 1200;
    if (!activeGesture) return false;
    try { this.createGraph(); }
    catch (error) {
      this.lastError = `Audio unavailable: ${String(error).slice(0, 140)}`;
      return false;
    }
    return this.beginPlayback(true);
  }

  private ownsActivation(owner: Activation): boolean {
    return this.activation === owner && owner.epoch === this.mediaEpoch && !this.disposed && !this.paused;
  }

  private beginPlayback(retry = false): Promise<boolean> {
    if (this.unlocking) return this.unlocking;
    if (!this.ctx || this.disposed || (this.retryRequired && !retry)) return Promise.resolve(false);
    if (retry) this.retryRequired = false;
    this.paused = false;
    let cancel!: () => void;
    const cancelled = new Promise<boolean>(resolve => { cancel = () => resolve(false); });
    const owner: Activation = { epoch: this.mediaEpoch, cancel: () => undefined };
    const timer = window.setTimeout(() => {
      if (this.ownsActivation(owner)) this.failPlayback('Audio activation timed out. Click Enable sound to retry.', owner.epoch);
    }, PLAY_TIMEOUT_MS);
    owner.cancel = () => { window.clearTimeout(timer); cancel(); };
    this.activation = owner;
    // runActivation reaches resume()/the FIRST four play() calls synchronously,
    // inside unlock's gesture. All later callers join this one owner.
    const promise = Promise.race([this.runActivation(owner), cancelled]).then(ok => {
      if (!this.ownsActivation(owner)) return false;
      window.clearTimeout(timer);
      this.activation = undefined;
      this.unlocking = undefined;
      if (ok) {
        if (this.lastError === this.playbackError) this.lastError = '';
        this.playbackError = '';
        // Apply a newer world/cue request only after the owned starts have settled.
        this.applyMix();
      }
      return ok && !this.retryRequired && !this.paused && this.ctx?.state === 'running';
    });
    // A synchronous media/context exception may already have cancelled this owner.
    // Never retain its resolved-false promise as the next gesture's activation.
    if (this.activation === owner) this.unlocking = promise;
    return promise;
  }

  private async runActivation(owner: Activation): Promise<boolean> {
    const ctx = this.ctx!;
    try {
      const firstPrime = !this.started;
      const slots = [...this.musicSlots, ...this.ambientSlots];
      const contextResume = ctx.resume();
      const starts = firstPrime ? slots.map(slot => {
        slot.element.src = this.url(assets.get('silence')!);
        slot.element.loop = true;
        return this.safePlay(slot);
      }) : slots.filter(slot => slot.asset && slot.target > 0).map(slot => this.safePlay(slot));
      const [, results] = await Promise.all([contextResume, Promise.all(starts)]);
      if (!this.ownsActivation(owner)) return false;
      if (ctx.state !== 'running' || results.some(ok => !ok)) {
        this.failPlayback('Audio could not resume. Click Enable sound to retry.', owner.epoch);
        return false;
      }
      if (firstPrime) {
        this.started = true; // Per-element gesture approval survives pause/clear.
        for (const slot of slots) { slot.element.pause(); slot.playing = false; }
      }
      this.applyMix(true, owner);
      const ready = await Promise.all(slots.filter(slot => slot.asset && slot.target > 0)
        .map(slot => slot.playPromise ?? Promise.resolve(slot.playing && !slot.element.paused)));
      if (!this.ownsActivation(owner)) return false;
      if (ready.some(ok => !ok)) {
        this.failPlayback('Local music playback failed. Click Enable sound to retry.', owner.epoch);
        return false;
      }
      void this.load();
      return true;
    } catch (error) {
      if (this.ownsActivation(owner)) this.failPlayback(`Audio activation failed: ${String(error).slice(0, 100)}. Click Enable sound to retry.`, owner.epoch);
      return false;
    }
  }

  settings(value: AudioLevels): void {
    this.levels = {
      master: clamp(value.master), music: clamp(value.music),
      ambience: clamp(value.ambience), effects: clamp(value.effects),
    };
    this.applyLevels();
  }

  mix(state: AudioWorldState, dt: number): void {
    if (this.disposed) return;
    this.state = { biome: String(state.biome || 'meadow'), night: !!state.night, blood: !!state.blood,
      inside: !!state.inside, threat: !!state.threat, royal: !!state.royal };
    if (this.cueName === 'title') this.cueName = undefined;
    this.applyMix();
    if (!this.audible || this.state.threat || this.state.inside || this.cueName === 'rescue') return;
    this.accentIn -= clamp(dt, 0, .1);
    if (this.accentIn <= 0) {
      this.accentIn = 17 + Math.random() * 19;
      const angle = Math.random() * Math.PI * 2;
      const radius = 9 + Math.random() * 12;
      const p = { x: this.listenerPosition.x + Math.cos(angle) * radius,
        y: this.listenerPosition.y + 3, z: this.listenerPosition.z + Math.sin(angle) * radius };
      this.play(this.state.night || this.state.blood ? 'bird_night' : Math.random() < .65 ? 'bird' : 'leaves', p, .22);
    }
  }

  listener(position: AudioPosition, forward: AudioPosition): void {
    this.listenerPosition = point(position);
    const f = point(forward), length = Math.hypot(f.x, f.y, f.z);
    if (length > .001) this.listenerForward = { x: f.x / length, y: f.y / length, z: f.z / length };
    const ctx = this.ctx;
    if (!ctx || this.disposed) return;
    const listener = ctx.listener, p = this.listenerPosition, direction = this.listenerForward;
    if (listener.positionX) {
      for (const [param, value] of [[listener.positionX, p.x], [listener.positionY, p.y], [listener.positionZ, p.z],
        [listener.forwardX, direction.x], [listener.forwardY, direction.y], [listener.forwardZ, direction.z],
        [listener.upX, 0], [listener.upY, 1], [listener.upZ, 0]] as [AudioParam, number][]) {
        param.setTargetAtTime(value, ctx.currentTime, .012);
      }
    } else {
      listener.setPosition(p.x, p.y, p.z);
      listener.setOrientation(direction.x, direction.y, direction.z, 0, 1, 0);
    }
  }

  /** Group names choose non-repeating rendered variations; exact asset IDs also work. */
  play(name: string, position?: AudioPosition, gain = 1): void {
    if (this.disposed) return;
    const normal = name.toLowerCase().replace(/[. /-]+/g, '_');
    const group = aliases[normal] ?? normal;
    if (group === 'death' || group === 'respawn') {
      this.clear();
      this.deathUntil = group === 'death' ? (this.ctx?.currentTime ?? 0) + 2.9 : 0;
    }
    // Caption the requested gameplay event even with muted buses or locked audio.
    // Audio variation, scheduling and gain behavior below remain unchanged.
    // Armor movement/notice shares rendered foley, not a contact event or its priority.
    if (Number.isFinite(gain) && gain > 0 && normal !== 'armor_rustle') this.emitCaption(group, position);
    if (!this.audible || !Number.isFinite(gain) || gain <= 0) return;
    const choices = groups.get(group);
    let asset: AudioAsset | undefined;
    if (choices?.length) {
      const previous = this.variation.get(group);
      const next = previous === undefined ? 0 : choices.length > 1
        ? (previous + 1 + Math.floor(Math.random() * (choices.length - 1))) % choices.length : 0;
      asset = choices[next];
      this.variation.set(group, next);
    } else {
      const candidate = assets.get(group);
      if (candidate?.kind === 'effect') asset = candidate;
    }
    if (!asset) return;
    const now = performance.now();
    const wait = group.startsWith('step_') ? 70 : group.startsWith('bird') ? 800 : group === 'fire_linger' ? 900 : group === 'ui' ? 30 : 45;
    if (now - (this.cooldown.get(group) ?? -Infinity) < wait) return;
    this.cooldown.set(group, now);
    let p = position ? point(position) : undefined;
    if (p && Math.hypot(p.x - this.listenerPosition.x, p.y - this.listenerPosition.y, p.z - this.listenerPosition.z) > 75) return;
    const entry = this.cache.get(asset.id);
    if (entry) {
      entry.used = ++this.clock;
      this.startEffect(asset, entry.buffer, p, gain);
      return;
    }
    if (this.pendingPlays >= MAX_PENDING_PLAYS) return;
    this.pendingPlays++;
    const generation = this.generation, originX = this.originX, originZ = this.originZ;
    // Late sword hits/steps are worse than a dropped one: pending sounds expire and are
    // invalidated on pause, death, restart, or dispose. Decoding may still fill the LRU.
    void this.buffer(asset).then(buffer => {
      if (!buffer || generation !== this.generation || !this.audible || performance.now() - now > 240) return;
      if (p) p = { x: p.x - (this.originX - originX), y: p.y, z: p.z - (this.originZ - originZ) };
      this.startEffect(asset!, buffer, p, gain);
    }).finally(() => { this.pendingPlays = Math.max(0, this.pendingPlays - 1); });
  }

  private emitCaption(group: string, position?: AudioPosition): void {
    if (!this.onCaption) return;
    const exact = assets.get(group);
    const canonical = exact?.kind === 'effect' ? exact.group : group;
    const text = SOUND_CAPTIONS[canonical];
    if (!text) return;
    if (position) {
      const p = point(position), listener = this.listenerPosition;
      if (Math.hypot(p.x - listener.x, p.y - listener.y, p.z - listener.z) > 75) return;
    }
    const now = performance.now(), age = now - this.lastCaptionAt;
    const priority = CONTACT_CAPTIONS.has(canonical) ? 2 : /release|impact/.test(canonical) ? 1 : 0;
    // Contact can immediately supersede a close release/charge. Once shown, protect
    // that outcome for one second from low-priority cues. No deferred caption queue.
    if (text === this.lastCaptionText && age < 1600) return;
    if (this.lastCaptionPriority === 2 && priority < 2 && age < 1000) return;
    if (age < 350 && priority <= this.lastCaptionPriority) return;
    this.lastCaptionAt = now;
    this.lastCaptionText = text;
    this.lastCaptionPriority = priority;
    try { this.onCaption(text); }
    catch (error) { console.warn('Sound caption handler failed', error); }
  }

  cue(name: 'rescue' | 'title'): void {
    if (this.disposed) return;
    this.cueName = name;
    this.deathUntil = 0;
    this.currentMusic = '';
    this.applyMix(true);
  }

  pause(): void {
    if (this.disposed) return;
    this.paused = true;
    this.invalidateMediaWork();
    this.lastCaptionText = ''; this.lastCaptionPriority = 0; this.lastCaptionAt = -Infinity;
    this.stopEffects();
    this.resetReverb();
    for (const slot of [...this.musicSlots, ...this.ambientSlots]) {
      slot.element.pause();
      if (slot.retireTimer !== undefined) { window.clearTimeout(slot.retireTimer); slot.retireTimer = undefined; }
      if (slot.target === 0) this.releaseSlot(slot);
    }
    if (this.ctx && this.ctx.state !== 'closed') void this.ctx.suspend().catch(() => undefined);
  }

  resume(): void {
    // An in-flight unlock owns both context and slots; finishEntry may safely call
    // resume immediately without starting another context/primer/transition path.
    if (this.disposed || !this.started || !this.ctx || this.activation || this.retryRequired || this.playbackReady) return;
    void this.beginPlayback();
  }

  /** Clears transients, reverb tails, cues and streaming players, but keeps the small LRU. */
  clear(): void {
    if (this.disposed) return;
    this.invalidateMediaWork();
    this.stopEffects();
    for (const slot of [...this.musicSlots, ...this.ambientSlots]) this.releaseSlot(slot);
    this.resetReverb();
    this.cueName = undefined;
    this.currentMusic = '';
    this.currentAmbience = '';
    this.zoneKey = '';
    this.deathUntil = 0;
    this.accentIn = 18;
    this.cooldown.clear();
    this.lastCaptionText = ''; this.lastCaptionPriority = 0; this.lastCaptionAt = -Infinity;
    this.state = { ...DEFAULT_STATE };
  }

  /** dx/dz are the world-origin displacement to SUBTRACT, in metres. */
  rebase(dx: number, dz: number): void {
    dx = finite(dx); dz = finite(dz);
    this.originX += dx; this.originZ += dz;
    this.listenerPosition.x -= dx; this.listenerPosition.z -= dz;
    // Rebasing is an instantaneous coordinate change, not audible movement.
    if (this.ctx) {
      const l = this.ctx.listener, p = this.listenerPosition, t = this.ctx.currentTime;
      if (l.positionX) {
        l.positionX.cancelScheduledValues(t); l.positionZ.cancelScheduledValues(t);
        l.positionX.setValueAtTime(p.x, t); l.positionZ.setValueAtTime(p.z, t);
      } else l.setPosition(p.x, p.y, p.z);
    }
    for (const voice of this.voices) {
      if (!voice.position || !voice.panner || !this.ctx) continue;
      voice.position.x -= dx; voice.position.z -= dz;
      voice.panner.positionX.setValueAtTime(voice.position.x, this.ctx.currentTime);
      voice.panner.positionZ.setValueAtTime(voice.position.z, this.ctx.currentTime);
    }
  }

  dispose(): void {
    if (this.disposed) return;
    this.clear();
    this.disposed = true;
    this.started = false;
    this.onCaption = undefined;
    for (const name of ['pointerdown', 'click', 'touchend', 'keydown']) document.removeEventListener(name, this.gesture, true);
    document.removeEventListener('visibilitychange', this.visibility);
    for (const slot of [...this.musicSlots, ...this.ambientSlots]) {
      slot.element.onended = null;
      slot.element.onerror = null;
      slot.element.removeAttribute('src');
      slot.element.load();
      slot.source.disconnect(); slot.gain.disconnect();
    }
    this.musicSlots = []; this.ambientSlots = [];
    this.cache.clear(); this.cacheBytes = 0; this.impulse = undefined; this.reverbImpulse = undefined;
    this.decoder = undefined;
    for (const task of this.decodeQueue.splice(0)) task.resolve(undefined);
    for (const node of [this.masterBus, this.musicBus, this.ambienceBus, this.effectsBus,
      this.musicFilter, this.convolver, this.wetBus, this.limiter, this.ceiling]) node?.disconnect();
    if (this.ctx && this.ctx.state !== 'closed') void this.ctx.close().catch(() => undefined);
  }

  /** Confirmed media transport readiness, not a claim of audible output or listening. */
  get playbackReady(): boolean {
    if (!this.started || this.paused || this.disposed || this.retryRequired || this.activation || this.ctx?.state !== 'running') return false;
    const live = (slots: MediaSlot[]) => slots.some(slot => !!slot.asset && slot.playing && !slot.element.paused && !slot.element.ended && !slot.element.error);
    return live(this.musicSlots) && live(this.ambientSlots);
  }

  /** Context/primer activation OR a bounded media-start handoff is still pending. */
  get activationPending(): boolean {
    return !this.disposed && (!!this.activation || [...this.musicSlots, ...this.ambientSlots].some(slot => !!slot.playPromise));
  }

  private invalidateMediaWork(): void {
    this.mediaEpoch++;
    const owner = this.activation;
    this.activation = undefined;
    this.unlocking = undefined;
    owner?.cancel();
    for (const slot of [...this.musicSlots, ...this.ambientSlots]) {
      slot.serial++;
      slot.cancelPlay?.();
      slot.cancelPlay = undefined;
      slot.playPromise = undefined;
      slot.playing = false;
    }
  }

  private failPlayback(message: string, epoch: number): void {
    if (this.disposed || epoch !== this.mediaEpoch) return;
    this.retryRequired = true;
    this.playbackError = message;
    this.lastError = message;
    this.invalidateMediaWork();
    this.stopEffects();
    for (const slot of [...this.musicSlots, ...this.ambientSlots]) this.releaseSlot(slot);
    // Preserve requested cue/world state, but never latch a failed track as current.
    // Only an explicit gesture retry clears the fault; mix() cannot retry per frame.
    this.currentMusic = ''; this.currentAmbience = ''; this.zoneKey = '';
  }

  /** Numeric resource diagnostics for the parent's debug panel; no listening assertion. */
  get diagnostics(): Readonly<Record<string, number | boolean | string>> {
    return { activated: this.started, paused: this.paused, format: this.format,
      playbackReady: this.playbackReady, activationPending: this.activationPending, retryRequired: this.retryRequired,
      context: this.ctx?.state ?? 'not-created', cachedSounds: this.cache.size,
      decodedBytes: this.cacheBytes + (this.impulse ? this.impulse.length * this.impulse.numberOfChannels * 4 : 0)
        + (this.reverbImpulse && this.reverbImpulse !== this.impulse ? this.reverbImpulse.length * this.reverbImpulse.numberOfChannels * 4 : 0),
      reverbSampleRate: this.reverbImpulse?.sampleRate ?? 0,
      liveEffects: this.voices.size, decoding: this.decoding, queuedDecodes: this.decodeQueue.length,
      streamingElements: this.musicSlots.length + this.ambientSlots.length,
      compressedBytes: AUDIO_COMPRESSED_BYTES, music: this.currentMusic, ambience: this.currentAmbience,
      lastError: this.lastError };
  }

  private get audible(): boolean { return this.started && !this.paused && !this.disposed && !this.retryRequired && this.ctx?.state === 'running'; }
  private url(asset: AudioAsset): string { return asset[this.format]; }

  private createGraph(): void {
    if (this.ctx) return;
    const Constructor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Constructor) throw new Error('Web Audio is unavailable');
    const ctx = this.ctx = new Constructor({ latencyHint: 'interactive' });
    this.masterBus = ctx.createGain();
    this.musicBus = ctx.createGain();
    this.ambienceBus = ctx.createGain();
    this.effectsBus = ctx.createGain();
    this.musicFilter = ctx.createBiquadFilter(); this.musicFilter.type = 'lowpass'; this.musicFilter.frequency.value = 10500;
    this.limiter = ctx.createDynamicsCompressor();
    this.limiter.threshold.value = -3; this.limiter.knee.value = 3; this.limiter.ratio.value = 16;
    this.limiter.attack.value = .004; this.limiter.release.value = .16;
    // A conservative final ceiling catches coincident transients during compressor
    // attack. Below -2 dBFS this curve is exactly linear, not constant saturation.
    this.ceiling = ctx.createWaveShaper();
    const curve = new Float32Array(4097);
    for (let i = 0; i < curve.length; i++) {
      const x = i / (curve.length - 1) * 2 - 1, a = Math.abs(x);
      curve[i] = a <= .78 ? x : Math.sign(x) * (.78 + .16 * Math.tanh((a - .78) / .16));
    }
    this.ceiling.curve = curve;
    this.masterBus.connect(this.limiter).connect(this.ceiling).connect(ctx.destination);
    this.musicBus.connect(this.musicFilter).connect(this.masterBus);
    this.ambienceBus.connect(this.masterBus);
    this.effectsBus.connect(this.masterBus);
    this.wetBus = ctx.createGain(); this.wetBus.gain.value = .035; this.wetBus.connect(this.masterBus);
    this.resetReverb();
    const makeSlot = (bus: GainNode): MediaSlot => {
      const element = document.createElement('audio');
      element.preload = 'none'; element.setAttribute('playsinline', '');
      const source = ctx.createMediaElementSource(element), gain = ctx.createGain();
      gain.gain.value = 0; source.connect(gain).connect(bus);
      return { element, source, gain, target: 0, serial: 0, playing: false };
    };
    this.musicSlots = [makeSlot(this.musicBus), makeSlot(this.musicBus)];
    this.ambientSlots = [makeSlot(this.ambienceBus), makeSlot(this.ambienceBus)];
    this.applyLevels();
    this.listener(this.listenerPosition, this.listenerForward);
  }

  private ramp(param: AudioParam | undefined, value: number, time = .08): void {
    if (!param || !this.ctx) return;
    const now = this.ctx.currentTime;
    param.cancelScheduledValues(now);
    param.setTargetAtTime(value, now, Math.max(.008, time));
  }

  private applyLevels(): void {
    // Asset mastering leaves headroom; fixed bus trims protect a busy combat mix.
    this.ramp(this.masterBus?.gain, this.levels.master);
    this.ramp(this.musicBus?.gain, this.levels.music * .65);
    this.ramp(this.ambienceBus?.gain, this.levels.ambience * .44);
    this.ramp(this.effectsBus?.gain, this.levels.effects * .78);
  }

  private applyMix(force = false, owner?: Activation): void {
    if (!this.audible || !this.ctx || this.ctx.currentTime < this.deathUntil || (this.activation && this.activation !== owner)) return;
    const s = this.state, forest = /forest|wood|pine|conifer|bog|marsh/i.test(s.biome);
    const music = this.cueName ?? (s.royal ? 'royal' : s.threat ? 'duel' : forest || s.blood || s.inside ? 'forest' : 'meadow');
    const ambience = s.inside ? 'castle' : s.night || s.blood ? 'night' : forest ? 'forest' : /snow|mountain|upland|heath|wind|ash/i.test(s.biome) ? 'wind' : 'meadow';
    if (force || this.currentMusic !== music) {
      if (this.transition(this.musicSlots, assets.get(`music_${music}`)!, music === 'rescue' ? 1.3 : 2.5) && !this.retryRequired) this.currentMusic = music;
    }
    const ambientWanted = this.cueName === 'title' ? 'wind' : ambience;
    if (force || this.currentAmbience !== ambientWanted) {
      if (this.transition(this.ambientSlots, assets.get(`ambient_${ambientWanted}`)!, 3.1) && !this.retryRequired) this.currentAmbience = ambientWanted;
    }
    const key = `${s.inside}/${s.blood}/${s.night}/${s.threat}/${forest}`;
    if (force || key !== this.zoneKey) {
      this.zoneKey = key;
      // Bloodmoon is the forest composition under a veiled filter and night field,
      // not an additional repeated-note generator. The effects room stays deliberately light.
      this.ramp(this.musicFilter?.frequency, s.blood && !s.threat ? 3200 : s.night ? 7300 : 10500, 1.1);
      this.ramp(this.wetBus?.gain, s.inside ? .14 : forest ? .065 : .025, .6);
    }
  }

  private transition(slots: MediaSlot[], asset: AudioAsset, seconds: number): boolean {
    if (!asset || !this.ctx || slots.length !== 2 || this.retryRequired) return false;
    // Do not abort an owned play() when mix/cue changes rapidly. State is already
    // saved by the caller; the settled start will apply the latest request once.
    if (slots.some(slot => !!slot.playPromise)) return false;
    const same = slots.find(slot => slot.asset?.id === asset.id && slot.target > 0);
    if (same) {
      this.ramp(same.gain.gain, 1, .12);
      if (!same.playing || same.element.paused) void this.safePlay(same);
      return true;
    }
    const incoming = slots.find(slot => !slot.asset) ?? slots.reduce((a, b) => a.target < b.target ? a : b);
    this.releaseSlot(incoming);
    incoming.asset = asset; incoming.target = 1;
    const serial = ++incoming.serial, epoch = this.mediaEpoch;
    incoming.element.src = this.url(asset); incoming.element.loop = asset.loop; incoming.element.preload = 'auto';
    incoming.gain.gain.cancelScheduledValues(this.ctx.currentTime);
    incoming.gain.gain.setValueAtTime(0, this.ctx.currentTime);
    void this.safePlay(incoming).then(ok => {
      if (!ok || this.disposed || this.paused || epoch !== this.mediaEpoch || incoming.serial !== serial || !this.ctx) return;
      // Hold the outgoing stream until the incoming element actually starts. A
      // slow decoder cannot fade the old music to silence while a play is pending.
      const now = this.ctx.currentTime;
      incoming.gain.gain.cancelScheduledValues(now);
      incoming.gain.gain.setValueAtTime(incoming.gain.gain.value, now);
      incoming.gain.gain.linearRampToValueAtTime(1, now + seconds);
      for (const outgoing of slots) {
        if (outgoing === incoming || !outgoing.asset) continue;
        outgoing.target = 0;
        if (outgoing.retireTimer !== undefined) window.clearTimeout(outgoing.retireTimer);
        const gain = outgoing.gain.gain, oldSerial = outgoing.serial;
        const current = gain.value;
        gain.cancelScheduledValues(now); gain.setValueAtTime(current, now); gain.linearRampToValueAtTime(0, now + seconds);
        outgoing.retireTimer = window.setTimeout(() => {
          if (epoch !== this.mediaEpoch || oldSerial !== outgoing.serial) return;
          outgoing.retireTimer = undefined;
          if (outgoing.target === 0) this.releaseSlot(outgoing);
        }, seconds * 1000 + 80);
      }
      if (!this.activation) this.applyMix();
    });
    return true;
  }

  private safePlay(slot: MediaSlot): Promise<boolean> {
    if (slot.playPromise) return slot.playPromise;
    if (this.disposed || this.paused || this.retryRequired) return Promise.resolve(false);
    if (slot.playing && !slot.element.paused && !slot.element.ended && !slot.element.error) return Promise.resolve(true);
    const serial = slot.serial, epoch = this.mediaEpoch, asset = slot.asset, codec = this.format;
    const current = () => !this.disposed && !this.paused && epoch === this.mediaEpoch && serial === slot.serial;
    slot.element.onerror = () => {
      if (!current() || !slot.element.error) return;
      const code = slot.element.error.code;
      const fallback = codec === 'ogg' && (code === 3 || code === 4);
      if (fallback) this.format = 'mp3';
      // Changing src here would race a pending play; select fallback for the next
      // explicit retry instead, after the failure owner has cancelled all starts.
      this.failPlayback(`Local ${asset?.id ?? 'activation primer'} playback failed (${code}). ${fallback ? 'MP3 fallback selected. ' : ''}Click Enable sound to retry.`, epoch);
    };
    slot.element.onended = () => {
      if (!current() || !slot.playing || !slot.element.ended || slot.asset !== asset) return;
      slot.playing = false;
      if (asset?.id === 'music_rescue' && this.cueName === 'rescue') {
        this.cueName = undefined; this.currentMusic = ''; this.applyMix(true);
      } else if (asset?.loop) this.failPlayback('A local audio loop stopped. Click Enable sound to retry.', epoch);
    };
    let cancel!: () => void;
    const cancelled = new Promise<boolean>(resolve => { cancel = () => resolve(false); });
    const timer = window.setTimeout(() => {
      if (current()) this.failPlayback(`Local ${asset?.id ?? 'activation primer'} playback timed out. Click Enable sound to retry.`, epoch);
    }, PLAY_TIMEOUT_MS);
    slot.cancelPlay = () => { window.clearTimeout(timer); cancel(); };
    let raw: Promise<void>;
    try { raw = Promise.resolve(slot.element.play()); }
    catch (error) { raw = Promise.reject(error); }
    const observed = raw.then(() => {
      if (!current()) return false;
      slot.playing = !slot.element.paused && !slot.element.ended;
      if (!slot.playing) this.failPlayback('Audio playback did not start. Click Enable sound to retry.', epoch);
      return slot.playing;
    }, error => {
      if (!current()) return false;
      const reason = (error as { name?: string })?.name;
      if (reason === 'NotSupportedError' && codec === 'ogg') this.format = 'mp3';
      this.failPlayback(reason === 'AbortError'
        ? 'Audio playback was interrupted. Click Enable sound to retry.'
        : `Audio playback failed: ${String(error).slice(0, 100)}. Click Enable sound to retry.`, epoch);
      return false;
    });
    const promise = Promise.race([observed, cancelled]).then(ok => {
      window.clearTimeout(timer);
      if (slot.playPromise === promise) { slot.playPromise = undefined; slot.cancelPlay = undefined; }
      return ok;
    });
    slot.playPromise = promise;
    return promise;
  }

  private releaseSlot(slot: MediaSlot): void {
    if (slot.retireTimer !== undefined) { window.clearTimeout(slot.retireTimer); slot.retireTimer = undefined; }
    slot.serial++;
    slot.cancelPlay?.(); slot.cancelPlay = undefined; slot.playPromise = undefined; slot.playing = false;
    slot.element.onended = null; slot.element.onerror = null; slot.element.pause();
    slot.asset = undefined; slot.target = 0;
    if (this.ctx) { slot.gain.gain.cancelScheduledValues(this.ctx.currentTime); slot.gain.gain.setValueAtTime(0, this.ctx.currentTime); }
    // Keep the same gesture-approved element/source, but release its media decoder.
    slot.element.removeAttribute('src'); slot.element.load();
  }

  private startEffect(asset: AudioAsset, buffer: AudioBuffer, position: AudioPosition | undefined, level: number): void {
    const ctx = this.ctx;
    if (!ctx || !this.audible || this.voices.size >= MAX_VOICES) return;
    const source = ctx.createBufferSource(), gain = ctx.createGain();
    source.buffer = buffer;
    source.playbackRate.value = asset.group.startsWith('step_') ? .97 + Math.random() * .06 : 1;
    const start = ctx.currentTime + .003, duration = buffer.duration / source.playbackRate.value;
    gain.gain.value = 0;
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(clamp(level, 0, 2), start + .003);
    gain.gain.setValueAtTime(clamp(level, 0, 2), start + Math.max(.004, duration - .012));
    gain.gain.linearRampToValueAtTime(0, start + duration);
    const voice: Voice = { source, gain, position, ended: false };
    source.connect(gain);
    if (position) {
      const panner = ctx.createPanner(); voice.panner = panner;
      panner.panningModel = 'HRTF'; panner.distanceModel = 'inverse';
      panner.refDistance = 2.1; panner.maxDistance = 75; panner.rolloffFactor = 1.12;
      panner.coneInnerAngle = 360; panner.coneOuterAngle = 360;
      panner.positionX.value = position.x; panner.positionY.value = position.y; panner.positionZ.value = position.z;
      gain.connect(panner).connect(this.effectsBus!);
    } else gain.connect(this.effectsBus!);
    source.onended = () => this.disconnectVoice(voice);
    this.voices.add(voice);
    source.start(start);
    // Every one-shot is explicitly finite even when a browser omits an ended event.
    source.stop(start + duration + .04);
  }

  private disconnectVoice(voice: Voice): void {
    if (voice.ended) return;
    voice.ended = true; voice.source.onended = null;
    voice.source.disconnect(); voice.gain.disconnect(); voice.panner?.disconnect();
    this.voices.delete(voice);
  }

  private stopEffects(): void {
    this.generation++;
    for (const voice of [...this.voices]) {
      try { voice.source.stop(); } catch { /* Already ended; disconnect regardless. */ }
      this.disconnectVoice(voice);
    }
  }

  private resetReverb(): void {
    if (!this.ctx || !this.effectsBus || !this.wetBus) return;
    if (this.convolver) {
      try { this.effectsBus.disconnect(this.convolver); } catch { /* Graph may be closing. */ }
      this.convolver.disconnect(); this.convolver.buffer = null;
    }
    const convolver = this.convolver = this.ctx.createConvolver();
    convolver.normalize = true;
    if (this.reverbImpulse?.sampleRate === this.ctx.sampleRate) convolver.buffer = this.reverbImpulse;
    this.effectsBus.connect(convolver).connect(this.wetBus);
    this.prepareImpulse();
  }

  private prepareImpulse(): void {
    const ctx = this.ctx, original = this.impulse;
    if (!ctx || !original || this.disposed) return;
    if (original.sampleRate === ctx.sampleRate) this.reverbImpulse = original;
    if (this.reverbImpulse?.sampleRate === ctx.sampleRate) {
      if (this.convolver) this.convolver.buffer = this.reverbImpulse;
      return;
    }
    if (this.resamplingImpulse) return;
    // Unlike AudioBufferSourceNode, ConvolverNode cannot convert sample rates. Decode
    // remains at 24k for the bounded SFX cache; only this tiny IR gets a live-rate copy.
    // A silent offline resampler is used, not a live source or an oscillator.
    this.resamplingImpulse = (async () => {
      try {
        const Offline = window.OfflineAudioContext ?? (window as unknown as { webkitOfflineAudioContext?: typeof OfflineAudioContext }).webkitOfflineAudioContext;
        if (!Offline) throw new Error('Impulse resampling is unavailable');
        const offline = new Offline(original.numberOfChannels, Math.ceil(original.duration * ctx.sampleRate), ctx.sampleRate);
        const source = offline.createBufferSource();
        source.buffer = original; source.connect(offline.destination); source.start();
        const resampled = await offline.startRendering();
        source.disconnect();
        if (this.disposed || this.ctx !== ctx) return;
        this.reverbImpulse = resampled;
        if (this.convolver && resampled.sampleRate === ctx.sampleRate) this.convolver.buffer = resampled;
      } catch (error) {
        // Dry effects must remain playable if optional room resampling is unavailable.
        this.lastError = `Room reverb unavailable: ${String(error).slice(0, 110)}`;
      } finally {
        this.resamplingImpulse = undefined;
      }
    })();
  }

  private buffer(asset: AudioAsset): Promise<AudioBuffer | undefined> {
    if (this.disposed || asset.kind === 'music' || asset.kind === 'ambience' || asset.kind === 'silence') return Promise.resolve(undefined);
    if (asset.kind === 'ir' && this.impulse) return Promise.resolve(this.impulse);
    const cached = this.cache.get(asset.id);
    if (cached) { cached.used = ++this.clock; return Promise.resolve(cached.buffer); }
    const pending = this.pendingDecodes.get(asset.id);
    if (pending) return pending;
    if (this.decodeQueue.length >= MAX_DECODE_QUEUE) return Promise.resolve(undefined);
    const promise = new Promise<AudioBuffer | undefined>(resolve => {
      this.decodeQueue.push({ asset, resolve });
    });
    this.pendingDecodes.set(asset.id, promise);
    this.pumpDecoder();
    return promise;
  }

  private pumpDecoder(): void {
    if (this.disposed) return;
    while (this.decoding < DECODE_CONCURRENCY && this.decodeQueue.length) {
      const task = this.decodeQueue.shift()!;
      this.decoding++;
      void this.decode(task.asset).then(buffer => {
        if (buffer && !this.disposed) {
          if (task.asset.kind === 'ir') {
            this.impulse = buffer;
            this.prepareImpulse();
          } else this.remember(task.asset.id, buffer);
        }
        task.resolve(this.disposed ? undefined : buffer);
      }).catch(error => {
        this.lastError = `Cannot decode local sound ${task.asset.id}: ${String(error).slice(0, 110)}. Reload the App.`;
        task.resolve(undefined);
      }).finally(() => {
        this.decoding--; this.pendingDecodes.delete(task.asset.id); this.pumpDecoder();
      });
    }
  }

  private async decode(asset: AudioAsset): Promise<AudioBuffer> {
    if (!this.decoder) {
      const Offline = window.OfflineAudioContext ?? (window as unknown as { webkitOfflineAudioContext?: typeof OfflineAudioContext }).webkitOfflineAudioContext;
      if (!Offline) throw new Error('Offline audio decoding is unavailable');
      this.decoder = new Offline(1, 1, SAMPLE_RATE);
    }
    const decoder = this.decoder;
    let problem: unknown;
    for (const format of [this.format, this.format === 'ogg' ? 'mp3' : 'ogg'] as const) {
      try {
        const url = asset[format];
        let bytes: ArrayBuffer;
        if (url.startsWith('data:')) {
          // Embedded production audio needs no connect-src permission or HTTP fetch.
          const comma = url.indexOf(','), header = url.slice(0, comma);
          if (comma < 0) throw new Error('Malformed embedded audio');
          const binary = /;base64$/i.test(header) ? atob(url.slice(comma + 1)) : decodeURIComponent(url.slice(comma + 1));
          const array = new Uint8Array(binary.length);
          for (let i = 0; i < binary.length; i++) array[i] = binary.charCodeAt(i);
          bytes = array.buffer;
        } else {
          const local = new URL(url, document.baseURI);
          if (local.origin !== location.origin) throw new Error('Audio assets must be local');
          const response = await fetch(local, { credentials: 'omit' });
          if (!response.ok) throw new Error(`HTTP ${response.status} for ${asset.id}`);
          bytes = await response.arrayBuffer();
        }
        return await decoder.decodeAudioData(bytes);
      } catch (error) { problem = error; }
    }
    throw problem;
  }

  private remember(id: string, buffer: AudioBuffer): void {
    const bytes = buffer.length * buffer.numberOfChannels * 4;
    if (bytes > CACHE_BYTES) return;
    while (this.cache.size >= CACHE_COUNT || this.cacheBytes + bytes > CACHE_BYTES) {
      let oldest = '', time = Infinity;
      for (const [key, entry] of this.cache) if (entry.used < time) { oldest = key; time = entry.used; }
      if (!oldest) break;
      this.cacheBytes -= this.cache.get(oldest)!.bytes; this.cache.delete(oldest);
    }
    this.cache.set(id, { buffer, bytes, used: ++this.clock }); this.cacheBytes += bytes;
  }
}
