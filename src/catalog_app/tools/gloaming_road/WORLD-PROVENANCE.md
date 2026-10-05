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
- There is exactly one castle feature, 820–1,230 metres from the spawn with a seed-derived bearing and yaw zero. The parent's keep is expected to face +Z and enter near local `z=+40`.
- The castle floor is completely flat through local `±41 × ±50` metres, enclosing the requested `±36 × ±45` footprint. Its apron blends over another 150 metres with a smoothstep grade. Plants/props are excluded within `±48 × ±58`; tree crown overhangs receive an additional margin.
- Spawn is at global `(0,0)`. The first 24 metres are naturally safe and graded; trees, rocks, logs, ruins, and enemies begin farther away. The initial rest circle is decorative, with a walkable entrance gap.
- The starting clearing is meadow through 66 metres, rich in pink flower spires. A guaranteed woodland pocket lies roughly northwest, around 80–190 metres away. Other woodland/conifer/upland regions follow coherent broad moisture, elevation, and climate fields rather than chunk-sized biome choices.
- Broad scalloped mountain ridges are part of the real traversable height function, not scenery walls. Winding trails branch across the global field; a trace visits both spawn and castle regions without requiring the player to follow it.
- Solid prop metadata covers oak/rowan/fir trunks, boulders, fallen logs, and ruined stones using positive `radius` and `height`. Plants have no collider metadata. Props and encounters always retain **global** positions.
- Sparse encounter opportunities occur in approximately 32% of chunks, occasionally as pairs, with stable seeded IDs; none start within 32 metres of spawn. The parent owns activation within 80 metres, enemy life cycles, and persistence.
- Rest sites are stable seeded records, including `seed:rest:spawn`. Wayside ruins are low stone fragments, never additional castles.

## Streaming integration and bounded resources

[World](<src/catalog_app/tools/gloaming_road/frontend/world.ts>) implements the exact `StreamWorld` interface and constructor `new World(seed, callbacks, quality?)`. [The worker](<src/catalog_app/tools/gloaming_road/frontend/world-worker.ts>) imports only deterministic terrain-generation code. [Scenery rendering](<src/catalog_app/tools/gloaming_road/frontend/scenery.ts>) owns the original asset cache and chunk batching.

The parent build must implement the `./world-worker.ts?worker-source` virtual import as a self-contained classic-worker JavaScript string. World creates a Blob worker and sends `init`, `chunk`, and `far` messages. A host that forbids Blob workers falls back to one CPU build per animation frame; `stats().fallback` makes that mode visible rather than claiming worker operation.

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

The supplied visual references and all three generated atlases were inspected directly. Final deterministic art generation completed successfully: 11 named mesh parts, 1,468 source triangles, and an 821,164-byte GLB. A strict TypeScript check of the four owned world modules completed with exit code zero after the density, ridge and CSP-loader revisions. No new test suite was created and no commit was made by the world author.

Parent-supplied production screenshots were also inspected. Early renderer feedback identified a reserved GLSL identifier (`patch`); it was renamed to `terrainPatch`, and the corrected screenshot showed the ground rendering. Subsequent screenshot feedback drove denser, taller flower drifts, narrower irregular flowering verges, paler granite, and sharper genuinely sampled ridge crests. The updated production meadow image visibly showed those improvements.

These are visual/compilation observations, not a frame-rate certification. Parent-reported headless SwiftShader profiling remained slow, so hardware performance targets are not claimed as achieved here. Final frame-rate, worker/CSP behavior in the MCP host, movement, collision, castle occlusion, and rebasing checks belong to the parent's integrated build evidence.
