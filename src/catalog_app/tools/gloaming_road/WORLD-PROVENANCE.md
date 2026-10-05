# The Gloaming Road — world and environment provenance

## Original authorship

The environment meshes, texture painting, terrain functions, population rules, and streaming code were authored specifically for this project. No game assets, photographs, image crops, downloaded textures, pretrained texture outputs, or third-party scenery meshes are incorporated.

Two supplied reference images were inspected as visual evidence only: a luminous meadow of irregular pink flower spires and a forest with textured, layered trees, mossy boulders, and warm understory accents. The images are **not** runtime assets and no pixels were sampled or copied from them.

The editable original source is [scenery.py](<src/catalog_app/tools/gloaming_road/art/scenery.py>). Run from this tool's directory:

```sh
python art/scenery.py
```

The generator uses Python's standard library and Pillow. Its fixed local art seed is `0x61042026`. It paints stems, alternating veined leaves, individual petal whorls, small meadow flowers, grass blades, fern pinnae, leaf clusters, conifer needles, and warm amber shrubs directly onto transparent pixel atlases. Geometry is independently authored from tapered branch sections, intersecting bent canopy shells, hanging frond whorls, jagged stone profiles, and broken masonry. Nothing in the generator reads the supplied visual references.

## Runtime art

| Deliverable | Content |
|---|---|
| [Scenery GLB](<src/catalog_app/tools/gloaming_road/frontend/assets/scenery/gloaming-scenery.glb>) | glTF 2.0, 11 named mesh parts, 1,468 source triangles, embedded original diffuse textures. Oak, rowan, fir, mossy boulder, fallen log, low broken wayside masonry, and a candle/rest stone circle. |
| [Foliage atlas](<src/catalog_app/tools/gloaming_road/frontend/assets/scenery/foliage-atlas.png>) | 1,024 × 1,024 RGBA; sixteen 256-pixel tiles. Three pink/lilac spire variants; white, lilac, yellow, and blue flowers; grasses; fern; amber shrub; oak and rowan leaf clusters; fir needles; bracken; clover; candle flame. |
| [Ground atlas](<src/catalog_app/tools/gloaming_road/frontend/assets/scenery/ground-atlas.png>) | 512 × 512 RGB; four 256-pixel paintings: meadow grass, compacted loam, fractured lichen stone, and forest leaf litter. |
| [Scenery atlas](<src/catalog_app/tools/gloaming_road/frontend/assets/scenery/scenery-atlas.png>) | 512 × 512 RGB; four 256-pixel paintings: bark, moss/lichen stone, weathered masonry, and cut wood. |
| [Art manifest](<src/catalog_app/tools/gloaming_road/frontend/assets/scenery/scenery-manifest.json>) | Deterministic mesh names, triangle counts, texture dimensions, and foliage tile legend. |

The seven authored prototypes are not substituted with runtime cones, spheres, or stock tree assets. Trees have tapered forked trunks and layered textured canopy lobes; firs use separate hanging needle fans. Runtime batching combines all solid prototypes into one chunk mesh and all leafy crowns into another. Meadow/understory cutouts use a single per-chunk instanced atlas mesh. The candle flame is emissive-looking art, not an added light. The parent owns all actual scene lighting, sky, and fog.

Textures are sRGB with nearest magnification, nearest-mipmap-linear minification, and mipmaps. Cutout cells have gutters. Terrain uses linear vertex colours and shader mixing of grass, loam, stone, and litter, with rotated secondary texture sampling and low-frequency patch modulation to break repeating tiles. Ground-path appearance is sampled from the same deterministic path field as planting exclusions.

## Deterministic world

[terrain.ts](<src/catalog_app/tools/gloaming_road/frontend/terrain.ts>) exports `createTerrain(seed: string): TerrainAPI` without changing the parent's [world contract](<src/catalog_app/tools/gloaming_road/frontend/world-contract.ts>). Simplex-noise 4.0.3 is the installed noise dependency; each named terrain channel owns an independently seeded PRNG. Chunk request order and floating-origin changes cannot consume world-generation randomness.

- Chunks are 64 metres, with a 2-metre grid and 2,048 ground triangles each. X/Z vertex coordinates start at zero locally; Y remains absolute terrain height. Normals sample absolute world coordinates on both sides of every edge.
- There is exactly one castle feature, 820–1,230 metres from the spawn with a seed-derived bearing and yaw zero. The keep faces +Z. Local `z=+40` is an exterior approach waypoint, not the door: the [authored gate plane](<src/catalog_app/tools/gloaming_road/frontend/assets/castle/layout.json#L565-L602>) is at local `z=+33.05`. The subsequent355 run actually crossed the gate/courtyard/stairs, opened the hall and completed the royal-room mission; its scope is recorded below and in the [mission ledger](<src/catalog_app/tools/gloaming_road/VERIFICATION.md#completed-candidate355-castle-mission-and-recovery>).
- The castle floor is completely flat through local `±41 × ±50` metres, enclosing the requested `±36 × ±45` footprint. Its apron blends over another 150 metres with a smoothstep grade. Plants/props are excluded within `±48 × ±58`; tree crown overhangs receive an additional margin.
- Spawn is at global `(0,0)`. The first 24 metres are naturally safe and graded; trees, rocks, logs, ruins, and enemies begin farther away. The initial stone/candle circle is decorative geometry with a walkable entrance gap; its associated rest-site record supplies the parent's functional E-rest interaction.
- The starting clearing is meadow through 66 metres, rich in pink flower spires. A guaranteed woodland pocket lies roughly northwest, around 80–190 metres away. Other woodland/conifer/upland regions follow coherent broad moisture, elevation, and climate fields rather than chunk-sized biome choices.
- Broad scalloped mountain ridges are part of the real traversable height function, not scenery walls. Winding trails branch across the global field; a trace visits both spawn and castle regions without requiring the player to follow it.
- Solid prop metadata covers oak/rowan/fir trunks, boulders, fallen logs, and ruined stones using positive `radius` and `height`. Plants have no collider metadata. Props and encounters always retain **global** positions.
- Sparse encounter opportunities occur in approximately 32% of chunks, occasionally as pairs, with stable seeded IDs; none start within 32 metres of spawn. The parent owns activation within 80 metres, enemy life cycles, and persistence.
- Rest sites are stable seeded records, including `seed:rest:spawn`. Wayside ruins are low stone fragments, never additional castles.

## Streaming integration and bounded resources

[World](<src/catalog_app/tools/gloaming_road/frontend/world.ts>) implements the exact `StreamWorld` interface and constructor `new World(seed, callbacks, quality?)`. [The worker](<src/catalog_app/tools/gloaming_road/frontend/world-worker.ts>) imports only deterministic terrain-generation code. [Scenery rendering](<src/catalog_app/tools/gloaming_road/frontend/scenery.ts>) owns the original asset cache and chunk batching.

The parent build must implement the virtual `?worker-source` import of [world-worker.ts](<src/catalog_app/tools/gloaming_road/frontend/world-worker.ts>) as a self-contained classic-worker JavaScript string. World creates a Blob worker and sends `init`, `chunk`, and `far` messages. A host that forbids Blob workers falls back to one CPU build per animation frame; `stats().fallback` makes that mode visible rather than claiming worker operation.

Bundled data-URL GLBs are decoded locally and passed to `GLTFLoader.parseAsync`, not fetched. A loader plugin uses `TextureLoader` / `Image.src` for embedded image buffers instead of the default `ImageBitmapLoader.fetch`, so scenery does not need a remote `connect-src` permission. Development file URLs retain normal `loadAsync` loading. The embedding host still needs to permit its local data/Blob image sources.

Hard bounds:

- **25** wanted/visible near chunks (5 × 5).
- **49** maximum retained chunk entries (radius-three unload hysteresis). Retained chunks outside the visual 5 × 5 are hidden.
- **2** maximum worker requests in flight, with at most **3** in-flight-plus-ready results. Obsolete chunk results are discarded rather than uploaded.
- **1** ready geometry result adopted per animation frame, independent of how often gameplay calls `update`.
- **1** moving far-terrain mesh, generated from the same global sampler with 8/16/32/64-metre LOD rings extending 1,792 metres from its current anchor. Its opaque sampled ridges can occlude the distant castle. It moves with global streaming, not with a finite spawn backdrop.
- Up to 4,320 candidate plant placements per chunk before exclusions. Balanced quality budgets 3,600 centre / 3,312 inner / 504 outer instances before biome weighting; low quality preserves a 2,500-instance centre rather than a barren clearing. Spires range roughly 1.32–1.73 metres with wide, heavily leafed bases. Wooded chunks need fewer understory cards because their crowns already fill the view.
- The foliage allocator subtracts visible ground and solid/crown triangles from a near-world budget (235k balanced, 200k low, 250k high), then proportionally thins instances to the remaining allowance. These are allocation targets, not a guarantee that static geometry alone cannot exceed a target. There is no protected minimum-flora reserve in the frozen source: if static geometry exhausted the target, the allocator could reduce foliage to zero. This does not pretend the parent's castle/actors or the 36k-triangle far terrain cost zero: `stats()` reports near and far triangles separately. Typical near rendering uses four world draw calls per chunk plus the single far mesh. Approximately 200 total draw calls remains an integration target, not an unmeasured performance claim.

`prepare(x,z)` resolves only after assets, the uploaded 3 × 3 neighbourhood and the first covering far terrain exist. It drives its own RAF upload scheduling, so it also works before the gameplay render loop begins. `onLoad(data)` runs **after main-thread geometry/material creation and scene insertion**; it is not a claim that an unrendered WebGL command has already completed on the GPU. The parent can create trimesh colliders at that point and retain only the nearest 3 × 3 collider set.

`readyAt(x,z)` means the containing uploaded terrain and its immediate 1.25-metre movement boundary guard exist. It does not unnecessarily demand all 25 visual chunks. Both this method and `update` take global coordinates. The parent remains responsible for checking collider availability before authoritative movement.

`setOrigin(x,z)` adjusts chunk/far render transforms without mutating any global feature, prop, rest, encounter or vertex-height metadata. Unloading/disposal releases private geometry and instance buffers, calls `onUnload`, terminates the worker, cancels upload scheduling and clears collections. The immutable, single-instance authored geometry/texture cache is intentionally shared between restarted worlds and is not accidentally disposed by a chunk.

## Validation scope

### Initial authoring checks

The supplied visual references and all three generated atlases were inspected directly. Final deterministic art generation completed successfully: 11 named mesh parts, 1,468 source triangles, and an 821,164-byte GLB. A strict TypeScript check of the four owned world modules completed with exit code zero after the density, ridge and CSP-loader revisions. No new test suite was created and no commit was made by the world author.

Parent-supplied production screenshots were also inspected. Early renderer feedback identified a reserved GLSL identifier (`patch`); it was renamed to `terrainPatch`, and the corrected screenshot showed the ground rendering. Subsequent screenshot feedback drove denser, taller flower drifts, narrower irregular flowering verges, paler granite, and sharper genuinely sampled ridge crests. The updated production meadow image visibly showed those improvements.

Those initial observations were visual/compilation checks, not frame-rate certification. The integrated journey below adds actual movement, origin-crossing and rest-persistence evidence; it does not turn every source/resource check into a played acceptance result. Parent-reported headless SwiftShader profiling remained slow, so hardware performance targets are not claimed as achieved here.

### Integrated on-foot journey and profile continuity — 5 October 2026 UTC

An automation launch/profile-mode change lost the earlier temporary browser test profile. This was not a demonstrated failure of the game's save transaction. The parent deliberately chose a fresh `silver-thistle` world through the actual UI in a persistent profile; earlier played fights and recovery history remain in the [verification ledger](<src/catalog_app/tools/gloaming_road/VERIFICATION.md>) and were not injected into this new journey.

The world author then travelled from that fresh spawn, starting at clock378.4333, to the deterministic conifer hearth `silver-thistle:rest:-5:12`. The route was **source-planned, not blind discovery**: shipped `createTerrain/buildChunk` had identified the target, and permitted read-only save inspection supplied global position checks. Only normal shipped UI and real keyboard/mouse input were used in this renewed handoff; there were no source/driver edits, teleports, direct database writes, or clock/player-position/health/mission-flag injections.

- The straight-segment sum between checked stops was approximately **1.01km**, not a continuous odometer. The route threaded meadow, woodland and conifer terrain, skirted trees and enemy homes, and included a western detour and subsequent correction. Brief ordinary sprint/walk legs left player health at100 throughout the verified route; no attacks/kills, deaths, Wake Again or royal combat occurred on this fresh leg.
- Normal travel crossed multiple64m chunk boundaries and the384m floating-origin ranges. Saved global stops included approximately `(-129.10,303.38)`, `(-199.89,456.47)`, `(-273.74,683.49)` and the hearth. Global movement and target identity remained consistent across those origin-crossing legs. No origin was forced or private rebase counter probed; no player terrain gap or persistent stall was visible at the inspected stops. This is not a per-frame seam, worker/CSP, memory-bound or hardware-performance certification.
- One large post-resume mouse turn did not register, extending travel west to approximately `(-370.96,624.40)`. Waiting for ordinary DOM pointer-lock confirmation before the next real mouse input produced the corrected turn. This was handled without editing the driver or game.
- Travel job336 was killed when its sandbox carrier disconnected. The browser survived. Normal key-up input explicitly released W/Shift/J/K, then Escape produced a verified pause before travel continued; no browser restart, reload or profile change was used to recover this renewed run.
- At the visible [E Rest prompt](<artifacts/travel-20-hearth-rest-prompt.png>), E produced [the rest confirmation](<artifacts/travel-21-hearth-rested.png>): “You rest. This quiet place will remember you.” The visible “Rest chimes” caption is not an audition claim. Escape then produced the [paused hearth state](<artifacts/travel-22-hearth-paused.png>).

At completion of that travel leg, the read-only save had clock `709.283333333032`, player global `(x,y,z)=(-271.80492401123047,67.47865356445313,801.4307250976562)`, yaw `1.234200000000001`, pitch `-0.48400000000000004`, and health/stamina `100/100`. Recovery was exactly `{id:"silver-thistle:rest:-5:12",x:-273.7259088009596,z:801.0333528928459}`. All three royal IDs were then undefeated, all doors closed and the princess unrescued. This travel-stage observation verified recovery **registration** only; the later355 mission actually exercised two post-death Wake Again returns to this same hearth, preserving royal/door progress, as recorded below.

### Subsequent naturally elapsed night

The same fresh journey subsequently remained ordinarily unpaused at the safe hearth. A read-only save at clock978.4 contained an actual event0 mage; the pre-castle night-stage Pause save reached clock1422.7 with100HP, the same recovery and no mission progress. No clock, player position, health or flags were injected to obtain that night. Later castle progress and naturally elapsed dawn are recorded separately below.

The inspected [natural blood-night hearth capture](<src/catalog_app/tools/gloaming_road/review/natural-blood-night.png>) shows a red/magenta clouded, star-speckled sky, dark conifers, dim ground, a nearby faceted rock, hearth flames, the E Rest prompt and the held sword. It does **not** show a moon-disc close-up or a caster fight. The night-state/event observation is distinct from the image's limited visual evidence; an engaged surviving mage through subsequent dawn remains unverified.

### Candidate355 residency follow-up

The approximately1.01km journey and first natural-night observations used standalone build306. Candidate355 later passed strict TypeScript/build and was actually reloaded/continued in359; it remained unchanged through the completed castle mission and final save410 described below. The latest verified live activation remains `95d2745094ed517139e3bc96912fd82eb95f67fb` at 06:13:55 UTC; the recorded actual live main-tool/resource call belongs to `92dfca7`. Post-mission candidate415 passed strict TypeScript/build (24.68MiB HTML, 12.03MiB gzip). Its normal reload/Continue and rescue-save preservation were actually checked in418, but publication/activation remains pending; that focused check is not a whole-mission415 replay.

Low NPC Y values in saved recent records were reported during travel, not witnessed as visible falls. The parent's source follow-up makes retained actors dormant outside collision residency, checks readiness before subsequent movement, restores low legacy NPC Y to actual support height without resetting health, rehydrates recent ordinary actors by their remembered positions, and retains castle collision while occupied. The 3×3 physics budget is preserved rather than expanding to the render/retention radii.

A real CPU Rapier **component-only** check reported the same Y `0.005095376968` before/after 300 simulated steps without the actor's collision tile, Y `-0.005670354366` after reattachment, and nine collision tiles. A below-ground `-52` cache was repaired to support height `0` while preserving16HP. The first fixture failed only on a missing mock `audio.clear`; corrected run347 passed. This is not a browser/gameplay retake.

The original new-night save also showed two mage capsules approximately0.44m apart at the same anchor. Candidate355 adds at most nine local ground/solid/body-clearance attempts while preserving no-front/no-close spawning. CPU Rapier component360 recorded1.100000→1.100002m separation after120 steps, skipped a solid-blocked alternative and kept expired event history from bypassing no-front spawning. In the actual355 save at clock1604.6, the two mage IDs both retained64HP and were approximately0.84m apart horizontally—saved-position evidence, not a visually witnessed caster fight. Normal reload/Continue, browser audio start/pause/resume, keyboard fallback and spaced pointer re-capture were also observed; none establishes listening quality. See the [focused candidate ledger](<src/catalog_app/tools/gloaming_road/VERIFICATION.md#candidate355-follow-up-and-focused-browser-checks>).

### Additional isolated real-Rapier clearance evidence

The component check reported by `c7e3b63d` passed with exit0 and touched no files, browser or real saves. It used a true3×3 set of distinct translated collision tiles, with ray hits at Y3, rather than nine references to one floor.

- **Fully blocked blood addition:** real stone blocked all nine candidate positions. Exactly nine real clearance calls occurred, with no actor views or capsules created. Counts stayed at11 colliders, nine chunks and one body.
- **Remembered blood actor:** current position `(32,-8,28)` was eligible at4m; its unchanged home `(1024,-1024)` was about1,448m away and was not incorrectly used for eligibility. One clearance preceded one view/capsule creation. Support repair changed Y−8→3 while preserving identity, home,16HP and event7. Capsule feet were at3.04, with zero other overlaps. Counts changed11→12 colliders and one→two bodies, with nine chunks unchanged.

These establish isolated clearance ordering, support repair and resource counts. They do not prove a visually witnessed blood-mage fight, every residency boundary or a quantitative long-run leak bound.

### Completed castle mission, two recoveries and natural dawn on355

The continuing run used the same unchanged355 page loaded in359:640×400 low detail/SwiftShader, pause-assisted, source-planned, native keyboard/mouse/UI input and read-only IndexedDB inspection. No state injection, direct storage writes, HTTP reload or source changes occurred during the mission run.

- The exterior gate opened by clock1665.85; courtyard/stair traversal and the hall door were observed by1677.60. Royal0 was defeated at1691.6833, leaving35HP. A real hall death at1703.6167 was followed by ordinary **Wake Again** at the registered conifer hearth at1704.2833 with100HP/100stamina; royal0's defeat and both open doors survived. The return reached the stairs at1770.5667.
- Royal1 was defeated at1792.0666666653806 at `(-390.9658021927,76.7434698486,838.3970794678)`, leaving64HP/60stamina. The nearer warden was drawn to the threshold while the far warden stayed back in the inspected frames; this is not a complete coordination/combat matrix.
- Input job396 was carrier-killed mid-attempt. Cleanup397 exited0 and found an actual second death at clock1807.9666666653661,0HP, with royal0/1 still defeated. The full intended input sequence and missing capture34 are not claimed. A second ordinary **Wake Again** in398 returned100/100 at clock1808.6333333320322 and `(-273.7253570557,67.6753393555,801.0328025818)`, preserving defeated royals and both open doors. This was the second of two deaths in this persistent mission run, not a claim that the carrier caused an in-game crash.
- The archived [dawn hearth](<src/catalog_app/tools/gloaming_road/review/dawn-hearth.png>) shows lavender clouds and green conifers after naturally elapsed clock1800. It closes the missing natural-dawn atmosphere view, **not** ordinary non-blood-night coverage or an engaged mage surviving across dawn.
- All three royals were defeated in405 at clock1892.8999999986222, `(-390.6097974777,76.7445379639,825.2247505188)`, with35HP/58stamina. Normal E Talk in407 opened the first beat; Continue advanced to “You came. I’m safe now. Thank you.” A second Continue acknowledged that final beat and returned to play/capture with all three defeats and `rescued:true` saved. The announcement was “Elowen is safe. The world remains open to you.”
- Actual post-rescue movement was followed by **in-App Save/Quit → Title → Continue**, which restored the stored clock/position/mission,35HP and pointer capture without a displayed error. More normal movement produced final save410 at clock1919.116666665265 and `(-389.21464109420776,76.74033416748047,816.4669189453125)`,35HP/100stamina, all three royal IDs in both guard/defeated lists, rescue true, gate/hall open and the same hearth recovery. The run ended normally paused, pointer released, no displayed error, all keys released and all input jobs collected.

The [mission ledger and exact final save](<src/catalog_app/tools/gloaming_road/VERIFICATION.md#completed-candidate355-castle-mission-and-recovery>) and [mission gallery](<src/catalog_app/tools/gloaming_road/review/COMPARISON.md#f--completed-mission-and-post-rescue-continuation-candidate355>) preserve the distinction between a pre-acknowledgement conversation frame, acknowledged rescue and later continuation. This completes core mission/recovery/in-App rescue persistence on355; it is not a whole-mission415 replay.

### Final415 normal reload and empty-hall movement

The parent's actual browser check418 exited0: the existing production preview at `http://127.0.0.1:4174/` returned HTTP200, and normal page reload loaded415. The final355 save was **exactly identical before reload and after reload at Title**, including clock1919.116666665265, player `(-389.21464109420776,76.74033416748047,816.4669189453125)`, yaw2.9942,35/100, all three royal defeats, rescue true and both open doors. Continue reached playing/canvas capture with35HP, no displayed error, audio retry hidden and two healthy native Ogg loops. Pause saved clock1920.93333333193 at `(-389.2146301269531,76.74452270507813,816.4669227600098)`,35/100 and unchanged mission flags. Tiny physics settling after Continue is not exact post-simulation position equality.

Native follow-up419 also exited0: normal Resume/capture, Digit2/K guard input, a J light swing and W movement were exercised in the empty hall. HUD health remained35; stamina was90 during play after the light cost/regeneration. About3m of real W movement led to final normal Pause at clock1925.8499999985922, player `(-389.6559753417969,76.74400390625,819.4325408935547)`, yaw2.9942,35/100, all three royal defeats, rescue true and gate/hall open, with pointer released and displayed error empty. The inspected, byte-identical archived [final415 continued frame](<src/catalog_app/tools/gloaming_road/review/final-build-continued.png>) shows the hall/sword/native HUD after movement, not a held guard pose. This is movement/input smoke, **not a hit, parry, duel or physical-controller test**.

**Still not claimed:** full four-sector/clean-parry/feint/shield/wall/ranged combat coverage; ordinary non-blood night or an engaged mage across dawn; final415 frozen A–E comparisons or publication/activation; actual MCP-host worker/CSP/controls behavior; quantitative long-run cleanup/leak bounds; hardware60FPS; physical controller/other browsers; or headphone/speaker/reference-audio audition. The actual Harness GUI at `http://127.0.0.1:3001` was freshly rechecked as `ECONNREFUSED`, the specified DSH checkout was absent, and no replacement GUI was started. The entire game has not passed acceptance.
