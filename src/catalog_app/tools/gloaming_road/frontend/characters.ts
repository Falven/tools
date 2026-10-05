import * as THREE from 'three';
import { GLTFLoader, type GLTF } from 'three/addons/loaders/GLTFLoader.js';
import swordsmanUrl from './assets/characters/swordsman.glb?url';
import eliteUrl from './assets/characters/elite.glb?url';
import shieldUrl from './assets/characters/shield.glb?url';
import archerUrl from './assets/characters/archer.glb?url';
import mageUrl from './assets/characters/mage.glb?url';
import princessUrl from './assets/characters/princess.glb?url';
import viewmodelUrl from './assets/characters/viewmodel.glb?url';

/** Metres, Y up, +Z forward. Every created root starts at the origin. */
export type CharacterKind =
  | 'swordsman' | 'elite' | 'shield' | 'archer' | 'mage' | 'princess' | 'viewmodel';

export interface CharacterView {
  readonly root: THREE.Group;
  readonly mixer: THREE.AnimationMixer;
  /** Play a clip in presentation time. Repeated calls for the active clip do not restart it. */
  play(name: string, fade?: number): void;
  /** Advance presentation playback. Does not advance a pose() sampled by gameplay. */
  update(dt: number): void;
  /** Authoritative absolute clip time in seconds. One-shots clamp; ambient loops wrap. */
  pose(name: string, time: number): void;
  /** Fresh, independent WORLD-space vectors, safe to retain for swept-hit comparisons. */
  weaponPoints(): { base: THREE.Vector3; tip: THREE.Vector3 };
  /** Release this actor's mixer/hierarchy only, never shared mesh/material/texture data. */
  dispose(): void;
}

export interface CharacterLibrary {
  readonly clips: Readonly<Record<CharacterKind, readonly string[]>>;
  create(kind: CharacterKind): CharacterView;
  /** Dispose after all actors are no longer needed; also retires any remaining actors. */
  dispose(): void;
}

/** Camera-child mount for ~70° vertical FOV / 16:9. Parents may adjust to their camera. */
export const VIEWMODEL_MOUNT = Object.freeze({
  position: [0.44, -0.30, -0.64] as const,
  rotation: [0, Math.PI, 0] as const,
  recommendedNear: 0.035,
});

/** Gameplay contact windows, in authored clip seconds (not normalized mixer phase). */
export const CHARACTER_ATTACK_TIMING = Object.freeze({
  light: Object.freeze({ duration: 0.70, contactStart: 0.24, contactEnd: 0.38 }),
  heavy: Object.freeze({ duration: 1.25, contactStart: 0.52, contactEnd: 0.70 }),
});

const URLS: Readonly<Record<CharacterKind, string>> = {
  swordsman: swordsmanUrl, elite: eliteUrl, shield: shieldUrl, archer: archerUrl,
  mage: mageUrl, princess: princessUrl, viewmodel: viewmodelUrl,
};
const KINDS = Object.keys(URLS) as CharacterKind[];
const CORE_CLIPS = [
  'idle', 'walk', 'guard-high', 'guard-left', 'guard-right', 'guard-low',
  'light-high', 'light-left', 'light-right', 'light-low',
  'heavy-high', 'heavy-left', 'heavy-right', 'heavy-low',
  'feint', 'dodge', 'roll', 'block', 'parry', 'stagger', 'hit', 'death',
] as const;
const EXTRA_CLIPS: Partial<Record<CharacterKind, string[]>> = {
  archer: ['draw', 'release'], mage: ['charge', 'cast'], princess: ['talk'],
};
const isLoop = (name: string): boolean =>
  name === 'idle' || name === 'walk' || name === 'talk' || name.startsWith('guard-');

type Template = { scene: THREE.Group; animations: readonly THREE.AnimationClip[] };

function textureSet(material: THREE.Material): Set<THREE.Texture> {
  const textures = new Set<THREE.Texture>();
  // Includes the one shared roughness/metalness map only once.
  for (const value of Object.values(material)) {
    if (value instanceof THREE.Texture) textures.add(value);
  }
  return textures;
}

function checkTemplate(gltf: GLTF, kind: CharacterKind): void {
  if (!gltf.scene.getObjectByName('weapon-base') || !gltf.scene.getObjectByName('weapon-tip')) {
    throw new Error(`Character ${kind} is missing its authored weapon attachments.`);
  }
  const clips = new Map(gltf.animations.map(clip => [clip.name, clip]));
  for (const name of [...CORE_CLIPS, ...(EXTRA_CLIPS[kind] ?? [])]) {
    const clip = clips.get(name);
    if (!clip || clip.duration <= 0 || clip.tracks.length < 4) {
      throw new Error(`Character ${kind} has no complete animation named "${name}".`);
    }
  }
  let meshes = 0;
  gltf.scene.traverse(object => {
    if (object instanceof THREE.Mesh) {
      ++meshes;
      if (!(object.material instanceof THREE.MeshStandardMaterial) || !object.material.map) {
        throw new Error(`Character ${kind} is missing its original textured material.`);
      }
    }
  });
  if (!meshes) throw new Error(`Character ${kind} contains no renderable authored meshes.`);
}

/**
 * Load the actual, local GLB exports with GLTFLoader. No primitive fallback and no
 * remote asset fetch. Vite's ?url imports are compatible with the app's data-URL build.
 * GLBs use rigid named joints, so ordinary recursive clones correctly share their
 * immutable BufferGeometry/Material/Texture objects without skeleton cloning.
 */
export async function loadCharacters(
  progress?: (label: string) => void,
): Promise<CharacterLibrary> {
  const loader = new GLTFLoader();
  loader.register(parser => {
    // ImageBitmapLoader performs fetch(blob:...), also blocked by connect-src
    // 'none'. TextureLoader uses Image.src and the host's img-src blob: allowance.
    // This is per-parser, not a global createImageBitmap/browser modification.
    parser.textureLoader = new THREE.TextureLoader(parser.options.manager)
      .setCrossOrigin(parser.options.crossOrigin);
    return { name: 'GLOAMING_LOCAL_IMAGE_LOADER' };
  });
  const templates = new Map<CharacterKind, Template>();
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();
  const textures = new Set<THREE.Texture>();
  const actors = new Set<CharacterView>();
  let canonicalMaterial: THREE.MeshStandardMaterial | undefined;
  let libraryDisposed = false;

  const disposeAssets = (): void => {
    for (const geometry of geometries) geometry.dispose();
    for (const material of materials) material.dispose();
    for (const texture of textures) texture.dispose();
    geometries.clear();
    materials.clear();
    textures.clear();
    templates.clear();
  };

  try {
    for (const kind of KINDS) {
      progress?.(`Loading ${kind === 'viewmodel' ? 'first-person gauntlets' : kind}…`);
      let gltf: GLTF;
      try {
        const url = URLS[kind];
        if (url.startsWith('data:')) {
          // The self-contained MCP App uses connect-src 'none'. Parsing decoded
          // bytes avoids a fetch(data:...) which is still governed by connect-src.
          const comma = url.indexOf(',');
          if (comma < 0 || !url.slice(0, comma).endsWith(';base64')) {
            throw new Error(`Character ${kind} has an unsupported embedded GLB URL.`);
          }
          const binary = atob(url.slice(comma + 1));
          const bytes = new Uint8Array(binary.length);
          for (let index = 0; index < binary.length; index++) bytes[index] = binary.charCodeAt(index);
          gltf = await loader.parseAsync(bytes.buffer, '');
        } else {
          gltf = await loader.loadAsync(url);
        }
      } catch (error) {
        throw new Error(`Unable to load the original ${kind} GLB.`, { cause: error });
      }
      // Register resources before validation so failures are cleanly released.
      gltf.scene.traverse(object => {
        if (!(object instanceof THREE.Mesh)) return;
        geometries.add(object.geometry);
        const list = Array.isArray(object.material) ? object.material : [object.material];
        for (const material of list) {
          materials.add(material);
          for (const texture of textureSet(material)) textures.add(texture);
        }
      });
      checkTemplate(gltf, kind);
      gltf.scene.traverse(object => {
        if (!(object instanceof THREE.Mesh)) return;
        const material = object.material as THREE.MeshStandardMaterial;
        if (!canonicalMaterial) {
          canonicalMaterial = material;
          canonicalMaterial.name = 'Gloaming Road / original shared character atlas';
          for (const texture of textureSet(material)) {
            texture.magFilter = THREE.NearestFilter;
            texture.minFilter = THREE.LinearMipmapLinearFilter;
            texture.generateMipmaps = true;
            texture.anisotropy = 1;
            texture.needsUpdate = true;
          }
        }
        // Every export uses exactly the same material/atlases. Deduplicate them
        // once at import, before any actor exists; never mutate them per actor.
        object.material = canonicalMaterial;
        object.castShadow = kind !== 'viewmodel';
        object.receiveShadow = kind !== 'viewmodel';
        object.frustumCulled = kind !== 'viewmodel';
        if (!object.geometry.boundingSphere) object.geometry.computeBoundingSphere();
      });
      templates.set(kind, { scene: gltf.scene, animations: gltf.animations });
    }
    // Release duplicate decoded maps/materials which no longer belong to any mesh.
    const retainedTextures = textureSet(canonicalMaterial!);
    for (const material of materials) {
      if (material !== canonicalMaterial) {
        material.dispose();
        materials.delete(material);
      }
    }
    for (const texture of textures) {
      if (!retainedTextures.has(texture)) {
        texture.dispose();
        textures.delete(texture);
      }
    }
  } catch (error) {
    disposeAssets();
    throw error;
  }

  const clipNames = Object.freeze(Object.fromEntries(KINDS.map(kind => [
    kind, Object.freeze(templates.get(kind)!.animations.map(clip => clip.name)),
  ]))) as Readonly<Record<CharacterKind, readonly string[]>>;

  const create = (kind: CharacterKind): CharacterView => {
    if (libraryDisposed) throw new Error('The character library has already been disposed.');
    const template = templates.get(kind);
    if (!template) throw new Error(`Unknown character kind: ${String(kind)}`);
    const model = template.scene.clone(true);
    model.animations = [...template.animations];
    const root = new THREE.Group();
    root.name = `gloaming-character-${kind}`;
    root.userData.characterKind = kind;
    root.add(model);
    const baseAttachment = model.getObjectByName('weapon-base')!;
    const tipAttachment = model.getObjectByName('weapon-tip')!;
    const mixer = new THREE.AnimationMixer(model);
    const actions = new Map<string, THREE.AnimationAction>();
    const retireAt = new Map<THREE.AnimationAction, number>();
    for (const clip of template.animations) actions.set(clip.name, mixer.clipAction(clip));
    let current: THREE.AnimationAction | undefined;
    let mode: 'play' | 'pose' = 'play';
    let disposed = false;

    const actionFor = (name: string): THREE.AnimationAction => {
      if (disposed) throw new Error(`Character ${kind} has already been disposed.`);
      const action = actions.get(name);
      if (!action) throw new Error(`Character ${kind} has no clip named "${name}".`);
      return action;
    };

    const view: CharacterView = {
      root, mixer,
      play(name, fade = 0.10) {
        const next = actionFor(name);
        if (!Number.isFinite(fade) || fade < 0) throw new RangeError('Animation fade must be finite and nonnegative.');
        if (current === next && mode === 'play') return;
        const previous = current;
        const wasPosed = mode === 'pose';
        mode = 'play';
        current = next;
        retireAt.delete(next);
        next.stopFading().stopWarping().reset();
        next.enabled = true;
        next.paused = false;
        next.setEffectiveTimeScale(1).setEffectiveWeight(1);
        next.setLoop(isLoop(name) ? THREE.LoopRepeat : THREE.LoopOnce, isLoop(name) ? Infinity : 1);
        next.clampWhenFinished = !isLoop(name);
        next.play();
        if (previous && previous !== next && fade > 0 && !wasPosed) {
          next.crossFadeFrom(previous, fade, false);
          retireAt.set(previous, mixer.time + fade);
        } else {
          for (const action of actions.values()) if (action !== next) action.stop();
          retireAt.clear();
        }
        mixer.update(0);
      },
      update(dt) {
        if (disposed) return;
        if (!Number.isFinite(dt) || dt < 0) throw new RangeError('Animation delta must be finite and nonnegative.');
        if (mode === 'play') {
          mixer.update(dt);
          for (const [action, end] of retireAt) {
            if (mixer.time >= end) {
              if (action !== current) action.stop();
              retireAt.delete(action);
            }
          }
        }
      },
      pose(name, time) {
        const action = actionFor(name);
        if (!Number.isFinite(time)) throw new RangeError('Authoritative animation time must be finite.');
        if (current !== action || mode !== 'pose') {
          mixer.stopAllAction();
          retireAt.clear();
          action.stopFading().stopWarping().reset();
          action.enabled = true;
          action.setEffectiveWeight(1).setEffectiveTimeScale(1);
          action.setLoop(THREE.LoopOnce, 1);
          action.clampWhenFinished = true;
          action.play();
          current = action;
          mode = 'pose';
        }
        const duration = action.getClip().duration;
        action.time = isLoop(name)
          ? THREE.MathUtils.euclideanModulo(Math.max(0, time), duration)
          : THREE.MathUtils.clamp(time, 0, duration);
        action.paused = true;
        action.enabled = true;
        // Zero delta applies PropertyBindings at this exact authoritative time.
        // It does not integrate dt, cross-fade combat contacts, or advance a paused action.
        mixer.update(0);
        root.updateWorldMatrix(true, true);
      },
      weaponPoints() {
        if (disposed) throw new Error(`Character ${kind} has already been disposed.`);
        root.updateWorldMatrix(true, true);
        return {
          base: new THREE.Vector3().setFromMatrixPosition(baseAttachment.matrixWorld),
          tip: new THREE.Vector3().setFromMatrixPosition(tipAttachment.matrixWorld),
        };
      },
      dispose() {
        if (disposed) return;
        disposed = true;
        mixer.stopAllAction();
        mixer.uncacheRoot(model);
        actions.clear();
        retireAt.clear();
        root.removeFromParent();
        root.clear();
        actors.delete(view);
        // Mesh data belongs to the library. A dead/streamed-out actor must not
        // invalidate another actor still using its geometry, atlas or material.
      },
    };
    actors.add(view);
    view.play('idle', 0);
    return view;
  };

  progress?.('Characters ready');
  return {
    clips: clipNames,
    create,
    dispose() {
      if (libraryDisposed) return;
      libraryDisposed = true;
      for (const actor of [...actors]) actor.dispose();
      disposeAssets();
    },
  };
}
