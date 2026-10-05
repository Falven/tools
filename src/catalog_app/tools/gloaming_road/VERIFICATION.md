# Verification record — core mission played; acceptance ongoing, 5 October 2026 UTC

This is an evidence ledger, not a completed acceptance checklist. **The core castle mission, two ordinary death recoveries, final conversation acknowledgement and in-App post-rescue persistence were actually completed on unchanged candidate355.** A successful bundle, screenshot, generated asset, or source review is still not equivalent to every combat path, host acceptance, hardware performance or a listening session.

**Publication/build boundary:** code candidate415 was published as `ad121301be2f71da3328e47a0656a4fd28d065e4` and catalog/runtime-activated at10:50:56 UTC on5 October2026; its live main-tool invocation and expected HTML resource listing subsequently succeeded. The immutable code-release record is below; later documentation-only revisions can have a newer commit without changing the tested bundle. The approximately1.01km on-foot/hearth route and first natural-night observations used standalone build306. Candidate355 was loaded through a normal page reload/Continue in359, then remained unchanged through the completed mission and final save410. **Post-mission candidate415 passed strict TypeScript/build (24.68MiB HTML,12.03MiB gzip); actual normal reload/Continue in418 preserved the rescue save and exercised native media start/Pause.** That focused415 check is not a replay of the whole mission, and the completed355 run must not be relabelled as415 acceptance.

## Published candidate415

- **Immutable code release:** [ad121301be2f71da3328e47a0656a4fd28d065e4](https://github.com/Falven/tools/commit/ad121301be2f71da3328e47a0656a4fd28d065e4), pushed to the configured main branch without a force update.
- **Actual ToolForge activation:** `runtime.catalog.applied` at2026-10-05T10:50:56.122723Z (`catalogCommit` matches, `toolCount=9`), then `runtime.applied` at10:50:56.137544Z (`commit` matches). A successful push alone was not treated as activation.
- **Actual post-activation API check:** `gloaming_road()` returned its useful title, controls, local-save/browser requirements and explicit unverified-audition note. The live resource listing contained `ui://gloaming-road/app.html`, MIME `text/html;profile=mcp-app`, with no external resource/connect domains. This establishes tool invocation and resource registration, not a new readback of the entire HTML body or an observed host-iframe render.
- **Frozen game bundle:** [app.js](<src/catalog_app/tools/gloaming_road/app.js>) SHA256 `9b290bf424c4255f1e4f1c59dfa8827ba3b7ba24cb143faf3f2a941b76ed087a`; strict build415 and actual reload/input checks418–419 refer to these bytes. All17 archived captures passed byte-identity, hash, dimensions and applicable build-reference checks; no reference pixels are bundled.
- This publication record is a subsequent **documentation-only update**. A newer documentation/runtime commit does not replace the immutable code-release/hash evidence above. It is not a claim that the code-release revision is the latest documentation commit.
- GitHub still reports six repository-wide dependency alerts (three high, three moderate). The game frontend's scoped audit389 reported zero; that was not claimed as a repository-wide security certification.

## Environment

- Production standalone preview: `http://127.0.0.1:4174/`; generated single-file build, not the Vite source server.
- Chromium 154.0.8037.92 / Linux / named agent-browser session. Graphics report `ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)), SwiftShader driver)`.
- Captures initially 1440×900; smaller 960×600 and 640×400 viewports are explicitly used for slow software-rendered functional exercises. The completed355 mission used640×400, low detail/SwiftShader, source-planned routes and pause-assisted native input. Image detail derives a proportional integer internal resolution; native UI is not rendered into the low-resolution target.
- The actual Harness GUI at `http://127.0.0.1:3001` was freshly rechecked and returned `ECONNREFUSED`; the specified DSH implementation checkout was absent. No replacement GUI/server was started. Earlier live publication/activation and an actual main-tool/resource call succeeded as recorded below; they are not observations of host CSP, controls or rendering inside this unavailable GUI.
- Profiling/long-running preview/input jobs encountered sandbox carrier/heartbeat failures. An owned Vite preview process survived one carrier disconnect, so a later attempted restart correctly failed with port-in-use; the existing URL was reused. These infrastructure interruptions are distinguished from in-game failures below.
- A later automation CLI invocation changed the managed browser's launch/profile mode and lost its temporary test profile. This was **automation profile replacement, not a demonstrated game-save failure**. The parent then deliberately selected a fresh `silver-thistle` world through the actual UI in a persistent browser profile. The earlier movement, death, mage/archer fights and spawn-rest records below remain historical evidence; those kills were not transplanted into the fresh journey. No old progress or clock/player position/health/mission flags were injected.

## Verified so far

| Check | Observation / scope |
|---|---|
| Strict integrated TypeScript | Passed, including pinned Three/Rapier/SDK types and all four world modules. Latest post-mission candidate415 passed strict TypeScript; that does not establish415 browser acceptance. |
| Production bundling | Candidate415:24.68MiB HTML,12.03MiB gzip; strict TypeScript/build passed, with no runtime CDN dependencies. Candidate355 was the unchanged played mission build. Earlier24.67MiB output is historical, not the latest size. |
| MCP registration, local SDK | Exactly one model tool `gloaming_road`, one expected HTML resource; actual SDK call returned non-error useful fallback (1,308 text characters); lazy resource rendered a single inline module. This is **not** live server activation evidence. |
| Live publication / activation | Pushed `92dfca70d1f0884eaa9275e8e2605e8b04055adf` without overwriting concurrent Minesweeper additions. ToolForge logs report `runtime.catalog.applied` and `runtime.applied` at05:02:31UTC; live resource listing includes the expected URI; actual `gloaming_road()` returned its useful fallback and opened the App entry. This is not a browser observation inside the unavailable Harness GUI. |
| Live lifecycle patch | Commit `95d2745094ed517139e3bc96912fd82eb95f67fb` was pushed without a force update; ToolForge reported catalog/runtime application at06:13:55UTC. This carries recovery, capture-loss, preview-write and sound-caption fixes. The subsequent candidate415 code release is verified above. |
| Scoped dependency audit | The game frontend audit identified a vulnerable Vite development-server pin. Updated to7.3.6 with its lockfile; subsequent `npm audit --json` reported0 vulnerabilities, strict TypeScript and bundling passed, and the patched preview served HTTP200. Scoped frontend audit389 again reported0. This is not a repository-wide security certification. |
| Seed/seam source checks | Ad-hoc execution for `silver-thistle`, `elderflower`, `rowan-7`: repeated chunk hashes identical; shared negative/zero chunk-edge height and normal differences exactly0; nine castle-floor samples exactly match the seeded foundation; ordinary encounters omit blood-event IDs. Not a substitute for travel. |
| Woodland traversal | Held WASD through the ordinary handlers, including a reload/Continue, reached x−62.6837,z−172.2057,y6.5668 at clock529 with100HP. Seen live: biome/fog/ground-cover transition, solid trees, a human armored swordsman approaching and a burgundy archer behind. About190m of actual on-foot route, not a teleport. |
| First new journey | Enter → seed → Begin reached playing with pointer lock and visible textured world. Initial failures were caught and fixed, below. |
| Audio activation | Real click path after scene-reset ordering fix reached play with no Enable sound retry indication. IR mismatch fixed using a correctly resampled live-context buffer. No listening claim. |
| Initial movement / save | Real held W input moved the capsule from the safe start to approximately x−0.0033,z−4.4981,y4.9069; local save contained health/stamina100, seed `silver-thistle`, clock402.8333, one recent encounter. Low software FPS throttled simulation; this was a short route, not long-travel evidence. |
| Pause and resume | Actual Escape released capture; the following rendered capture shows the pause menu, seed and deliberate Return button. Immediate CDP evaluation can precede the asynchronous pointerlockchange; the rendered/awaited state is authoritative. Resume accepted a click and recaptured. Focus-loss event path also paused. |
| Reload / Continue | Normal355 reload/Continue preceded the completed mission; post-rescue in-App Save/Quit→Continue preserved progress. Actual final415 reload418 preserved the exact saved clock/position/mission before and after reload at Title, then Continue restored play/capture with35HP. Tiny subsequent physics settling is not exact post-simulation position equality. |
| Completed core mission on355 | All three royals defeated, final conversation acknowledged, `rescued:true`, both doors open; actual post-rescue movement and in-App persistence passed. Final355 save410 had35/100 at clock1919.116666665265. |
| Cross-tile death / Wake Again | Two actual deaths in the persistent355 mission, the second during carrier-killed input396. Both ordinary recoveries returned100/100 at the registered conifer hearth with royal defeats/open doors preserved. Full396 sequence/missing capture34 are not claimed. |
| Final415 native-input smoke | Check419 exited0: native Digit2/K input, J light-swing stamina cost and about3m of W movement in the empty hall; final Pause/capture release with35/100 and rescue flags unchanged. Not a captured held-guard pose, hit, parry, duel or physical-controller check. |
| No implicit saved journey | In a fresh isolated Chromium browser context, opened the actual production page, waited for its title, navigated away and reopened. IndexedDB `current` was absent before and after (`null → null`); context was disposed. No Begin/Continue or direct state write was used. |
| Keyboard guard / pause | Actual left guard pose captured; a charged empty swing consumed stamina. After J/K keyboard input, Escape now releases pointer lock **and** reaches paused, rather than only releasing capture. |
| Positional dodge | Separate idle Space press moved the capsule from approximately(0,0) to(0.5767,−0.8976), about1.067m including ordinary velocity damping after the0.9m impulse. It consumed stamina and did not change health; not a claim of tested invulnerability (none is implemented). |
| Played caster fight | Approached on foot, saw staff/charge/visible fire, attempted a counter that was interrupted and lost24HP. Re-established physical range: a right light cut reduced saved mage health64→40; the subsequent charged strike reduced40→0 and set its ordinary dead snapshot. Player ended76HP. Normal mouse/keys only; no injected health, death, teleport, or hit result. These are functional observations, not a60FPS feel claim. |
| Return and rest | Walked about43m back to the visible hearth prompt, pressed E: health/stamina100, recovery `silver-thistle:rest:spawn` at(0,0), clock598.6833; the defeated mage remained dead in the local snapshot. |
| Played archer exchange | Advanced under K guard, observed bow draw/release and an actual arrow block with stamina cost and no health loss. Heavy cut reduced56→16HP, subsequent light cut16→0/dead. Player remained100HP. Captures preserve the bow pose, guarded contact, wounded archer and death. The block frame exposed oversized nearby sparks and a lower-priority release caption hiding the block cue; refinements are tracked separately, not retroactively claimed as verified. |
| Onward field travel | After the archer kill, normal sprint/walk inputs reached x−67.7384,z187.3821,y−3.9655 at clock734.9 with100/100. Both defeated ordinary enemies remained in the bounded recent snapshot. This was still only an approximately200m displacement, not a completed castle route. |
| Fresh persistent-profile hearth route | Approximately1.01km between checked on-foot stops, through meadow/woodland/conifers and normal chunk/origin-rebase regions. Visible E Rest interaction registered `silver-thistle:rest:-5:12`, followed by a verified pause at clock709.2833 with100HP/100stamina. Source-planned route, no attacks/kills/deaths or royal progress on this fresh leg; full scope below. |
| Naturally elapsed blood night / dawn | At the pre-castle hearth stage, read-only save clock978.4 included an actual event0 mage; Pause at1422.7 retained100HP, the same recovery and no mission progress. That night image shows atmosphere/hearth, not a moon close-up or caster fight. Later355 castle views show the red moon, and the post-recovery dawn image shows lavender clouds/green conifers after naturally elapsed1800; no engaged mage-across-dawn claim. |
| New-world resource lifecycle | Replaced the title preview using the normal Begin action without the prior audio-clear exception. No broad leak-free claim. |
| Original character delivery | Actual GLTFLoader/mixer loaded seven GLBs and 159 clips; child author measured795 finite poses, repeat error0, clone resource sharing, disposal, world attachment transforms and strict connect-src-none embedded-texture loading. Parent regenerated final source successfully after the author's last interrupted command. |
| Real blade geometry | Author sampled all eight viewmodel attacks: max camera-origin blade reach1.823m, endpoints stay at least0.670m forward, contact tips1.705–1.799m forward near center. NPC active-window blade segments intersect a0.31m capsule at1.65m. This establishes geometric plausibility, **not played duel quality**. |
| Original audio files | All212 encodings re-decoded and measured: zero clipped samples; highest4× peak estimate−2.757dBFS; checksums/lengths in audio manifest. No auditory comparison. |
| Existing repository checks | 46 existing JavaScript tests passed after installing that tool's unchanged locked dependencies. After remote integration, Python discovery:116 passed, one pre-existing import error for absent `catalog_app.tools.hello_world` (the earlier checkout had49 passing tests). No new test suite or changes to unrelated tool behavior. |

## Caught, investigated and fixed

1. **Missing ground:** reserved GLSL identifier `patch` caused a real shader compile failure. Renamed `terrainPatch`; subsequent captures show near and far terrain.
2. **Unbundled worker import:** the Vite custom-loader plugin ran too late / missed timestamped query strings. Made it a pre-plugin with normalized query handling. Production classic-worker bundling is separately verified.
3. **New World stopped at loading:** resetting audio assigned a24kHz IR to a44.1kHz ConvolverNode. Only the small impulse is now resampled to actual context rate; reset reuses the matching buffer.
4. **Audio consent false failure:** scene reset interrupted pending media priming after a click. Scene disposal now happens synchronously before unlock in the same trusted action. Genuine AbortError and permission-denial messages are distinct, with explicit retry.
5. **Embedded resource CSP:** GLB loading previously used fetch(data:) and embedded images could use fetch(blob:). Local bytes now go directly to parseAsync; per-loader Image.src texture loading avoids connect permissions. Sound-effect bytes also decode locally. App host still must allow local image/media data and WebAssembly.
6. **Menu/gamepad issues:** inactive controller buttons now establish controller menu mode. Escape on an already opened pause menu no longer requests immediate recapture. Scene/recovery loading rejections are caught and displayed.
7. **Art/quality mismatches:** narrowed broad barren track; increased layered pink-spire height/density; introduced genuine sampled ridge crests; corrected cloud sampling aspect; low-quality render targets/shaders and dynamic density settings are explicit. These changes do not by themselves prove full scene fidelity.

8. **Recovery stream race:** Wake Again actually stalled at “Returning to a quiet place” after death in the distant woodland. The frame loop was recentering streaming on the old player while preparation requested the hearth. Loading now owns its destination, and health is restored only after the destination is ready/teleported. The later355 mission exercised two actual cross-tile deaths/ordinary Wake Again returns to the conifer hearth, both at100HP/100stamina with defeated royals/open doors preserved. The historical stall is retained here; normal recovery is no longer an unplayed requirement.
9. **Keyboard and rapid Escape capture loss:** native Escape can be consumed by pointer lock. Capture loss now pauses regardless of the last input device, including an immediate click→Escape where lock-change notifications coalesce. Both the keyboard path and rapid click/Escape were exercised successfully after correction.
10. **Title preview must not save:** preview construction and partially replaced worlds are no longer eligible for persistence. Only a successfully entered/continued journey writes; leaving title alone passed the isolated-context check above. Incompatible-save messaging no longer offers an unimplemented export control and explicitly warns that New World replaces it.
11. **Presentation/contact corrections:** both sides of flower cards use their authored upward diffuse normal, rather than black flipped undersides; actual balanced rendering compiled with no recorded browser errors. Flame ground rings now use the actual ground/castle floor and paired forms respect the8-form cap. Nearby fire-burst LOS now tests the player, not a mistakenly reused velocity vector. The latter contact corrections still need their targeted replay.
12. **Meaningful sound captions:** replaced the unused dialogue toggle with selective, distance-culled sound cues, available while muted. Actual UI sequence set Master volume0 and triggered Rest: “Rest chimes” appeared in the HUD; captured at640×400 balanced resolution, with no browser errors. Written dialogue remains independent. Physical screen-reader audition remains unverified.

Further source tuning: committed royal attacks resist light-hit interruption (heavy hits/parries can still interrupt); the authored princess talk clip now advances during dialogue. Static menus/loads render at a reduced cadence while their DOM/input remain responsive; normal play is not frame-throttled. The355 mission subsequently completed all three royal fights and final Talk acknowledgement; that does not certify every heavy/parry timing case or animation quality.

## Integrated hearth journey and natural night

### Fresh on-foot route, rest and origin crossings

These observations belong to the fresh UI-chosen persistent-profile journey, not a restoration of the lost temporary profile. The page remained the already-loaded standalone build306 candidate at640×400/low detail. The route was **source-planned, not blind discovery**: shipped `createTerrain/buildChunk` had identified the target hearth, and read-only IndexedDB inspection supplied checked global positions. During the renewed handoff, only the existing [normal-input driver](<artifacts/gloaming-controls.mjs>) dispatched real mouse/keyboard/UI input. No source/driver edits, direct database writes, teleports or clock/player-position/health/mission-flag injections were used.

The approximately **1.01km** figure is the straight-segment sum between checked stops, not a continuous odometer. Representative global X/Z stops were spawn → `(-54.42,51.45)` → `(-49.22,134.84)` → `(-129.10,303.38)` → `(-199.89,456.47)` → `(-230.68,551.53)` → `(-287.27,583.97)` → `(-370.96,624.40)` → `(-314.99,652.28)` → `(-273.74,683.49)` → `(-275.61,741.38)` → the conifer hearth. Meadow, woodland and conifer terrain, solid trees and the distant [castle silhouette](<artifacts/travel-09-castle-horizon.png>) were visible. Ordinary sidesteps/detours avoided trunks and enemy homes; a mage and swordsman pursued briefly but were left behind without player damage.

- Normal movement crossed multiple64m chunks and the384m floating-origin ranges. Saved global positions and the deterministic rest identity stayed consistent through those origin-crossing legs; no origin was forced or private counter probed. No player terrain gap or persistent stall was visible at the inspected stops. This exercises ordinary travel/rebasing, not every boundary, a quantitative memory/cleanup bound, or MCP-host worker/CSP acceptance.
- A large post-resume look did not register once: saved yaw remained2.123 and movement extended west to approximately `(-370.96,624.40)`. Waiting for the normal DOM pointer-lock state before another real mouse move produced a verified corrected turn. This was an input/capture observation, not a terrain teleport or a source fix.
- Job336 was killed with “The Sandbox carrier disconnected.” The browser stayed alive. The driver sent normal W/Shift/J/K key-up inputs, then Escape; phase paused and100HP were verified before continuing. No browser restart/reload/profile switch was used to recover this renewed run. All19 travel jobs were collected:18 completed, one carrier-killed; none remained running at handback.
- Player health remained100 throughout this fresh route. There were **no attacks/kills, deaths, Wake Again or royal combat** on it. This does not erase the separate earlier-profile fight/death evidence above.

At the [visible E Rest prompt](<artifacts/travel-20-hearth-rest-prompt.png>), normal E input produced the [confirmation](<artifacts/travel-21-hearth-rested.png>) “You rest. This quiet place will remember you.” The HUD also showed the “Rest chimes” caption; no auditory judgment follows from that caption. Escape then produced the [paused hearth screen](<artifacts/travel-22-hearth-paused.png>).

The **travel-completion** read-only save, distinct from the later night save, was:

```text
seed: silver-thistle
clock: 709.283333333032
player X/Y/Z: -271.80492401123047, 67.47865356445313, 801.4307250976562
yaw/pitch: 1.234200000000001, -0.48400000000000004
health/stamina: 100/100
recovery ID: silver-thistle:rest:-5:12
recovery X/Z: -273.7259088009596, 801.0333528928459
savedAt: 1791186122296
mission: three royal IDs present; defeated []; rescued false; doors []
phase: paused
```

This travel-stage observation verifies recovery **registration**, not a post-death return or healing from injury on that leg. The later355 mission actually exercised two ordinary post-death Wake Again returns to the registered hearth, with progress preserved; those completed recoveries are recorded below.

### Subsequent naturally elapsed blood night

The same fresh journey subsequently stayed ordinarily unpaused at this safe hearth. A read-only save reached clock978.4 and included an actual event0 mage. The pre-castle night-stage Pause save reached **clock1422.7,100HP, the same recovery and no mission progress**. No clock, player position, health or flags were injected to reach that state.

The [natural blood-night hearth image](<src/catalog_app/tools/gloaming_road/review/natural-blood-night.png>) was inspected directly: a red/magenta clouded, star-speckled sky, dark conifers, dim ground, a nearby faceted rock, hearth flames, the E Rest prompt and held sword are visible. The image is **not a moon-disc close-up and does not show a caster fight**. The event0 observation comes from the read-only save, not from identifying an unseen enemy in the picture. Later355 play naturally reached dawn, as recorded below; ordinary non-blood-night coverage and an engaged mage surviving across dawn remain unverified.

## Candidate355 follow-up and focused browser checks

The following source passed strict TypeScript/build355. It was **not the build used for the long journey/night above**; it was subsequently loaded through normal page reload and Continue in359. These initial focused observations preceded the completed unchanged355 mission below. The final source/bundle is415, with separate normal-reload/input checks and verified code-release activation at10:50:56 UTC; the completed355 mission is not relabelled as a whole-mission415 replay.

| Follow-up | Evidence and limit |
|---|---|
| NPC/castle collision residency | Actual travel saves contained low-Y recent NPC records after leaving them behind; no visual fall was witnessed. The parent traced retained actors applying gravity after their3×3 collision tile was released, before98/125m despawn. Source now makes retained actors dormant outside physics residency, checks readiness before next movement, restores low legacy NPC Y to actual support without resetting health, rehydrates recent ordinary actors at remembered positions, and keeps castle collision while occupied. The3×3 physics budget is preserved. Subsequent355 castle traversal and two recoveries supply integrated evidence; a targeted visual retake of ordinary low-Y residency remains separate. |
| Real CPU Rapier component run347 | Before/dormant Y was `0.005095376968`, unchanged after 300 simulated steps without the actor's tile; after reattachment/return Y was `-0.005670354366`. The check reported nine collision tiles. A below-ground `-52` cache was repaired to support height `0`, preserving16HP. This is component-only, not itself a played death/recovery or castle test. |
| Component fixture failure | The first fixture failed only because its mock lacked `audio.clear`. After correcting the mock, run347 passed. That failed fixture is not recorded as an in-game audio failure. |
| Blood-addition body clearance | The original natural-night save showed two mage capsules approximately0.44m apart at one anchor. Candidate355 adds at most nine local ground/solid/body-clearance attempts, retaining no-front/no-close spawning. Real CPU Rapier component360 produced1.100000→1.100002m separation after120 steps, skipped a solid-blocked alternative and prevented an expired event record bypassing the no-front rule. In the actual355 save at clock1604.6, the ordinary/blood mage IDs both retained64HP and were approximately0.84m apart horizontally (greater than their0.62m capsule diameter). This is saved-position evidence, not a visually witnessed caster duel. |
| Additional real-Rapier check, `c7e3b63d` | Passed exit0 without touching files/browser/real saves. True3×3 distinct translated tiles gave ray hits at Y3. Real stone blocked all nine blood candidates: exactly nine clearance calls, zero views/capsules, counts unchanged11 colliders/nine chunks/one body. Remembered actor `(32,-8,28)` was eligible by current4m, not its1,448m-away home `(1024,-1024)`; one clearance preceded one view/capsule. Y−8→3 support repair preserved ID/home/16HP/event7; feet3.04, zero other overlaps,11→12 colliders/one→two bodies/nine chunks. Component-only; [full scope](<src/catalog_app/tools/gloaming_road/WORLD-PROVENANCE.md#additional-isolated-real-rapier-clearance-evidence>). |
| Actual candidate Continue | In359, the updated production page reloaded normally, displayed Continue, and resumed the persistent near-castle journey at100HP. No New World or direct storage write was used. Mission progress was empty at that point; the later completed mission/in-App persistence and final415 reload are recorded separately below. |
| Native browser audio | In359, read-only browser inspection found exactly four HTMLAudioElements: two playing, ready-state4 looping Ogg streams (nominal120s score/24s field), no element errors, and one running44.1kHz AudioContext. Escape paused the streams and suspended the context. A later normal Resume continued playback; this is actual browser transport evidence, **not audition, loop-gap assessment or reference-audio matching**. |
| Rapid capture fallback and recovery | The first Resume in362 continued stream positions from about5.84s to9.25s. An immediately repeated Escape→Resume was denied pointer capture by Chrome and the driver's strict capture wait timed out. Read-only DOM363 showed a healthy playing state,100HP, no pointer lock and the explicit arrow/J/K/controller fallback message. In364, real ArrowRight changed saved yaw1.8392→1.406533; Escape followed by a1.5s pause and fresh Resume restored canvas capture, hid audio retry and left two streams playing without element errors. That stage ended normally paused at clock1604.6,100HP, same hearth, no mission progress. This was not an audio failure or game-state injection. |
| Audio source/component scope | Conifer/upland routing, single activation ownership,10s deadlines, cancelled/stale media completions, explicit retry without frame floods and urgent caption priority passed strict/source/controlled-async checks. Browser startup/resume/pause and later actual355 rescue-cue handoff were additionally observed. Deliberate browser failure recovery and remaining close-contact caption cases are not covered by those observations. |

## Completed candidate355 castle mission and recovery

### Run boundary, gate, hall and first recovery

This completed run used **the same unchanged355 page loaded in359**, at640×400 low detail/SwiftShader. It was source-planned and pause-assisted, with raw native keyboard/mouse/UI input and read-only IndexedDB inspection. There was no state injection, direct storage write, HTTP reload or source change during the mission run. Candidate415's later fixes are not retroactively present in these observations or captures.

The east/front approach reached the visible Open prompt and opened the exterior gate. At clock1665.85, normal Pause/read-only save recorded approximately(−390.7596,74.9445,870.5944),100HP/100stamina and `mission.doors=['gate']`. The archived [exterior](<src/catalog_app/tools/gloaming_road/review/castle-exterior-blood.png>) and [open gate/courtyard view](<src/catalog_app/tools/gloaming_road/review/castle-gate-open.png>) show the actual red moon disc; they are not caster-combat evidence. “Door creaks” was a caption, not an audition.

The player crossed the courtyard, climbed the first stair steps and used the hall Open prompt. At clock1677.60, the save recorded approximately(−390.7676,75.8445,843.0459),100/100 and `doors=['gate','hall']`; all royals were then undefeated and rescue was false. An approaching royal's notice foley displayed “Armor struck” before a hit: a confirmed caption-semantic issue, **not a successful clash**. The355 run was kept unchanged through mission completion; the later415 source correction is recorded separately below.

Royal0 was defeated through actual combat. Normal Pause at clock1691.6833 recorded approximately(−390.7696,76.4445,841.6866),35HP/70stamina and `defeated=['silver-thistle:castle:royal:0']`. The inspected [blocked-contact frame](<src/catalog_app/tools/gloaming_road/review/C-armored-contact.png>) contains smaller sparks and “Blow blocked”; it is not a confirmed parry. Charges/taps were sometimes blocked or interrupted, so attempts are not counted as successful heavy hits.

A real combat death occurred in the hall at clock1703.6167, approximately(−393.4696,76.7437,828.0785),0HP. The ordinary **Wake Again** button returned to the conifer hearth with100HP/100stamina, pointer capture and no displayed error; normal Pause saved clock1704.2833 at approximately(−273.7254,67.6753,801.0328). **The first royal defeat and both opened doors survived.** This is actual cross-tile death/recovery evidence on355, not the earlier isolated component test.

The return through the still-open gate reached the stairs at clock1770.5667, approximately(−390.5723,74.9445,845.0860),100/100. A subagent interruption occurred only after input job385 had completed normally; its20 input jobs were all collected with exit0. The parent found no surviving driver, sent harmless key-up cleanup and independently confirmed the same paused/pointer-released save. No interrupted input, lost progress or game crash was observed in that interruption. The later carrier interruption below is a separate event.

### Second royal, interrupted attempt and second ordinary recovery

Royal1 was killed at clock1792.0666666653806, player `(-390.9658021927,76.7434698486,838.3970794678)`,64HP/60stamina. The nearer warden was drawn to the threshold while the far warden stayed back in the inspected frames. That scoped observation is not a complete two-actor coordination or combat-matrix pass.

Input job396 was **carrier-killed mid-final attempt**. Cleanup397 exited0 and found the player dead at0HP, clock1807.9666666653661, with royal0/1 still defeated. The full intended396 input sequence and missing capture34 are **not claimed**. This records the observed death and interrupted automation, not a demonstrated game crash or a claim that every intended attack occurred.

The second ordinary **Wake Again** in398 returned100HP/100stamina at clock1808.6333333320322, player `(-273.7253570557,67.6753393555,801.0328025818)`. Both defeated royals and open gate/hall were preserved. There were **two actual deaths in this persistent mission run**, the second during the carrier interruption; both normal recoveries passed.

The archived [dawn hearth image](<src/catalog_app/tools/gloaming_road/review/dawn-hearth.png>) shows lavender clouds and green conifers after naturally elapsed clock1800. This is a real dawn-atmosphere observation, not an ordinary non-blood-night pass or proof of an engaged mage surviving across dawn.

### All three defeats and final acknowledged conversation

In405, **all three royals were defeated**. The read-only save at clock1892.8999999986222 placed the player at `(-390.6097974777,76.7445379639,825.2247505188)`,35HP/58stamina.

Normal E Talk in407 opened the “For so long…” first beat. Continue advanced to **“You came. I’m safe now. Thank you.”** The second Continue acknowledged that final beat and returned to playing with pointer lock. The save contained all three defeated royals **and `rescued:true`** at clock1898.9166666652834, player `(-388.3320026398,77.0471502686,810.5286712646)`,35HP/100stamina. The announcement read **“Elowen is safe. The world remains open to you.”** The conversation screenshot before final acknowledgement is not used by itself to claim the rescue flag.

Native media inspection immediately afterward found four media elements and one running44.1kHz AudioContext. The rescue cue had duration35.010667s, current time3.493333s, `loop:false`, `paused:false`. After a requested40s ordinary unpaused wait, that cue was paused/reset while the ordinary120.010667s loop was playing at13.36s. This is observed finite-cue handoff, **not `ended:true` evidence, audition or gapless-loop/transition proof**. Normal Pause afterward saved clock1914.0666666652696.

### Post-rescue movement, in-App Save/Quit and Continue

Actual movement changed the player's position from `(-388.3319354057,77.0444342041,810.5316123962)` to `(-388.9192280769,76.7445303345,814.4881668091)` at clock1916.1166666652678. **In-App Save/Quit** reached Title and stored the exact clock/position/mission; **Continue** returned to playing with pointer capture,35HP and no displayed error. Further normal W movement produced the final355 save410:

```text
seed: silver-thistle
clock: 1919.116666665265
savedAt: 1791195063916
player X/Y/Z: -389.21464109420776, 76.74033416748047, 816.4669189453125
yaw/pitch: 2.9942, 0
health/stamina: 35/100
mission.guardIds:
  silver-thistle:castle:royal:0
  silver-thistle:castle:royal:1
  silver-thistle:castle:royal:2
mission.defeated: same three IDs
mission.rescued: true
mission.doors: gate, hall
recovery ID: silver-thistle:rest:-5:12
recovery X/Z: -273.7259088009596, 801.0333528928459
phase: paused; pointer released; displayed error empty; all keys released
```

All input jobs were collected; none remained running. This completes **core castle traversal/combat, both recoveries, acknowledged rescue and in-App rescue persistence/continued exploration on355**. Save/Quit→Continue is not an HTTP reload, and no415 reload/publication is inferred from it.

### Archived mission frames and their scope

All four images below are unaltered355 captures already archived and inspected by the parent. They do not replace final415 A–E retakes.

| Frame | Evidence / limitation |
|---|---|
| [Dawn hearth](<src/catalog_app/tools/gloaming_road/review/dawn-hearth.png>) | Naturally reached dawn, lavender clouds and green conifers after clock1800; no mage-across-dawn proof. |
| [Princess conversation](<src/catalog_app/tools/gloaming_road/review/F-princess-conversation.png>) | Inside the royal chamber **before final acknowledgement**; not alone proof of rescue completion. |
| [Rescue acknowledged](<src/catalog_app/tools/gloaming_road/review/F-rescue-acknowledged.png>) | **After** the final Continue; paired with the read-only all-three-defeated/rescued save above. |
| [Post-rescue continued](<src/catalog_app/tools/gloaming_road/review/post-rescue-continued.png>) | Later continued play; the exact movement and in-App persistence comparisons come from the input/read-only-save observations, not a still alone. |

The [comparison gallery](<src/catalog_app/tools/gloaming_road/review/COMPARISON.md#f--completed-mission-and-post-rescue-continuation-candidate355>) shows these alongside the preserved earlier development frames.

## Post-mission415 input and caption checks — source/component scope

After the unchanged355 mission, an isolated fake-DOM/gamepad baseline reproduced three source issues: optional gamepad API `SecurityError` escaped; a held right trigger on entry synthesized a press; and an idle connected pad erased keyboard K guard. Candidate415 safely reads the optional API, seeds already-held buttons, preserves mixed keyboard/mouse guard with deadzoned pad look, and clears/pauses once on controller loss.

Corrected component414 passed with exit0: denied-API W movement; held RT requiring a fresh press/release; idle/drifting pad preserving K and mouse guard; controller loss causing one pause/one notice after100 polls; and menu A not becoming an interaction. The combined fixture initially failed **only** because its mock omitted `document` during `audio.dispose`; corrected DOM fixture414 passed. These were isolated component checks, not a physical controller or actual-host observation.

The played355 notice-caption error is also corrected in415: `armor-rustle` reuses existing audio/gain and is excluded **before urgent-caption bookkeeping**. Real `armor`, `hit-armor` and numbered armor assets still caption; no new asset or volume heuristic was added. Muted/locked notice suppression and real contact preempting a release cue passed in the corrected component fixture. Browser replay of these415 changes remains separate from the completed355 mission.

Strict TypeScript/build415 passed at24.68MiB HTML /12.03MiB gzip. The parent-reported415 [bundle](<src/catalog_app/tools/gloaming_road/app.js>) content digest is `9b290bf424c4255f1e4f1c59dfa8827ba3b7ba24cb143faf3f2a941b76ed087a`. The scoped frontend audit389 again reported0 vulnerabilities. Neither result establishes final publication, actual-host controls/CSP, hardware performance or broad acceptance.

## Actual final415 reload and native-input smoke

Parent browser check418 was collected with exit0. The existing production preview at `http://127.0.0.1:4174/` returned HTTP200; an actual normal page reload loaded415. The rescue save was **exactly identical before reload and afterward at Title**: clock1919.116666665265, player `(-389.21464109420776,76.74033416748047,816.4669189453125)`, yaw2.9942,35HP/100stamina, all three royal defeats, rescue true and gate/hall open.

Normal Continue reached playing with **CANVAS pointer capture**,35HP, displayed error empty and audio retry hidden. Native inspection found four HTMLAudioElements: two unused paused primers and two playing Ogg loops, readyState4, error null, durations120.010667s/24.010667s and times around2.590s; one running44,100Hz AudioContext. Normal Pause released capture and saved clock1920.93333333193, player `(-389.2146301269531,76.74452270507813,816.4669227600098)`,35/100, mission flags unchanged. Tiny post-Continue physics settling is **not** claimed as exact position restoration after simulation.

Native follow-up419 also exited0: normal Resume/capture, Digit2 and K guard input, a J light swing, then W movement. During play HUD health was35, stamina90 after the light cost/regeneration, and displayed error empty. This does not measure the nominal light cost as10 or establish contact. Final normal Pause/pointer release saved:

```text
clock: 1925.8499999985922
player X/Y/Z: -389.6559753417969, 76.74400390625, 819.4325408935547
yaw: 2.9942
health/stamina: 35/100
mission: all three royal IDs defeated; rescued true; doors gate, hall
phase: paused; pointer released; displayed error empty
```

Compared with418's final X/Z `(-389.2146301269531,816.4669227600098)`, this is about3m of actual W movement. The byte-identical archived [final415 continued frame](<src/catalog_app/tools/gloaming_road/review/final-build-continued.png>), inspected by the parent, shows the hall/sword/native HUD after resumed movement at640×400 low detail. It is **not combat or a captured held-guard pose**: K input was sent, but the reviewed post-release sword view is idle. J stamina cost and W movement were observed; no hit, parry or duel is inferred.

These are actual415 normal-reload persistence, startup/Pause and empty-hall input observations—not a whole-mission415 replay, physical-controller test, listening session or actual-host CSP/controls pass. The separately verified code-release activation and subsequent live API check are recorded above.

## Measured performance limitation

SwiftShader is software emulation, not an ordinary laptop GPU. Earlier balanced/soft builds at480×300 internal resolution had12-frame median600ms / worst833ms. The original GPU profile recorded about42.2s in GPU work over roughly44s, versus about1.25s in main animation callbacks, with most display frames dropped. A prior JS heap sample was207.5MB; it is not total memory or a proven bound.

After a fresh browser session, byte-format render target, simpler soft-quality foliage/terrain shading and anisotropy reduction, a15-frame sample at480×300 measured **median466.7ms / worst650ms**. That is still inadequate for normal responsive play and **does not meet the60FPS target**. It is not presented as a hardware result, a stable benchmark, or proof of a leak-free long run. High-quality captures likewise do not prove real-time performance. Further functional exercises use clearly noted smaller viewports; a physical integrated-GPU pass remains necessary.

## Still pending / not claimed

**Not pending:** the core355 castle route/combat, all three royal defeats, both ordinary Wake Again recoveries, final conversation acknowledgement, continued exploration and in-App rescue persistence. Final415 also has actual normal-reload rescue-save preservation, Continue/start/Pause and an empty-hall keyboard/movement smoke. These completed scopes do not stand in for the remaining checks below.

- Publication/activation of415 and browser-observed startup/capabilities in the actual MCP App host. Last verified live activation is95d2745; the actual live main-tool/resource invocation belongs to92dfca7. The unavailable Harness GUI was freshly rechecked as `ECONNREFUSED`; no replacement GUI was used.
- Complete played directional-duel coverage: all four sectors, clean hit/miss/parry, correct/late/wrong guard, feint, heavy guard pressure, wall contact, two-actor coordination, shield flank, archer flight and mage burst. The played royals, earlier individual mage/archer exchanges and415 empty-hall smoke do not complete that matrix.
- Save replacement/cancel, multiple played seeds, and extended quantitative bounded-streaming/cleanup/leak checks. Exact pre-/post-HTTP-reload save comparison at Title passed on415; tiny physics settling after Continue is not claimed as exact post-simulation coordinate equality.
- Ordinary non-blood night and an engaged mage surviving across dawn. Naturally elapsed blood-night atmosphere/event0, the red moon and later natural dawn are observed; an unseen continuous night/dawn fight is not inferred.
- Targeted visual/combat replay of blood-addition clearance and retained ordinary-NPC residency; remaining contact-caption cases and deliberate browser media-failure recovery. Castle traversal and both recoveries supply integrated evidence, while the additional clearance checks remain component-only. The actual355 rescue cue/ordinary-loop handoff is complete as transport evidence, not as audition.
- Final frozen415 A–E comparison retakes. Historical A–E and archived355 castle/mission frames are not415 captures. A full415 mission replay is not claimed.
- Physical integrated-GPU/hardware60FPS validation; physical controller; Firefox/Safari; headphone/speaker/reference-audio audition; native loop-gap and subjective mix checks. Actual host CSP/controls are unverified, despite isolated optional-API/gamepad/caption checks.

The complete game is not accepted as passed.

No debug panel, teleport menu, forced-completion control, hidden verification mode or test-only game logic is shipped. Temporary browser drivers dispatch real keyboard/mouse input to the ordinary handlers; they do not write world state or mission flags. Read-only IndexedDB inspection confirms persisted observations. Source-based math/resource checks are labelled separately from played evidence.
