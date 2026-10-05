# Verification record — ongoing, 5 October 2026 UTC

This is an evidence ledger, not a completed acceptance checklist. A successful bundle, screenshot, generated asset, or source review is not equivalent to a played mission or a listening session.

## Environment

- Production standalone preview: `http://127.0.0.1:4174/`; generated single-file build, not the Vite source server.
- Chromium 154.0.8037.92 / Linux / named agent-browser session. Graphics report `ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)), SwiftShader driver)`.
- Captures initially 1440×900; smaller 960×600 and 640×400 viewports are explicitly used for slow software-rendered functional exercises. Image detail derives a proportional integer internal resolution; native UI is not rendered into the low-resolution target.
- The actual Harness GUI at `http://127.0.0.1:3001` is not reachable from this command sandbox. No replacement GUI/server was started. Live publication/activation and a real main-tool call have now succeeded; actual host capability checks remain separate.
- Profiling/long-running preview jobs encountered sandbox carrier/heartbeat failures. An owned Vite preview process survived one carrier disconnect, so a later attempted restart correctly failed with port-in-use; the existing URL was reused. This is distinct from an in-game error.

## Verified so far

| Check | Observation / scope |
|---|---|
| Strict integrated TypeScript | Passed, including pinned Three/Rapier/SDK types and all four world modules. |
| Production bundling | Latest completed output: 24.67 MiB HTML, 12.03 MiB gzip; no runtime CDN dependencies. |
| MCP registration, local SDK | Exactly one model tool `gloaming_road`, one expected HTML resource; actual SDK call returned non-error useful fallback (1,308 text characters); lazy resource rendered a single inline module. This is **not** live server activation evidence. |
| Live publication / activation | Pushed `92dfca70d1f0884eaa9275e8e2605e8b04055adf` without overwriting concurrent Minesweeper additions. ToolForge logs report `runtime.catalog.applied` and `runtime.applied` at05:02:31UTC; live resource listing includes the expected URI; actual `gloaming_road()` returned its useful fallback and opened the App entry. This is not a browser observation inside the unavailable Harness GUI. |
| Seed/seam source checks | Ad-hoc execution for `silver-thistle`, `elderflower`, `rowan-7`: repeated chunk hashes identical; shared negative/zero chunk-edge height and normal differences exactly0; nine castle-floor samples exactly match the seeded foundation; ordinary encounters omit blood-event IDs. Not a substitute for travel. |
| Woodland traversal | Held WASD through the ordinary handlers, including a reload/Continue, reached x−62.6837,z−172.2057,y6.5668 at clock529 with100HP. Seen live: biome/fog/ground-cover transition, solid trees, a human armored swordsman approaching and a burgundy archer behind. About190m of actual on-foot route, not a teleport. |
| First new journey | Enter → seed → Begin reached playing with pointer lock and visible textured world. Initial failures were caught and fixed, below. |
| Audio activation | Real click path after scene-reset ordering fix reached play with no Enable sound retry indication. IR mismatch fixed using a correctly resampled live-context buffer. No listening claim. |
| Initial movement / save | Real held W input moved the capsule from the safe start to approximately x−0.0033,z−4.4981,y4.9069; local save contained health/stamina100, seed `silver-thistle`, clock402.8333, one recent encounter. Low software FPS throttled simulation; this was a short route, not long-travel evidence. |
| Pause and resume | Actual Escape released capture; the following rendered capture shows the pause menu, seed and deliberate Return button. Immediate CDP evaluation can precede the asynchronous pointerlockchange; the rendered/awaited state is authoritative. Resume accepted a click and recaptured. Focus-loss event path also paused. |
| Reload / Continue | Reload of the production page exposed Continue and resumed the saved world. Extended exact-coordinate/mission reload comparisons remain pending. |
| No implicit saved journey | In a fresh isolated Chromium browser context, opened the actual production page, waited for its title, navigated away and reopened. IndexedDB `current` was absent before and after (`null → null`); context was disposed. No Begin/Continue or direct state write was used. |
| Keyboard guard / pause | Actual left guard pose captured; a charged empty swing consumed stamina. After J/K keyboard input, Escape now releases pointer lock **and** reaches paused, rather than only releasing capture. |
| Positional dodge | Separate idle Space press moved the capsule from approximately(0,0) to(0.5767,−0.8976), about1.067m including ordinary velocity damping after the0.9m impulse. It consumed stamina and did not change health; not a claim of tested invulnerability (none is implemented). |
| Played caster fight | Approached on foot, saw staff/charge/visible fire, attempted a counter that was interrupted and lost24HP. Re-established physical range: a right light cut reduced saved mage health64→40; the subsequent charged strike reduced40→0 and set its ordinary dead snapshot. Player ended76HP. Normal mouse/keys only; no injected health, death, teleport, or hit result. These are functional observations, not a60FPS feel claim. |
| Return and rest | Walked about43m back to the visible hearth prompt, pressed E: health/stamina100, recovery `silver-thistle:rest:spawn` at(0,0), clock598.6833; the defeated mage remained dead in the local snapshot. |
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

8. **Recovery stream race:** Wake Again actually stalled at “Returning to a quiet place” after death in the distant woodland. The frame loop was recentering streaming on the old player while preparation requested the hearth. Loading now owns its destination, and health is restored only after the destination is ready/teleported. A direct distant-death/Wake Again retake is still pending.
9. **Keyboard and rapid Escape capture loss:** native Escape can be consumed by pointer lock. Capture loss now pauses regardless of the last input device, including an immediate click→Escape where lock-change notifications coalesce. Both the keyboard path and rapid click/Escape were exercised successfully after correction.
10. **Title preview must not save:** preview construction and partially replaced worlds are no longer eligible for persistence. Only a successfully entered/continued journey writes; leaving title alone passed the isolated-context check above. Incompatible-save messaging no longer offers an unimplemented export control and explicitly warns that New World replaces it.
11. **Presentation/contact corrections:** both sides of flower cards use their authored upward diffuse normal, rather than black flipped undersides; actual balanced rendering compiled with no recorded browser errors. Flame ground rings now use the actual ground/castle floor and paired forms respect the8-form cap. Nearby fire-burst LOS now tests the player, not a mistakenly reused velocity vector. The latter contact corrections still need their targeted replay.
12. **Meaningful sound captions:** replaced the unused dialogue toggle with selective, distance-culled sound cues, available while muted. Actual UI sequence set Master volume0 and triggered Rest: “Rest chimes” appeared in the HUD; captured at640×400 balanced resolution, with no browser errors. Written dialogue remains independent. Physical screen-reader audition remains unverified.

Further source tuning: committed royal attacks resist light-hit interruption (heavy hits/parries can still interrupt); the authored princess talk clip now advances during dialogue. Static menus/loads render at a reduced cadence while their DOM/input remain responsive; normal play is not frame-throttled. Royal/talk acceptance is still part of the pending castle playthrough.

## Measured performance limitation

SwiftShader is software emulation, not an ordinary laptop GPU. Earlier balanced/soft builds at480×300 internal resolution had12-frame median600ms / worst833ms. The original GPU profile recorded about42.2s in GPU work over roughly44s, versus about1.25s in main animation callbacks, with most display frames dropped. A prior JS heap sample was207.5MB; it is not total memory or a proven bound.

After a fresh browser session, byte-format render target, simpler soft-quality foliage/terrain shading and anisotropy reduction, a15-frame sample at480×300 measured **median466.7ms / worst650ms**. That is still inadequate for normal responsive play and **does not meet the60FPS target**. It is not presented as a hardware result, a stable benchmark, or proof of a leak-free long run. High-quality captures likewise do not prove real-time performance. Further functional exercises use clearly noted smaller viewports; a physical integrated-GPU pass remains necessary.

## Still pending / not claimed

- Browser-observed startup/capabilities in the actual MCP App host (live publication, activation and main tool call are complete).
- Played directional duel: all sectors, clean hit/miss, correct/late/wrong guard, feint, heavy guard pressure, wall contact, two-actor coordination, shield flank, archer flight and mage burst.
- Ordinary input route through woodland, across multiple chunks/origin shifts, and into the actual castle/royal room.
- All three durable elite defeats, final acknowledged conversation, continued exploration and mission reload without replaying completed guards.
- Death/recovery, save replacement/cancel, multiple seeds, long bounded-streaming/cleanup runs.
- Ordinary night, genuine seeded blood moon and subsequent dawn with an engaged surviving mage.
- Comparative captures A–E and castle interior/exterior on a final frozen build.
- Physical controller; Firefox/Safari; headphone and speaker audition; reliable reference soundtrack matching; native media-loop gap checks.

No debug panel, teleport menu, forced-completion control, hidden verification mode or test-only game logic is shipped. Temporary browser drivers dispatch real keyboard/mouse input to the ordinary handlers; they do not write world state or mission flags. Read-only IndexedDB inspection confirms persisted observations. Source-based math/resource checks are labelled separately from played evidence.
