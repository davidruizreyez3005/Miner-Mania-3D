extends TestCase
## Graphics presets: the data is sane and ordered (Low is the cheapest in
## every respect), first-launch device detection picks Low for entry-level
## phones, a built world follows the preset (lights, scenery, shadows,
## materials) and comes back intact, the player's choice sticks, and the
## frame-rate watchdog steps an automatic choice down when frames are slow.

const KEYS := ["name", "render_scale", "msaa", "anisotropy", "mesh_lod_threshold", "shadows", "shadow_atlas", "shadow_distance",
	"glow", "lite_shaders", "lite_materials", "gallery_lamps", "shaft_lights", "crystal_lights", "decor_density", "grass",
	"decor_shadows", "detail_scale", "max_full_rigs", "vfx", "camera_far", "fps"]
const GB := 1073741824

static var _world: MineWorld


func after_each() -> void:
	# Leave the session's settings as they were for the other suites.
	Settings.values["quality"] = GraphicsQuality.HIGH
	Settings.values["quality_auto"] = true
	Settings._apply("quality")


func test_presets_complete_and_ordered() -> void:
	var p := GraphicsQuality.presets()
	assert_eq(p.size(), 3, "Low, Medium, High")
	for q in p.size():
		for k in KEYS:
			assert_true((p[q] as Dictionary).has(k), "%s preset has %s" % [p[q].get("name", q), k])
	var low: Dictionary = p[0]
	var med: Dictionary = p[1]
	var high: Dictionary = p[2]
	for k in ["render_scale", "msaa", "anisotropy", "gallery_lamps", "decor_density", "detail_scale", "max_full_rigs", "vfx", "camera_far"]:
		assert_true(float(low[k]) <= float(med[k]) and float(med[k]) <= float(high[k]), "%s grows from Low to High" % k)
	assert_true(float(low["mesh_lod_threshold"]) >= float(med["mesh_lod_threshold"]), "Low simplifies meshes most")
	assert_false(low["shadows"], "Low has no sun shadows")
	assert_false(low["glow"], "Low has no glow")
	assert_true(low["lite_shaders"] and low["lite_materials"], "Low uses the cheap shading")
	assert_false(high["lite_shaders"] or high["lite_materials"], "High uses the full shading")
	assert_eq(int(low["fps"]), 30, "Low caps at 30 fps")
	assert_true(float(low["render_scale"]) >= 0.5 and float(high["render_scale"]) == 1.0, "render scales")


func test_device_detection() -> void:
	var cases := [
		["llvmpipe", 16 * GB, "forward_plus", false, GraphicsQuality.HIGH, "desktop"],
		["Adreno (TM) 740", 12 * GB, "gl_compatibility", true, GraphicsQuality.LOW, "OpenGL ES fallback"],
		["Adreno (TM) 740", 3 * GB, "mobile", true, GraphicsQuality.LOW, "3 GB phone"],
		["Mali-G52 MC2", 6 * GB, "mobile", true, GraphicsQuality.LOW, "Mali-G52"],
		["Mali-G57 MC1", 4 * GB + GB / 2 + 1, "mobile", true, GraphicsQuality.LOW, "Mali-G57"],
		["PowerVR Rogue GE8320", 6 * GB, "mobile", true, GraphicsQuality.LOW, "PowerVR GE8320"],
		["Adreno (TM) 610", 6 * GB, "mobile", true, GraphicsQuality.LOW, "Adreno 610"],
		["Adreno (TM) 506", 6 * GB, "mobile", true, GraphicsQuality.LOW, "Adreno 506"],
		["Adreno (TM) 650", 6 * GB, "mobile", true, GraphicsQuality.MEDIUM, "Adreno 650"],
		["Mali-G68 MC4", 8 * GB, "mobile", true, GraphicsQuality.MEDIUM, "Mali-G68"],
		["Adreno (TM) 740", 12 * GB, "mobile", true, GraphicsQuality.HIGH, "Adreno 740"],
		["Mali-G710 MC10", 8 * GB, "mobile", true, GraphicsQuality.HIGH, "Mali-G710"],
		["Adreno (TM) 740", 0, "mobile", true, GraphicsQuality.MEDIUM, "flagship GPU, memory unknown"],
		["Some Future GPU", 8 * GB, "mobile", true, GraphicsQuality.MEDIUM, "unknown GPU"],
	]
	for c in cases:
		var r := GraphicsQuality.detect(String(c[0]), int(c[1]), String(c[2]), bool(c[3]))
		assert_eq(int(r["quality"]), int(c[4]), "%s -> %s (%s)" % [c[5], GraphicsQuality.value(int(c[4]), "name"), r["reason"]])


func _small_world() -> MineWorld:
	if _world == null:
		var sim := Simulation.new(content())
		sim.new_game(7)
		sim.state.money = 1e9
		sim.unlock_depth_internal(2)
		var w: MineWorld = load("res://game/world/world.gd").new()
		(Engine.get_main_loop() as SceneTree).root.add_child(w)
		w.setup(sim)
		_world = w
	return _world


func test_world_follows_the_preset() -> void:
	var w := _small_world()
	Settings.set_value("quality", GraphicsQuality.LOW, false)
	var dv: DepthView = w.depth_views[1]
	var lit := 0
	for l in dv.lights:
		lit += 1 if (l as Light3D).visible else 0
	assert_eq(lit, 0, "Low: hanging lamps only glow")
	assert_gt(dv.fill.light_energy, DepthView.FILL_ENERGY, "Low: the fill light takes over")
	assert_false(w.atmosphere.sun.shadow_enabled, "Low: no sun shadows")
	assert_eq(w.atmosphere.sun.shadow_caster_mask, Atmosphere.LAYER_SURFACE, "the galleries never cast sun shadows")
	assert_true(WorldMaterials.lite and MaterialLite.lite, "Low: cheap shading")
	assert_eq((dv.gallery.material_override as ShaderMaterial).shader, WorldMaterials.ROCK_LITE_SHADER, "lite rock shader")
	var shown := 0
	var total := 0
	var grass := 0
	for item in w.decor:
		var mmi: MultiMeshInstance3D = item["mmi"]
		var n := mmi.multimesh.visible_instance_count
		n = mmi.multimesh.instance_count if n < 0 else n
		if not mmi.visible:
			n = 0
		if String(item["kind"]) == "grass":
			grass += n
		elif String(item["kind"]) != "cliff":
			shown += n
			total += int(item["count"])
		assert_eq(mmi.cast_shadow, GeometryInstance3D.SHADOW_CASTING_SETTING_OFF, "Low: scenery casts no shadows")
	assert_eq(grass, 0, "Low: no grass")
	assert_true(total > 0 and float(shown) <= float(total) * 0.35 + float(w.decor.size()), "Low thins the scenery (%d of %d)" % [shown, total])
	for l in w._shaft_lights:
		assert_false((l as Light3D).visible, "Low: no shaft lights")
	# Back to High: everything returns.
	Settings.set_value("quality", GraphicsQuality.HIGH, false)
	lit = 0
	for l in dv.lights:
		lit += 1 if (l as Light3D).visible else 0
	assert_eq(lit, dv.lights.size(), "High: every lamp shines")
	assert_near(dv.fill.light_energy, DepthView.FILL_ENERGY, 1e-6, "High: normal fill")
	assert_true(w.atmosphere.sun.shadow_enabled, "High: sun shadows")
	assert_eq((dv.gallery.material_override as ShaderMaterial).shader, WorldMaterials.ROCK_SHADER, "full rock shader")
	var params_ok := (dv.gallery.material_override as ShaderMaterial).get_shader_parameter("rock_normal") != null
	assert_true(params_ok, "full shader parameters restored after the lite one")
	for item in w.decor:
		var mmi2: MultiMeshInstance3D = item["mmi"]
		assert_true(mmi2.visible and mmi2.multimesh.visible_instance_count < 0, "High: all scenery")
	# Medium: every other lamp.
	Settings.set_value("quality", GraphicsQuality.MEDIUM, false)
	lit = 0
	for l in dv.lights:
		lit += 1 if (l as Light3D).visible else 0
	assert_eq(lit, 2, "Medium: two lamps shine")


func test_viewport_follows_the_preset() -> void:
	var root := (Engine.get_main_loop() as SceneTree).root
	Settings.set_value("quality", GraphicsQuality.LOW, false)
	assert_near(root.scaling_3d_scale, float(GraphicsQuality.value(0, "render_scale")), 1e-6, "Low 3D resolution")
	assert_eq(root.msaa_3d, Viewport.MSAA_DISABLED, "Low: no MSAA")
	assert_eq(int(root.anisotropic_filtering_level), 0, "Low: no anisotropic filtering")
	Settings.set_value("quality", GraphicsQuality.HIGH, false)
	assert_near(root.scaling_3d_scale, 1.0, 1e-6, "High: full resolution")


func test_player_choice_sticks_and_brings_the_frame_cap() -> void:
	var fps0 := int(Settings.get_value("fps_limit", 60))
	Settings.choose_quality(GraphicsQuality.LOW)
	assert_false(bool(Settings.get_value("quality_auto", true)), "a picked quality is no longer automatic")
	assert_eq(int(Settings.get_value("fps_limit", 0)), 30, "Low brings 30 fps")
	assert_eq(Engine.max_fps, 30)
	Settings.choose_quality(GraphicsQuality.HIGH)
	assert_eq(int(Settings.get_value("fps_limit", 0)), 60, "High brings 60 fps")
	Settings.set_value("fps_limit", fps0, false)


func test_watchdog_steps_down_when_frames_are_slow() -> void:
	var gs := GameState.fsm
	var base0 := gs.base
	var overlays0 := gs.overlays.duplicate()
	Settings.values["quality"] = GraphicsQuality.HIGH
	Settings.values["quality_auto"] = true
	Settings.values["fps_limit"] = 60
	Settings._apply("quality")
	Settings._apply("fps_limit")
	gs.base = GameStateMachine.State.PLAYING
	gs.overlays.clear()
	var wd := FrameWatchdog.new()
	# 10 fps for the settle time and a whole window.
	for i in 260:
		wd._process(0.1)
	assert_eq(GraphicsQuality.current(), GraphicsQuality.MEDIUM, "slow frames: one level down")
	for i in 260:
		wd._process(0.1)
	assert_eq(GraphicsQuality.current(), GraphicsQuality.LOW, "still slow: Low")
	assert_eq(Engine.max_fps, 30, "Low caps at 30 fps")
	for i in 260:
		wd._process(0.1)
	assert_eq(GraphicsQuality.current(), GraphicsQuality.LOW, "never below Low")
	# A quality the player picked is left alone.
	Settings.choose_quality(GraphicsQuality.HIGH)
	for i in 260:
		wd._process(0.1)
	assert_eq(GraphicsQuality.current(), GraphicsQuality.HIGH, "the player's choice stays")
	wd.free()
	gs.base = base0
	gs.overlays.assign(overlays0)
	Settings.values["fps_limit"] = 60
	Settings._apply("fps_limit")
