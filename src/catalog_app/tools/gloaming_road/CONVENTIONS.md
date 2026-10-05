# The Gloaming Road — production conventions

Original game, not source-game code/assets. Tool ID and MCP name `gloaming_road`; resource `ui://gloaming-road/app.html`. Isolated under this directory. No unrelated edits. Vite/TypeScript, Three 0.180, Rapier 0.19.3, ext-apps 2.0.0, simplex-noise 4.0.3. One self-contained HTML App; local standalone production build also generated. Metres, Y up. World east +X, north -Z; humanoids face +Z locally; camera faces -Z. Character feet Y=0; height 1.8m. Objects near player rebased at fixed-step boundaries; global coordinates remain JS doubles and stable IDs.

## Asset delivery
Editable scripts under `art/` or `audio-source/`. Runtime art under `frontend/assets/`. All exports deterministic and original, local URLs embedded at build. Textures small PNG, textured irregular silhouettes, coherent realistic simplified humans, not placeholder capsule meshes. Assets GLB containing named rigid articulated nodes and named animation clips. Animation clips at seconds; light 0.24/0.14/0.32; heavy 0.52/0.18/0.55. Gameplay controls attack phase and mixer time; no root translation authority. Foliage alpha-cutout, nearest magnification and mipmap minification. Collision dimensions defined by gameplay/world, not decorative plants.

## File ownership
Parent: build/package configuration, App registration, gameplay/lifecycle, input/UI/save, castle, physics integration, final docs.
Character artist: `art/characters.*`, `frontend/assets/characters*`, `frontend/characters.ts`, character provenance. Provide knight/shield/archer/mage/princess/viewmodel and animations; API described in delegation.
Audio composer: `audio-source/`, `frontend/assets/audio/`, `frontend/audio.ts`, audio provenance. Local composed/rendered score, ambient loops, material-specific SFX.
World artist: `frontend/terrain.ts`, `frontend/world.ts`, `frontend/world-worker.ts`, `frontend/scenery.ts`, `art/scenery.*`, scenery assets/provenance (when delegated).

No new test suite. Run typecheck/build and exercise shipped controls; evidence must distinguish observed behavior from unperformed checks. Do not claim auditory fidelity from signals alone.
