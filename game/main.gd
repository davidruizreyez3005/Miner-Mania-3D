extends Node
## Application root. Every step of the flow is a game-state transition:
##
##   BOOT      splash; check the game data (asset catalog, content)
##   MAIN_MENU title screen over a small 3D diorama; continue / new claim
##   LOADING   load or start the claim, catch up offline time, preload the
##             models, build the world step by step (progress bar)
##   PLAYING   world + HUD; overlays (panels, popups, pause, tutorial) on top
##   ERROR     a friendly message with a way back to the title
##
## Prestige rebuilds the world through LOADING; quitting to the title saves.

const State := GameStateMachine.State
const TIPS := [
	"Tap a vein again and again: every swing of the foreman's pick is ore in the bank.",
	"A full shaft station stops the miners. Wind the lift or hire a lift operator.",
	"Processing multiplies value: crushed, washed, sorted, smelted, refined.",
	"The Flow screen shows your bottleneck. Upgrade the slowest stage first.",
	"Workers keep mining while you are away - up to the offline limit.",
	"Deeper levels hold richer ore - and flooding, gas, heat and worse.",
	"Selling the claim gives Legacy Points: permanent income for every future claim.",
]

var ui: UiRoot
var world: MineWorld
var rig: CameraRig
var touch: TouchInput
var screen: Control
var diorama: MenuDiorama
var fps_label: Label
var _mode := "continue"                 # continue | new | rebuild
var _progress: ProgressBar
var _progress_label: Label
var _tip_label: Label


func _ready() -> void:
	ui = UiRoot.new()
	ui.main = self
	add_child(ui)
	EventBus.state_changed.connect(_on_state_changed)
	EventBus.sim_event.connect(_on_sim_event)
	EventBus.offline_report.connect(_on_offline_report)
	EventBus.settings_changed.connect(func(k: String, _v: Variant) -> void:
		if k == "show_fps":
			fps_label.visible = bool(Settings.get_value("show_fps", false)))
	get_tree().set_auto_accept_quit(false)
	get_tree().set_quit_on_go_back(false)
	fps_label = UiKit.label("", "Caption")
	fps_label.position = Vector2(16, 4)
	fps_label.visible = bool(Settings.get_value("show_fps", false))
	ui.root.add_child(fps_label)
	var watchdog := FrameWatchdog.new()
	watchdog.name = "FrameWatchdog"
	add_child(watchdog)
	_boot()


func world_ref() -> MineWorld:
	return world


func camera_rig() -> CameraRig:
	return rig


# -------------------------------------------------------------------- boot

func _boot() -> void:
	_show_screen(_splash("Waking up the mine..."))
	await get_tree().process_frame
	print("[boot] Miner Mania 3D %s on %s: window %s, view %s, %s/%s (%s), graphics %s%s" % [
		String(ProjectSettings.get_setting("application/config/version", "?")), OS.get_name(),
		str(get_window().size), str(get_viewport().get_visible_rect().size),
		RenderingServer.get_current_rendering_method(), RenderingServer.get_current_rendering_driver_name(),
		RenderingServer.get_video_adapter_name(), String(GraphicsQuality.current_value("name", "?")),
		" (auto)" if bool(Settings.get_value("quality_auto", true)) else ""])
	if Assets.assets.is_empty():
		GameState.fail("The game's model library is missing. Please reinstall Miner Mania 3D.")
		return
	if Session.content == null or not Session.content.load_errors.is_empty():
		GameState.fail("The game data could not be read. Please reinstall Miner Mania 3D.")
		return
	if not Session.content_errors.is_empty():
		push_warning("Content validation reported %d problems" % Session.content_errors.size())
	Assets.preload_assets(MenuDiorama.PRELOAD)
	var t0 := Time.get_ticks_msec()
	while Assets.preload_progress() < 1.0 or Time.get_ticks_msec() - t0 < 900:
		if _progress:
			_progress.value = Assets.preload_progress()
		await get_tree().process_frame
	GameState.request(State.MAIN_MENU)


func _on_state_changed(from: int, to: int) -> void:
	match to:
		State.MAIN_MENU:
			if from != State.SETTINGS:
				_show_menu()
		State.LOADING:
			_load()
		State.ERROR:
			_show_error(String(GameState.payload.get("message", "Something went wrong.")))


# -------------------------------------------------------------------- menu

func _show_menu() -> void:
	_teardown_game()
	if diorama == null:
		diorama = MenuDiorama.new()
		add_child(diorama)
		diorama.build(Session.content.regions[0])
	var c := Control.new()
	c.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	c.theme = UiTheme.get_theme()
	var grad := TextureRect.new()
	var gt := GradientTexture2D.new()
	gt.fill_from = Vector2(0, 0)
	gt.fill_to = Vector2(0, 1)
	var g := Gradient.new()
	g.set_color(0, Color(0, 0, 0, 0.0))
	g.set_color(1, Color(0.04, 0.05, 0.07, 0.92))
	g.add_point(0.45, Color(0, 0, 0, 0.1))
	gt.gradient = g
	grad.texture = gt
	grad.stretch_mode = TextureRect.STRETCH_SCALE
	grad.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	grad.mouse_filter = Control.MOUSE_FILTER_IGNORE
	c.add_child(grad)
	var v := UiKit.vbox(18)
	v.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	v.offset_left = 48
	v.offset_right = -48
	v.offset_top = 150
	v.offset_bottom = -90
	c.add_child(v)
	var t := UiKit.label("MINER MANIA", "Big", HORIZONTAL_ALIGNMENT_CENTER)
	t.add_theme_font_size_override("font_size", 84)
	t.add_theme_constant_override("outline_size", 14)
	t.add_theme_color_override("font_outline_color", Color("2a1a04"))
	v.add_child(t)
	var t2 := UiKit.label("3D", "Big", HORIZONTAL_ALIGNMENT_CENTER)
	t2.add_theme_font_size_override("font_size", 60)
	t2.add_theme_color_override("font_color", UiTheme.TEAL)
	t2.add_theme_constant_override("outline_size", 12)
	t2.add_theme_color_override("font_outline_color", Color("06221f"))
	v.add_child(t2)
	v.add_child(UiKit.label("Dig deep. Build an empire.", "Heading", HORIZONTAL_ALIGNMENT_CENTER))
	var sp := UiKit.spacer(false)
	sp.size_flags_vertical = Control.SIZE_EXPAND_FILL
	v.add_child(sp)
	var has_save := SaveService.has_save()
	if has_save:
		v.add_child(UiKit.button("Continue", func() -> void: _start("continue"), "Primary", 110))
	v.add_child(UiKit.button("New claim" if has_save else "Start mining", func() -> void:
		if has_save:
			ui.open_panel("confirm", {"text": "Start a brand-new claim? Your current mine, legacy and achievements will be erased.",
				"yes": "Start over", "action": func() -> void:
					SaveService.delete_all()
					_start("new")})
		else:
			_start("new"), "Teal" if has_save else "Primary", 110))
	v.add_child(UiKit.button("Settings", func() -> void: ui.open_panel("settings"), "Chip", 90))
	var ver := UiKit.label("v%s" % String(ProjectSettings.get_setting("application/config/version", "1.0.0")), "Caption", HORIZONTAL_ALIGNMENT_CENTER)
	v.add_child(ver)
	_show_screen(c, true)
	Audio.set_music("surface")
	Audio.set_ambience("surface")


func _start(mode: String) -> void:
	_mode = mode
	GameState.request(State.LOADING)


# ----------------------------------------------------------------- loading

func _load() -> void:
	ui.close_all()
	ui.show_game(false)
	_show_screen(_splash("Opening the claim..."))
	await get_tree().process_frame
	match _mode:
		"continue":
			if not Session.load_game():
				Session.new_game()
		"new":
			Session.new_game()
		"rebuild":
			pass
	var s := Session.sim
	# Offline catch-up before the world is built, so it shows the result.
	while Session.offline_in_progress():
		var f := Session.step_offline()
		_set_progress(0.05 + 0.25 * f, "Catching up on %s away..." % Num.duration(float(Session.offline_pending.get("elapsed", 0.0))))
		await get_tree().process_frame
	_teardown_game()
	if diorama:
		diorama.queue_free()
		diorama = null
	Assets.preload_assets(_needed_assets(s))
	while Assets.preload_progress() < 1.0:
		_set_progress(0.3 + 0.35 * Assets.preload_progress(), "Loading equipment...")
		await get_tree().process_frame
	world = MineWorld.new()
	add_child(world)
	world.begin(s)
	var steps := world.steps()
	for i in steps.size():
		_set_progress(0.65 + 0.33 * float(i) / float(steps.size()), String(steps[i][0]) + "...")
		await get_tree().process_frame
		world.run_step(steps[i])
	rig = CameraRig.new()
	add_child(rig)
	rig.setup(world)
	var start_level := 1 if s.state.deepest_unlocked() >= 1 else 0
	rig.focus_on(Vector3(2.0, s.content.depth_floor_y(start_level) + 1.9, CameraRig.GALLERY_Z) if start_level > 0 else Vector3(2, 0, -14), 29.0)
	rig.focus = rig.target_focus
	touch = TouchInput.new()
	add_child(touch)
	touch.setup(rig, world)
	touch.tapped.connect(_on_tap)
	Audio.position_resolver = world.event_position
	_set_progress(1.0, "Ready")
	await get_tree().process_frame
	Session.save_now()
	_hide_screen()
	GameState.request(State.PLAYING)
	ui.show_game(true)
	Audio.set_music("mine")
	if not Session.offline_report.is_empty():
		ui.open_panel("offline", {"report": Session.offline_report})
	if Session.load_notice != "":
		ui.toast(Session.load_notice, "bad")
	Telemetry.track("world_ready", {"ms": world.timings})
	EventBus.world_ready.emit()


## Models the current claim will show (loaded on worker threads meanwhile).
func _needed_assets(s: Simulation) -> Array:
	var ids := {}
	for f in s.content.facilities:
		ids[String(f.get("asset", ""))] = true
	for w in s.state.workers:
		ids[String(w.get("variant", ""))] = true
	for dep in s.state.depths:
		if dep["unlocked"]:
			for n in dep["nodes"]:
				ids[String(s.content.resource_by_id.get(String(n["resource"]), {}).get("node_asset", ""))] = true
	for m in s.content.modules.get("modules", []):
		ids[String(m.get("asset", ""))] = true
	for t in s.content.tool_tiers:
		ids[String(t.get("tool_asset", ""))] = true
		ids[String(t.get("machine_asset", ""))] = true
	for extra in ["veh_utility_01", "veh_mining_truck_01", "veh_mine_cart_01", "prop_ore_sack_01", "prop_crate_carry_01",
			"tool_pickaxe_01", "tool_jackhammer_01", "tool_wrench_01", "tool_hammer_01", "chr_worker_miner_01"]:
		ids[extra] = true
	ids.erase("")
	return ids.keys()


func _teardown_game() -> void:
	Audio.position_resolver = Callable()
	for n in [touch, rig, world]:
		if n != null and is_instance_valid(n):
			(n as Node).queue_free()
	touch = null
	rig = null
	world = null


# ---------------------------------------------------------------- playing

func _process(_delta: float) -> void:
	if fps_label.visible:
		fps_label.text = "%d fps  sim %.1f ms" % [Engine.get_frames_per_second(), Session.sim_frame_ms()]
	# Coming back from the background: catch up the time away in the open world.
	if Session.offline_in_progress() and GameState.fsm.base == State.PLAYING:
		Session.step_offline()


func _on_tap(target: String, _pos: Vector3, floor_level: int, floor_pos: Vector3) -> void:
	if world == null:
		return
	var p := target.split(":")
	match p[0]:
		"node":
			world.agents.foreman.mine(int(p[1]), int(p[2]))
		"worker":
			ui.open_panel("worker", {"worker": int(p[1])})
		"facility":
			ui.open_panel("facility", {"facility": p[1]})
		"depth":
			if floor_level == int(p[1]):
				world.agents.foreman.walk_to(floor_level, floor_pos)
			ui.open_panel("depth", {"depth": int(p[1])})
		_:
			if floor_level >= 0:
				world.agents.foreman.walk_to(floor_level, floor_pos)


func _on_sim_event(ev: Dictionary) -> void:
	if String(ev.get("type", "")) == "prestige":
		call_deferred("_after_prestige")


func _after_prestige() -> void:
	ui.close_all()
	_mode = "rebuild"
	Session.save_now()
	GameState.clear_overlays()
	GameState.request(State.LOADING)


func _on_offline_report(report: Dictionary) -> void:
	# Reports produced while playing (resume from background).
	if GameState.fsm.base == State.PLAYING and world != null:
		ui.open_panel("offline", {"report": report})


func quit_to_menu() -> void:
	ui.close_all()
	# Saving is a game state of its own: the mine stands still while the
	# save is written and verified, then the title screen opens.
	GameState.clear_overlays()
	GameState.request(State.SAVE)
	while Session.offline_in_progress():
		Session.step_offline()
	var ok := Session.save_now()
	EventBus.save_completed.emit(ok, "" if ok else "write failed")
	if not ok:
		ui.toast("Could not save - your progress is kept in memory", "bad")
		GameState.close(State.SAVE)
		return
	ui.show_game(false)
	GameState.clear_overlays()
	GameState.request(State.MAIN_MENU)


func reset_progress() -> void:
	SaveService.delete_all()
	Session.sim = null
	ui.close_all()
	ui.show_game(false)
	if GameState.fsm.base == State.MAIN_MENU:
		_show_menu()
	else:
		GameState.clear_overlays()
		GameState.request(State.MAIN_MENU)


func _on_back_requested() -> void:
	ui.back()


func _notification(what: int) -> void:
	match what:
		NOTIFICATION_WM_GO_BACK_REQUEST:
			if not ui.back() and GameState.fsm.base == State.MAIN_MENU:
				get_tree().quit()
		NOTIFICATION_WM_CLOSE_REQUEST:
			if Session.sim != null and GameState.fsm.base == State.PLAYING:
				Session.save_now()
			get_tree().quit()


# ------------------------------------------------------------------ screens

func _splash(text: String) -> Control:
	var c := Control.new()
	c.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	c.theme = UiTheme.get_theme()
	var bg := ColorRect.new()
	bg.color = UiTheme.BG
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	c.add_child(bg)
	var v := UiKit.vbox(20)
	v.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.offset_left = 60
	v.offset_right = -60
	c.add_child(v)
	var icon := Icon.make("pick", 160, UiTheme.TEXT, UiTheme.GOLD)
	icon.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	v.add_child(icon)
	var t := UiKit.label("MINER MANIA 3D", "Title", HORIZONTAL_ALIGNMENT_CENTER)
	t.add_theme_color_override("font_color", UiTheme.GOLD)
	v.add_child(t)
	_progress = UiKit.progress(0, 1, "", 22)
	v.add_child(_progress)
	_progress_label = UiKit.label(text, "Caption", HORIZONTAL_ALIGNMENT_CENTER)
	v.add_child(_progress_label)
	_tip_label = UiKit.wrap(TIPS[randi() % TIPS.size()], "Small")
	_tip_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(_tip_label)
	return c


func _set_progress(f: float, text: String) -> void:
	if _progress and is_instance_valid(_progress):
		_progress.value = f
		_progress_label.text = text


func _show_screen(c: Control, keep_3d: bool = false) -> void:
	_hide_screen()
	screen = c
	ui.root.add_child(c)
	ui.root.move_child(c, 0)
	if not keep_3d and diorama == null and world == null:
		pass


func _hide_screen() -> void:
	if screen and is_instance_valid(screen):
		screen.queue_free()
	screen = null
	_progress = null


func _show_error(message: String) -> void:
	ui.close_all()
	ui.show_game(false)
	var c := _splash(message)
	_progress.visible = false
	_tip_label.visible = false
	var v: VBoxContainer = c.get_child(1)
	v.add_child(UiKit.button("Back to title", func() -> void:
		if not Assets.assets.is_empty() and Session.content != null:
			GameState.request(State.MAIN_MENU)
		else:
			get_tree().quit(), "Primary"))
	_show_screen(c)
