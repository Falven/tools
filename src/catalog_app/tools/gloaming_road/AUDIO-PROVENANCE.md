# The Gloaming Road — original audio provenance and integration

## What this is — and is not

All 106 audio assets were composed or synthesized specifically for this project from mathematical oscillators, coloured noise, envelopes, resonators and original event arrangements. There are **no recordings, soundfonts, sample packs, downloaded reference tracks, source-game assets, or external runtime audio dependencies**. NumPy/SciPy render the sound offline; the browser plays the rendered local files. There is no runtime musical note sequencer or repeated-note/drone substitute for the score.

**This is not a verified source soundtrack, a transcription, an auditory reconstruction, or a claim of auditory matching. No headphones, speakers, or listening tool were available to the audio agent.** Signal measurements establish file integrity, headroom and structural differences—not musical beauty, perceptual realism, or fidelity to another game. Human audition remains explicitly required below.

The work is project-original generative composition/sound design. No third-party audio attribution or recording licence is being claimed. Tool/library licences remain their respective owners' licences.

## Editable source and reproduction

- [render.py](<src/catalog_app/tools/gloaming_road/audio-source/render.py>): composition builder, instrument models, sound design, circular reverb, mastering and dual-codec export.
- [score.json](<src/catalog_app/tools/gloaming_road/audio-source/score.json>): editable timed note/event score; 1,410 individual arranged events. Existing edits are preserved on ordinary render runs.
- [measure.py](<src/catalog_app/tools/gloaming_road/audio-source/measure.py>): independent re-decode, hash/size checks, peak/RMS, 4× oversampled peak estimate and material spectra.
- [measurements.json](<src/catalog_app/tools/gloaming_road/audio-source/measurements.json>): complete measured delivery report.
- [manifest.json](<src/catalog_app/tools/gloaming_road/frontend/assets/audio/manifest.json>): every asset's group, duration, channels, sample rate, source PCM bytes, sample peak/RMS/DC, loop-boundary step, and per-encoding bytes, SHA-256, actual decoded duration and measurements.
- [catalog.ts](<src/catalog_app/tools/gloaming_road/frontend/assets/audio/catalog.ts>): generated static local asset imports and a compact runtime manifest.
- [audio.ts](<src/catalog_app/tools/gloaming_road/frontend/audio.ts>): the parent-facing `GameAudio` implementation.

From the workspace root, using the already installed environment:

```sh
.venv/bin/python src/catalog_app/tools/gloaming_road/audio-source/render.py
.venv/bin/python src/catalog_app/tools/gloaming_road/audio-source/measure.py
```

Optional `--only music`, `--only ambience`, or `--only effects` re-renders just that category and rebuilds the manifest/catalog. **`--rewrite-score` deliberately replaces score edits** with the original composition builder. The fixed seed is `20261005`; encoding uses ffmpeg 7.0.2-static through `imageio_ffmpeg.get_ffmpeg_exe()`, libvorbis/libmp3lame and bitexact flags. A separately rendered grass-step variation was confirmed byte-identical in both codecs on this environment. No temporary PCM exports are retained.

## The miniature consort score

The original five-note cell is **D4–F4–E4–A4–C5**. Its wider modal palette is D Dorian, with open fifths, added seconds, occasional B-natural colour, and incomplete cadences. It is a project-original motif, not a quotation. Phrase variants change direction, register, note lengths, omitted beats, replies and endings. Low organ chords breathe and leave gaps; they are not a single endless held drone.

| Cue | Duration | Form and orchestration | Playback |
|---|---:|---|---|
| Title | 60 s | 16 slow 3/4 bars; first plucked invitation, answering reed, quiet open return; 113 events | Loop, `cue('title')` |
| Meadow | 120 s | 32 slow 3/4 bars; eight varied phrases, irregular lute figures, middle-section countervoice, glass harmonics and sparse seed percussion; 276 events | Exploration loop |
| Forest | 120 s | 32 slow 3/4 bars; lowered reed, separated organ breaths, muted bass viol and distant high replies; 209 events | Forest/bloodmoon loop |
| Duel | 64 s | 32 4/4 bars at quarter-note 120; fractured motif calls, measured frame drum, wooden knocks, turnaround rests; 352 events | Threat loop |
| Royal | 64 s | Separate 32-bar ceremonial form, antiphonal reeds, broader organ voicing and late rising answers; 403 events | Royal encounter loop |
| Rescue | 35 s | Through-composed seven-breath rising answer, suspended second and quiet return; 57 events | One-shot, `cue('rescue')` |

The slow 3/4 exploration/title quarter-note tempo is 48 BPM. The palette comprises soft plucked harmonic strings, additive reed/breath voices, a small organ consort, a low bowed-tone analogue, restrained glass-like harmonics, frame drum, seed/shaker and wooden knock. Attack/release envelopes, harmonic-specific damping, very small rendered detuning, deterministic level variation, panning and offline stereo reverb are baked into the assets. Loop reverb wraps its tails circularly, and boundary correction does not insert a silent beat. Rescue has a composed ending and a 2.8-second final release.

Bloodmoon deliberately reuses the forest arrangement under a veiled music filter and the night field. It is not represented as a seventh unique composition.

## Ambiences and 93 discrete sounds

Five **24-second stereo loops**: wind, meadow, forest, night and castle. They use periodic spectrally coloured wind, unequal slow gust cycles, canopy/grass layers, sparse synthesized birds, insect groups separated by quiet intervals, and distant castle drops/reflections. Their musical/ambient spaces are different assets rather than equal-volume copies.

Canonical `play()` group names choose a rendered variation without immediately repeating the previous one. Exact suffixed IDs such as `step_grass_3` also work. Hyphens, dots, slashes and spaces normalize to underscores.

| Groups | Variations per group | Design distinction |
|---|---|---|
| `step_dirt`, `step_grass`, `step_stone`, `step_wood` | 4 each | Grit/weight; brushing blades; brief hard click/sole; resonant plank body |
| `cloth`, `leaves`, `bird`, `bird_night` | 3, 3, 4, 2 | Folded fabric, dry small leaf clusters, irregular chirp contours, low two-part night call |
| `whoosh_light`, `whoosh_heavy`, `miss` | 3, 3, 2 | Fast airy edge, longer low displacement, unconnected pass |
| `parry`, `block`, `shield`, `armor`, `flesh`, `enemy_death` | 3 each | Long high metal ring; short braced contact; low shield body; several small plate contacts; damped low tissue impact; breath/cloth/body fall |
| `shield_break` | 1 | Low failed structure plus splintering transients |
| `bow_draw`, `bow_release`, `arrow_pass`, `arrow_impact` | 2, 3, 3, 3 | Tension/creak, string twang, narrow fly-by, shaft strike |
| `arrow_wood`, `arrow_stone`, `arrow_flesh` | 2 each | Wooden modes, short bright stone contact, damped soft impact |
| `fire_charge`, `fire_release`, `fire_travel`, `fire_impact`, `fire_linger` | 2, 2, 2, 3, 1 | Growing pressure, initial expulsion, moving turbulent body, bass impact/crackles, finite 2.8-second residual fire |
| `door`, `latch`, `rest`, `ui`, `ui_confirm`, `ui_cancel`, `death`, `respawn` | 2, 2, 1, 2, 1, 1, 1, 1 | Wood/hinge closure, metal catch, recovery cadence, short selections, descending death and returning respawn cells |

There are also one **1.35-second original room impulse** and one silent 0.25-second media-element activation primer. The death sounds contain no sampled human voice. Fire travel/linger are bounded one-shots, not unmanaged looping sources.

The parent's existing names are mapped, including `swing-heavy`, `swing-light`, `impact-stone`, `impact-wood`, `hit-flesh`, `death-enemy`, `step-stone`, `step-grass`, `step-dirt`, `step-wood`, `fire-charge`, `fire-release`, `fire-impact`, `bow-draw`, `bow-release`, `cloth`, `armor`, `shield`, `parry`, `block`, `door`, `rest`, `ui` and `respawn`. `SOUND_NAMES` exports the canonical groups.

## Local payload and measured headroom

**All 212 compressed files together: 5,932,787 bytes (5.933 decimal MB).**

| Category | Asset count | Ogg bytes | MP3 bytes |
|---|---:|---:|---:|
| Score | 6 | 2,399,363 | 1,391,762 |
| Ambiences | 5 | 778,118 | 362,232 |
| Discrete effects | 93 | 570,582 | 404,755 |
| Room impulse + silent primer | 2 | 16,743 | 9,232 |
| **Total** | **106** | **3,764,806** | **2,167,981** |

Primary Ogg/Vorbis uses 24 kHz, stereo for score/fields and mono for spatial effects. Vorbis quality is −1 to meet the self-contained payload budget. Every asset has a local MP3 fallback; long-form MP3 is 24 kb/s mono, while short effects use 40 kb/s. **Mono fallback trades stereo ambience/score width for payload/browser compatibility**; positional effects still use the Web Audio panner. Base64 embedding necessarily expands the audio portion of the HTML/JS beyond the compressed-file size (about 7.9 MB before code/minification).

Observed offline measurements on all 212 delivered files:

- All SHA-256 and byte counts agree with the manifest; no integrity/peak problems remain.
- **Zero full-scale clipped samples.** Highest decoded sample peak: **0.7226756**. Highest 4× oversampled estimate: **0.7280001, −2.757 dBFS**. The latter is a SciPy/Kaiser estimate, not a certified ITU true-peak measurement.
- Score source RMS is approximately −20.7 dBFS and source peaks remain at/below 0.47; primary encoded score peaks remain below 0.48. Ambient source RMS is around −24 dBFS.
- Both encodings of every long score/ambient asset decode to its advertised full duration. Short Vorbis final packets can pad/trim a one-shot by up to **20.667 ms**; **actual codec durations are separately recorded**, and the runtime uses `AudioBuffer.duration`, not a guessed source duration. Runtime one-shots add a 3 ms start ramp and 12 ms end ramp to guard lossy-codec edge ringing.
- All long-loop source endpoint steps are zero after boundary correction; per-codec residual steps are recorded. Native media-element looping, especially fallback MP3, still needs human/browser boundary audition. A zero source endpoint step is not proof of an inaudible browser loop seam.
- Mean measured primary footstep spectral centroids differ: dirt ~2,183 Hz, grass ~4,248 Hz, stone ~3,524 Hz, wood ~1,254 Hz. Parry concentrates in higher ringing modes while shield/body contacts retain lower energy. These numbers demonstrate signal differences, not successful perceptual material recognition.

## Runtime resource and lifecycle contract

`GameAudio` exports the requested constructor and `load`, `unlock`, `settings`, `mix`, `listener`, `play`, `cue`, `pause`, `resume`, `clear`, `rebase`, `dispose` methods, plus `diagnostics` and readonly `playbackReady` / `activationPending` getters. `diagnostics.activated` means prior successful priming, not current playback. The parent bases retry visibility on confirmed playback or pending activation, not merely a running context; neither getter claims audible device output.

- **Loading is silent.** `load(progress)` warms 20 small effects/IR items in an `OfflineAudioContext`; it creates no live audio graph and never starts media. Decoding concurrency is 2 with a bounded queue. Embedded data URLs decode directly from base64; only same-origin unbundled development assets use fetch. Essential preload failures produce an explicit `diagnostics.lastError` with asset IDs and recovery guidance, rather than silently reporting ready.
- **First sound requires a real gesture.** Invoke `unlock()` directly in the parent's trusted click/touch/key handler, before any unrelated `await`; complete synchronous old-scene disposal/`clear()` first. The method checks active browser user activation (trusted-event fallback for older engines), resumes the live context and first-primes the same four elements inside that gesture. One activation owner serializes overlapping unlock/resume/mix requests; successful priming is reused rather than repeated. Lifecycle epochs make stale completion inert. Activation and track-start deadlines are10s; a real transport failure releases failed streams, exposes an actionable retry and does not retry every frame. Cancellation is not presented as a new playback failure. Explicit retry can select the MP3 fallback. The boolean return does not bypass autoplay policy; `resume()` cannot perform first activation.
- **Four reusable media players maximum:** two music and two ambience during crossfades. Ordinary exploration uses one of each. Long assets never enter the effect PCM cache. Crossfades are 2.5 s music, 3.1 s ambience and 1.3 s into rescue. Old decoder sources are released after the fade.
- Decoding every source would occupy **118,953,576 bytes of float32 PCM** at 24 kHz. Instead the LRU is capped at **40 effects / 8 MiB**, with at most **24 live finite effect sources**, 12 pending play requests and 2 concurrent decodes. The tiny room impulse is separate. Media-element streaming buffers are browser-managed; no claim is made that all browser-owned native media memory fits a specific PCM number.
- Master/music/ambience/effects buses have ramped settings, fixed headroom trims, a master compressor and a conservative final ceiling curve. The optional effects room is light outdoors and slightly stronger indoors. **Convolver impulses must match the actual live sample rate**: the 24 kHz original IR is separately resampled with a silent offline renderer to the live context's rate and cached; `clear()` reuses that matching-rate copy. Dry effects remain available while it is prepared.
- `mix()` prioritizes royal, then threat/duel, then biome exploration. Actual `conifer` terrain selects forest music/field; `upland` selects meadow music/wind field. Night/bloodmoon select night ambience; interiors select castle ambience. `cue('title')` is left at the next gameplay `mix()` and does not itself unpause a deliberately quiet title. `cue('rescue')` overrides subsequent mixes for the finite35-second, non-looping cue, then returns to the latest requested world state. Pending stream changes coalesce; the outgoing track is retained until the incoming play is confirmed. Do not immediately call `pause()` on a victory screen if the rescue cue should finish.
- Positional one-shots use HRTF, inverse-distance attenuation and a 75 m cull/max range. Listener coordinates are local metres, Y up, with normalized forward (normally camera −Z). `rebase(dx,dz)` **subtracts** that same origin displacement from listener, active panners and subsequently decoded pending positions; it is not movement.
- `pause()` suspends the context, pauses retained media, clears one-shots/room tails and invalidates delayed plays. Visibility loss also pauses, but visibility return does **not** automatically restart sound. `resume()` continues only a previously gesture-activated context. `clear()` additionally removes cues/streams, resets the state and cancels transient carryover. `play('death')` clears first and holds music for 2.9 s; `play('respawn')` clears before its return cue. `dispose()` also releases caches, media sources, event handlers, automation graph and the context.
- Master zero means mute; other buses remain independently adjustable. The `diagnostics` getter reports state, format, cache bytes/count, source/decode counts, active tracks, actual reverb sample rate and the last actionable error. It is not an audio-quality meter.

The production bundler must embed static `.ogg`/`.mp3` imports as data URLs. A restrictive host CSP must allow `media-src data:` for long-file media playback; embedded effects require no network/connect permission. No audio path points to a reference download.

## Verification performed and limitations

Performed by the audio agent: complete offline render; re-decode/integrity/duration/peak/spectral measurements of every codec file; byte-identical same-environment re-render of one grass variation; isolated strict TypeScript check; and in-memory esbuild with both audio extensions as data URLs. No new test suite or unrelated repository edits were added.

A parent-observed real Chromium 154/Linux production run exposed a 24 kHz IR versus 44.1 kHz live-context `ConvolverNode` mismatch during world entry. The runtime was corrected to resample only the small IR to the live rate and to guard every convolver assignment. **The parent then confirmed that New World entry succeeds in the real production browser with this fix.** This is a functional browser observation, not an auditory assessment or a complete lifecycle/memory check. At that earlier stage, isolated strict TypeScript and in-memory data-URL bundle checks also passed (7,986,382 bytes for that unminified audio module plus embedded assets); that byte count is not a measurement of the later355 or415 module. **The audio agent has not listened to any result or verified perceptual loop transparency, subjective mix balance, real-world material recognition, or Safari playback.**

From the frontend working directory, the isolated type/bundle checks are reproducible without writing a test or build artifact:

```sh
node node_modules/typescript/bin/tsc --noEmit --strict --skipLibCheck --module ESNext --moduleResolution Bundler --target ES2022 --lib ES2022,DOM --types vite/client audio.ts
node --input-type=module -e "import {build} from 'esbuild'; const r=await build({entryPoints:['audio.ts'],bundle:true,write:false,format:'esm',loader:{'.ogg':'dataurl','.mp3':'dataurl'}}); console.log(r.outputFiles[0].contents.byteLength);"
```

### Candidate355 transport and caption follow-up

Controlled asynchronous component checks covered shared priming ownership, repeated unlock/resume, coalesced transitions, rejection/timeout and explicit retry, stale pause/clear/dispose completions, conifer/upland routing, finite rescue return and urgent caption preemption. They are not browser-policy or listening evidence. Captions remain selected descriptions: urgent contact may preempt release/charge, lower-priority cues cannot immediately overwrite it, and different equal-priority events inside350ms may still be throttled.

The parent loaded actual production candidate355 through a normal reload/Continue in359. Read-only Chromium media observations in359–364 found four elements, two healthy playing Ogg loops and a running44.1kHz context; Pause paused the streams/suspended the context, and a normal later Resume continued playback. A deliberately too-rapid second mouse re-capture was browser-denied, not an audio failure: keyboard look remained usable and a fresh, spaced Resume restored pointer lock with healthy media. These observations establish transport behavior only—not audibility, output-device volume, subjective quality, gapless loops or reference matching. See the [focused verification ledger](<src/catalog_app/tools/gloaming_road/VERIFICATION.md#candidate355-follow-up-and-focused-browser-checks>).

### Actually played rescue cue and return to the world on355

The same unchanged355 page was used through the completed castle mission, two ordinary Wake Again recoveries, final acknowledged conversation and in-App Save/Quit→Continue. The run used native input/read-only save inspection at640×400 low detail on SwiftShader, with source-planned routes and pauses; no state injection, HTTP reload or source changes occurred during the mission.

After all three royal defeats, normal E Talk in407 showed the first “For so long…” beat; Continue showed “You came. I’m safe now. Thank you.” A second Continue acknowledged the final beat and returned to play/pointer capture. The read-only save contained all three defeated royals and `rescued:true` at clock1898.9166666652834,35HP/100stamina. The announcement was “Elowen is safe. The world remains open to you.” This is an actual mission-completion trigger, not an isolated call to `cue()`.

- Immediately after acknowledgement, native media inspection found **four media elements and one running44.1kHz AudioContext**. The rescue element had decoded duration35.010667s, current time3.493333s, `loop:false` and `paused:false`.
- After a requested40s ordinary unpaused wait, the rescue element was paused/reset and the ordinary120.010667s exploration loop was playing at13.36s. This establishes observed finite-cue handoff to ordinary music. It does **not** assert an observed `ended:true`, complete auditory cadence, gapless handoff, output-device sound or subjective quality. Normal Pause afterward saved clock1914.0666666652696.
- Normal movement and in-App Save/Quit→Title→Continue then preserved the rescue and resumed exploration without replaying the guards. See the [completed mission ledger](<src/catalog_app/tools/gloaming_road/VERIFICATION.md#completed-candidate355-castle-mission-and-recovery>) and [acknowledged-rescue image](<src/catalog_app/tools/gloaming_road/review/F-rescue-acknowledged.png>); a still image alone is not audio evidence.

### Post-mission415 caption correction — source/component scope

Played355 incorrectly displayed “Armor struck” for an approaching royal's notice foley before contact. Post-mission415 gives that notice the semantic `armor-rustle` alias while reusing the same existing audio/gain. It excludes the notice **before urgent-caption bookkeeping**; it does not add assets or guess meaning from a volume threshold. Real `armor`, `hit-armor` and numbered armor-asset contact calls still caption.

The corrected isolated DOM fixture414 passed with exit0: muted/locked notice suppression and real-contact preemption of a release cue were exercised. The first combined fixture failed only because its mock omitted `document` during `audio.dispose`; that was corrected in the fixture, not treated as an in-game failure. These are component checks, **not physical listening, actual-host observations or a browser replay of the notice/contact-caption cases**. The later415 empty-hall smoke did not involve contact.

Candidate415 passed strict TypeScript/build at24.68MiB HTML /12.03MiB gzip. Its publication/activation remains pending: the latest verified live activation is still `95d2745094ed517139e3bc96912fd82eb95f67fb` at 06:13:55 UTC, with the actual live main-tool/resource call belonging to `92dfca7`. The actual Harness GUI at `http://127.0.0.1:3001` was freshly rechecked as `ECONNREFUSED`; no replacement GUI was used.

### Final415 normal reload and native-media resume

Parent browser check418 was collected with exit0. The existing production preview at `http://127.0.0.1:4174/` returned HTTP200, and an actual normal page reload loaded415. The rescue save was exactly identical before reload and afterward at Title: clock1919.116666665265, player `(-389.21464109420776,76.74033416748047,816.4669189453125)`, yaw2.9942,35HP/100stamina, all three royal defeats, rescue true and gate/hall open.

Normal Continue reached playing with canvas pointer capture,35HP, no displayed error and the audio retry hidden. Native inspection found four HTMLAudioElements: two unused paused primers and two playing Ogg loops, readyState4/error null, durations120.010667s and24.010667s, both around2.590s; one44,100Hz AudioContext was running. Normal Pause released capture and saved clock1920.93333333193, player `(-389.2146301269531,76.74452270507813,816.4669227600098)`,35/100 with mission flags unchanged. Tiny post-Continue physics settling is not described as exact position restoration after simulation.

Follow-up419 exited0 with normal Resume/capture, Digit2/K guard input, a J light swing and about3m of W movement in the empty hall. Health stayed35; stamina was90 during play after the light cost/regeneration and100 at final Pause. The save reached clock1925.8499999985922 at `(-389.6559753417969,76.74400390625,819.4325408935547)`, yaw2.9942,35/100, mission flags unchanged, pointer released and displayed error empty. This does not establish a contact-caption replay, hit, parry or duel.

This is actual415 reload/persistence/start/Pause and empty-hall input evidence, not a whole-mission415 replay, physical-controller test, actual-host acceptance or listening session. Neither it nor the completed355 rescue transport observation replaces the human audition pass below.

## Exact human audition / acceptance pass — still required

Use headphones first at a low master setting (~0.35), then ordinary speakers. Record browser/version, output device, all four levels, codec and findings. These are **instructions for a human**, not a claim they were completed.

1. **Consent and silent load:** open/reload the App and wait without clicking. Confirm no audible autoplay. Click the actual Start/Continue control once; confirm music/field start without an error. Repeat on desktop Chromium and Safari/iOS, including a background-tab return. Check `diagnostics.lastError` and the live/reverb sample rates.
2. **Full composed phrases:** audition the complete 60 s title plus 10 s across its boundary; meadow and forest for at least 130 s each; duel and royal for at least 74 s each. Listen for the five-note cell, different phrase replies, breathing gaps, absence of harsh reed/organ aliasing, and any seam click or dropped beat at 60/120/64 s. Do not judge only the first few seconds.
3. **Finite rescue audition:** the355 mission already demonstrated non-looping rescue transport and return to the ordinary loop after a requested40s unpaused wait. A human must still trigger rescue, listen through the complete cadence and handoff, and check that it ends once without an audible gap or repeat. Verify the audible result of explicit pause; transport flags alone do not supply that judgment.
4. **Fields:** listen to each of the five 24 s ambiences for at least 50 s with music muted, then in the intended mix. Note seam pulses, overly periodic insects, piercing birds, low-frequency rumble and masking of nearby gameplay.
5. **Materials and variations:** on each of dirt/grass/stone/wood, take at least 16 steps at walking pace, then run. Compare four variants at ~450 ms spacing in isolation if necessary. Listen for weight differences, excessive repeated pattern, wood body, grass brushing and stone hardness—not just loudness. Turn 180° with a sounding enemy at ±8 m and confirm sensible lateral/front-back change.
6. **Combat distinctions:** audition light/heavy/miss, then successful parry, ordinary block, shield contact, armor contact, flesh hit and enemy death. Parry should be a sharper longer ring than block; shield should have lower body; flesh should not sound metallic. Audit crowded combat at the user's maximum intended settings for harshness, pumping or distortion.
7. **Ranged/magic/UI:** draw/release bow, pass then each material impact; charge/release/travel/impact/linger fire; door and latch; rest, selections, confirm/cancel, death and respawn. Ensure fire/cloth do not mask the contact cue and the UI does not startle.
8. **Lifecycle/resource check:** pause mid-fire and during a crossfade, resume, die, respawn, restart and dispose. Old one-shots and room tails must not reappear. Rebase the world while a nearby source rings; it must not leap to the opposite side. Exercise fast biome/threat changes. Observe ≤24 effects, ≤40 cached effects, ≤2 concurrent effect decodes and four media elements; do not infer total native browser media memory from JS cache statistics.
9. **Mix controls/fallback:** move each bus independently, test master zero, then repeat short portions using the local MP3 versions. Accept the documented mono fallback consciously or revise bitrate/payload after listening. Note any device-specific native loop gap.

Only after this pass should a human sign off subjective mix, material recognition and loop transparency. The delivered source supports revision without replacing original provenance with unsupported listening claims.
