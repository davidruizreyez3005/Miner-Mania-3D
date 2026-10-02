extends TestCase
## World validation: module definitions against the generated asset
## catalog, the surface camp layout at every tier, a full world build with
## every depth dug out and every facility at its top tier (zero placement
## errors: bounds, mounts, rotation/scale rules, overlaps, the walkway),
## navigation reachability of every work spot, cage routes between levels,
## agents acting out the simulation, and the scene's triangle budgets.

static var _world: MineWorld


static func _perf() -> Dictionary:
	var d = JsonUtil.load_file("res://data/performance.json")
	return d if d is Dictionary else {}


func _full_sim() -> Simulation:
	var sim := Simulation.new(content())
	sim.new_game(99)
	sim.state.money = 1e30
	sim.state.research_points = 1e12
	for t in content().tech_by_id:
		sim.state.techs[t] = true
	sim.invalidate_modifiers()
	for d in range(1, content().depth_count() + 1):
		sim.unlock_depth_internal(d)
	for q in content().quest_by_id:
		sim.state.quests[q] = "claimed"             # every role unlocked (haulers, supervisors, engineers)
	for f in content().facility_by_id:
		sim.execute({"type": "build", "facility": f})
		sim.execute({"type": "upgrade", "facility": f, "count": 1000})
	for d in range(1, 4):
		sim.execute({"type": "upgrade_equipment", "depth": d, "equipment": "mining", "count": 30})
		sim.execute({"type": "upgrade_equipment", "depth": d, "equipment": "haulage", "count": 12})
	for h in [["miner", "depth:1"], ["miner", "depth:1"], ["miner", "depth:1"], ["hauler", "depth:1"], ["miner", "depth:3"],
			["geologist", "depth:2"], ["supervisor", "depth:1"], ["operator", "headframe"], ["operator", "crusher"],
			["mechanic", "workshop"], ["engineer", "office"], ["supervisor", "plant"], ["miner", "depth:8"]]:
		sim.execute({"type": "hire", "role": h[0], "post": h[1]})
	return sim


func _world_full() -> MineWorld:
	if _world == null:
		var w: MineWorld = load("res://game/world/world.gd").new()
		(Engine.get_main_loop() as SceneTree).root.add_child(w)
		w.setup(_full_sim())
		_world = w
	return _world


func test_module_definitions_valid() -> void:
	var lib := ModuleLibrary.new(content())
	var e := lib.validate_definitions()
	assert_true(e.is_empty(), "module definition errors: %s" % str(e))
	assert_true(lib.defs.size() >= 30, "module library has %d modules" % lib.defs.size())


func test_module_validation_catches_bad_placements() -> void:
	var lib := ModuleLibrary.new(content())
	var t := Transform3D(Basis(), Vector3(-20.0, 0, -30.0))
	assert_true(lib.check("mod_container", t, "gallery", 1).size() > 0, "container outside the gallery zone rejected")
	assert_true(lib.check("mod_container", Transform3D(Basis(Vector3.UP, 0.3), Vector3(0, 0, -20)), "surface", 0).size() > 0,
		"off-grid rotation rejected")
	assert_true(lib.check("mod_crate", Transform3D(Basis().scaled(Vector3.ONE * 3.0), Vector3(0, 0, -20)), "surface", 0).size() > 0,
		"out-of-range scale rejected")
	lib.reserve("mod_container", Transform3D(Basis(), Vector3(0, 0, -20)), "surface", 0)
	assert_true(lib.check("mod_crate", Transform3D(Basis(), Vector3(0, 0, -20)), "surface", 0).size() > 0, "overlap rejected")
	assert_true(lib.check("unknown_module", Transform3D(), "surface", 0).size() > 0, "unknown module rejected")


func test_site_layout_valid_at_every_tier() -> void:
	var e := SiteLayout.problems(content(), WorldLayout.new(content()))
	assert_true(e.is_empty(), "camp layout problems: %s" % str(e))


func test_full_world_has_no_placement_errors() -> void:
	var w := _world_full()
	assert_true(w.modules.errors.is_empty(), "placement errors: %s" % str(w.modules.errors.slice(0, 12)))
	assert_eq(w.depth_views.size(), content().depth_count(), "every depth built")
	assert_eq(w.facility_views.size(), content().facilities.size() - 1, "every facility view (headframe is the lift)")
	assert_true(Assets.missing.is_empty(), "missing asset files: %s" % str(Assets.missing))


func test_navigation_reaches_every_stop() -> void:
	var w := _world_full()
	var nav := w.agents.nav
	for lvl in range(0, content().depth_count() + 1):
		var g := nav.grid(lvl)
		var start := nav.landing(lvl)
		var a := g.to_cell(g.snap(Vector2(start.x, start.z)))
		var stops: Array = []
		if lvl == 0:
			for loc in ["surface:rest", "surface:gate", "plant"]:
				stops.append([loc, w.layout.position(loc)])
			for fid in w.facility_views:
				stops.append(["facility:" + fid, (w.facility_views[fid] as FacilityView).work_transform("operate").origin])
				if content().facility(fid).get("repairable", false):
					stops.append(["facility:%s:repair" % fid, (w.facility_views[fid] as FacilityView).work_transform("repair").origin])
			stops.append(["facility:headframe:repair", w.lift_view.work_transform("repair").origin])
		else:
			for loc in ["station", "rest", "face"]:
				stops.append([loc, w.layout.position("depth:%d:%s" % [lvl, loc])])
			for slot in int(content().depth(lvl).get("node_slots", 3)):
				stops.append(["node %d" % slot, w.agents.node_spot(lvl, slot, 0)["pos"]])
		for st in stops:
			var p: Vector3 = st[1]
			var snapped := g.snap(Vector2(p.x, p.z))
			assert_true(snapped.distance_to(Vector2(p.x, p.z)) < 1.6, "level %d %s is far from walkable floor" % [lvl, st[0]])
			var b := g.to_cell(snapped)
			var ids := g.astar.get_id_path(a, b)
			assert_true(not ids.is_empty() or a == b, "level %d: no path from the landing to %s" % [lvl, st[0]])


func test_cage_route_between_levels() -> void:
	var w := _world_full()
	var nav := w.agents.nav
	var from := w.layout.position("surface:rest")
	var to: Vector3 = w.agents.node_spot(8, 0, 0)["pos"]
	var legs := nav.route(from, 0, to, 8)
	var kinds := []
	for l in legs:
		kinds.append(l["kind"])
	assert_true("ride" in kinds, "route rides the cage: %s" % str(kinds))
	var t := MineNav.route_time(legs, 2.6)
	assert_true(t > 10.0 and t < 200.0, "route time %.1f s" % t)
	var sim_t := w.layout.travel_time("surface:rest", "depth:8:node:0")
	assert_true(absf(t - sim_t) < sim_t * 0.6 + 8.0, "visual route (%.1f s) close to the simulation's travel time (%.1f s)" % [t, sim_t])


func test_mechanic_walks_between_machines() -> void:
	## The mechanic is seen walking its service round: it reaches several
	## different machines across the camp, and works at each one.
	var w := _world_full()
	var mech: WorkerAgent = null
	for a in w.agents.agents.values():
		if (a as WorkerAgent).role == "mechanic":
			mech = a
	if not assert_true(mech != null, "a mechanic agent exists"):
		return
	var spots: Array = []
	var worked := {}
	for i in 1800:
		w.sim.tick(0.1)
		w.sync(0.1)
		if not mech.moving and mech.activity in ["service", "repair"]:
			worked[String(mech.record["target"])] = true
			var p := mech.position
			var seen := false
			for q in spots:
				seen = seen or (q as Vector3).distance_to(p) < 3.0
			if not seen:
				spots.append(p)
	assert_ge(float(worked.size()), 3.0, "worked at several stops: %s" % str(worked.keys()))
	assert_ge(float(spots.size()), 3.0, "stood at several places across the camp (%d)" % spots.size())


func test_haulers_carry_ore() -> void:
	## Haulers walk the face <-> station loop with a sack - they used to
	## stand at the rest corner with nothing to do.
	var w := _world_full()
	var hauler: WorkerAgent = null
	for a in w.agents.agents.values():
		if (a as WorkerAgent).role == "hauler":
			hauler = a
	if not assert_true(hauler != null, "a hauler agent exists"):
		return
	var carried := false
	var empty := false
	var lo := INF
	var hi := -INF
	for i in 1500:
		w.sim.tick(0.1)
		w.sync(0.1)
		if hauler.activity == "haul":
			carried = carried or hauler.carrying
			empty = empty or not hauler.carrying
			lo = minf(lo, hauler.position.x)
			hi = maxf(hi, hauler.position.x)
	assert_true(carried and empty, "the hauler alternates carrying a sack and walking back (carried %s, empty %s)" % [carried, empty])
	assert_gt(hi - lo, 8.0, "it walks between the face and the station (%.1f m)" % (hi - lo))


## The smallest gap between two trucks' footprints over `ticks` (m, 0 when
## they touch or overlap); `left` marks the trucks that went out.
var closest_info := ""


func _closest_trucks(w: MineWorld, ticks: int, left: Array) -> float:
	var sv := w.sales_view
	var closest := INF
	for i in ticks:
		w.sim.tick(0.1)
		w.sync(0.1)
		var feet: Array = []
		for t in sv.trucks:
			feet.append(_footprint(t["node"], sv.model))
			if t["state"] == "out":
				left[sv.trucks.find(t)] = true
		for a in feet.size():
			for b in range(a + 1, feet.size()):
				var g := _poly_gap(feet[a], feet[b])
				if g < closest:
					closest = g
					var pa: Vector3 = sv.trucks[a]["node"].global_position
					var pb: Vector3 = sv.trucks[b]["node"].global_position
					closest_info = "tick %d: truck %d %s at (%.1f, %.1f), truck %d %s at (%.1f, %.1f)" % [i, a, sv.trucks[a]["state"], pa.x, pa.z,
						b, sv.trucks[b]["state"], pb.x, pb.z]
	return closest


## A truck's footprint on the ground (xz) as it is drawn.
func _footprint(node: Node3D, model: String) -> PackedVector2Array:
	var bb := Assets.bounds(model)
	var out := PackedVector2Array()
	for c in [Vector2(bb.position.x, bb.position.z), Vector2(bb.end.x, bb.position.z), Vector2(bb.end.x, bb.end.z), Vector2(bb.position.x, bb.end.z)]:
		var p := node.global_transform * Vector3(c.x, 0.0, c.y)
		out.append(Vector2(p.x, p.z))
	return out


static func _poly_gap(a: PackedVector2Array, b: PackedVector2Array) -> float:
	if a[0].distance_to(b[0]) > 16.0:
		return INF
	if not Geometry2D.intersect_polygons(a, b).is_empty():
		return 0.0
	var best := INF
	for k in 2:
		var p := a if k == 0 else b
		var q := b if k == 0 else a
		for v in p:
			for i in q.size():
				best = minf(best, v.distance_to(Geometry2D.get_closest_point_to_segment(v, q[i], q[(i + 1) % q.size()])))
	return best


func test_trucks_keep_their_distance() -> void:
	## Every truck has its own bay and they leave one after another: they never
	## drive or park inside each other - passing on the other lane, pulling out
	## across it or reversing into their bays - also when SELL sends them out
	## by hand.
	var w := _world_full()
	var sv := w.sales_view
	var bays := SiteLayout.truck_bays(w.layout)
	w.sim.tick(0.1)
	w.sync(0.1)                                       # the fleet follows the depot level
	assert_eq(sv.trucks.size(), mini(4, bays.size()), "a full fleet at the top depot level")
	var left := [false, false, false, false]
	w.sim.state.warehouse = {"stone": 1e9}
	var auto_gap := _closest_trucks(w, 900, left)
	assert_gt(auto_gap, 0.15, "automatic sales: trucks keep apart (closest %.2f m, %s)" % [auto_gap, closest_info])
	assert_eq(left.count(true), sv.trucks.size(), "every truck drives: %s" % str(left))
	# By hand: without the dispatch research the trucks wait for SELL.
	w.sim.state.techs.erase("automated_dispatch")
	w.sim.invalidate_modifiers()
	w.sim.state.warehouse = {"stone": 1e9}
	left = [false, false, false, false]
	_closest_trucks(w, 400, left)                     # trucks out on the auto sale come home
	left = [false, false, false, false]
	for k in 3:
		assert_ok(w.sim.execute({"type": "dispatch"}))
	var manual_gap := _closest_trucks(w, 700, left)
	assert_gt(manual_gap, 0.15, "SELL: trucks keep apart (closest %.2f m, %s)" % [manual_gap, closest_info])
	assert_eq(left.count(true), sv.trucks.size(), "SELL sends every truck out in turn: %s" % str(left))
	_closest_trucks(w, 300, [false, false, false, false])
	for i in sv.trucks.size():
		var p: Vector3 = sv.truck_positions()[i]
		var bay: Vector3 = bays[i]
		assert_lt(Vector2(p.x, p.z).distance_to(Vector2(bay.x, bay.z)), 0.5, "truck %d parks in its own bay" % i)
	w.sim.state.techs["automated_dispatch"] = true
	w.sim.invalidate_modifiers()


func test_agents_follow_simulation() -> void:
	var w := _world_full()
	assert_eq(w.agents.agents.size(), w.sim.state.workers.size(), "one agent per worker")
	for i in 600:
		w.sim.tick(0.1)
		w.sync(0.1)
	var settled := 0
	for a in w.agents.agents.values():
		var wa := a as WorkerAgent
		if not wa.moving:
			settled += 1
			assert_true(wa.position.distance_to(wa.spot.get("pos", wa.position)) < 3.5 or wa.activity in ["haul", "survey", "supervise", "manage"],
				"worker %d (%s) settled far from its spot" % [wa.wid, wa.role])
	assert_true(settled >= w.agents.agents.size() / 2, "most agents reached their work (%d/%d)" % [settled, w.agents.agents.size()])


func test_foreman_mines_through_the_simulation() -> void:
	var w := _world_full()
	var f := w.agents.foreman
	var before := float(w.sim.state.run_stats.get("manual_swings", 0.0))
	f.mine(1, 0)
	for i in 300:
		w.sim.tick(1.0 / 30.0)
		w.sync(1.0 / 30.0)
		# No frames run inside a test: advance the clips by hand so the
		# pick's impact frame fires exactly as in play.
		if f.rig.anim:
			f.rig.anim.advance(1.0 / 30.0)
		f.rig._check_events()
		if i % 20 == 0:
			f.mine(1, 0)
	assert_gt(float(w.sim.state.run_stats.get("manual_swings", 0.0)), before, "the foreman's swings reach the simulation")


func test_foreman_queues_taps_on_the_way() -> void:
	var w := _world_full()
	var f := w.agents.foreman
	# Start at the shaft landing of depth 1, clear of the veins.
	var start := w.agents.nav.landing(1) + Vector3(2.2, 0, 0.6)
	start.y = w.agents.nav.floor_y(1, start.x, start.z)
	f.walk_to(1, start)
	f.place(start, 1)
	f.rig.play("Idle")
	# A full vein and room at the station (the crews share this world).
	var dep := w.sim.state.depth(1)
	for n in dep["nodes"]:
		if int(n["slot"]) == 0:
			n["hp"] = n["max_hp"]
			n["respawn_at"] = -1.0
	var attempts := [0]
	f.swung.connect(func(_r: Dictionary) -> void: attempts[0] += 1)
	var before := float(w.sim.state.run_stats.get("manual_swings", 0.0))
	# Five taps while he runs to the vein: five swings when he gets there.
	for k in 5:
		f.mine(1, 0)
		for i in 3:
			w.sync(1.0 / 30.0)
	assert_true(f.moving, "the foreman is on his way")
	for i in 1200:
		(dep["station"] as Dictionary).clear()
		w.sync(1.0 / 30.0)
		if f.rig.anim:
			f.rig.anim.advance(1.0 / 30.0)
		f.rig._check_events()
	assert_eq(attempts[0], 5, "every tap on the way became a swing")
	assert_eq(float(w.sim.state.run_stats.get("manual_swings", 0.0)) - before, 5.0, "and each one mined")


func test_camera_drags_follow_the_finger() -> void:
	var w := _world_full()
	var rig := CameraRig.new()
	w.add_child(rig)
	rig.setup(w)
	assert_false(rig.has_method("rotate_by"), "the camera has no rotation")
	# Surface: a finger moving up the screen brings the cut edge (+z) closer.
	rig.focus_on(Vector3(4, 0, -20), 30.0)
	var z0 := rig.target_focus.z
	rig.pan_pixels(Vector2(0, -80))
	assert_gt(rig.target_focus.z, z0, "surface: drag up moves toward the cut edge")
	var x0 := rig.target_focus.x
	rig.pan_pixels(Vector2(-80, 0))
	assert_gt(rig.target_focus.x, x0, "surface: drag left moves the view right")
	# Underground: up the screen goes deeper, down comes back up.
	rig.focus_target("depth:3")
	var y0 := rig.target_focus.y
	rig.pan_pixels(Vector2(0, -80))
	assert_lt(rig.target_focus.y, y0, "underground: drag up goes deeper")
	y0 = rig.target_focus.y
	rig.pan_pixels(Vector2(0, 160))
	assert_gt(rig.target_focus.y, y0, "underground: drag down comes up")
	# One continuous drag up from the camp flows over the edge into the mine,
	# and down again back out of it.
	rig.focus_on(Vector3(4, 0, -6), 30.0)
	for k in 30:
		rig.pan_pixels(Vector2(0, -40))
	assert_lt(rig.target_focus.y, -1.0, "dragging up over the edge descends")
	for k in 60:
		rig.pan_pixels(Vector2(0, 40))
	assert_eq(rig.target_focus.y, 0.0, "dragging down climbs back to the camp")
	assert_lt(rig.target_focus.z, CameraRig.FRONT_Z, "and on into the camp")
	# While a finger is down the view sticks to it (no easing lag).
	rig.focus_target("depth:2")
	rig._process(1.0 / 30.0)
	rig.grab()
	rig.pan_pixels(Vector2(120, -60))
	rig._process(1.0 / 30.0)
	assert_true(rig.focus.is_equal_approx(rig.target_focus), "drag follows the finger 1:1")
	rig.dragging = false
	# The view never turns.
	for i in 30:
		rig._process(1.0 / 30.0)
	var fwd := -rig.camera.global_transform.basis.z
	assert_near(fwd.x, 0.0, 1e-4, "camera faces straight into the hills")
	rig.queue_free()


func _triangles(root: Node, budget_nodes: Array) -> int:
	budget_nodes.append(root.name)
	return _tris_under(root)


## Triangles drawn under `n`. Subtrees queued for deletion are skipped: the
## tests run simulation ticks without engine frames, so a vein model that
## regrew as another ore is freed only at the end of the frame.
static func _tris_under(n: Node) -> int:
	if n.is_queued_for_deletion():
		return 0
	var tri := 0
	var gi := n as GeometryInstance3D
	if gi != null and gi.visibility_range_begin <= 0.0:          # (> 0: a distant LOD level)
		if gi is MultiMeshInstance3D:
			var mm := (gi as MultiMeshInstance3D).multimesh
			if mm and mm.mesh:
				tri += _mesh_tris(mm.mesh) * mm.instance_count
		elif gi is MeshInstance3D and (gi as MeshInstance3D).mesh:
			tri += _mesh_tris((gi as MeshInstance3D).mesh)
	for c in n.get_children():
		tri += _tris_under(c)
	return tri


static func _mesh_tris(m: Mesh) -> int:
	var t := 0
	for s in m.get_surface_count():
		var arr := m.surface_get_arrays(s)
		var idx: PackedInt32Array = arr[Mesh.ARRAY_INDEX] if arr[Mesh.ARRAY_INDEX] != null else PackedInt32Array()
		t += idx.size() / 3 if idx.size() > 0 else (arr[Mesh.ARRAY_VERTEX] as PackedVector3Array).size() / 3
	return t


func test_scene_triangle_budgets() -> void:
	var w := _world_full()
	var perf := _perf()
	var tb: Dictionary = perf.get("triangles", {})
	var seen := []
	var surface := _triangles(w.surface_root, seen) + _triangles(w.decor_root, seen)
	assert_true(surface <= int(tb.get("surface_lod0", 3200000)), "surface LOD0 triangles %d over budget" % surface)
	for d in w.depth_views:
		var g := _triangles(w.depth_views[d], seen)
		assert_true(g <= int(tb.get("gallery_lod0_each", 350000)), "depth %d gallery triangles %d over budget" % [d, g])
	for id in Assets.assets:
		var a: Dictionary = Assets.assets[id]
		if String(a.get("type", "")) == "character":
			assert_true(int(a.get("triangles", 0)) <= int(tb.get("character_lod0", 26000)), "%s over the character budget" % id)
	print("     surface LOD0 triangles: %d" % surface)
