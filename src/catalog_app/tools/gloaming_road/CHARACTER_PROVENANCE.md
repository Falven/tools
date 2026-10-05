# The Gloaming Road — original character art

## Authorship and sources

These are original project assets, authored as contoured geometry, custom bevelled plates, folded cloth, shaped faces, individually modelled fingers, weapons and articulated glTF nodes. No downloaded character mesh, stock humanoid primitive, source-game data, photographic texture or external asset URL is used.

The refreshed Steam [knight reference](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/4214710/4331eeae821e64fcffe6a9cd45ef12505b92578e/ss_4331eeae821e64fcffe6a9cd45ef12505b92578e.1920x1080.jpg) and [mage reference](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/4214710/d7a8331afd7a401fcb4bd88d7e9a4d55d411153d/ss_d7a8331afd7a401fcb4bd88d7e9a4d55d411153d.1920x1080.jpg) were viewed for the requested retro medieval direction only. Their pixels were not incorporated into the textures or exports. Those reference screenshots are not distributed as runtime assets.

The editable [character workshop](<src/catalog_app/tools/gloaming_road/art/characters.py>) generates the geometry, glTF binary containers, texture painting and animation keys deterministically with Python, NumPy and Pillow. No Blender is required. All GLBs embed their three original 512 × 512 PNG atlases:

- [Color atlas](<src/catalog_app/tools/gloaming_road/frontend/assets/characters/characters-atlas.png>): rubbed pale steel, metal edging, mail links, leather, oxblood cloth, mustard, muted gilt, skin, hair, ivory, rose, wood, black, blue-grey robe, stone and thread.
- [Surface atlas](<src/catalog_app/tools/gloaming_road/frontend/assets/characters/characters-surface.png>): authored roughness and metalness, with low metalness for skin/cloth/wood.
- [Emission atlas](<src/catalog_app/tools/gloaming_road/frontend/assets/characters/characters-emission.png>): restrained glow on small stone details only.

Texture magnification is nearest; minification uses linear mipmaps. Faceted vertex normals, narrow metal seams, raised flutes and surface mottling are intentional, rather than an untextured low-poly placeholder treatment.

## Shipped inventory

| Kind / GLB | Triangles | Articulated meshes | Clips | Appearance |
| --- | ---: | ---: | ---: | --- |
| [swordsman](<src/catalog_app/tools/gloaming_road/frontend/assets/characters/swordsman.glb>) | 7,464 | 21 | 22 | Pale-steel ridged breastplate, overlapping shoulder lames, mail joints, fauld, tassets, knee wings, sabatons, narrow visor and red cloth |
| [elite](<src/catalog_app/tools/gloaming_road/frontend/assets/characters/elite.glb>) | 8,116 | 22 | 22 | Restrained gilt construction details, red mantle, edged tabard and decorated arming sword |
| [shield](<src/catalog_app/tools/gloaming_road/frontend/assets/characters/shield.glb>) | 8,174 | 22 | 22 | Armoured swordsman with a broad, solid rectangular red-painted wooden shield, metal rim/boss and rear straps |
| [archer](<src/catalog_app/tools/gloaming_road/frontend/assets/characters/archer.glb>) | 5,007 | 22 | 24 | Burgundy quilted cloth, mustard shoulders, pointed open helmet, bow, changing string, nocked arrow and feathered quiver arrows |
| [mage](<src/catalog_app/tools/gloaming_road/frontend/assets/characters/mage.glb>) | 6,071 | 22 | 24 | Open hood, pale simplified aged face, beard, trimmed pleated robe, red stole and carved staff with caged stone |
| [princess](<src/catalog_app/tools/gloaming_road/frontend/assets/characters/princess.glb>) | 6,385 | 21 | 23 | Open circlet, face, parted/braided hair, ivory and muted-rose fitted medieval gown, long folded skirt; no combat equipment |
| [viewmodel](<src/catalog_app/tools/gloaming_road/frontend/assets/characters/viewmodel.glb>) | 2,986 | 7 | 22 | Two contoured vambraces, mirrored gauntlets and curled fingers gripping a long, narrow, straight diamond-section sword |

The [machine-readable export manifest](<src/catalog_app/tools/gloaming_road/frontend/assets/characters/characters-manifest.json>) records sizes, triangle counts and exact float32 clip durations. All seven GLBs together are approximately 8.2 MB before transport compression. The material atlases are deduplicated once at import in the runtime library.

[Character lineup](<src/catalog_app/tools/gloaming_road/art/characters-lineup.png>) and [first-person view](<src/catalog_app/tools/gloaming_road/art/characters-viewmodel.png>) are captures of the separate art turntable, **not screenshots of the integrated game**.

## Units, rig and attachments

- Metres, Y up, local forward +Z. Feet in the neutral construction are at Y = 0. Human proportions target 1.8 m; helmet/crown points extend slightly above the head.
- The public actor root starts at zero position/rotation and unit scale. No root transform is keyed.
- Rigid articulated hierarchy: `character-root → hips → spine → chest → neck → head`; each upper arm owns its forearm and hand; each thigh owns its shin and foot. Tassets, tabard, cape and four robe/skirt panels have independent named nodes.
- Rotations are authored quaternion tracks. Hips have a **vertical-only** bob/crouch/fall track; no animation owns X/Z locomotion. Walk and roll are in place.
- Sword and staff are children of `hand-r`; the bow is a child of `hand-l`; shield is a child of `hand-l`. `weapon-base` and `weapon-tip` are explicit GLB attachment nodes under `weapon`.
- Swordsman/elite/shield blade markers span local sword Y = .083 to 1.062 m. Viewmodel blade spans .083 to 1.104 m. Marker positions describe the actual visible blade, excluding hilt/pommel.
- Archer markers describe the stable bow/shot axis; the separate `arrow` node moves back with the nock and is hidden during release. They are not a melee sword segment. Mage markers span the staff. Princess markers coincide at her hand and do not imply a weapon.

## Runtime interface

Implemented in [characters.ts](<src/catalog_app/tools/gloaming_road/frontend/characters.ts>):

```ts
export async function loadCharacters(
  progress?: (label: string) => void
): Promise<CharacterLibrary>;

type CharacterKind =
  | 'swordsman' | 'elite' | 'shield' | 'archer'
  | 'mage' | 'princess' | 'viewmodel';

interface CharacterLibrary {
  readonly clips: Readonly<Record<CharacterKind, readonly string[]>>;
  create(kind: CharacterKind): CharacterView;
  dispose(): void;
}

interface CharacterView {
  readonly root: THREE.Group;
  readonly mixer: THREE.AnimationMixer;
  play(name: string, fade?: number): void;
  update(dt: number): void;
  pose(name: string, time: number): void;
  weaponPoints(): { base: THREE.Vector3; tip: THREE.Vector3 };
  dispose(): void;
}
```

`play` uses `AnimationMixer`, defaults to .10 s cross-fade and does not repeatedly restart an already playing clip. Locomotion, idle, guards and talk loop; attacks/reactions/draw/charge are clamped one-shots. To deliberately restart the same one-shot in presentation mode, first `pose(name, 0)` and then `play(name, 0)`.

For combat, use `pose(name, authoritativeSeconds)` each simulation update. It stops presentation blends and evaluates the animation at the requested absolute clip time with `mixer.update(0)`. One-shots clamp; ambient loops wrap. `update(dt)` does not advance a manually sampled pose. Do not call `mixer.update` separately when using this phase-authoritative path.

`weaponPoints()` updates ancestor/descendant matrices and returns **fresh world-space vectors**, suitable for retaining previous-frame endpoints. Returned positions are in the actual parent scene's world coordinates. If the viewmodel lives in a separate identity-camera scene, those coordinates are camera-relative to the game; the parent must apply the real game camera's world matrix before collision tests. A model directly parented to the real game camera already returns game-world positions and must not be transformed twice.

Every actor owns its node transforms, actions and mixer, but shares immutable geometry, material and texture data with other clones. Actor `dispose()` releases only its mixer and hierarchy. Library `dispose()` retires all remaining actors and disposes GPU data exactly at library lifetime end. Do not tint/mutate shared materials per actor.

Missing files, failed decoding, incomplete rigs, absent textures and unknown clip names throw errors. There is no primitive/placeholder fallback.

### Self-contained MCP loading

Imports use `?url`. For embedded base64 URLs the library decodes bytes directly and calls the real `GLTFLoader.parseAsync`; it does not `fetch(data:...)`. A per-parser loader plugin selects `THREE.TextureLoader`, making embedded PNGs load through `Image.src` rather than `ImageBitmapLoader`'s `fetch(blob:...)`. This works with `connect-src 'none'` and ordinary `img-src data: blob:` permissions. Non-data URLs retain `loadAsync` for local Vite development. No global browser API is patched.

## Clip mapping and authored action

Every kind has the common 22 clips below. Ranged/dialogue additions are kind-specific, and unknown names do not silently map to idle.

| Clip name(s) | Duration, seconds | Authored motion |
| --- | ---: | --- |
| `idle` | 3.20 | Breathing chest, shoulders, wrists and small head/weight changes; equipment-appropriate resting hands |
| `walk` | .90 | Alternating thigh swing, knee flexion, foot recovery, hip bob, counter-rotation and cloth motion |
| `guard-high`, `guard-left`, `guard-right`, `guard-low` | 1.30 | Four genuinely different arm/weapon/torso guards with subtle held-pose movement |
| `light-high`, `light-left`, `light-right`, `light-low` | .70 | Sector-specific anticipation, extended active sweep and recovery; contact .24–.38 |
| `heavy-high`, `heavy-left`, `heavy-right`, `heavy-low` | 1.25 | Deeper/longer windup, torso/leg commitment, active sweep and longer recovery; contact .52–.70 |
| `feint` | .50 | Starts an overhead commitment, interrupts into a side guard and recovers |
| `dodge` | .64 | Crouch, body lean, knee flexion and protected arms; parent supplies lateral movement |
| `roll` | .84 | Tucked in-place full turn through explicit intermediate rotation keys; parent supplies travel |
| `block` | .56 | Raised guard, recoil and guarded recovery |
| `parry` | .45 | Side interception and shorter recoil/recovery |
| `hit` | .45 | Short chest/head/arm impact response |
| `stagger` | .88 | Larger body recoil, leg compression and slower recovery |
| `death` | 1.60 | Stumble/collapse, vertical hip lowering, backward fall and held ground pose |
| Archer: `draw` | 1.10 | Raise bow, bring finger pads/nock toward cheek, pull the string and arrow back; hold drawn |
| Archer: `release` | .65 | Finger/arm recoil, string snap and temporary arrow disappearance; parent launches projectile |
| Mage: `charge` | 1.45 | Raise casting hand, brace staff, lean back and pulse the gathering gesture |
| Mage: `cast` | .90 | Forward palm/staff/body commitment, extension at .24 and recovery |
| Princess: `talk` | 3.10 | Alternating listening nod, explanatory right-hand gesture and emphasis, returning to clasped hands |

Sector names are relative to the actor's authored +Z-forward space. Opposing-actor left/right mapping belongs to gameplay; it should be mirrored when interpreting incoming directions. Slow telegraphs may stretch only the windup, then sample the original active interval. Do not stretch the whole clip and inadvertently move the contact window.

The viewmodel has dedicated first-person arm choreography rather than reusing third-person arm positions. Its overhead preparation stays forward of the camera, and contact sweeps converge toward the reticle.

## Recommended first-person mount and measured reach

The exported `VIEWMODEL_MOUNT` is the single recommended mount for approximately 70° vertical FOV / 16:9:

```ts
position: [0.44, -0.30, -0.64]
rotation: [0, Math.PI, 0]
recommendedNear: 0.035
```

The idle sword sits near the right fifth of the frame; the forearms rise from the lower edge. Parents may adapt presentation to aspect/FOV, but changing position/scale changes real collision reach.

Actual `GLTFLoader` + `AnimationMixer` sampling at 201 times per attack found all viewmodel blade base/tip positions at least **.670 m forward** of the camera. Maximum full 3D camera-origin endpoint reach was **1.823 m**, with maximum horizontal XZ reach **1.801 m**. Thus the sampled visual arcs remain under 1.85 m without a fake extended collision ray.

At the middle of contact (.31 s light / .61 s heavy), measured camera-frame tip positions were:

| Sector | X | Y | Z |
| --- | ---: | ---: | ---: |
| high | .134 | .070 | -1.705 |
| left | .082 | -.146 | -1.763 |
| right | .152 | -.056 | -1.758 |
| low | .123 | -.273 | -1.799 |

### Third-person sweep verification

Swordsman and elite were sampled at 241 times **inside each active window**, measuring the entire base-to-tip blade segment against a capsule axis at local `(X=0, Z=1.65, Y=.5…1.7)`, rather than checking only a tip at a single instant.

| Attack | High axis clearance | Left | Right | Low |
| --- | ---: | ---: | ---: | ---: |
| Light | .149 m | .147 m | .151 m | .195 m |
| Heavy | .144 m | .147 m | .151 m | .194 m |

All eight attacks enter a capsule radius of at least .196 m; the parent's .31 m player capsule has margin. Closest blade crossings lie around Y = 1.11–1.32 m, Z = 1.46–1.506 m and X near zero (low: -.044 m). Root locomotion is not required for this intersection.

## Reproduction and validation

From the repository working directory:

```sh
.venv/bin/python src/catalog_app/tools/gloaming_road/art/characters.py
node src/catalog_app/tools/gloaming_road/art/characters-preview.mjs
```

The second command bundles the [turntable source](<src/catalog_app/tools/gloaming_road/art/characters-preview.ts>) with its [local builder](<src/catalog_app/tools/gloaming_road/art/characters-preview.mjs>) into a temporary self-contained HTML file. It does not start a server or change the game. The art preview deliberately uses `connect-src 'none'` to exercise embedded loading.

Observed checks:

- Seven textured GLBs loaded and rendered through the real Three 0.180 GLTFLoader, including under restrictive CSP; the browser recorded zero `fetch` resource entries.
- Every one of 159 clips has nonconstant authored tracks. 795 sampled mixer poses produced finite attachment positions.
- Repeating an authoritative pose after death and `update(10)` gave exactly zero endpoint drift.
- Nested translation/rotation checks confirmed world-space attachment output.
- Actor clones share geometry/materials; all kinds share the atlas material. Disposing one actor emitted no shared geometry disposal and left its clone usable.
- Unknown clip names throw instead of substituting idle.
- Consecutive generator runs produced byte-identical GLB/PNG outputs.
- The character library was typechecked independently with strict TypeScript using the installed Three/Vite types.
- No new test suite, unrelated edits, publication or git commit was made by the character artist.

## Deliberate limits

- Rigid-articulated retro models, not continuously skinned film-resolution characters. Plate/cloth intersections can occur in extreme blends; no runtime cloth simulation, ragdoll, foot-ground IK or terrain-conforming hem is included.
- Faces have shaped features but no blendshape speech/lip-sync. `talk` is a body/hand/head performance. Fingers are modelled as individual shapes within each rigid hand, not independently animated finger joints.
- Death/roll are authored presentation; gameplay remains responsible for collision, locomotion and corpse placement on slopes.
- Archer projectile spawning and mage particles/fire are gameplay responsibilities. The assets animate the equipment and gestures only.
- Shared combat clips exist on mage/princess for API completeness, but intended behaviour uses charge/cast or talk, not princess melee.
- Reach measurements assume the documented unscaled root/mount and standing capsule. They do not claim an integrated game duel, audio quality, production frame rate or publication was tested by the character artist.
