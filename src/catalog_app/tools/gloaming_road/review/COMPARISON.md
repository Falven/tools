# Visual comparison record — development and completed-mission captures

These are **actual, unaltered in-game captures**, not asset turntables, mockups or painted-over images. Historical A–E views and the completed candidate355 mission gallery below are **not final415 frozen-build captures or a complete acceptance set**. All five main views use a640×400 viewport and the low-detail320×200 game target, with native-resolution UI. The separate muted-caption view uses balanced640×400 rendering. Mission355 remained unchanged after its normal reload/Continue in359; its native-input, read-only-save run was source-planned and pause-assisted on SwiftShader, without state injection, HTTP reload or source changes during the run.

Candidate415 passed strict TypeScript/build (24.68MiB HTML,12.03MiB gzip) after that mission. Actual normal reload/Continue in418 preserved the rescue save and exercised healthy native-media start/Pause. Its code release `ad121301be2f71da3328e47a0656a4fd28d065e4` was catalog/runtime-activated at10:50:56 UTC on5 October2026, followed by a successful live main-tool invocation and expected resource listing; see the [publication record](<src/catalog_app/tools/gloaming_road/VERIFICATION.md#published-candidate415>). Subsequent documentation-only revisions do not change the bundle. None of this is a whole-mission415 replay or makes the older pictures415 captures.

The reference is Bani’s [Before the Sun Sets](https://store.steampowered.com/app/4214710/Before_the_Sun_Sets/). Its public media is labelled early development. The [reference ledger](<src/catalog_app/tools/gloaming_road/REFERENCE-NOTES.md>) distinguishes directly inspected stills, supplied video observations, inferred techniques and original adaptation decisions. No reference image, model, texture or recording is used in the game runtime.

## A — Flower country and distant layering

![Actual flower-country approach](<src/catalog_app/tools/gloaming_road/review/A-meadow.png>)

Compare with the [flower-overlook still](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/4214710/9736612c1d1ae6aafdd68ccb1b5a72ade6dfcd66/ss_9736612c1d1ae6aafdd68ccb1b5a72ade6dfcd66.1920x1080.jpg).

- Present: tall pink spires with green leaf layers, textured ground, mixed tree silhouettes, broad pale clouds, mountain layers and a narrow right-side steel blade.
- Difference: this lower-resolution development capture is coarser and its canopy forms more regular than the reference. The castle is not visible in this particular frame. A final castle-role composition remains required.

## B — Woodland enclosure

![Actual woodland entered on foot](<src/catalog_app/tools/gloaming_road/review/B-woodland.png>)

Compare with the environment behind the [woodland-knight still](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/4214710/4331eeae821e64fcffe6a9cd45ef12505b92578e/ss_4331eeae821e64fcffe6a9cd45ef12505b92578e.1920x1080.jpg), and the supplied3:07–3:11 study observation in the ledger.

- Present: a real walk into green ground cover, shrubs, trunks and overlapping fogged canopy layers; trees are solid obstacles.
- Difference: this grove reads greener, rounder and more evenly spaced than the cooler reference woodland. The conifer approach needs its own final comparison view. This still does not establish smooth travel or absence of streaming artifacts elsewhere.

## C — An articulated armored opponent

![Actual blocked steel contact with an armored royal](<src/catalog_app/tools/gloaming_road/review/C-armored-contact.png>)

The earlier [woodland approach frame](<src/catalog_app/tools/gloaming_road/review/C-armored-human.png>) is retained separately.

Compare with the [woodland-knight still](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/4214710/4331eeae821e64fcffe6a9cd45ef12505b92578e/ss_4331eeae821e64fcffe6a9cd45ef12505b92578e.1920x1080.jpg) and the supplied newer exchange observations at1:30–1:34 and2:18–2:24.

- Present in the newer candidate355 frame: a full articulated royal, narrow visor, layered armor, belt/cloak, player and opposing steel, localized smaller sparks and the actual “Blow blocked” feedback during combat. This closes the previous approach-only gap for a blocked-contact composition, **not a confirmed parry**.
- The encounter subsequently ended with the first royal's durable defeat and the player at35HP. Some intended charges were blocked or interrupted; the screenshot does not prove every attempted heavy landed.
- Difference: this is a dim blood-night castle threshold rather than the reference's brighter woodland. Low-resolution capture and differing light remain important comparison limits. It is not proof of60FPS swordplay feel or complete four-sector combat coverage.

## D — Burgundy archer in the flowers

![Actual wounded archer continuing its bow action](<src/catalog_app/tools/gloaming_road/review/D-archer.png>)

The comparison target is the supplied Steam-trailer observation at approximately10–24s; no fresh video viewing is claimed.

- Present: an articulated burgundy/gold archer, exposed curved bow and string, face/hands, full-body scale against the flowers and the player’s sword.
- Functional observation from this encounter: guarded incoming arrows without losing health, then a physical heavy cut reduced56HP to16; a following light cut defeated the archer. The player remained100HP.
- This frame is after the heavy hit, not a clearly isolated in-flight projectile. A final release/flight view remains useful.

## E — Dark caster and charge contrast

![Actual dark caster charging on approach](<src/catalog_app/tools/gloaming_road/review/E-caster.png>)

Compare with the [hooded-mage still](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/4214710/d7a8331afd7a401fcb4bd88d7e9a4d55d411153d/ss_d7a8331afd7a401fcb4bd88d7e9a4d55d411153d.1920x1080.jpg) and [broad-fire still](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/4214710/33a62ee0cde60ce77b31fc94c703da0084d83596/ss_33a62ee0cde60ce77b31fc94c703da0084d83596.1920x1080.jpg).

- Present: near-black hooded body, staff, bright charge contrast, tall vegetation and first-person steel.
- **Not yet closed:** this is an ordinary daytime charge, not a blood moon, a narrow projectile or a broad fire burst. Separate ordinary-woodland and naturally reached blood-moon/impact views are still required. Spark geometry was subsequently reduced and close contact placement refined; this older charge frame does not show that refinement.

## Supplementary functional feedback

### Arrow block before the spark refinement

![Actual guarded arrow contact before smaller sparks were implemented](<src/catalog_app/tools/gloaming_road/review/arrow-block-before-refinement.png>)

A real guarded arrow consumed stamina and left health unchanged. The large near-camera streaks in this frame motivated smaller, proximity-limited spark geometry and blade-anchored defensive contact. This is the **before** image, not validation of the subsequent change. Its historical short-range caption reads “Arrow released” rather than the contact cue. Subsequent urgent-contact priority passed component checks; this old image does not show that correction, and selected captions can still throttle closely spaced equal-priority cues.

### Muted sound captions / balanced flowers

![Actual rest cue with Master volume set to zero](<src/catalog_app/tools/gloaming_road/review/muted-caption-balanced.png>)

Master volume was set to0 through the actual settings UI; pressing E at the hearth showed “Rest chimes.” Balanced flower rendering compiled with no recorded browser errors. This establishes the visual caption path, not an audio audition or screen-reader listening check.

## Naturally reached hearth, blood night and castle

![Visited conifer hearth acknowledged with E Rest](<src/catalog_app/tools/gloaming_road/review/hearth-rest.png>)

The fresh persistent journey reached this hearth through approximately1.01km of checked on-foot segments, following a source-planned route. The visible Rest action registered a real recovery point. It is not blind-discovery evidence.

![Natural blood-night atmosphere at the same hearth](<src/catalog_app/tools/gloaming_road/review/natural-blood-night.png>)

Time advanced through ordinary unpaused gameplay; no clock or state injection produced this sky. This frame shows atmosphere and the hearth, **not a moon-disc close-up or a caster fight**.

![Actual castle exterior and red moon](<src/catalog_app/tools/gloaming_road/review/castle-exterior-blood.png>)

![Opened exterior gate revealing the courtyard and hall](<src/catalog_app/tools/gloaming_road/review/castle-gate-open.png>)

These candidate355 views were reached through ordinary movement and E Open. They show the actual red moon disc, original stonework/towers, opening gate, courtyard and the hall ahead. The player then crossed the courtyard, climbed the stairs, opened the hall and fought the royals. “Door creaks” is caption evidence, not an audio audition. Neither exterior frame by itself establishes final rescue; the later completed mission is documented below.

### Natural dawn after the second ordinary recovery

![Naturally elapsed dawn at the conifer hearth on candidate355](<src/catalog_app/tools/gloaming_road/review/dawn-hearth.png>)

The archived, unaltered image shows lavender clouds and green conifers after naturally elapsed clock1800. The second ordinary Wake Again returned here at clock1808.6333333320322 with100HP/100stamina and both earlier royal defeats/open doors preserved. It is dawn-atmosphere evidence, **not ordinary non-blood-night coverage or proof of an engaged mage surviving across dawn**.

Two real deaths occurred during this persistent mission run; both normal Wake Again recoveries succeeded. Input job396 was carrier-killed during the second death's attempt; cleanup397 exited0 and found0HP at clock1807.9666666653661. The full intended396 sequence and missing capture34 are not claimed. This image is not evidence for an unobserved attack or a game crash.

## F — Completed mission and post-rescue continuation (candidate355)

All three royals were killed through normal play by clock1892.8999999986222, leaving35HP/58stamina. This is the completed unchanged355 run, not a source-triggered victory or a415 capture. All images in this section were archived unchanged and inspected by the parent.

### Princess conversation — before final acknowledgement

![Actual princess conversation before final acknowledgement](<src/catalog_app/tools/gloaming_road/review/F-princess-conversation.png>)

Normal E Talk opened the first “For so long…” beat; Continue advanced to “You came. I’m safe now. Thank you.” This chamber/conversation frame is **before the final acknowledgement**. It is not used alone to assert the rescue flag, return of player control or completed music cadence.

### Rescue — after final acknowledgement

![Actual rescue after the final Continue acknowledgement](<src/catalog_app/tools/gloaming_road/review/F-rescue-acknowledged.png>)

A second Continue acknowledged the final beat and returned to playing with pointer capture. The announcement was “Elowen is safe. The world remains open to you.” Read-only save inspection—not the image alone—confirmed all three defeated royal IDs and `rescued:true` at clock1898.9166666652834, position `(-388.3320026398,77.0471502686,810.5286712646)`,35HP/100stamina.

Native media inspection immediately after acknowledgement found four media elements, one running44.1kHz context, and a35.010667s rescue cue playing non-looped at3.493333s. After a requested40s ordinary unpaused wait, that cue was paused/reset and the ordinary120.010667s loop was playing at13.36s. This is transport/handoff evidence, **not an observed `ended:true`, audition or gapless transition proof**; the screenshot itself cannot establish any sound.

### Continued exploration and in-App persistence

![Actual post-rescue continuation on unchanged candidate355](<src/catalog_app/tools/gloaming_road/review/post-rescue-continued.png>)

Actual post-rescue movement changed position from `(-388.3319354057,77.0444342041,810.5316123962)` to `(-388.9192280769,76.7445303345,814.4881668091)` at clock1916.1166666652678. In-App **Save/Quit → Title → Continue** preserved the exact stored clock/position/mission and resumed playing/capture with35HP and no displayed error. Further W movement produced final save410 at clock1919.116666665265, position `(-389.21464109420776,76.74033416748047,816.4669189453125)`,35HP/100stamina, all three royal IDs defeated, rescue true and both doors open. The registered conifer-hearth recovery remained unchanged.

The run ended normally paused, pointer released, displayed error empty, all keys released and all input jobs collected. The still demonstrates its scoped later view; movement and durable mission state are supported by the native-input/read-only-save record in the [completed mission ledger](<src/catalog_app/tools/gloaming_road/VERIFICATION.md#completed-candidate355-castle-mission-and-recovery>). **Core castle mission, both recoveries, final acknowledgement and in-App post-rescue persistence are complete on355**, not pending. In-App Continue is not an HTTP reload of415.

## Final415 reload and empty-hall input scope

![Actual final415 hall after resumed movement, with sword and native HUD](<src/catalog_app/tools/gloaming_road/review/final-build-continued.png>)

This640×400 low-detail frame is the byte-identical archived419 moved capture, inspected by the parent; its reported content digest is `1bef64210b18076234da6183c29fe0a7880a4bb4f0e74924af55eae4e3ab60a2`. It shows the hall, sword and native HUD after resumed movement, **not combat or a held guard pose**. Native K guard input was sent during the check, but reviewed post-release sword views are idle; no captured guard pose is claimed.

Actual browser check418 exited0. The existing production preview at `http://127.0.0.1:4174/` returned HTTP200; normal page reload loaded415. Before reload and afterward at Title, the save was exactly identical: clock1919.116666665265, player `(-389.21464109420776,76.74033416748047,816.4669189453125)`, yaw2.9942,35HP/100stamina, all three royal defeats, rescue true and gate/hall open. Continue reached playing/canvas capture with no displayed error, audio retry hidden and two healthy native Ogg loops. Normal Pause released capture and saved clock1920.93333333193 at `(-389.2146301269531,76.74452270507813,816.4669227600098)`,35/100, mission unchanged. Tiny physics settling after Continue is not exact post-simulation coordinate equality.

Native follow-up419 exited0: Resume/capture, Digit2/K guard input, a J light swing and W movement occurred in the empty hall. During play, HUD health was35 and stamina90 after the light cost/regeneration, with no displayed error. About3m of real W movement produced a normally paused, pointer-released save at clock1925.8499999985922, player `(-389.6559753417969,76.74400390625,819.4325408935547)`, yaw2.9942,35/100, all three royal defeats, rescue true and both doors open. This is **empty-hall input/movement smoke**, not a hit, parry, duel or physical-controller test. It does not turn the355 mission images above into415 captures.

## Still required for the final set

- Final frozen415 A–E retakes, including ordinary/blood-moon caster circumstances. Earlier A–E and the355 mission frames remain historical evidence, not relabelled final captures. The355 blocked steel-contact frame is not a confirmed clean parry.
- Full four-sector, clean-parry, feint, shield, wall and ranged/combat coverage. Successful royal fights and earlier individual archer/mage exchanges do not complete that matrix.
- Ordinary non-blood night and an engaged mage across dawn. Natural blood-night atmosphere, the red moon and later natural dawn are now shown, without combining them into an unseen continuous fight.
- Publication/activation of415 and actual MCP-host CSP/controls. Normal standalone reload/Continue, exact pre-/post-reload Title save preservation, native media start and Pause were actually observed in418; that is not a whole-mission415 replay. The actual Harness GUI at `http://127.0.0.1:3001` was freshly rechecked as `ECONNREFUSED`; no replacement GUI was used.
- Extended quantitative streaming/cleanup/leak bounds, hardware60FPS, physical controller, other browsers, headphone/speaker and reference-audio audition. Still images, component fixtures and transport checks cannot establish these.

The played355 “Armor struck” notice before contact was a semantic error;415 suppresses that notice before urgent-caption bookkeeping while keeping real armor-contact captions. Isolated corrected DOM/gamepad/caption fixture414 passed, not a browser/physical-controller replay. See the [verification ledger](<src/catalog_app/tools/gloaming_road/VERIFICATION.md>) for the exact completed evidence, historical failures and remaining limits.
