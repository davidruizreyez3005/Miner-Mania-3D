class_name AgentManager
extends Node3D
## The visible workforce: one WorkerAgent per hired worker (reused from a
## small pool so hiring during play does not hitch), the player's foreman,
## shared navigation, the spots where people stand (vein sockets, machine
## controls, bench seats, spread-out crowd positions), animation detail by
## camera distance, and throttled impact effects and sounds. Reads the
## simulation only; the foreman's swings go through Session.command.

signal foreman_swung(result: Dictionary)

const FULL_DETAIL_M := 34.0
const REDUCED_DETAIL_M := 80.0
const MAX_FULL_RIGS := 28
const POOL_PER_ASSET := 3
const FX_PER_S := 7.0

var world: MineWorld
var sim: Simulation
var nav: MineNav
var agents: Dictionary = {}          # worker id -> WorkerAgent
var foreman: Foreman
var selected := -1
var _pool: Dictionary = {}           # asset id -> Array[WorkerAgent]
var _nav_surface_dirty := false
var _first_sync := true
var _fx_budget := FX_PER_S
var _sound_budget := 4.0
var _select_ring: MeshInstance3D
var _detail_t := 0.0
var _max_full := MAX_FULL_RIGS            # graphics preset (apply_quality)
var _detail_scale := 1.0
var _fx_rate := FX_PER_S


func setup(w: MineWorld) -> void:
	world = w
	sim = w.sim
	name = "Agents"
	nav = MineNav.new(w)
	nav.extra_obstacles = w.decor_obstacles
	nav.rebuild_all()
	w.rebuilt.connect(_on_rock_rebuilt)
	w.facilities_changed.connect(_on_facilities_changed)
	set_process(false)
	foreman = Foreman.new()
	add_child(foreman)
	foreman.setup_foreman(self, outfit_asset())
	var start_level := 1 if sim.state.deepest_unlocked() >= 1 else 0
	var start := nav.landing(start_level) + Vector3(2.2, 0, 0.6)
	start.y = nav.floor_y(start_level, start.x, start.z)
	foreman.place(start, start_level, 0.0)
	foreman.swung.connect(func(r: Dictionary) -> void: foreman_swung.emit(r))
	_select_ring = _make_ring(Color(0.35, 0.8, 1.0, 0.9))
	_select_ring.visible = false
	add_child(_select_ring)
	EventBus.selection_changed.connect(_on_selection_changed)


func outfit_asset() -> String:
	var cid := String(sim.state.cosmetics.get("equipped", {}).get("foreman_outfit", ""))
	var c: Dictionary = sim.content.cosmetic_by_id.get(cid, {})
	var aid := String(c.get("asset", "chr_worker_miner_01"))
	return aid if Assets.has(aid) else "chr_worker_miner_01"


func _on_rock_rebuilt() -> void:
	for d in world.unlocked_depths():
		if not nav.grids.has(int(d)):
			nav.build_depth(int(d))


func _on_facilities_changed() -> void:
	_nav_surface_dirty = true


# -------------------------------------------------------------------- sync

## Driven by MineWorld.sync every frame.
func sync(delta: float) -> void:
	if _nav_surface_dirty:
		_nav_surface_dirty = false
		nav.build_surface()
	var rt := sim.state.run_time
	var seen := {}
	for w in sim.state.workers:
		var id := int(w["id"])
		seen[id] = true
		var a: WorkerAgent = agents.get(id)
		if a == null:
			a = _spawn(w)
			var fresh := String(w["location"]) == "surface:gate" or float(w.get("hired_at", 0.0)) > rt - 1.0
			if fresh and not _first_sync:
				var g := sim.layout.position("surface:gate")
				a.place(Vector3(g.x, nav.floor_y(0, g.x, g.z), g.z), 0, -PI * 0.5)
				a.sync(w, rt, false)
			else:
				a.sync(w, rt, true)
		else:
			a.sync(w, rt, false)
	for id in agents.keys():
		if not seen.has(id):
			_despawn(int(id))
	_first_sync = false
	if outfit_asset() != foreman.outfit:
		_swap_foreman_outfit()
	for a in agents.values():
		(a as WorkerAgent).tick(delta)
	foreman.tick(delta)
	_fx_budget = minf(_fx_rate, _fx_budget + delta * _fx_rate)
	_sound_budget = minf(4.0, _sound_budget + delta * 4.0)
	_detail_t -= delta
	if _detail_t <= 0.0:
		_detail_t = 0.25
		_update_detail()
	if selected >= 0 and agents.has(selected):
		var sa: WorkerAgent = agents[selected]
		_select_ring.visible = true
		_select_ring.global_position = sa.global_position + Vector3(0, 0.04, 0)
	else:
		_select_ring.visible = false


func _spawn(w: Dictionary) -> WorkerAgent:
	var aid := String(w.get("variant", ""))
	var a: WorkerAgent = null
	var pool: Array = _pool.get(aid, [])
	while not pool.is_empty() and a == null:
		a = pool.pop_back()
	if a != null:
		a.visible = true
		a.process_mode = Node.PROCESS_MODE_INHERIT
		a.sig = ""
		a.wid = int(w["id"])
		a.role = String(w["role"])
		a.name = "Worker_%d" % a.wid
		for c in a.get_children():
			if c is StaticBody3D:
				(c as StaticBody3D).set_meta("target", "worker:%d" % a.wid)
	else:
		a = WorkerAgent.new()
		add_child(a)
		a.setup_worker(self, w)
	agents[int(w["id"])] = a
	return a


func _despawn(id: int) -> void:
	var a: WorkerAgent = agents[id]
	agents.erase(id)
	if selected == id:
		selected = -1
	var aid := a.rig.asset_id
	var pool: Array = _pool.get_or_add(aid, [])
	if pool.size() < POOL_PER_ASSET:
		a.stop()
		a.visible = false
		a.process_mode = Node.PROCESS_MODE_DISABLED
		pool.append(a)
	else:
		a.queue_free()


func _swap_foreman_outfit() -> void:
	var pos := foreman.position
	var lvl := foreman.level
	var y := foreman.yaw
	foreman.queue_free()
	foreman = Foreman.new()
	add_child(foreman)
	foreman.setup_foreman(self, outfit_asset())
	foreman.place(pos, lvl, y)
	foreman.swung.connect(func(r: Dictionary) -> void: foreman_swung.emit(r))


## Graphics preset: how many crew rigs animate at full rate, how far the
## animation detail reaches and how many impact effects fly.
func apply_quality(p: Dictionary) -> void:
	_max_full = int(p.get("max_full_rigs", MAX_FULL_RIGS))
	_detail_scale = clampf(float(p.get("detail_scale", 1.0)), 0.3, 1.0)
	_fx_rate = FX_PER_S * clampf(float(p.get("vfx", 1.0)), 0.1, 1.0)
	_detail_t = 0.0


## Animation detail: nearest rigs animate every frame, far ones at a low
## rate, off-screen or very far ones not at all.
func _update_detail() -> void:
	var cam := get_viewport().get_camera_3d() if is_inside_tree() else null
	if cam == null:
		return
	var cp := cam.global_position
	var list: Array = []
	for a in agents.values():
		list.append([cp.distance_squared_to((a as Node3D).global_position), a])
	list.sort_custom(func(x: Array, y: Array) -> bool: return float(x[0]) < float(y[0]))
	var full := 0
	for item in list:
		var dist := sqrt(float(item[0]))
		var rig: CharacterRig = (item[1] as WorkerAgent).rig
		var lv := CharacterRig.DETAIL_FROZEN
		if dist < FULL_DETAIL_M * _detail_scale and full < _max_full:
			lv = CharacterRig.DETAIL_FULL
			full += 1
		elif dist < REDUCED_DETAIL_M * _detail_scale:
			lv = CharacterRig.DETAIL_REDUCED
		rig.set_detail(lv)
	foreman.rig.set_detail(CharacterRig.DETAIL_FULL)


# ------------------------------------------------------------------- spots

func tool_tier(level: int) -> int:
	var dep := sim.state.depth(level)
	return int(dep.get("tool_tier", 1)) if not dep.is_empty() else 1


## Rank of a worker among those sharing its location (stable by id), so
## crews spread out instead of standing inside each other.
func _rank(w: Dictionary) -> int:
	var k := 0
	for o in sim.state.workers:
		if o["location"] == w["location"] and int(o["id"]) < int(w["id"]):
			k += 1
	return k


func _y(level: int, p: Vector3) -> Vector3:
	return Vector3(p.x, nav.floor_y(level, p.x, p.z), p.z)


## A free spot near `p` for the k-th person there (rings of 0.9 m).
func _spread(level: int, p: Vector3, k: int) -> Vector3:
	if k <= 0:
		return _y(level, p)
	var ring := 1 + (k - 1) / 6
	var ang := float((k - 1) % 6) * TAU / 6.0 + float(ring) * 0.5
	var q := p + Vector3(cos(ang), 0, sin(ang)) * (0.9 * float(ring))
	var g := nav.grid(level)
	var s := g.snap(Vector2(q.x, q.z))
	return _y(level, Vector3(s.x, 0, s.y))


static func _yaw_of(t: Transform3D) -> float:
	var f := t.basis.z
	return atan2(f.x, f.z)


func spot_for(_a: Agent, w: Dictionary) -> Dictionary:
	var loc := String(w["location"])
	var parts := loc.split(":")
	var k := _rank(w)
	var lvl := sim.layout.level_of(loc)
	if parts[0] == "depth" and parts.size() > 2:
		var d := int(parts[1])
		match parts[2]:
			"node":
				return node_spot(d, int(parts[3]), k)
			"rest":
				return _rest_spot(d, k)
			"face":
				var fp := _spread(d, sim.layout.position(loc), k)
				return {"pos": fp, "yaw": PI, "level": d}
			"station":
				var sp := _spread(d, sim.layout.position(loc), k)
				return {"pos": sp, "yaw": PI, "level": d, "look": station_point(d)}
			_:
				return {"pos": _spread(d, sim.layout.position(loc), k), "yaw": 0.0, "level": d}
	if parts[0] == "facility":
		var fid := parts[1]
		var kind := "repair" if parts.size() > 2 and parts[2] == "repair" else "operate"
		var t := Transform3D()
		var look := Vector3.ZERO
		if fid == "headframe":
			t = world.lift_view.work_transform(kind)
			look = world.lift_view.global_position + Vector3(0, 1.5, 0)
		elif world.facility_views.has(fid):
			var fv: FacilityView = world.facility_views[fid]
			t = fv.work_transform(kind)
			look = fv.global_position + Vector3(0, 1.2, 0)
		else:
			t = Transform3D(Basis(), sim.layout.position(loc))
		var p := t.origin
		if k > 0:
			p = _spread(0, p, k)
		p = _y(0, p)
		return {"pos": p, "yaw": _yaw_of(t), "level": 0, "look": look}
	if loc == "surface:rest":
		return _rest_spot(0, k)
	return {"pos": _spread(lvl, sim.layout.position(loc), k), "yaw": 0.0, "level": lvl}


## Mining position k at a vein (the asset's mine sockets, then a fan).
func node_spot(d: int, slot: int, k: int) -> Dictionary:
	var dv: DepthView = world.depth_views.get(d)
	var order := [0, 2, 1]
	var t: Transform3D
	var look: Vector3
	if dv:
		t = dv.mine_socket(slot, order[k % 3])
		look = dv.node_position(slot)
	else:
		var p := sim.layout.position("depth:%d:node:%d" % [d, slot])
		t = Transform3D(Basis(Vector3.UP, PI), p)
		look = p + Vector3(0, 0.8, -1.6)
	var pos := t.origin
	if k >= 3:
		pos += t.basis.x * (0.8 * float(k / 3) * (1.0 if k % 2 == 0 else -1.0)) + t.basis.z * -0.5
	return {"pos": _y(d, pos), "yaw": _yaw_of(t), "level": d, "look": look}


## Where the foreman swings at a vein (socket 2, kept free of the crew order).
func foreman_spot(d: int, slot: int) -> Dictionary:
	var dv: DepthView = world.depth_views.get(d)
	if dv:
		var t := dv.mine_socket(slot, 1)
		return {"pos": _y(d, t.origin), "yaw": _yaw_of(t), "level": d, "look": dv.node_position(slot)}
	var p := sim.layout.position("depth:%d:node:%d" % [d, slot])
	return {"pos": _y(d, p), "yaw": PI, "level": d, "look": p + Vector3(0, 0.8, -1.6)}


func _rest_spot(level: int, k: int) -> Dictionary:
	var seats: Array = world.seats(level)
	if k < seats.size():
		var t: Transform3D = seats[k]
		return {"pos": t.origin, "yaw": _yaw_of(t), "level": level, "clip": "Sit"}
	var base := sim.layout.position("surface:rest" if level <= 0 else "depth:%d:rest" % level)
	return {"pos": _spread(level, base + Vector3(1.4, 0, 1.0), k - seats.size()), "yaw": 0.0, "level": level, "clip": "Rest"}


func station_point(level: int) -> Vector3:
	var g: Dictionary = sim.layout.data.get("gallery", {})
	var st: Array = g.get("station", [-9.5, -5.5])
	return _y(level, Vector3(float(st[0]), 0, float(st[1]))) + Vector3(0, 0.4, 0)


## Hauling loop ends: where sacks are picked up (by the face) and dropped
## (at the station pile).
func haul_pick_point(level: int, wid: int = 0) -> Vector3:
	var p := sim.layout.position("depth:%d:face" % level)
	return _spread(level, p + Vector3(float(wid % 5) * 1.3 - 2.6, 0, 0), 0)


func haul_drop_point(level: int, wid: int = 0) -> Vector3:
	var p := sim.layout.position("depth:%d:station" % level)
	return _spread(level, p + Vector3(float(wid % 3) * 0.7, 0, 0.3), 0)


## Next stop for geologists and supervisors walking their rounds.
func wander_point(a: WorkerAgent, activity: String) -> Vector3:
	a._t += 1.0
	var n := int(a._t * 7.0 + float(a.wid) * 3.0)
	if a.level > 0:
		if activity == "survey":
			var slots: Array = sim.layout.data.get("gallery", {}).get("node_slots", [])
			var dep := sim.state.depth(a.level)
			var count := maxi(1, (dep.get("nodes", []) as Array).size())
			var s := n % mini(count, slots.size())
			return node_spot(a.level, s, 3 + (a.wid % 2))["pos"]
		var base := sim.layout.position("depth:%d:station" % a.level)
		return _spread(a.level, base + Vector3(float(n % 5) * 2.5, 0, 0), 0)
	var here := sim.layout.position(String(a.record.get("location", "plant")))
	var off := Vector3(float(n % 5) - 2.0, 0, float((n / 5) % 3) - 1.0) * 1.8
	return _spread(0, here + off, 0)


## Player commands from agents (the foreman's swings): through the Session
## when this world shows the session's game (events, tutorial, autosave),
## straight to the simulation for standalone worlds (tools, tests).
func command(cmd: Dictionary) -> Dictionary:
	if Session.sim == sim:
		return Session.command(cmd)
	return sim.execute(cmd)


# ------------------------------------------------------------------ effects

func on_impact(a: Agent, at: Vector3) -> void:
	if not a.rig.on_screen or _fx_budget < 1.0:
		return
	var cam := get_viewport().get_camera_3d()
	if cam == null or cam.global_position.distance_to(a.global_position) > 45.0:
		return
	_fx_budget -= 1.0
	var p := at.lerp(a.global_position + Vector3(0, 0.9, 0), 0.35)
	VfxLibrary.spawn(world, "rock_chips", p)
	if _sound_budget >= 1.0:
		_sound_budget -= 1.0
		Audio.play("pick_hit", p)


func on_foreman_swing(f: Foreman, r: Dictionary, at: Vector3) -> void:
	# The swing's sound and haptics come from the simulation's manual_mined
	# event (Audio); here only the chips fly.
	var p := at.lerp(f.global_position + Vector3(0, 0.9, 0), 0.3)
	if r.get("ok", false):
		VfxLibrary.spawn(world, "rock_chips", p)
		VfxLibrary.spawn(world, "sparks", p)
	else:
		VfxLibrary.spawn(world, "dust", p)


# ---------------------------------------------------------------- selection

func _on_selection_changed(target: String) -> void:
	selected = int(target.split(":")[1]) if target.begins_with("worker:") else -1


func _make_ring(c: Color) -> MeshInstance3D:
	var ring := MeshInstance3D.new()
	var tm := TorusMesh.new()
	tm.inner_radius = 0.5
	tm.outer_radius = 0.62
	tm.rings = 24
	tm.ring_segments = 6
	ring.mesh = tm
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = c
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	ring.material_override = mat
	ring.scale = Vector3(1, 0.25, 1)
	ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	ring.layers = Atmosphere.LAYER_SURFACE | Atmosphere.LAYER_UNDERGROUND
	return ring


## Agent position for events that name a worker (popups, camera focus).
func worker_position(id: int) -> Variant:
	if agents.has(id):
		return (agents[id] as Node3D).global_position
	return null
