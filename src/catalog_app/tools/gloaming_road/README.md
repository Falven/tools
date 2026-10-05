# The Gloaming Road

*There is still light in the world.*

An original single-player, first-person medieval-fantasy MCP App: textured flower country, cool woodland, physical directional swordplay, and one princess-rescue mission in a unique seeded castle. The world continues after the rescue. There is no account, gameplay service, paid runtime API, CDN, inventory treadmill, minimap, quest log, mission countdown, or recurring fetch task. The hosting MCP server's existing authentication still applies when opening its tools.

**The core mission is actually played; broader verification remains ongoing.** On unchanged standalone candidate355, normal controls completed all three royal defeats, two ordinary death/Wake Again recoveries, the final conversation acknowledgement, post-rescue movement and in-App Save/Quit→Continue with mission progress preserved. This was source-planned, pause-assisted play at640×400/low detail on software-rendered Chromium, not a hardware60FPS or full combat-matrix pass. The [verification record](<src/catalog_app/tools/gloaming_road/VERIFICATION.md>) separates that evidence from source/component checks and unavailable host/listening/hardware checks. The [comparison and mission gallery](<src/catalog_app/tools/gloaming_road/review/COMPARISON.md>) contains actual, unaltered captures; historical A–E and completed355 mission frames are not final415 retakes.

**Build/publication boundary:** post-mission candidate415 passed strict TypeScript/build at24.68MiB HTML /12.03MiB gzip. Actual normal reload/Continue in418 preserved the rescue save and exercised native media start/Pause; follow-up419 sent keyboard guard input and observed a light-swing stamina cost/~3m movement in the empty hall, not a captured held-guard pose, hit/parry/duel or whole-mission415 replay. Code candidate415 was published as `ad121301be2f71da3328e47a0656a4fd28d065e4`; ToolForge confirmed catalog/runtime application at10:50:56 UTC on5 October2026. The live main-tool call and expected HTML resource listing then succeeded. The [publication record](<src/catalog_app/tools/gloaming_road/VERIFICATION.md#published-candidate415>) pins the tested bundle; subsequent documentation-only commits do not change it.

## Open and play

Call `gloaming_road()` in an MCP Apps-capable client. The tool returns a useful plain-text fallback and declares `ui://gloaming-road/app.html`; it does not start a save, post a score, or change server state. The App's own **Enter the world → Begin** starts a local journey. Enter a seed or accept the generated one. **Continue** resumes this browser's most recent save. Replacing a save requires an explicit second confirmation.

The browser must support WebGL2 and WebAssembly. Mouse capture and audio request activation from a real click. **Escape** releases capture and pauses; **Return to the world** deliberately recaptures. If the host denies pointer lock, keyboard-look and controller controls remain available. A touch-only phone is not presented as a supported first-person control scheme. Fullscreen uses the official MCP Apps host API, never a replacement full-page navigation.

If a local asset, graphics initialization, storage, or audio activation fails, the interface reports it. Audio activation can be retried. Denied storage leaves the game playable but explicitly unsaved. A host that forbids workers uses the same deterministic generator with bounded main-thread scheduling. WebAssembly compilation itself must be permitted by the host. Closing/hiding/defocusing the game stops simulation/input and audio; there is no offline catch-up.

### Controls

| Action | Keyboard / mouse | Standard controller |
|---|---|---|
| Move / look | WASD / mouse | Left / right stick |
| Light strike | Tap left mouse; J also works | Tap right trigger |
| Heavy strike | Hold, then release left mouse / J | Hold, then release right trigger |
| Guard / early feint | Right mouse; K also works | Left trigger |
| High / left / right / low | 1 / 2 / 3 / 4, or deliberate mouse gesture | D-pad up / left / right / down |
| Dodge | Space + movement direction | B / Circle + left stick |
| Sprint | Shift | Left-stick press |
| Interact | E | A / Cross |
| Pause | Escape | Menu / Start |
| Keyboard-only look | Arrow keys | — |

Guard selection persists. Aim movements below the gesture threshold do not accidentally change guard. Match the sector where the incoming blade enters **your** space: an enemy's anatomical left is your right. Begin the correct guard just before impact to parry; holding the correct guard blocks at a stamina cost. Wrong-side and late defense fail. A dodge moves the capsule and supplies **no invulnerability**. Active strikes and recovery are committed; only early windup permits a feint.

Settings provide independent audio buses, mouse sensitivity, FOV, inverted Y, motion/flash reduction, blood, selective sound captions (also while muted), image detail, and movement/sector key rebinding. The controls table shows defaults; the settings screen shows current bindings. Menus support keyboard and controller navigation. Soft detail preserves nearby plant texture/density while reducing resolution, shadows and foliage lighting; it is not a switch to an empty world.

## A single mission, without a rail

The castle lies roughly 820–1,230 metres from the safe start; terrain, trails and changing views—not UI markers—provide context. Explore in any direction. Open the actual hinged outer gates, cross the courtyard, climb the broad hall stair and open the interior doors. Three separately identified elite royal guards stand between you and the princess's chamber. Their defeats are durable and never reset as ordinary encounters do. Approach the princess inside her real chamber and use the contextual Talk prompt. The final acknowledged conversation beat completes the mission once and returns control; it does not replace the world with a victory screen.

The princess, Elowen, and all dialogue are original. The reference game's linear escape story, locations, final interiors and undisclosed music are not claimed as reproductions.

**Observed completion on355:** the normal Talk sequence reached “You came. I’m safe now. Thank you.”; its final Continue acknowledged the rescue and returned control with “Elowen is safe. The world remains open to you.” Read-only saves confirmed all three royal defeats and rescue true, including after in-App Save/Quit→Continue and further movement. The [completed mission record](<src/catalog_app/tools/gloaming_road/VERIFICATION.md#completed-candidate355-castle-mission-and-recovery>) also records both successful hearth recoveries and the interrupted input attempt honestly. The [conversation frame](<src/catalog_app/tools/gloaming_road/review/F-princess-conversation.png>) is before final acknowledgement; the separate [acknowledged-rescue frame](<src/catalog_app/tools/gloaming_road/review/F-rescue-acknowledged.png>) is after it.

## Systems and bounds

- **World:** immutable seeded global coordinates; 64 m chunks / 2 m near terrain grid; independently seeded terrain/biome/placement noise; sampled path and exclusion masks; a wide flat castle terrace. Long-range terrain is another moving sample of the same world—not a painted backdrop or finite arena.
- **Streaming:** at most 25 wanted/visible chunks and 49 retained; 2 worker requests in flight; pending plus ready backlog ≤3; at most one main-thread geometry upload per animation frame. A containing-cell / 1.25 m boundary guard prevents stepping into unloaded collision. Initial and recovery preparation waits for a full 3×3 neighborhood and covering far terrain. One far mesh uses progressively coarser 8/16/32/64 m rings to 1,792 m.
- **Physics:** Rapier kinematic capsule, real terrain/tree/boulder/castle/door colliders, slope/step/snap handling, a 3×3 collision working set, wall visibility, swept ranged projectiles and actual animated blade-segment samples. One hit per target per swing. Player and visual endpoints move coherently through 384 m floating-origin shifts. Retained distant actors become dormant outside resident collision instead of falling into unloaded terrain; occupied castle geometry remains collidable until those actors leave.
- **Combat:** light/heavy commitments, resource costs and recovery, guard-break/stagger, directional parry/block, physical repositioning, delayed opponent reactions, circle/separation/retreat/path decisions. Swordsmen, shield guards, archers, mages and durable elites use readable articulated bodies. At most two actors reserve meaningful attack slots; others approach/reposition rather than all striking. Nearby ambient actor target ≤12, with up to three designated castle guards managed separately.
- **Finite effects/resources:** 384 spark/blood instances, at most 8 local flame forms, 12 blood pools, finite projectiles with geometry-contact expiry, bounded corpse/actor/recent-encounter retention. Shared immutable art is reused; private chunk/actor resources are disposed on unload and reset.
- **Time:** fixed 60 Hz simulation, render-time accumulator capped at 0.1 s / five steps to prevent runaway catch-up. A 30-minute game-time day/night cycle continues indefinitely. Each night has a deterministic seeded 20% blood-moon decision. Blood nights add eligible dark mages without close visible pop-in; dawn stops new event spawning while nearby living fights may finish. Pauses, hidden tabs and closing the App do not advance time.
- **Saves:** versioned IndexedDB world/mission/clock/global position, with small localStorage settings. Autosave plus pause/quit/death/rest/guard/conversation writes. Latest 64 ordinary encounter snapshots retain health/death briefly; ordinary enemies may repopulate after 600 game seconds away. Royal identities/defeats and the rescue flag never use that cache. Recovery is a quiet visited stone hearth; death restores health/stamina at that site, not at the death location. Use one active game window per browser profile: writes are serialized within an App instance, not coordinated between simultaneous tabs.
- **Practical extent:** no authored map edge or invisible perimeter. JavaScript/float physics are not mathematically infinite; floating-origin local coordinates preserve ordinary travel precision. Million-metre and multi-day continuous routes are not claimed as exercised.

The tuning constants are centralized in [state.ts](<src/catalog_app/tools/gloaming_road/frontend/state.ts>). Key starting values: movement 3 m/s, sprint 4.6 m/s; player 100 health/stamina; light 24 damage / 12 stamina, heavy 40 / 24; heavy charge ≥0.36 s; light 0.24 s windup +0.14 contact +0.32 recovery, heavy 0.52 +0.18 +0.55; parry window 0.14 s; dodge 22 stamina /0.28 s /0.9 m; nominal melee reach 1.85 m. Baseline ordinary health 56–88; elite health 104. Royal armor preserves a committed attack against light-hit interruption, making heavy pressure and timed defense consequential. These are game rules, not source-game measurements.

## Local build and source

The frontend is isolated from other Tools and pins all dependencies in [package-lock.json](<src/catalog_app/tools/gloaming_road/frontend/package-lock.json>). From its frontend directory:

```sh
npm ci
npm run typecheck
npm run build
npm run preview -- --port 4174 --strictPort
# Optional unbundled authoring:
npm run dev -- --port 4173 --strictPort
```

Open the printed preview URL. The build embeds the original GLBs, PNGs, fonts, worker, Rapier and both audio codecs into one module: [app.js](<src/catalog_app/tools/gloaming_road/app.js>). The tool's [HTML template](<src/catalog_app/tools/gloaming_road/app.html>) hosts it. The build also produces a self-contained [standalone HTML](<src/catalog_app/tools/gloaming_road/frontend/dist/index.html>) (ignored generated output); serve it over localhost for stable storage. No runtime network dependency is required after the HTML is loaded. Development uses same-origin asset requests; production's GLBs, embedded images and sound effects parse locally without fetch. Audio media use local data URLs.

Post-mission candidate415 passed strict TypeScript/build with **24.68MiB uncompressed HTML /12.03MiB gzip**. The scoped frontend dependency audit389 again reported0 vulnerabilities; this is not a repository-wide security certification. Build/audit success does not prove415 publication or played acceptance. No secret, analytics beacon, remote texture or source-game asset is embedded. Software packages/font licenses are reproduced in [THIRD_PARTY_NOTICES.txt](<src/catalog_app/tools/gloaming_road/THIRD_PARTY_NOTICES.txt>).

ToolForge publication is normal GitOps: commit this Tool Directory and push the configured branch; check activation separately. There is exactly one new model-facing tool and one HTML resource. No additional shared server dependency or authentication change is required. Existing tools are not renamed or modified.

## Original art, audio and provenance

- [Reference ledger](<src/catalog_app/tools/gloaming_road/REFERENCE-NOTES.md>): refreshed URLs, directly inspected screenshots, supplied footage observations, inferred techniques, and proposed adaptation decisions.
- [Character provenance](<src/catalog_app/tools/gloaming_road/CHARACTER_PROVENANCE.md>): seven original articulated GLBs, original 512 px atlases, 159 clips, conventions, measured real blade trajectories and rigid-articulation limitations.
- [World provenance](<src/catalog_app/tools/gloaming_road/WORLD-PROVENANCE.md>): original scenery GLB, sixteen plant tiles, texture painters, generation/streaming conventions and bounds.
- [Audio provenance and audition checklist](<src/catalog_app/tools/gloaming_road/AUDIO-PROVENANCE.md>): 106 originals /212 encoded files, six composed cues, five ambience loops, 93 variations, manifests and measurement results.
- [Castle authoring source](<src/catalog_app/tools/gloaming_road/art/castle.mjs>) and [atmosphere texture painter](<src/catalog_app/tools/gloaming_road/art/atmosphere.py>): the pale keep, ochre towers, courtyard, furnished royal room, stone/wood/roof/sky/moon paintings are project-original. Castle render zones are batched; authored collider/hinge/navigation metadata share the same model coordinates. The small dragon silhouette is original in-code geometry; it follows occasional bounded global flyovers, not the camera.

The offline art tools require the separately pinned [authoring requirements](<src/catalog_app/tools/gloaming_road/art/requirements.txt>), not new MCP runtime dependencies:

```sh
python -m pip install -r art/requirements.txt
python art/scenery.py
python art/characters.py
python art/atmosphere.py
node art/castle.mjs
python audio-source/render.py
python audio-source/measure.py
```

Read the audio provenance before regenerating all codecs. Rebuild the frontend after changing generated assets. All sources use fixed art seeds; gameplay world seeds are independent. No reference screenshots are used by a generator or shipped as runtime content.

## Known verification boundaries

Numeric waveform/peak checks and native browser media transport—including the actually triggered355 rescue cue and its observed return to ordinary music—do **not** establish audible quality, a gapless handoff or reference resemblance. No headphone/speaker/reference-audio audition, physical controller, Safari/Firefox run or hardware60FPS result is claimed. GLTFLoader/mixer trajectory checks and successful royal fights do not complete the four-sector/clean-parry/feint/shield/wall/ranged combat matrix.

Core mission, both ordinary recoveries, acknowledged rescue and in-App persistence are complete on355. Final415's actual normal reload/Continue in418 preserved the rescue save and resumed healthy native media; this is not a whole-mission415 replay. Final415 frozen A–E retakes, ordinary non-blood night, an engaged mage across dawn, extended quantitative streaming/leak bounds, actual-host CSP/controls and final publication remain separate. The actual Harness GUI at `http://127.0.0.1:3001` was freshly rechecked as `ECONNREFUSED`, and the specified DSH implementation checkout was absent; no replacement GUI was started.

Post-mission415 also corrects optional-gamepad API denial, held-trigger entry, mixed keyboard/mouse guard and controller-loss handling, plus the erroneous pre-contact “Armor struck” notice. The corrected fake-DOM/gamepad/caption component fixture414 passed; these component results are not physical-controller, listening or actual-host observations.

There is no new automated test suite. Existing repository tests and strict compilation are run without editing unrelated app behavior. The pre-existing Python discovery target referencing a missing `hello_world` tool remains an unrelated known failure.
