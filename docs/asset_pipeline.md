# Miner Mania 3D - asset pipeline

Every 3D asset in the game (workers, animations, tools, machinery, vehicles,
buildings, environment pieces, resource nodes and props) is generated from
code by a headless, deterministic Blender pipeline, exported as GLB and
validated four times before Godot sees it. Nothing is modelled by hand;
artistic intent lives in the generators' construction rules and parameters.

## Quick start

```bash
# Full library (clean -> build -> validate -> manifest -> report); non-zero exit on any failure
blender --background --factory-startup --python blender/build.py

# Representative smoke set first (1 worker, 1 machine, 1 vehicle, 1 resource, 1 prop)
blender --background --factory-startup --python blender/build.py -- --profile smoke

# Partial rebuilds while iterating (no clean stage, keep going after a failure, review thumbnails)
blender --background --factory-startup --python blender/build.py -- --only mach_drill_01,veh_loader_01 --no-clean --keep-going --previews
blender --background --factory-startup --python blender/build.py -- --category environment --no-clean

# Byte-for-byte determinism check (builds everything twice, compares every GLB)
blender --background --factory-startup --python blender/build.py -- --verify-determinism

# Standalone validation (no Blender): re-inspect every file, Khronos validator, negative self-test
python -m pip install --require-hashes -r requirements.txt
npm ci --prefix tools/gltf_validator
python tools/validate_assets.py --khronos --self-test

# Godot import + validation (project.godot is the repository root)
godot --headless --path . --import
godot --headless --path . --script res://godot/pipeline/validate_assets.gd
```

Pinned toolchain: Blender **4.5.14 LTS** (glTF exporter 4.5.51), Godot
**4.7.2**, Python 3.11 + numpy 1.26.4 (hash-pinned), Node 22 +
gltf-validator 2.0.0-dev.3.10 (lockfile). `tools/ci/install_blender.sh` and
`tools/ci/install_godot.sh` download and checksum-verify the exact builds.
The build refuses to run on another Blender or exporter version.

## Repository layout

```
blender/
  build.py                entry point (stage orchestration lives in core/cli.py)
  core/                   config, registry glue, build context, stages, manifest, report, previews
  registry/               asset definitions - one line per asset (see "Adding an asset")
  generators/             construction rules: characters/, machinery/, vehicles/, buildings/,
                          environment/, resources/, props/, kit.py (mechanical parts), rocks.py
  rigging/                human_rig.py (shared humanoid skeleton), worker_rig.py, mech_rig.py, rig_validation.py
  animation/              clip authoring (locomotion, mining, carrying, operating, repairing, gestures),
                          IK solver, machine clip baking, animation_validation.py
  materials/              palette-driven procedural materials, UV atlas, texture baking
  exporters/              glTF export, LOD generation, collision, per-clip GLB split
  validators/             mesh/UV/origin checks and the independent GLB inspector (pure numpy)
  utilities/              geometry kit (meshkit.py)
assets/
  source/                 pipeline_config.json, palette.json, animation_clips.json (the contracts)
  generated/              characters/ machinery/ vehicles/ environment/ resources/ props/
                          animations/ collisions/ lod/   (build output, not versioned)
  manifests/              asset_manifest.json, animations.json, validation_expectations.json
  reports/                build_report.json/.txt, standalone/khronos/godot validation reports, previews/
godot/pipeline/           asset_post_import.gd (clip loop modes), validate_assets.gd (headless checks)
tools/                    validate_assets.py, gltf_validator/ (Khronos runner), ci/ (installers, summary)
.github/workflows/assets.yml
```

Source (generators, contracts) and runtime outputs never mix; generated
files are rebuilt from source in CI and published as workflow artifacts.

## Build stages

For every selected definition the pipeline runs, per state:

1. **clean** - removes stale outputs (full builds wipe `assets/generated`, manifests and reports).
2. **generate** - the generator builds named geometry parts (`ctx.geo`), bones, sockets, collision specs and clips.
3. **rig** - humanoid or mechanical armature, rigid or smooth skinning, rig validation (naming, hierarchy, rest pose, weights, deformation tests for characters).
4. **animate** - humanoid clips from the animation library (IK, contact and grip checks) or procedural machine clips.
5. **optimize** - mesh cleanup and triangulation, one UV atlas per asset, bake of base colour / ORM / normal / emissive (edge wear and AO grime baked in).
6. **collision** - convex hulls/primitives (`-convcolonly`), validated closed, convex, bounded and simple.
7. **LOD** - decimated LODs with silhouette-deviation limits and exact triangle bookkeeping.
8. **validate** - scale, origin, budgets, texel density, UV overlap/coverage, materials.
9. **export** - GLB per state, per LOD, per collision set, per clip (animation library).
10. **post_validate** - the exported bytes are re-read and inspected (structure, references, accessors, skin, animations evaluated, textures, bounds, names).
11. **manifest** and **report** - deterministic manifests (no timestamps) and the build report.

Errors always fail an asset; a warning fails it unless its code is listed in
`pipeline_config.json` `validation.allowed_warning_codes` (currently budget
below target / slightly over target, low texel density, missed LOD triangle
target, accepted Khronos warnings). A failed asset's partial outputs are
deleted. The build exits non-zero if anything failed (`--keep-going` still
builds the rest first).

## Conventions

### Units, axes and scale
Metres, scale 1.0. Blender is +Z up with the model front at -Y; the glTF
exporter converts to +Y up / +Z front, which is Godot's `Vector3.MODEL_FRONT`.
A point at Blender `(x, y, z)` is at Godot `(x, z, -y)`. The manifest stores
both for every socket, and the Godot validator checks the conversion.

### Naming
`<prefix>_<name>_<variant>` with category prefixes `chr_ mach_ veh_ bld_ env_
res_ prop_ tool_ eqp_` and `anim_` for clips: `chr_worker_miner_01`,
`mach_drill_01`, `mach_conveyor_01`, `veh_mining_truck_01`, `prop_crate_wood_01`,
`env_rock_large_01`, `res_ore_iron_01`, `anim_worker_walk`. State variants
append the state (`res_ore_iron_01_damaged`), LODs `_lod<N>`, collision files
`_collision`. Bones use lowercase names with `.L`/`.R` suffixes; sockets are
empty nodes named `socket_<name>`. Blender duplicate suffixes (`.001`) and
random names fail validation.

### Origins
| asset | origin |
|---|---|
| machine, vehicle, building, prop | base centre on the ground (lowest point at z = 0) |
| character | root at the ground between the feet (pelvis is the first child) |
| resource node, rocks, piles | ground contact centre, base sunk a few cm (`embedded`) |
| terrain tile | tile centre at ground level (skirt below) |
| hanging lamp | ceiling mount point (geometry below) |
| tool | the grip point |
| door / gate / wheel / conveyor pulley | the bone head sits on the hinge / axle / pulley axis |

### Sockets (interaction and chaining points)
Sockets are how game code places things. A worker socket is where the
worker's root goes; its rotation is the worker's facing (yaw 0 = the worker
faces Blender -Y = Godot +Z). Machines are built *from* the animation
contract (`assets/source/animation_clips.json` `interaction_points`), so
playing the matching clip at the socket puts the hands on the levers, button,
bolt or load surface:

- `socket_operate` (Operate), `socket_interact` (Interact), `socket_repair` (Repair, kneeling), `socket_load` (Load/Unload)
- vehicles: `socket_driver` (seat), `socket_entry` (outside the door), attachment points such as `socket_bucket_edge`
- resources: `socket_mine_1..3` (Mine clip: the pickaxe tip meets the rock surface)
- modular pieces: `socket_start` / `socket_end` (tunnel, track, pipes, fence, catwalk), `socket_tile_left/right` (cliff), `socket_north/south` (terrain)
- buildings: `socket_door_main`, `socket_dropoff`, `socket_workbench`, `socket_cage` (bone-attached), ...

Bone-attached sockets (e.g. the headframe cage) import as `BoneAttachment3D` in Godot and follow the animation.

### Budgets
Triangle ranges are the spec's mobile targets (`pipeline_config.json`
`budgets`): tiny prop 500-2,000, prop 2,000-8,000, important prop
5,000-15,000, hero machinery 8,000-25,000, large structure 3,000-25,000,
background NPC 5,000-12,000, worker 10,000-30,000, hero character
20,000-50,000. Below the range is reported as a warning; up to 15 % over is a
warning; beyond that the asset fails. Each budget also fixes the texture size
(256-2048), file size limit and LOD ratios. The build report lists triangles,
materials, textures, file sizes, clip and bone counts per asset.

### Materials and textures
Materials are palette driven (`assets/source/palette.json`, keys like
`paint_worn:industrial_yellow`, `stone:stone_warm`, `metal:galvanized`) and
baked into one texture set per asset: base colour, ORM (occlusion, roughness,
metallic) and a tangent-space normal map, plus an emissive map when lamps or
glowing crystals exist. Only glass stays a separate unbaked material. All
materials are standard glTF metallic-roughness PBR.

### LODs and collision
LOD ratios come from the budget (e.g. hero machinery 0.5 / 0.25 / 0.12).
Detail parts may drop out of lower LODs; large islands never do; the
silhouette deviation is bounded per level. Collision files contain only
convex shapes named `*-convcolonly`, which Godot turns into
`StaticBody3D` + `ConvexPolygonShape3D`. Characters get a gameplay capsule
(radius 0.3 m, height 1.8 m) recorded in the manifest.

## Characters and animation

All 14 worker variants (miners, haulers, operators, mechanics, engineers,
geologists, supervisors; varied body type, presentation, skin tone, hair,
outfit, helmet and equipment) share one skeleton, `humanoid_worker_v1`, with
identical bone names, hierarchy and rest frames. Body variation lives in the
meshes only, so **every humanoid clip plays on every worker** (the Godot
validator proves each clip binds to each worker skeleton).

Clips (30 fps, in place; `loop` in brackets): Idle [loop], Idle_Variant,
Walk [loop], Run [loop], Turn_Left, Turn_Right, Mine [loop], Mine_Heavy
[loop], Pick_Up, Put_Down, Carry [loop], Carry_Walk [loop], Load, Unload,
Operate [loop], Repair [loop], Hammer [loop], Drill [loop], Dig [loop],
Push [loop], Pull [loop], Celebrate, React, Rest [loop], Sit [loop],
Death_or_Fall, Interact, and optional Inspect [loop], Pull_Lever.

- Each worker GLB embeds the clips; `anim_worker_library.glb` holds the
  library and `assets/generated/animations/anim_worker_<clip>.glb` one clip
  each (a stub mesh keeps them importable) for streaming.
- `animations.json` records per clip: loop flag, duration, frames, foot mode,
  root motion (`none` / in-place locomotion / rotation), tool, grip,
  interaction socket, event times and measured foot slide / grip error.
- Tools attach to `hand_tool.R` / `hand_tool.L` at identity: a tool's origin
  is its grip, its handle runs along +Z and the working face points -Y
  (Blender). The clips hold the grip within millimetres of the contract.
- Other attachment bones: `back_equipment`, `helmet_attachment`, `waist_equipment`, `carry_attachment`.

glTF has no loop flag; `godot/pipeline/asset_post_import.gd` (the default
scene import script in `project.godot`) sets every clip's loop mode from the
manifest at import time.

## Machinery, vehicles and buildings

Machines are assembled from engineered parts (frames, motors, gearboxes,
pulleys and belts, hydraulic cylinders, hoppers, chutes, conveyors, tracks,
wheels, ladders, railings, control panels, lights) and animated through a
rigid mechanical rig: each moving part is a bone and every clip is a function
of time. Loops are seamless by construction (whole turns of every spinning
part, whole pitches of belts and track pads); hydraulic cylinders keep their
barrel and rod attached through the motion. Typical clips: `Idle`, `Work`,
`Drive`, `Steer_Left`, `Steer_Right`, `Dump`, `Dig`, `Scoop`, `Door`,
`Roller_Door`, `Gates`, `Hoist`. Bone and clip lists are in each generator's
module docstring and in the manifest entry's `metadata.clips`.

- Machinery: drill rig, jaw crusher, conveyor, pump, generator, smelter, washer, sorter, silo, processor.
- Vehicles: mining truck, excavator (tracked), articulated loader, mine cart (600 mm gauge), utility vehicle - wheels spin at the recorded speed, steering, suspension, doors, attachments, driver and entry sockets.
- Buildings: mine portal (tunnel section chains to `env_tunnel_straight_01`), headframe (sheave, cage and a hoist rope that scales with the travel), warehouse (roll-up and hinged doors), site office, workshop (travelling hoist).

## Environment and resources

Environment pieces are modular: rocks, boulder, tiling strata cliff,
stockpiles, 4 m terrain tiles whose seams match exactly, vegetation (trees
with trunk collision, bushes and grass without), timber and steel supports,
a 4 m tunnel segment that chains seamlessly, track pieces, pipes, cables,
signs, lamps, fences, barriers, containers, scaffold, catwalk and a water
tank.

Resource nodes (coal, iron, copper, silver, gold, amethyst, diamond,
uranium) have `full`, `damaged` and `depleted` states from the same seed, so
the silhouette erodes consistently. Each state has its own GLB, LOD and
collision; the manifest lists them under `states`.

## Validation layers

1. **In-build checks** - geometry, UVs, origins, scale, budgets, rig and
   deformation, animation contacts/loops/grips, collision.
2. **Post-export inspection** (`blender/validators/glb_inspector.py`) - the
   exported bytes: GLB structure, references and accessors, finite data,
   normals/tangents, skin and inverse bind matrices, bone hierarchy, clips
   evaluated frame by frame (loops, contacts, foot slide, grips), embedded
   power-of-two textures, bounds, names, budgets.
3. **Standalone re-validation** (`tools/validate_assets.py`) - every
   manifest file re-inspected from disk with the exact build-time
   expectations (`validation_expectations.json`), sha256 checks, recorded vs
   actual triangle counts, stale-file detection; `--khronos` runs the Khronos
   glTF-Validator strictly; `--self-test` corrupts real GLBs (truncation, bad
   magic, dangling references, NaN vertices, over-budget geometry, duplicate
   names, missing sockets, external images, missing clips, non-unit or
   non-monotonic keys) and fails unless every mutation is rejected.
4. **Godot import validation** (`godot/pipeline/validate_assets.gd`) - what
   Godot actually imported: scenes load and instantiate, triangle counts,
   textured materials, bounds after axis conversion, socket positions,
   skeleton bone counts, clip sets, loop modes, lengths, track binding and
   finite poses, convex collision shapes with no visible meshes, and every
   humanoid clip binding to every worker.

## Manifests

- `asset_manifest.json` - per asset: type, model path, triangles, materials,
  textures and resolution, skeleton and bone count, clips, LOD models (with
  triangles and hashes), collision model and shape count, dimensions, bounds,
  sockets and socket transforms (Blender and Godot space), file size, sha256,
  budget, seed, generator, tags, UV statistics, validation status, states,
  per-clip models and public metadata (clips, interactions, speeds, resource
  info).
- `animations.json` - the humanoid clip contract plus measured results.
- `validation_expectations.json` - the inspector expectations for every file.

Manifests contain no timestamps; the same sources produce the same bytes.

## Determinism

Every definition carries an explicit seed; all randomness flows from a
seeded RNG derived per asset and part; Blender runs with
`--factory-startup`; exports and manifests are sorted. `--verify-determinism`
rebuilds into a second output root and requires identical GLB bytes.

## Continuous integration

`.github/workflows/assets.yml` (push, pull request, manual dispatch, and
`workflow_call` so the Android workflow can reuse it):

1. **smoke** job - checkout, Python + hash-pinned dependencies, system
   libraries, cached and checksum-verified Blender (version asserted), Node
   + pinned validator, smoke build, standalone validation with Khronos and
   the self-test, pinned Godot import and validation, job summary, reports
   and assets uploaded.
2. **full** job - runs only after the smoke job passes (skipped for
   `profile: smoke`): the whole library (optionally with the determinism
   rebuild), the same validation chain, and the `generated-assets` and
   `asset-reports` artifacts.

## Adding an asset

Register a definition; no pipeline code changes:

```python
# blender/registry/props.py
P(id="prop_barrel_oil_03", generator="props.barrel", seed=2104, budget="prop",
  params={"color": "safety_orange"}, tags=("container",), description="Steel oil drum, orange"),
```

Definitions are validated at start-up (naming pattern and prefix, budget,
generator, collision mode, state names, power-of-two texture sizes, explicit
positive seeds, tool references). A new *kind* of asset needs a generator
module exposing `build(ctx)`; the context provides `geo()` parts, `bone()`,
`socket()`, `col_box/col_cylinder/col_hull()`, `clip()` and `metadata`.
