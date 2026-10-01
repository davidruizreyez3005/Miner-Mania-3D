extends SceneTree
## Frame-cost benchmark of the real game (main.tscn): a claim at a given
## stage is saved, loaded through the title screen and played; for each
## camera view it measures the frame time (average and 90th percentile), the
## CPU time of scripts and engine processing, draw calls, triangles and
## objects, at a given graphics quality. With a renderer (for example Xvfb +
## Mesa lavapipe / llvmpipe) the numbers include rendering and compare
## settings, stages and renderers on one machine; headless gives the CPU
## side only.
##
##   godot --path . --resolution 720x1600 --script res://tools/godot/bench_frame.gd -- \
##         [--stage early|mid|late] [--quality 0|1|2|auto] [--frames 90] [--json out.json] [--shots <dir>] [--check]
##
## --check compares draw calls and triangles with data/performance.json
## (graphics.render_budgets) and exits 1 when a view is over budget.

const VIEWS := ["gallery", "surface", "plant"]

var main: Node
var report := {}
# Loaded at run time: it reads the Settings autoload, which a --script tool
# cannot name at compile time.
var gq: GDScript


func _initialize() -> void:
	await process_frame
	gq = load("res://game/core/graphics_quality.gd")
	var stage := _arg("--stage", "mid")
	var frames := int(_arg("--frames", "90"))
	var sim := _claim(stage)
	var saves = root.get_node("SaveService")
	saves.delete_all()
	sim.state.meta["tutorial_done"] = true
	sim.state.meta["tutorial_step"] = 99
	saves.write(sim.state, int(Time.get_unix_time_from_system()))
	var q := _arg("--quality", "")
	if q != "" and q != "auto":
		# As a player would pick it (the frame-rate watchdog then leaves it alone).
		root.get_node("Settings").choose_quality(int(q))
	main = (load("res://game/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	var gs = root.get_node("GameState")
	while gs.current() != GameStateMachine.State.MAIN_MENU:
		await process_frame
	Engine.max_fps = 0
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	# Headless frames are otherwise paced (low-processor sleep): measure the
	# work itself.
	OS.low_processor_usage_mode_sleep_usec = 0
	main._start("continue")
	while gs.fsm.base != GameStateMachine.State.PLAYING:
		await process_frame
	main.ui.close_all()
	# Experiments: override viewport settings (--msaa 0..3, --scale 0.5..1,
	# --aniso 0..4, --lod <pixels>).
	for kv in [["--msaa", "msaa_3d"], ["--scale", "scaling_3d_scale"], ["--aniso", "anisotropic_filtering_level"], ["--lod", "mesh_lod_threshold"]]:
		var val := _arg(String(kv[0]), "")
		if val != "":
			root.set(String(kv[1]), float(val) if String(kv[1]) in ["scaling_3d_scale", "mesh_lod_threshold"] else int(val))
	var vp_rid := root.get_viewport_rid()
	RenderingServer.viewport_set_measure_render_time(vp_rid, true)
	report = {"stage": stage, "quality": int(root.get_node("Settings").get_value("quality", 1)),
		"renderer": "%s/%s" % [RenderingServer.get_current_rendering_method(), RenderingServer.get_current_rendering_driver_name()],
		"window": str(root.get_window().size) if root.get_window() else "", "view_size": str(root.get_visible_rect().size),
		"msaa_3d": root.msaa_3d, "scaling_3d_scale": root.scaling_3d_scale, "anisotropy": root.anisotropic_filtering_level,
		"mesh_lod_threshold": root.mesh_lod_threshold,
		"workers": sim.state.workers.size(), "depths": sim.state.deepest_unlocked(), "views": {}}
	# Visit every view once first: pipelines compile on first sight.
	for v in VIEWS:
		_focus(v)
		for i in 40:
			await process_frame
	for v in VIEWS:
		_focus(v)
		for i in 60:
			await process_frame
		var times: Array = []
		var proc := 0.0                   # Performance TIME_PROCESS: the slowest process step of the last second
		var rcpu := 0.0
		var rgpu := 0.0
		var t_prev := Time.get_ticks_usec()
		for i in frames:
			await process_frame
			var t := Time.get_ticks_usec()
			times.append(float(t - t_prev) / 1000.0)
			t_prev = t
			proc = maxf(proc, Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0)
			rcpu += RenderingServer.viewport_get_measured_render_time_cpu(vp_rid)
			rgpu += RenderingServer.viewport_get_measured_render_time_gpu(vp_rid)
		var shots := _arg("--shots", "")
		if shots != "":
			DirAccess.make_dir_recursive_absolute(shots)
			root.get_viewport().get_texture().get_image().save_png(shots.path_join("%s_q%d_%s.png" % [stage, int(report["quality"]), v]))
		times.sort()
		var sum := 0.0
		for x in times:
			sum += float(x)
		var rs := RenderingServer
		report["views"][v] = {
			"frame_ms_avg": snappedf(sum / float(frames), 0.01),
			"frame_ms_p90": snappedf(float(times[int(frames * 0.9)]), 0.01),
			"process_ms_max": snappedf(proc, 0.01),
			"render_cpu_ms": snappedf(rcpu / float(frames), 0.01),
			"render_gpu_ms": snappedf(rgpu / float(frames), 0.01),
			"draw_calls": rs.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME),
			"primitives": rs.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME),
			"objects": rs.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_OBJECTS_IN_FRAME),
		}
	report["video_memory_mb"] = snappedf(float(RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_VIDEO_MEM_USED)) / 1e6, 0.1)
	var over := _check_budgets(stage)
	print(JSON.stringify(report, "  "))
	print("bench_frame: %s claim, %s, %s: %s" % [stage, String(gq.value(int(report["quality"]), "name", "?")), report["renderer"],
		("over budget: " + "; ".join(PackedStringArray(over))) if not over.is_empty() else "within budget"])
	var jp := _arg("--json", "")
	if jp != "":
		var f := FileAccess.open(jp, FileAccess.WRITE)
		if f:
			f.store_string(JSON.stringify(report, "  "))
	main.queue_free()
	for i in 10:
		await process_frame
	saves.delete_all()
	quit(1 if OS.get_cmdline_user_args().has("--check") and not over.is_empty() else 0)


## Views over their draw-call / triangle budget (empty when within, or when
## the stage and preset have no budget).
func _check_budgets(stage: String) -> Array:
	var over: Array = []
	var budgets: Dictionary = gq.data().get("render_budgets", {}).get(stage, {}).get(
		String(gq.value(int(report["quality"]), "name", "")), {})
	report["budget"] = budgets
	if budgets.is_empty() or DisplayServer.get_name() == "headless":
		return over
	for v in report["views"]:
		var r: Dictionary = report["views"][v]
		if int(r["draw_calls"]) > int(budgets.get("draw_calls", 1 << 30)):
			over.append("%s %d draw calls > %d" % [v, r["draw_calls"], budgets["draw_calls"]])
		if int(r["primitives"]) > int(budgets.get("triangles", 1 << 30)):
			over.append("%s %d triangles > %d" % [v, r["primitives"], budgets["triangles"]])
	report["over_budget"] = over
	return over


## A claim at a stage of the game, played by the autoplay bot (cached in
## user:// between runs).
func _claim(stage: String) -> Simulation:
	var cache := "user://bench_%s.save" % stage
	var content := ContentDB.load_default()
	if FileAccess.file_exists(cache):
		var r := SaveCodec.decode(FileAccess.get_file_as_string(cache))
		if r.get("ok", false):
			return Simulation.new(content, r["state"])
	var sim := _play(stage, content)
	var f := FileAccess.open(cache, FileAccess.WRITE)
	if f:
		f.store_string(SaveCodec.encode(sim.state, int(Time.get_unix_time_from_system())))
	return sim


func _play(stage: String, content: ContentDB) -> Simulation:
	var sim := Simulation.new(content)
	sim.new_game(4242)
	match stage:
		"early":
			var bot := AutoplayBot.new(sim)
			bot.play(240.0, 0.5)
		"mid":
			AutoplayBot.new(sim).play(3 * 3600.0, 1.0)
		"late":
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
			for round in 8:
				for d in range(1, sim.content.depth_count() + 1):
					for role in ["miner", "miner", "hauler"]:
						sim.execute({"type": "hire", "role": role, "post": "depth:%d" % d})
			sim.advance(60.0, 0.5)
	return sim


func _focus(v: String) -> void:
	var rig = main.camera_rig()
	match v:
		"gallery":
			rig.focus_target("depth:1")
		"surface":
			rig.focus_target("surface")
		"plant":
			rig.focus_on(Vector3(0.0, 0.0, -18.0), 22.0)


func _arg(name: String, default: String) -> String:
	var a := OS.get_cmdline_user_args()
	var i := a.find(name)
	return a[i + 1] if i >= 0 and i + 1 < a.size() else default
