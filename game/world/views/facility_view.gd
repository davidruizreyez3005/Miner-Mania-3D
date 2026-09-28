class_name FacilityView
extends Node3D
## A surface facility on its layout plot. Unbuilt facilities are fenced
## construction sites with a translucent preview of the machine; built ones
## show the generated asset, animate with utilisation (Work / Idle), smoke
## when worn, loop their machine sound, and grow with level tiers (more silos,
## twin machines, busier yards). A collider makes the facility tappable.

const TIER_LEVELS := {"silo": [1, 10, 25, 50], "conveyor": [1, 25, 100], "generator": [1, 25, 100],
	"pump": [1, 25], "crusher": [1, 50], "washer": [1, 50], "sorter": [1, 50], "smelter": [1, 50], "refinery": [1, 50],
	"warehouse": [1, 10, 50], "office": [1, 20], "workshop": [1], "depot": [1, 10]}
const LOOPS := {"crusher": "crusher_loop", "washer": "hum_loop", "sorter": "conveyor_loop", "smelter": "hum_loop",
	"refinery": "pump_loop", "generator": "generator_loop", "pump": "pump_loop", "conveyor": "conveyor_loop"}
const GHOST_SHADER := preload("res://game/world/shaders/ghost.gdshader")

var world: MineWorld
var fid: String
var fac: Dictionary
var plot: Dictionary
var asset_id: String
var yaw := 0.0
var built := false
var tier := 0
var units: Array = []            # instanced asset roots (one per visual unit)
var anims: Array = []            # AnimationPlayers of the units
var site: Node3D                 # construction site (unbuilt)
var loop_player: AudioStreamPlayer3D
var smoke: GPUParticles3D
var _anim_state := ""
var _worn := false


func setup(w: MineWorld, facility_id: String) -> void:
	world = w
	fid = facility_id
	fac = w.content.facility(fid)
	asset_id = String(fac.get("asset", ""))
	plot = w.layout.plot(String(fac.get("plot", fid)))
	name = "Facility_" + fid
	var pos: Array = plot.get("pos", [0, 0])
	yaw = float(plot.get("yaw", 0.0))
	position = Vector3(float(pos[0]), 0.0, float(pos[1]))
	position.y = w.ground_height(position.x, position.z)
	rotation_degrees.y = yaw
	_add_pick_collider()
	_rebuild()


func _add_pick_collider() -> void:
	var body := StaticBody3D.new()
	body.name = "Pick"
	body.collision_layer = MineWorld.PICK_LAYER
	body.collision_mask = 0
	body.set_meta("target", "facility:" + fid)
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	var b := Assets.bounds(asset_id)
	box.size = b.size.max(Vector3(2.5, 2.5, 2.5))
	cs.shape = box
	cs.position = b.get_center()
	body.add_child(cs)
	add_child(body)


func level() -> int:
	return world.sim.facility_level(fid)


func current_tier() -> int:
	var t := 0
	for lv in TIER_LEVELS.get(fid, [1]):
		if level() >= int(lv):
			t += 1
	return t


func _rebuild() -> void:
	for u in units:
		u.queue_free()
	units.clear()
	anims.clear()
	if site:
		site.queue_free()
		site = null
	built = world.sim.facility_built(fid)
	tier = current_tier()
	if not built:
		_build_site()
		return
	match fid:
		"silo":
			var sp: Array = plot.get("spacing", [3.8, 0.0])
			var counts: Array = plot.get("count_by_tier", [1, 2, 3, 4])
			var n := int(counts[clampi(tier - 1, 0, counts.size() - 1)])
			for i in n:
				_add_unit(Vector3(float(sp[0]) * i, 0, float(sp[1]) * i))
		"conveyor":
			var seg := float(plot.get("segment", 6.77))
			var n2 := int(plot.get("segments", 5))
			for i in n2:
				_add_unit(Vector3(0, 0, -seg * i))
			if tier >= 2:
				for i in n2:
					_add_unit(Vector3(2.2, 0, -seg * i))
		"depot":
			pass                      # trucks are driven by SalesView; the depot is its yard
		_:
			_add_unit(Vector3.ZERO)
			if tier >= 2 and fid in ["crusher", "washer", "sorter", "smelter", "refinery", "generator", "pump"]:
				var b := Assets.bounds(asset_id)
				_add_unit(Vector3(b.size.x + 1.2, 0, 0))
	_add_yard_dressing()
	if LOOPS.has(fid) and loop_player == null:
		loop_player = Audio.attach_loop(String(LOOPS[fid]), self, Vector3(0, 1.5, 0))


func _add_unit(offset: Vector3) -> void:
	var inst := Assets.instantiate(asset_id, "", true)
	inst.position = offset
	add_child(inst)
	units.append(inst)
	for ap in inst.find_children("*", "AnimationPlayer", true, false):
		anims.append(ap)
		if (ap as AnimationPlayer).has_animation("Idle"):
			(ap as AnimationPlayer).play("Idle")
	_anim_state = ""


func _build_site() -> void:
	site = Node3D.new()
	site.name = "ConstructionSite"
	add_child(site)
	var b := Assets.bounds(asset_id)
	var half := Vector2(b.size.x, b.size.z) * 0.5 + Vector2(1.2, 1.2)
	var center := Vector3(b.get_center().x, 0, b.get_center().z)
	# Ghost preview of what will stand here.
	var ghost := Assets.instantiate(asset_id, "", false)
	ghost.position = Vector3.ZERO
	site.add_child(ghost)
	var gm := ShaderMaterial.new()
	gm.shader = GHOST_SHADER
	var unlocked := SimCommands.facility_requirement_met(world.sim, fid)
	gm.set_shader_parameter("tint", Color(0.35, 0.8, 1.0, 0.32) if unlocked else Color(0.6, 0.6, 0.65, 0.18))
	for gi in ghost.find_children("*", "GeometryInstance3D", true, false):
		(gi as GeometryInstance3D).material_override = gm
		(gi as GeometryInstance3D).cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	for ap in ghost.find_children("*", "AnimationPlayer", true, false):
		(ap as AnimationPlayer).stop()
	# Fence line, cones and a sign around the plot.
	var fences := []
	var fence_len := 3.0
	var x := -half.x
	while x < half.x - 0.1:
		fences.append(Transform3D(Basis(Vector3.UP, PI * 0.5), center + Vector3(x + fence_len * 0.5, 0, half.y)))
		fences.append(Transform3D(Basis(Vector3.UP, PI * 0.5), center + Vector3(x + fence_len * 0.5, 0, -half.y)))
		x += fence_len
	Scatter.place(site, "env_fence_01", fences, Atmosphere.LAYER_SURFACE, true, 90.0)
	var cones := [Transform3D(Basis(), center + Vector3(-half.x, 0, half.y + 0.6)), Transform3D(Basis(), center + Vector3(half.x, 0, half.y + 0.6))]
	Scatter.place(site, "prop_cone_01", cones, Atmosphere.LAYER_SURFACE, false, 60.0)
	var sign := Assets.instantiate("env_sign_warning_01", "", false)
	sign.position = center + Vector3(half.x - 0.8, 0, half.y + 1.0)
	site.add_child(sign)
	var crates := Assets.instantiate("prop_crate_wood_01", "", false)
	crates.position = center + Vector3(-half.x + 0.9, 0, half.y - 0.9)
	crates.rotation_degrees.y = 17.0
	site.add_child(crates)


func _add_yard_dressing() -> void:
	## Level tiers make yards visibly busier (pallets, barrels, containers).
	if fid == "warehouse" and tier >= 2:
		var b := Assets.bounds(asset_id)
		var ts := []
		for i in (4 if tier >= 3 else 2):
			ts.append(Transform3D(Basis(Vector3.UP, 0.1 * i), Vector3(b.end.x + 1.4, 0, b.position.z + 2.0 + 1.5 * i)))
		Scatter.place(self, "prop_pallet_01", ts, Atmosphere.LAYER_SURFACE, true, 80.0)
		if tier >= 3:
			var c := Assets.instantiate("env_container_02", "", true)
			c.position = Vector3(b.end.x + 5.0, 0, b.get_center().z)
			c.rotation_degrees.y = 90.0
			add_child(c)
			units.append(c)


func sync(delta: float) -> void:
	var now_built := world.sim.facility_built(fid)
	if now_built != built or (built and current_tier() != tier):
		_rebuild()
		if now_built and delta > 0.0:
			VfxLibrary.spawn(world, "construct_dust", global_position + Vector3(0, 0.5, 0))
	if not built:
		return
	var fs: Dictionary = world.sim.state.facilities.get(fid, {})
	var util := float(fs.get("util", 0.0))
	if fid == "conveyor":
		util = 1.0 if Simulation.inv_total(world.sim.state.surface_bin) > 0.01 else 0.0
	elif fid == "generator":
		util = maxf(util, 0.3)
	var want := "Work" if util > 0.03 else "Idle"
	if want != _anim_state:
		_anim_state = want
		for ap in anims:
			var a := ap as AnimationPlayer
			if a.has_animation(want):
				a.play(want, 0.4)
	var cond := float(fs.get("condition", 1.0))
	var speed := (0.55 + 0.6 * clampf(util, 0.0, 1.0)) * (0.5 + 0.5 * cond) if want == "Work" else 1.0
	for ap in anims:
		(ap as AnimationPlayer).speed_scale = speed
	if loop_player:
		Audio.set_loop_level(loop_player, util if want == "Work" else 0.0)
	var worn := bool(fs.get("repairing", false))
	if worn != _worn:
		_worn = worn
		if worn and smoke == null:
			smoke = VfxLibrary.attach(self, "worn_smoke", Assets.bounds(asset_id).get_center() + Vector3(0, Assets.bounds(asset_id).size.y * 0.4, 0))
		if smoke:
			smoke.emitting = worn


## Where an operator stands (world transform) - the asset's operate socket.
func work_transform(kind: String = "operate") -> Transform3D:
	var sock := kind if Assets.has_socket(asset_id, kind) else ("interact" if Assets.has_socket(asset_id, "interact") else "")
	if sock != "" and not units.is_empty():
		return (units[0] as Node3D).global_transform * Assets.socket(asset_id, sock)
	var w: Array = plot.get("work" if kind == "operate" else "repair", [0, 2])
	return global_transform * Transform3D(Basis(), Vector3(float(w[0]), 0, float(w[1])))
