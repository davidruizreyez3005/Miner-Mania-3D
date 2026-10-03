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
- **Power in line order**: the grid (65 kW: the belt, the crusher and the
  washer at full load) plus the Diesel Generator's output feed the loads in
  `balance.power.priority` order - the belt and the pumps first, then the
  machines along the line. A machine the supply does not fully reach runs
  at the share it gets (`UtilitySystem.power_factor`), so building a new
  machine never slows the belt or the machines already running; the player
  is told which machine is short (`power_short`).
- **Wear and mechanics**: working machines wear and run slower. Mechanics
  walk a service round (the workshop for parts, then every machine that
  wears: `service_s` at each stop, leaving it in full condition) and drop it
  for any machine below `service_at`, claiming jobs so two never swap
  machines; every 20 % of condition they restore counts as a repair.
- **Automation that stays on**: the lift runs by itself once an operator is
  hired for it, and sales once a sales manager is (`Simulation.on_duty`
  counts workers at their post, working or waiting for work). An operator
  waiting for ore keeps the lift - and a machine operator the machine -
  ready; on a break the winder runs at its relief pace (`lift.relief_pace`)
  instead of stopping, so the LIFT and SELL buttons never come back while
  someone is hired.
- **Haulage never slows the mine**: miners fill the face buffer as fast as
  the posted haulers (and carts) can carry it to the station
  (`TransportSystem.haul_capacity`) and carry the rest themselves at 55 %
  pace, so a hired hauler always has ore to carry and never costs output.
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
  the lift), the depot's trucks.
- **Trucks** (`SalesView`): every truck has its own bay in the depot's yard
  (`surface.truck_yard`); it loads, pulls out and turns onto the eastbound
  lane, drives off the map to the market, comes back on the other lane and
  reverses into its bay along a quarter turn. Trucks drive their whole round
  at one speed, so where each will be is known when it leaves: a loaded
  truck pulls out only when its round keeps clear of every other truck's
  (separating-axis test of the footprints along both rounds) and waits in
  its bay otherwise - automatic sales and SELL alike.
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
  hauls sacks between the face and the station, operates, services and
  repairs machines (wrench and hammer while a machine needs work, a
  look-over once it is in shape), surveys, supervises or rests on a bench.
  Work spots snap onto the walkable grid.
- The foreman walks where you tap and swings at the vein you tap; each
  swing's impact frame sends `manual_swing` through the Session, so the
  animation and the income are one.
- `CharacterRig` plays clips with cross-fades and speed matched to ground
  speed, swaps hand tools on the `hand_tool.R` socket, carries props on the
  `carry_attachment` bone and emits clip events. Crews use the ~5k-triangle
  LOD models with the shared clip library; off-screen rigs stop animating
  and distant ones animate at a reduced rate.

## Camera and input

`CameraRig` looks at a focus point from a fixed heading; the pitch follows
the focus height - a high 3/4 view over the camp, a near-level view into the
galleries - and a drag past the camp's front edge flows down the cut face.
Drags keep the content under the finger everywhere (up the screen is toward
the cut edge on the surface and deeper underground), 1:1 while the finger is
down - easing is only for flights, inertia and zoom, so the view never trails
the finger at a low frame rate. Pan with inertia, pinch
zoom, focus flights, following an agent, bounds, and see-through buildings
in front of the focus; the camera does not rotate. `TouchInput` turns gestures
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

Panels share one spacing scale (`UiTheme.GAP` between blocks, `GAP_IN`
inside a card - equal to a card's padding - and `GAP_ROW` between the
buttons of a row) and a facility reads as a column of cards: upgrade (level,
stats now > next, +1 / +10 / MAX, the next look), condition, power (the grid
and the generator, what the machine draws and whether the supply reaches
it), crew (operators, or the workshop's mechanics and what each is doing)
and a live readout with the facility's actions. The scroll bar has its own
lane (`GUTTER`, ScrollContainer reserve mode) taken out of the frame's right
margin, so content keeps equal margins and the same width whether or not a
list scrolls; the smoke test checks margins, gaps and button widths.

Every panel's list is a `TouchScroll`: a drag scrolls it wherever the finger
lands. Godot only scrolls a ScrollContainer by touch when the drag reaches
it, so the buttons, cards, bars and icons inside let pointer events pass up;
a tap still presses a button, and a drag past the dead zone cancels the
press and scrolls instead (sliders keep their drags).

The tutorial (`data/tutorial.json`, `TutorialOverlay`) shows one tip at a
time with a Next button and a marker on what to touch - a HUD button, the
control inside an open panel (scrolled into view), a vein or a gallery. A
tip completes on its game event, as soon as its `done_when` objectives hold
in the simulation (so an action done early, or from a full-screen panel that
hides the card, still counts), or with Next. A claim starts with enough
money for the first miner and the first upgrade the tips ask for.

## Audio and effects

Sounds are synthesised by `tools/audio/synth.py` (43 effects, music and
ambience loops, checked for clipping, DC offset and loop seams). `Audio`
pools 2D and positional players, maps simulation events to sounds and
haptics (`data/audio.json`), crossfades music and ambience between the camp,
the mine and the deep levels, and reverberates underground. `VfxLibrary`
builds pooled, mobile-sized particle effects in code (rock chips, sparks,
dust, discovery bursts, steam, drips, exhaust, motes).

## Performance

Budgets live in `data/performance.json` and are checked by the tests,
`tools/godot/perf_report.gd` (CPU side, late-game mine) and
`tools/godot/bench_frame.gd` (the real game drawn by a real renderer: frame
time, draw calls and triangles per camera view, per graphics preset, for a
claim early, mid or late in the game). A late-game mine (all 8 depths, every
facility, ~80 workers) costs about 0.8 ms per simulation tick and 1-2 ms per
frame for world and agent updates on the build machine.

Graphics presets (`GraphicsQuality`, data in `performance.json` under
`graphics`; Low also drops the fog's aerial perspective and sky
reflections):

| | Low | Medium | High |
| --- | --- | --- | --- |
| 3D resolution | 60 % | 80 % | 100 % |
| MSAA / anisotropic filtering | off / off | off / 2x | 2x / 4x |
| Sun shadows / glow | off / off | on (1024, 55 m) / off | on (2048, 90 m) / on |
| Terrain, rock, models | one-texture shaders, per-vertex lighting, no normal/roughness/metal/AO maps | full | full |
| Gallery lamps with real light | 0 of 4 (warm fill instead) | 2 | 4 |
| Scenery drawn / grass / its shadows | 35 % / no / no | 70 % / yes / no | all / yes / yes |
| Crew rigs at full animation rate | 8 | 16 | 28 |
| Frame cap | 30 fps | 60 fps | 60 fps |

The first launch picks a preset for the device (`Settings` and
`GraphicsQuality.detect`; the engine does not report the memory size on
Android, so it is asked from the platform through the Java bridge -
`android.system.Os.sysconf`): Low on the OpenGL ES fallback, under 4.5 GB
of memory or with an entry-level or software GPU (Mali-G31..G57, Mali-T,
PowerVR, Adreno 3xx-61x, llvmpipe, SwiftShader), High for a flagship GPU
with 7.5 GB or more, Medium otherwise.
While the choice is automatic, `FrameWatchdog` measures the frame rate in
play and steps down a level when it stays under 80 % of the cap; a quality
the player picks sticks. Presets apply live: the viewport (3D scale, MSAA,
anisotropy, mesh LOD detail, shadow atlas), `WorldMaterials` and
`MaterialLite` (shader and material features), and `MineWorld.apply_quality`
(lights, scenery, crew detail, effects, camera reach).

Always on: the sun only casts shadows from surface geometry (the galleries
underneath never enter its shadow map); scenery is batched per 24 m patch so
patches off screen are culled and far ones use lower automatic mesh LODs;
galleries off screen rest (lamp flicker, cart, drill animation, hazard
particles); VRAM-compressed textures capped at 1024/512 px, crew LOD
characters, MultiMesh batching, visibility ranges, animation throttling and
threaded model preloading. Measured with `bench_frame.gd` on Mesa's
software Vulkan at 720x1600 (a stand-in for a weak GPU: costs compare, the
absolute times do not), a new claim's frame now costs 55 ms on Low against
327 ms for the previous Low preset and about 395 ms for the previous default
(Medium); Medium dropped to 225 ms, High is unchanged. Low draws 110-130
calls and 80-115 k triangles per view early in the game, 115-235 calls and
115-225 k triangles with 70 workers and five depths.

Android frame pacing (Swappy) is on for phones: it keeps frames evenly
spaced at the 30 fps cap and on 90/120 Hz screens. Agile input flushing hands
touches to the game before every physics step, not once per drawn frame,
which keeps taps and drags responsive on a phone below its frame target. The emulator's virtual
Vulkan GPU cannot present with it, so x86_64 builds - only the emulator
test twin - turn it off with a feature override in `project.godot`.

## Testing

`tests/run_tests.gd` runs every suite headlessly (engine errors fail the
test): core (RNG, numbers, curves), content (validation catches bad data),
gameplay (commands, costs, processing, wear and repair), offline (guards,
accuracy, reports), progression (quests, achievements, contracts,
prestige, determinism), saves (round trip, migration, corruption,
checksums, timestamps), balance (pacing), game state (transitions) and world
(module definitions, camp layout and truck bays, full-world placement,
navigation, cage routes, agents, the foreman and taps queued on his way,
haulers carrying sacks, mechanics walking between machines, trucks that
never touch - automatic sales and SELL - and park in their own bays, camera
drag directions, triangle budgets) and graphics (presets, device detection, the
world following a preset and back, the player's choice, the watchdog).
`tools/godot/ui_smoke.gd` boots the real game and plays it end to end with
touch events - every tutorial tip (Next, taps on the vein, LIFT, SELL and
the controls the marker points at), a menu scrolled by a finger drag, camera
drags on the surface and underground and a two-finger twist that must not
turn it, live preset switches - including memory checks (opening every
panel repeatedly and going into the mine and back must not leave objects
behind).

`tools/device/device_smoke.py` plays the exported APK on an Android device
or emulator with real touch input through adb, following the game's log
lines (`[boot]`, `[state] A -> B`, `[save] ...`): title, new claim,
tutorial, camera pan (the picture must change), pause menu, Back key,
autosaves with the claim clock advancing, background and resume in the same
process, the graphics preset the first launch picked, an update installed
over the running game that must keep the save (and, when the previous CI
build carries the same signing key, an update from that build with a saved
claim), and no crash, ANR or engine error. CI runs it on an Android 15 x86_64 emulator (4 GB, software
graphics - the first launch must pick Low): the shipped arm64-v8a APK
(through the image's ARM translation) on the OpenGL ES fallback (the
emulator without Vulkan), and an x86_64 twin exported from a copy of the
same preset - `tools/apk/compare_content.py` proves it identical apart from
the engine's native library - on Vulkan, where the twin runs without frame
pacing.

## Android updates

A new APK installs over the game - keeping the save - only with the same
package id, a version code that is not lower and the same signing key.
`tools/apk/set_version.py` stamps every build with a version code from its
commit time (minutes since 2020), and CI signs with one update key
(`tools/ci/update_key.sh`). It is derived from a single repository secret,
`ANDROID_UPDATE_SEED`, by `tools/apk/update_key.py`: SHAKE-256 seeds a
deterministic RSA-3072 prime search and the self-signed certificate is
signed with PKCS#1 v1.5, so the same seed gives a byte-identical
certificate on every run (a keystore of your own in three other secrets
takes precedence). `tools/apk/verify_apk.py` checks the version and the
signing certificate of every APK. Setup, and the one-time switch from builds
signed with a one-off key: [android_signing.md](android_signing.md).
