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


func _triangles(root: Node, budget_nodes: Array) -> int:
	var tri := 0
	for n in root.find_children("*", "GeometryInstance3D", true, false):
		var gi := n as GeometryInstance3D
		if gi.visibility_range_begin > 0.0:
			continue                              # a distant LOD level
		if gi is MultiMeshInstance3D:
			var mm := (gi as MultiMeshInstance3D).multimesh
			if mm and mm.mesh:
				tri += _mesh_tris(mm.mesh) * mm.instance_count
		elif gi is MeshInstance3D and (gi as MeshInstance3D).mesh:
			tri += _mesh_tris((gi as MeshInstance3D).mesh)
	budget_nodes.append(root.name)
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
