class_name FacilityView
extends Node3D
## A surface facility on its layout plot. Unbuilt facilities are fenced
## construction sites with a translucent preview of the machine; built ones
## show the generated asset, animate with utilisation (Work / Idle), smoke
## when worn, loop their machine sound, and grow with level tiers (more silos,
## twin machines, busier yards). A collider makes the facility tappable.

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
	return SiteLayout.tier_for_level(fid, level(), true)


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
		world.notify_facility_rebuilt()
		return
	for off in SiteLayout.unit_offsets(fid, plot, asset_id, tier):
		_add_unit(off)
	_add_yard_dressing()
	world.notify_facility_rebuilt()
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


var _yard: Node3D


func _add_yard_dressing() -> void:
	## Level tiers make yards visibly busier (pallets, containers); pieces go
	## through the module library's placement validation like all dressing.
	var owner := "yard:" + fid
	world.modules.release(owner)
	if _yard:
		_yard.queue_free()
		_yard = null
	if fid != "warehouse" or tier < 2:
		return
	_yard = Node3D.new()
	_yard.name = "Yard"
	world.surface_root.add_child(_yard)
	var b := Assets.bounds(asset_id)
	var xf := Transform3D(Basis(Vector3.UP, deg_to_rad(yaw)), position)
	for i in (4 if tier >= 3 else 2):
		var lp := Vector3(b.end.x + 1.4, 0, b.position.z + 2.0 + 1.6 * i)
		var t := xf * Transform3D(Basis(), lp)
		t.origin.y = world.ground_height(t.origin.x, t.origin.z)
		world.modules.try_place(_yard, "mod_pallet", t, "surface", 0, owner)
	if tier >= 3:
		var ct := xf * Transform3D(Basis(Vector3.UP, PI * 0.5), Vector3(b.end.x + 5.0, 0, b.get_center().z))
		ct.origin.y = world.ground_height(ct.origin.x, ct.origin.z)
		world.modules.try_place(_yard, "mod_container_red", ct, "surface", 0, owner)


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


## Footprints agents walk around: [centre xz, half extents xz, yaw] per
## visual unit, or the fenced construction site while unbuilt.
func blocked_boxes() -> Array:
	var out: Array = []
	var b := Assets.bounds(asset_id)
	var xf := Transform3D(Basis(Vector3.UP, deg_to_rad(yaw)), position)
	var ry := deg_to_rad(yaw)
	if not built:
		if fid == "depot":
			return out
		var c := xf * Vector3(b.get_center().x, 0, b.get_center().z)
		out.append([Vector2(c.x, c.z), Vector2(b.size.x, b.size.z) * 0.5 + Vector2(1.2, 1.2), ry])
		return out
	for u in units:
		var n := u as Node3D
		var ub := Assets.bounds(String(n.get_meta("asset_id", asset_id)))
		var c2 := xf * (n.position + n.basis * ub.get_center())
		out.append([Vector2(c2.x, c2.z), Vector2(ub.size.x, ub.size.z) * 0.5 + Vector2(0.2, 0.2), ry + n.rotation.y])
	return out


## Where an operator stands (world transform) - the asset's operate socket.
func work_transform(kind: String = "operate") -> Transform3D:
	var sock := kind if Assets.has_socket(asset_id, kind) else ("interact" if Assets.has_socket(asset_id, "interact") else "")
	if sock != "" and not units.is_empty():
		return (units[0] as Node3D).global_transform * Assets.socket(asset_id, sock)
	# Layout work/repair offsets are world-space (as the simulation reads them).
	var w: Array = plot.get("work" if kind == "operate" else "repair", [0, 2])
	var base := transform if not is_inside_tree() else global_transform
	var p := base.origin + Vector3(float(w[0]), 0, float(w[1]))
	return Transform3D(Basis(Vector3.UP, atan2(-float(w[0]), -float(w[1]))), p)
