# Miner Mania 3D

A 3D mobile mining tycoon for Android, built with Godot 4.7. Revive an
abandoned mine: swing the pick yourself, wind the lift, send the trucks,
then hire crews, research new machines and dig deeper - from the Topsoil
Drift to the Anomaly Core - until the mine runs itself, even while the
phone is locked. Sell the claim for Legacy Points and start again in a new
region, stronger.

Every model, animation, texture and sound in the game is generated from
code in this repository (Blender and Python, headless), and the whole game
is built, tested and exported to an APK by GitHub Actions.

## What's in the game

- **A living cutaway mine**: surface camp (headframe, silos, conveyor,
  crusher, washer, sorter, smelter, refinery, generator, pumps, warehouse,
  truck depot, office, workshop) above eight hand-shaped depths, each with
  its own rock, lighting, hazards (flooding, gas, rockfalls, heat,
  radiation) and deposits of 16 resources.
- **You and your crew**: the foreman is yours to move and mine with;
  miners, haulers, operators, mechanics, engineers, geologists and
  supervisors walk, ride the cage and work where the simulation says they
  are, with animated tools and props.
- **Economy**: a deterministic production chain (mining -> haulage -> lift
  -> silos -> processing -> warehouse -> trucks) with upgrades, milestones,
  wear and mechanics on service rounds, power (the grid plus a generator,
  fed along the line so a new machine never slows the running ones),
  research (33 technologies), 40 quests, delivery
  contracts, 36 achievements, a discovery codex, prestige with legacy
  upgrades and four regions, outfits.
- **Idle for real**: offline progress is simulated on load (capped and
  guarded against clock tricks) and reported in "WHILE YOU WERE AWAY".
- **Mobile-first**: portrait touch controls (drag to pan, pinch to zoom,
  tap to mine, drag to scroll every menu), progressive disclosure UI,
  tutorial coaching, atomic saves with backup and corruption recovery.
- **Runs on entry-level phones**: Low / Medium / High graphics presets, the
  first launch picks one for the device (Low for the OpenGL ES fallback,
  under 4.5 GB of memory or an entry-level GPU) and a frame-rate watchdog
  steps down when the phone cannot keep up. Low renders 3D at 60 % with
  one-texture terrain and rock, per-vertex lighting, no shadows, MSAA or
  glow, fewer real lights and thinner scenery, at 30 fps with Android frame
  pacing - about six times cheaper per frame than the previous Low preset
  (seven times cheaper than the previous default).

## Repository map

| Path | What |
| --- | --- |
| `game/core`, `game/sim` | Deterministic simulation (pure GDScript data, no nodes): economy, systems, commands, offline simulator, saves |
| `game/content` | Content database and validation for everything in `data/` |
| `data/` | All game content as JSON (resources, depths, facilities, workers, research, quests, achievements, legacy, regions, cosmetics, balance, tutorial, audio, world layout and modules, performance budgets) |
| `game/world` | The 3D world: rock and terrain builders, facility/depth/lift/sales views, module placement validation, navigation, agents |
| `game/camera`, `game/input` | 3/4 camera rig and touch gestures |
| `game/ui` | Theme, icons, HUD, panels, popups, tutorial |
| `game/autoload` | Event bus, game state, session, saves, settings, audio, assets, telemetry |
| `blender/` | Procedural asset generators and the headless build pipeline |
| `tools/` | Asset catalog, audio and texture generators, import tuning, export filter, APK verification, CI installers, Godot tools |
| `tests/` | Headless test suites |
| `.github/` | CI: assets, validate, android, release |

## Building locally

Pinned tools: Blender 4.5.14 LTS, Godot 4.7.2, Python 3.11 with
`requirements.txt`, JDK 17+, and for Android the SDK build-tools installed by
`tools/ci/install_android_sdk.sh`.

```sh
# 1. Asset library (models, animations, LODs) - about 25 minutes
blender --background --factory-startup --python blender/build.py -- --profile full
# 2. Sounds, textures, runtime catalog
python tools/audio/synth.py && python tools/textures/texgen.py && python tools/assets/build_catalog.py --check
# 3. Import (twice: the second pass applies the mobile texture settings)
godot --headless --path . --import; python tools/assets/tune_imports.py; godot --headless --path . --import
# 4. Tests, end-to-end smoke test, performance report, frame benchmark
godot --headless --path . --script res://tests/run_tests.gd
godot --headless --path . --script res://tools/godot/ui_smoke.gd
godot --headless --path . --script res://tools/godot/perf_report.gd
#    (with a renderer: per-view frame time, draw calls and triangles per preset)
godot --path . --rendering-method mobile --resolution 720x1600 --script res://tools/godot/bench_frame.gd -- --stage early --quality 0 --check
# 5. APK (debug keystore from the Godot editor settings) and its verification
godot --headless --path . --export-debug Android build/MinerMania3D-debug.apk
python tools/apk/verify_apk.py build/MinerMania3D-debug.apk --sdk "$ANDROID_HOME"
# 6. Play it on a device: an emulator (tools/ci/start_android_emulator.sh) or a
#    phone with USB debugging (720x1280-class portrait screen)
python tools/device/device_smoke.py --apk build/MinerMania3D-debug.apk --sdk "$ANDROID_HOME" --serial <serial>
```

Run the game on desktop with `godot --path .` (mouse emulates touch; WASD /
arrows and +/- move the camera).

## Continuous integration

- **Assets** - builds and validates the asset library when its sources change.
- **Validate** - scripts, all test suites, the runtime smoke test (it plays
  every tutorial tip, scrolls a menu and moves the camera with touch
  events), render budgets per graphics preset on a software Vulkan
  renderer at 720x1600, and a balance report (pull requests; also the first
  stage of Android).
- **Android** - on every push: validate, export a debug APK stamped with a
  version code from the commit time and signed with the update key derived
  from one repository secret, `ANDROID_UPDATE_SEED` (so it installs over the
  previous build and keeps the save - see
  [docs/android_signing.md](docs/android_signing.md)), verify it
  and upload it with its reports; then play it on an Android 15 emulator
  with touch input - title screen, new claim, tutorial, camera, pause menu,
  Back key, autosaves, background and resume, an update installed over the
  running game (and over the previous build with a saved claim) that must
  keep the save - failing on any crash, ANR or engine error (report, logcat
  and screenshots are uploaded); the first launch must pick the Low preset
  there. Played: the shipped arm64-v8a APK
  (through the emulator's ARM translation) on the OpenGL ES fallback, and
  its x86_64 twin (same preset and game files, proven identical, native on
  the emulator) on Vulkan. Phones run Vulkan with Android frame pacing
  (Swappy), which the emulator's virtual GPU cannot present with, so the
  twin turns it off (an x86_64-only project setting override).
- **Release** - on a `v*` tag: an APK signed with the same update key
  (`ANDROID_UPDATE_SEED`, or a keystore of your own in
  `ANDROID_KEYSTORE_BASE64` / `ANDROID_KEYSTORE_PASSWORD` /
  `ANDROID_KEY_ALIAS`), verified and attached to a GitHub release.

No keys, passwords or tokens live in this repository; signing material comes
only from GitHub Secrets and the APK is scanned for leaks before publishing.

## Documentation

- [docs/game_architecture.md](docs/game_architecture.md) - how the game is put together
- [docs/asset_pipeline.md](docs/asset_pipeline.md) - the procedural asset pipeline
- [docs/android_signing.md](docs/android_signing.md) - updates that keep the save: the one secret to add
