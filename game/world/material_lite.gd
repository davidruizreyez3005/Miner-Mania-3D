class_name MaterialLite
extends RefCounted
## Entry-level shading for the models' materials (the Low preset): lighting
## per vertex instead of per pixel, and only the colour and glow textures -
## no normal, roughness, metallic or ambient-occlusion maps. The original
## settings are kept on each material so a higher preset restores them.
## Materials of imported models are shared resources: every instance of a
## model changes at once, and new instances (hires, upgrades) are registered
## as they are created (Assets.instantiate, Scatter).

static var lite := false
static var _tracked: Dictionary = {}   # StandardMaterial3D -> true (imported or cached, never freed mid-game)


static func set_lite(on: bool) -> void:
	lite = on
	for m in _tracked.keys():
		if is_instance_valid(m):
			_apply(m as StandardMaterial3D)


## Registers the materials of every mesh under `root` and applies the mode.
static func track(root: Node) -> void:
	for mi in root.find_children("*", "MeshInstance3D", true, false):
		var m := mi as MeshInstance3D
		if m.mesh == null:
			continue
		for s in m.mesh.get_surface_count():
			track_material(m.get_active_material(s))


static func track_mesh(mesh: Mesh) -> void:
	if mesh:
		for s in mesh.get_surface_count():
			track_material(mesh.surface_get_material(s))


## Materials made at runtime for one world are left alone (they would be
## kept alive here); imported ones and the cached structure materials live
## for the whole session.
static func track_material(mat: Material, cached: bool = false) -> void:
	var sm := mat as StandardMaterial3D
	if sm == null or _tracked.has(sm) or (sm.resource_path == "" and not cached):
		return
	_tracked[sm] = true
	_apply(sm)


static func _apply(m: StandardMaterial3D) -> void:
	if m.shading_mode == BaseMaterial3D.SHADING_MODE_UNSHADED:
		return
	if not m.has_meta("mm_full"):
		m.set_meta("mm_full", {"normal_enabled": m.normal_enabled, "ao_enabled": m.ao_enabled, "roughness_texture": m.roughness_texture,
			"metallic_texture": m.metallic_texture, "shading_mode": m.shading_mode})
	var full: Dictionary = m.get_meta("mm_full")
	m.normal_enabled = false if lite else bool(full["normal_enabled"])
	m.ao_enabled = false if lite else bool(full["ao_enabled"])
	m.roughness_texture = null if lite else full["roughness_texture"]
	m.metallic_texture = null if lite else full["metallic_texture"]
	m.shading_mode = BaseMaterial3D.SHADING_MODE_PER_VERTEX if lite else int(full["shading_mode"]) as BaseMaterial3D.ShadingMode
