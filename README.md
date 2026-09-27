# Miner Mania 3D

Mobile mining tycoon for Godot 4. This repository currently contains the
game's procedural 3D asset pipeline: headless Blender generators for every
worker, animation, tool, machine, vehicle, building, environment piece,
resource node and prop, with GLB export, LODs, collision, manifests, four
layers of validation and a Godot import check.

- Build everything: `blender --background --factory-startup --python blender/build.py`
- Documentation: [docs/asset_pipeline.md](docs/asset_pipeline.md)
- CI: [.github/workflows/assets.yml](.github/workflows/assets.yml)

Generated assets are not versioned; CI publishes them as workflow artifacts.
