extends SceneTree
## Performance report against data/performance.json: a late-game mine (every
## depth dug, every facility built, a 60-strong crew) is built and run;
## measures world build time, simulation tick cost, per-frame world + agent
## update cost, and - when a renderer is present - draw calls, primitives and
## video memory for the typical views. Exits 1 when a CPU budget is missed.
##
##   godot --headless --path . --script res://tools/godot/perf_report.gd -- [--json out.json]

var world
var sim: Simulation
var report := {}
var cam: Camera3D


func _initialize() -> void:
	await process_frame
	var perf: Dictionary = JsonUtil.load_file("res://data/performance.json")
	sim = Simulation.new(ContentDB.load_default())
	sim.new_game(4242)
	sim.state.money = 1e30
	sim.state.research_points = 1e12
	for t in sim.content.tech_by_id:
		sim.state.techs[t] = true
	sim.invalidate_modifiers()
	for d in range(1, sim.content.depth_count() + 1):
		sim.unlock_depth_internal(d)
	for f in sim.content.facility_by_id:
		sim.execute({"type": "build", "facility": f})
		sim.execute({"type": "upgrade", "facility": f, "count": 1000})
	for d in range(1, sim.content.depth_count() + 1):
		sim.execute({"type": "upgrade_equipment", "depth": d, "equipment": "mining", "count": 100})
		sim.execute({"type": "upgrade_equipment", "depth": d, "equipment": "haulage", "count": 60})
	var hired := 0
	for round in 12:
		for d in range(1, sim.content.depth_count() + 1):
			for role in ["miner", "miner", "hauler"]:
				if sim.execute({"type": "hire", "role": role, "post": "depth:%d" % d}).get("ok", false):
					hired += 1
	for h in [["operator", "headframe"], ["operator", "crusher"], ["operator", "washer"], ["operator", "sorter"],
			["operator", "smelter"], ["operator", "refinery"], ["mechanic", "workshop"], ["engineer", "office"], ["supervisor", "plant"]]:
		if sim.execute({"type": "hire", "role": h[0], "post": h[1]}).get("ok", false):
			hired += 1
	report["workers"] = sim.state.workers.size()
	# Simulation tick cost.
	var t0 := Time.get_ticks_usec()
	for i in 600:
		sim.tick(0.1)
	report["sim_tick_ms"] = float(Time.get_ticks_usec() - t0) / 1000.0 / 600.0
	# World build.
	world = load("res://game/world/world.gd").new()
	root.add_child(world)
	t0 = Time.get_ticks_usec()
	world.setup(sim)
	report["world_build_ms"] = float(Time.get_ticks_usec() - t0) / 1000.0
	report["world_build_steps_ms"] = world.timings
	report["agents"] = world.agents.agents.size()
	cam = Camera3D.new()
	cam.fov = 52
	cam.far = 700
	root.add_child(cam)
	cam.current = true
	_look(Vector3(4, -8.0, 26), Vector3(4, -10.2, -3.8))
	# Per-frame world/agent update cost (CPU side, 60 Hz steps).
	for i in 30:
		await process_frame
	t0 = Time.get_ticks_usec()
	var frames := 240
	for i in frames:
		sim.tick(1.0 / 60.0)
		world.sync(1.0 / 60.0)
	report["world_sync_ms"] = float(Time.get_ticks_usec() - t0) / 1000.0 / float(frames)
	report["memory_static_mb"] = float(OS.get_static_memory_usage()) / 1e6
	# Rendering statistics (only with a real renderer).
	if DisplayServer.get_name() != "headless":
		report["views"] = {}
		for v in [["gallery", Vector3(4, -8.0, 26), Vector3(4, -10.2, -3.8)], ["surface", Vector3(4, 22, 20), Vector3(4, 0, -14)],
				["overview", Vector3(2, -30, 90), Vector3(2, -40, -5)]]:
			_look(v[1], v[2])
			for i in 8:
				await process_frame
			var rs := RenderingServer
			report["views"][v[0]] = {
				"draw_calls": rs.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME),
				"objects": rs.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_OBJECTS_IN_FRAME),
				"primitives": rs.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME),
			}
		report["video_memory_mb"] = float(RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_VIDEO_MEM_USED)) / 1e6
		report["texture_memory_mb"] = float(RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TEXTURE_MEM_USED)) / 1e6
	# Budgets.
	var fails := []
	var sim_budget := float(perf.get("sim", {}).get("tick_ms", 4.0))
	if float(report["sim_tick_ms"]) > sim_budget:
		fails.append("simulation tick %.2f ms > %.2f ms" % [report["sim_tick_ms"], sim_budget])
	var frame_budget := 1000.0 / float(perf.get("target_fps", 60)) * 0.5
	if float(report["world_sync_ms"]) > frame_budget:
		fails.append("world update %.2f ms > %.2f ms (half a %d fps frame)" % [report["world_sync_ms"], frame_budget, int(perf.get("target_fps", 60))])
	report["budget_failures"] = fails
	report["passed"] = fails.is_empty()
	print(JSON.stringify(report, "  "))
	var a := OS.get_cmdline_user_args()
	var i := a.find("--json")
	if i >= 0 and i + 1 < a.size():
		var f := FileAccess.open(a[i + 1], FileAccess.WRITE)
		if f:
			f.store_string(JSON.stringify(report, "  "))
	quit(0 if fails.is_empty() else 1)


func _look(eye: Vector3, at: Vector3) -> void:
	cam.global_transform = Transform3D(Basis(), eye).looking_at(at, Vector3.UP)
