# Game architecture

Miner Mania 3D separates a deterministic, engine-free **simulation** from the
**presentation** that shows it. The simulation owns every number in the
game; rendering, animation, audio and UI only read it, and all player intent
reaches it as commands. That split is what makes the economy testable
headlessly, offline progress exact, and saves small and safe.

```
 data/*.json ──> ContentDB ──> Simulation (SimState + systems) <── SimCommands <── Session.command() <── UI / touch / foreman
                                     │ events                                        ▲
                                     ▼                                               │
                                 EventBus ──> UI (toasts, popups), Audio, VFX        │
                                     │                                               │
 MineWorld (views, agents) <── reads SimState / runtime metrics every frame ─────────┘
```

## Layers

| Layer | Code | Depends on |
| --- | --- | --- |
| Core utilities | `game/core` (deterministic RNG, number formatting, stat curves, canonical JSON, the game-state machine) | nothing |
| Content | `game/content/content_db.gd` + `data/` | core |
| Simulation | `game/sim` | core, content |
| Session & services | `game/autoload` | simulation, engine |
| World & agents | `game/world` | simulation (read-only), assets |
| Camera, input, UI | `game/camera`, `game/input`, `game/ui` | world, session |
| Application flow | `game/main.gd` | everything above |

## Game state

`GameStateMachine` (pure logic, `game/core`) holds a base state - BOOT,
MAIN_MENU, LOADING, PLAYING, ERROR - and a stack of overlays - PAUSED,
UPGRADE, PROCESSING, OFFLINE_REWARD, PRESTIGE, SAVE, SETTINGS, TUTORIAL,
DISCOVERY, QUEST. Every change goes through an explicit transition table;
anything else is refused and logged. The `GameState` autoload is the only
place the state changes and broadcasts it on the `EventBus`.

- The simulation runs in PLAYING and in overlays that do not stop time
  (panels, tutorial, popups); PAUSED and anything outside PLAYING stop it.
- Every UI panel stands for an overlay: opening a panel requests its state,
  closing it closes the state, and a state closed elsewhere closes its
  panel. Confirmations are the only panels outside the machine.
- `main.gd` drives the flow: BOOT (data checks) -> MAIN_MENU -> LOADING (load
  or new claim, offline catch-up, threaded model preload, staged world
  build) -> PLAYING; prestige rebuilds through LOADING; ERROR shows a way
  back to the title.

## Simulation

`Simulation.tick(dt)` advances fixed systems in a fixed order: workforce,
utilities (power, hazards), mining, haulage, lift, processing, sales,
maintenance, progression. Rules that matter:

- **Deterministic**: the xoshiro128** RNG with keyed streams, no engine
  randomness, sorted iteration wherever order matters; the same seed and
  commands give the same result (tested).
- **Commands only**: `SimCommands` validates and applies every player intent
  atomically (build, upgrade, hire, research, prestige, manual swing...), or
  refuses it with an error code the UI turns into a message.
- **Buffers in seconds**: stations, silos and warehouses hold a number of
  seconds of upstream throughput, so upgrades keep flows balanced.
- **Soft chokepoints**: ore that a processing machine cannot take bypasses it
  and sells for less - production never deadlocks.
- **Automation stages** (Manual, Semi-Automated, Automated, Industrial) come
  from what runs without the player: miners, lift operators, sales managers,
  self-running machines.

`Session` (autoload) owns the running simulation: fixed 0.1 s ticks (at most
8 per frame), event forwarding, autosave every 30 s and on app pause, and the
offline catch-up.

### Offline progress

On load (and when the app returns from the background) `OfflineSimulator`
checks the elapsed wall-clock time against the last save and the highest
time ever seen: negative or impossible values, clock rollbacks, and
duplicate claims credit nothing; long absences are capped and scaled by the
offline efficiency (research and legacy upgrades raise both). The credited
time is simulated with larger steps (about 1200 steps, stock carried over
between steps so arrivals are not lost) spread over frames with a progress
bar, then summarised in **WHILE YOU WERE AWAY**. Offline results match live
play within a few percent (tested at several step sizes).

### Saves

`SaveCodec` writes a versioned envelope: JSON metadata + the state as Godot
binary (`var_to_bytes`, objects disabled) in base64, with a SHA-256 over the
payload. Version 1 and 2 saves migrate forward. `SaveService` writes
atomically (temporary file, verification read-back, rename), keeps the
previous save as a backup, falls back to it when the main save is damaged and
quarantines unreadable files so a new claim can start. Settings live in a
separate file so a bad save never loses them.

## Content

Everything the player meets is data in `data/`: 16 resources with
processing chains, 8 depths, 14 facilities and depth equipment, 7 worker
roles, 33 technologies, 40 quests plus contracts, 36 achievements, legacy
upgrades, regions, cosmetics, balance constants, the tutorial, audio
routing, the world layout and the module library. `ContentDB.validate()`
rejects duplicate ids, missing references, invalid costs and stat curves,
dependency cycles in research and quests, and assets missing from the
generated catalog.

## World

`MineWorld` builds the scene from data and the generated asset library in
named steps (the loading screen shows them) and then only reads the
simulation:

- **Rock** (`rock_builder.gd`): the cutaway face with rounded gallery
  openings for every dug depth, gallery shells with depth-specific rock and
  strata shading, the shaft.
- **Terrain** (`terrain_builder.gd`): a heightfield with flattened pads under
  every plot, dirt roads and footpaths, splat shading, distant mountains.
- **Views**: facilities (level tiers, construction sites with a ghost of the
  machine, work animations by utilisation, worn smoke, loop sounds), depths
  (lamps, supports, rails, carts, station piles, dressing, hazards, veins
  that deplete and regrow), the headframe (cage, rope and sheave driven by
  the lift), the trucks.
- **Atmosphere** per region and depth (sky, fog, ambient, sun), with render
  layers so the sun never lights the galleries.

### Placement validation

Every placed piece is a module from `data/world/modules.json` (asset,
zones, mount, solidity and clearance, rotation step, scale range,
connection points, LOD range, collision, batching). `ModuleLibrary`
validates the definitions against the asset catalog and every placement
against its constraints - zone bounds, floor/ceiling contact, rotation and
scale rules, overlaps with other solid pieces and the gallery walkway -
before it is instanced; chains (the barrier along the cut face) snap by
their connection points. `SiteLayout` validates the surface camp at every
level tier: no facility unit may clip another, the road, a footpath, a
walk stop or the cut face. The world tests build the whole mine with every
depth dug and every facility at its top tier and require zero errors.

## Agents

`MineNav` keeps an A* walk grid (`AStarGrid2D`) for the camp and for each
gallery, built from facility footprints and validated placements, and routes
between levels through the cage. `AgentManager` keeps one `WorkerAgent` per
hired worker (pooled) and the player's `Foreman`:

- A worker reads its simulation record (job, target, location, arrival time,
  resting) and acts it out: walks and rides the cage to arrive about when
  the simulation says, then mines with the tier's tool (pick, jackhammer),
  hauls sacks between the face and the station, operates, repairs,
  surveys, supervises or rests on a bench.
- The foreman walks where you tap and swings at the vein you tap; each
  swing's impact frame sends `manual_swing` through the Session, so the
  animation and the income are one.
- `CharacterRig` plays clips with cross-fades and speed matched to ground
  speed, swaps hand tools on the `hand_tool.R` socket, carries props on the
  `carry_attachment` bone and emits clip events. Crews use the ~5k-triangle
  LOD models with the shared clip library; off-screen rigs stop animating
  and distant ones animate at a reduced rate.

## Camera and input

`CameraRig` orbits a focus point; the pitch follows the focus height - a
high 3/4 view over the camp, a near-level view into the galleries - and a
drag past the camp's front edge flows down the cut face. Pan with inertia,
pinch zoom, twist rotation, focus flights, following an agent, bounds, and
see-through buildings in front of the focus. `TouchInput` turns gestures
into camera moves and taps into actions, picking veins before workers before
buildings before whole galleries.

## UI

The UI is built in code with one theme (`UiTheme`) and a vector icon set
(`Icon`), so it is crisp at any density. The HUD shows money, income,
research and legacy points, the automation stage, a level strip to jump
between the camp and the depths, the manual actions (lift, sell, rally -
they step aside once automated) and the navigation bar. Panels: facility,
depth, worker, crew, research, goals/contract/achievements, codex,
production flow (with the current bottleneck), prestige, outfits, settings,
more, pause; popups: WHILE YOU WERE AWAY, discoveries, confirmations. Toasts,
floating "+ore" texts and the tutorial coach complete it. Features appear as
the game introduces them.

## Audio and effects

Sounds are synthesised by `tools/audio/synth.py` (43 effects, music and
ambience loops, checked for clipping, DC offset and loop seams). `Audio`
pools 2D and positional players, maps simulation events to sounds and
haptics (`data/audio.json`), crossfades music and ambience between the camp,
the mine and the deep levels, and reverberates underground. `VfxLibrary`
builds pooled, mobile-sized particle effects in code (rock chips, sparks,
dust, discovery bursts, steam, drips, exhaust, motes).

## Performance

Budgets live in `data/performance.json` and are checked by the tests and by
`tools/godot/perf_report.gd`. A late-game mine (all 8 depths, every
facility, ~80 workers) measures about 0.8 ms per simulation tick and 2 ms per
frame for world and agent updates on the build machine; views draw 170-330
calls and ~0.75 M triangles with ~100 MB of texture memory. Mobile specifics:
VRAM-compressed textures capped at 1024/512 px, Godot mesh LOD instead of
pipeline LOD models, crew LOD characters, MultiMesh batching for dressing,
visibility ranges, animation throttling, threaded model preloading, and a
30/60 fps setting. Android frame pacing (Swappy) is off: on the emulator's
virtual Vulkan GPU the first present after Swappy starts fails and the
render loop stalls, while Godot's standard presentation works on Vulkan and
OpenGL ES alike.

## Testing

`tests/run_tests.gd` runs every suite headlessly (engine errors fail the
test): core (RNG, numbers, curves), content (validation catches bad data),
gameplay (commands, costs, processing, wear and repair), offline (guards,
accuracy, reports), progression (quests, achievements, contracts,
prestige, determinism), saves (round trip, migration, corruption,
checksums, timestamps), balance (pacing), game state (transitions) and world
(module definitions, camp layout, full-world placement, navigation, cage
routes, agents, the foreman, triangle budgets). `tools/godot/ui_smoke.gd`
boots the real game and plays it end to end, including memory checks
(opening every panel repeatedly and going into the mine and back must not
leave objects behind).

`tools/device/device_smoke.py` plays the exported APK on an Android device
or emulator with real touch input through adb, following the game's log
lines (`[boot]`, `[state] A -> B`, `[save] ...`): title, new claim,
tutorial, camera pan (the picture must change), pause menu, Back key,
autosaves with the claim clock advancing, background and resume in the same
process, and no crash, ANR or engine error. CI runs it on an Android 15
x86_64 emulator with software graphics: the shipped arm64-v8a APK (through
the image's ARM translation) on Vulkan and on the OpenGL ES fallback (the
emulator without Vulkan), and an x86_64 twin exported from a copy of the
same preset - `tools/apk/compare_content.py` proves it identical apart from
the engine's native library - on Vulkan.
