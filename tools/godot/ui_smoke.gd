extends SceneTree
## Runtime smoke test of the real game: boots main.tscn, waits for the title
## screen, starts a new claim, plays every first-session tip with touch
## events (Next, taps on the vein, LIFT, SELL, the controls the tips point
## at), plays on (taps veins, winds the lift, sells), opens every panel and
## popup, scrolls a menu and moves the camera by touch, pauses, quits to the
## title - failing on any script/engine error, a tip that does not advance
## or a missed state transition. With a display it also saves screenshots
## of every step (SHOTDIR env or --shots <dir>).
##
##   godot --headless --path . --script res://tools/godot/ui_smoke.gd -- [--shots <dir>] [--report <path>]

const PANELS := [["depth", {"depth": 1}], ["facility", {"facility": "headframe"}], ["facility", {"facility": "crusher"}],
	["facility", {"facility": "generator"}], ["facility", {"facility": "workshop"}],
	["crew", {}], ["research", {}], ["quests", {}], ["quests", {"tab": "achievements"}], ["stats", {}], ["codex", {}],
	["prestige", {}], ["cosmetics", {}], ["settings", {}], ["more", {}], ["pause", {}], ["worker", {"worker": 1}],
	["discovery", {"resource": "gold", "depth": 3}]]


class Capture extends Logger:
	## The headless dummy renderer keeps no GPU data, and its storage is not
	## thread-safe: its material storage can report a race between a freed
	## material and a pending instance update, and its texture storage a
	## texture created while models load on worker threads. The real
	## renderers (Vulkan, GLES3 - thread-safe storage; runs of this same test
	## and the device test) never show them. These messages are reported as
	## warnings, never dropped.
	const HEADLESS_ONLY := ["servers/rendering/dummy/storage/material_storage.cpp",
		"servers/rendering/dummy/storage/texture_storage.h"]
	var errors: Array = []
	var warnings: Array = []
	var mutex := Mutex.new()

	func _log_error(function: String, file: String, line: int, code: String, rationale: String, _editor_notify: bool,
			error_type: int, script_backtraces: Array) -> void:
		var bt := ""
		for b in script_backtraces:
			bt += " | " + str((b as ScriptBacktrace).format()).replace("\n", " / ")
		var msg := "%s %s:%d %s %s%s" % ["SCRIPT ERROR" if error_type == ERROR_TYPE_SCRIPT else "ERROR", file, line, function,
			rationale if rationale != "" else code, bt]
		mutex.lock()
		if file.trim_prefix("./") in HEADLESS_ONLY and DisplayServer.get_name() == "headless":
			warnings.append(msg)
		else:
			errors.append(msg)
		mutex.unlock()

	func _log_message(_message: String, _error: bool) -> void:
		pass


var cap := Capture.new()
var main: Node
var shots := ""
var steps: Array = []
var failures: Array = []
var log_lines: Array = []


func _initialize() -> void:
	OS.add_logger(cap)
	var args := OS.get_cmdline_user_args()
	for i in args.size():
		if args[i] == "--shots" and i + 1 < args.size():
			shots = args[i + 1]
	if shots == "" and OS.get_environment("SHOTDIR") != "":
		shots = OS.get_environment("SHOTDIR")
	if shots != "":
		DirAccess.make_dir_recursive_absolute(shots)
	await process_frame
	# A clean slate: no save from earlier runs.
	root.get_node("SaveService").delete_all()
	main = (load("res://game/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await _run()
	# Tear the game down before quitting (errors on the way out count too).
	main.queue_free()
	await _frames(30)
	var report := {"failures": failures, "errors": cap.errors, "headless_renderer_warnings": cap.warnings, "steps": log_lines}
	var rp := _arg("--report")
	if rp != "":
		var f := FileAccess.open(rp, FileAccess.WRITE)
		if f:
			f.store_string(JSON.stringify(report, "  "))
	print("ui_smoke: %d steps, %d failures, %d engine errors, %d headless-renderer warnings" % [log_lines.size(), failures.size(),
		cap.errors.size(), cap.warnings.size()])
	for w in cap.warnings:
		print("  ~ ", w)
	for e in failures + cap.errors:
		print("  - ", e)
	OS.remove_logger(cap)
	quit(0 if failures.is_empty() and cap.errors.is_empty() else 1)


func _arg(name: String) -> String:
	var a := OS.get_cmdline_user_args()
	var i := a.find(name)
	return a[i + 1] if i >= 0 and i + 1 < a.size() else ""


func _state() -> int:
	return root.get_node("GameState").current()


func _wait_state(s: int, timeout: float, what: String) -> bool:
	var t := 0.0
	while _state() != s and root.get_node("GameState").fsm.base != s:
		await process_frame
		t += 1.0 / 60.0
		if t > timeout * 3.0:
			failures.append("timed out waiting for %s" % what)
			return false
	return true


func _frames(n: int) -> void:
	for i in n:
		await process_frame


func _shot(name: String) -> void:
	log_lines.append(name)
	if shots == "" or DisplayServer.get_name() == "headless":
		return
	await _frames(2)
	var img := root.get_viewport().get_texture().get_image()
	img.save_png(shots.path_join(name + ".png"))


func _run() -> void:
	var GS := GameStateMachine.State
	if not await _wait_state(GS.MAIN_MENU, 30.0, "the title screen"):
		return
	await _frames(20)
	await _shot("01_title")
	main._start("new")
	if not await _wait_state(GS.PLAYING, 120.0, "the game to load"):
		return
	await _frames(30)
	await _shot("02_playing")
	# Back (Android) while the first tutorial tip shows opens the pause menu;
	# closing it brings the tip back.
	if _state() != GS.TUTORIAL:
		failures.append("a new claim should open the tutorial: %s" % GameStateMachine.name_of(_state()))
	elif not main.ui.back() or _state() != GS.PAUSED:
		failures.append("Back did not open the pause menu over the tutorial: %s" % GameStateMachine.name_of(_state()))
	else:
		main.ui.back()
		await _frames(10)
		if _state() != GS.TUTORIAL:
			failures.append("the tutorial did not come back after the pause menu: %s" % GameStateMachine.name_of(_state()))
	var sim: Simulation = root.get_node("Session").sim
	await _tips_by_touch(sim)
	# Play: swing at a vein until ore piles up, wind the lift, sell.
	main._on_tap("node:1:0", Vector3.ZERO, -1, Vector3.ZERO)
	var foreman = main.world_ref().agents.foreman
	var waited := 0
	while foreman.moving and waited < 900:
		await process_frame
		waited += 1
	for i in 10:
		main._on_tap("node:1:0", Vector3.ZERO, -1, Vector3.ZERO)
		await _frames(20)
	await _shot("03_mining")
	if float(sim.state.run_stats.get("manual_swings", 0.0)) < 1.0:
		failures.append("the foreman never swung at the vein")
	root.get_node("Session").command({"type": "call_lift"})
	await _frames(90)
	root.get_node("Session").command({"type": "dispatch"})
	sim.state.money += 5000.0
	root.get_node("Session").command({"type": "hire", "role": "miner", "post": "depth:1"})
	await _frames(60)
	await _shot("04_crew_at_work")
	var ui = main.ui
	var i := 5
	for p in PANELS:
		var panel = ui.open_panel(String(p[0]), p[1])
		if panel == null:
			failures.append("could not open panel %s" % p[0])
			continue
		await _frames(12)
		await _shot("%02d_panel_%s%s" % [i, p[0], "_" + str(p[1].values()[0]) if not p[1].is_empty() else ""])
		ui.close_panel(panel)
		await _frames(6)
		i += 1
		if _state() != GS.PLAYING and not root.get_node("GameState").has(GS.TUTORIAL):
			failures.append("state not restored after closing %s: %s" % [p[0], GameStateMachine.name_of(_state())])
	await _scroll_by_touch(ui)
	await _camera_by_touch()
	await _switch_quality()
	await _panel_layout(ui)
	# Memory: opening and closing every panel again and again must not leave
	# objects or orphan nodes behind (the first pass warms the caches).
	var counts: Array = []
	for cycle in 3:
		for p in PANELS:
			var again = ui.open_panel(String(p[0]), p[1])
			await _frames(3)
			if again != null:
				ui.close_panel(again)
			await _frames(3)
		await _frames(40)
		counts.append([int(Performance.get_monitor(Performance.OBJECT_COUNT)),
			int(Performance.get_monitor(Performance.OBJECT_ORPHAN_NODE_COUNT))])
	print("ui_smoke: objects/orphan nodes after each panel cycle: ", counts)
	if int(counts[2][0]) - int(counts[1][0]) > 60 or int(counts[2][1]) > int(counts[1][1]):
		failures.append("objects pile up while opening and closing panels: %s" % str(counts))
	ui.open_panel("offline", {"report": {"away_s": 7300.0, "credited_s": 7200.0, "capped": true, "efficiency": 0.6,
		"mined": {"stone": 420.0, "coal": 95.0, "copper": 12.0}, "processed_units": 300.0, "sold_units": 480.0, "earned": 18450.0,
		"discoveries": ["copper"]}})
	await _frames(12)
	await _shot("%02d_offline" % i)
	ui.close_all()
	await _frames(6)
	# Surface view and a camera sweep.
	main.camera_rig().focus_target("surface")
	await _frames(70)
	await _shot("%02d_surface" % (i + 1))
	main.camera_rig().focus_target("depth:1")
	await _frames(50)
	main.quit_to_menu()
	if not await _wait_state(GS.MAIN_MENU, 30.0, "the title after quitting"):
		return
	await _frames(10)
	await _shot("%02d_title_again" % (i + 2))
	if not root.get_node("SaveService").has_save():
		failures.append("quitting to the title did not save")
	# Memory: going back into the mine and out again must not keep the
	# previous world (views, agents, effects) alive.
	var at_title: Array = []
	for trip in 2:
		main._start("continue")
		if not await _wait_state(GS.PLAYING, 120.0, "the saved game to load"):
			return
		await _frames(60)
		main.quit_to_menu()
		if not await _wait_state(GS.MAIN_MENU, 30.0, "the title after another trip"):
			return
		await _frames(60)
		at_title.append([int(Performance.get_monitor(Performance.OBJECT_COUNT)),
			int(Performance.get_monitor(Performance.OBJECT_ORPHAN_NODE_COUNT)),
			int(Performance.get_monitor(Performance.OBJECT_RESOURCE_COUNT))])
	print("ui_smoke: objects/orphan nodes/resources at the title after each trip: ", at_title)
	if int(at_title[1][0]) - int(at_title[0][0]) > 150 or int(at_title[1][1]) > int(at_title[0][1]):
		failures.append("the previous world stays in memory after leaving it: %s" % str(at_title))
	log_lines.append("continue_and_quit_twice")


# ------------------------------------------------------------ touch helpers

## Touch events in viewport coordinates (converted to window coordinates, as
## a phone's screen would send them; the engine turns the first finger into
## mouse events for the UI).
func _touch(index: int, p: Vector2, down: bool) -> void:
	var e := InputEventScreenTouch.new()
	e.index = index
	e.position = root.get_final_transform() * p
	e.pressed = down
	Input.parse_input_event(e)


func _drag_touch(index: int, p: Vector2, rel: Vector2) -> void:
	var xf := root.get_final_transform()
	var e := InputEventScreenDrag.new()
	e.index = index
	e.position = xf * p
	e.relative = xf.basis_xform(rel)
	e.velocity = xf.basis_xform(rel * 30.0)
	Input.parse_input_event(e)


func _tap(p: Vector2) -> void:
	_touch(0, p, true)
	await _frames(2)
	_touch(0, p, false)
	await _frames(2)


## A one-finger swipe from `a` by `by` in `steps` moves.
func _swipe(a: Vector2, by: Vector2, steps: int = 12) -> void:
	_touch(0, a, true)
	await _frames(2)
	for k in steps:
		_drag_touch(0, a + by * float(k + 1) / float(steps), by / float(steps))
		await _frames(1)
	_touch(0, a + by, false)
	await _frames(2)


func _tip() -> int:
	var s = root.get_node("Session").sim
	return int(s.state.meta.get("tutorial_step", 0)) if s != null else -1


## Waits (up to `frames`) for the tutorial to move past tip `idx`.
func _tip_passed(idx: int, frames: int) -> bool:
	for i in frames:
		if _tip() > idx:
			return true
		await process_frame
	return _tip() > idx


## Plays every first-session tip as a player would: taps land where the
## card's buttons and the tip's marker are.
func _tips_by_touch(sim: Simulation) -> void:
	var ids := []
	for st in main.ui.tutorial.steps():
		ids.append(String(st.get("id", "")))
	if ids != ["welcome", "mine", "lift", "sell", "hire", "upgrade", "quests", "done"]:
		failures.append("tips changed (%s): update the touch walkthrough" % str(ids))
		return
	for idx in ids.size():
		if _tip() != idx:
			failures.append("tip %d (%s) expected, on tip %d" % [idx, ids[idx], _tip()])
			return
		if not main.ui.tutorial.card.visible and main.ui.stack.is_empty():
			failures.append("tip %d (%s) is not showing" % [idx, ids[idx]])
		await _play_tip(idx)
		if not await _tip_passed(idx, 900):
			failures.append("tip %d (%s) did not advance after its action (swings %s, money %.0f, panels %s)" % [idx, ids[idx],
				str(sim.state.run_stats.get("manual_swings", 0)), sim.state.money, str(main.ui.stack.map(func(p): return p.panel_id()))])
			return
	await _frames(10)
	if not bool(sim.state.meta.get("tutorial_done", false)) or root.get_node("GameState").has(GameStateMachine.State.TUTORIAL):
		failures.append("the tutorial did not finish")
	log_lines.append("tips_by_touch")


func _play_tip(idx: int) -> void:
	var tut = main.ui.tutorial
	var hud = main.ui.hud
	match idx:
		0:
			await _tap(tut.next_button.get_global_rect().get_center())
		1:
			# Tap the vein again and again (taps on the way queue swings).
			for k in 8:
				if _tip() > 1:
					return
				await _tap(tut.step_anchor_pos(1))
				await _frames(20)
		2:
			await _tap((hud.buttons["lift"] as Control).get_global_rect().get_center())
		3:
			await _tap((hud.buttons["sell"] as Control).get_global_rect().get_center())
		4, 5:
			# Where the marker points: the gallery (opens its panel), then
			# the button in the panel.
			for k in 3:
				if _tip() > idx:
					return
				await _tap(tut.step_anchor_pos(idx))
				await _frames(30)
		6:
			main.ui.close_all()
			await _frames(20)
			await _tap(tut.step_anchor_pos(6))
			await _frames(20)
		7:
			main.ui.close_all()
			await _frames(20)
			await _tap(tut.next_button.get_global_rect().get_center())


## Menus scroll with a finger dragged over their buttons and cards, and a
## tap on a list button still presses it.
func _scroll_by_touch(ui) -> void:
	ui.close_all()
	await _frames(10)
	var techs := _sim().state.techs.size()
	var p = ui.open_panel("research", {})
	await _frames(20)
	if p == null or p.scroll == null:
		failures.append("research panel did not open")
		return
	var view: Rect2 = p.scroll.get_global_rect()
	if p.content.size.y <= view.size.y + 50.0:
		failures.append("research list too short to test scrolling")
	var start := Vector2(view.get_center().x, view.position.y + view.size.y * 0.8)
	await _swipe(start, Vector2(0, -view.size.y * 0.5))
	await _frames(20)
	if p.scroll.scroll_vertical < 40:
		failures.append("a finger drag over the research list did not scroll it (%d px)" % p.scroll.scroll_vertical)
	if _sim().state.techs.size() != techs or ui.top_panel() != p:
		failures.append("the scroll drag pressed a button")
	ui.close_all()
	await _frames(10)
	var more = ui.open_panel("more", {})
	await _frames(20)
	var first: Button = null
	for b in more.content.find_children("*", "Button", true, false):
		first = b
		break
	if first == null:
		failures.append("no button in the More panel")
	else:
		await _tap(first.get_global_rect().get_center())
		await _frames(10)
		if ui.top_panel() == more:
			failures.append("a tap on a list button did not press it")
	ui.close_all()
	await _frames(10)
	log_lines.append("menus_scroll_by_touch")


func _sim() -> Simulation:
	return root.get_node("Session").sim


## Drags move the view with the finger (up the screen: toward the cut edge
## on the surface, deeper underground; down: back up) and two fingers never
## turn it.
func _camera_by_touch() -> void:
	var rig = main.camera_rig()
	var vp := root.get_visible_rect().size
	var mid := Vector2(vp.x * 0.45, vp.y * 0.45)
	rig.focus_target("surface")
	await _frames(90)
	var before: Vector3 = rig.target_focus
	await _swipe(mid, Vector2(0, -vp.y * 0.12))
	await _frames(5)
	if rig.target_focus.z <= before.z + 0.5:
		failures.append("surface: dragging up did not move the view toward the cut edge (z %.2f -> %.2f)" % [before.z, rig.target_focus.z])
	# Underground (only depth 1 is open: the view can only go up from there).
	rig.focus_target("depth:1")
	await _frames(90)
	before = rig.target_focus
	await _swipe(mid, Vector2(0, vp.y * 0.12))
	await _frames(5)
	if rig.target_focus.y <= before.y + 0.5:
		failures.append("underground: dragging down did not move the view up (y %.2f -> %.2f)" % [before.y, rig.target_focus.y])
	# Two-finger twist: the fingers turn around their midpoint.
	var c := Vector2(vp.x * 0.45, vp.y * 0.42)
	_touch(0, c + Vector2(-120, 0), true)
	_touch(1, c + Vector2(120, 0), true)
	await _frames(2)
	for k in 12:
		var ang := deg_to_rad(6.0 * float(k + 1))
		_drag_touch(0, c - Vector2(cos(ang), sin(ang)) * 120.0, Vector2.ZERO)
		_drag_touch(1, c + Vector2(cos(ang), sin(ang)) * 120.0, Vector2.ZERO)
		await _frames(1)
	_touch(0, c, false)
	_touch(1, c, false)
	await _frames(40)
	var fwd: Vector3 = -rig.camera.global_transform.basis.z
	if absf(fwd.x) > 0.01:
		failures.append("a two-finger twist turned the camera (forward %s)" % str(fwd))
	log_lines.append("camera_by_touch")


## Upgrade panels are laid out on one spacing scale: equal margins left and
## right (the scroll bar keeps its own lane), the same gap between every
## block, upgrade buttons of equal width - whether the list scrolls or not.
func _panel_layout(ui) -> void:
	ui.close_all()
	await _frames(10)
	var widths := {}
	for p in [["facility", {"facility": "headframe"}], ["facility", {"facility": "generator"}], ["depth", {"depth": 1}]]:
		var panel = ui.open_panel(String(p[0]), p[1])
		await _frames(24)
		var name := "%s %s" % [p[0], str(p[1].values()[0])]
		if panel == null:
			failures.append("layout: %s did not open" % name)
			continue
		var frame: Rect2 = panel.frame.get_global_rect()
		var box: Rect2 = panel.content.get_global_rect()
		var left := box.position.x - frame.position.x
		var right := frame.end.x - box.end.x
		if absf(left - right) > 2.0:
			failures.append("layout: %s margins differ (left %.0f, right %.0f)" % [name, left, right])
		widths[name] = box.size.x
		var prev_end := -1.0
		for c in panel.content.get_children():
			var ctl := c as Control
			if ctl == null or not ctl.visible:
				continue
			var r := ctl.get_global_rect()
			if prev_end >= 0.0 and absf(r.position.y - prev_end - float(UiTheme.GAP)) > 1.5:
				failures.append("layout: %s gap of %.0f px before %s (expected %d)" % [name, r.position.y - prev_end, ctl.get_class(), UiTheme.GAP])
			prev_end = r.end.y
		var rows := 0
		for b in panel.content.find_children("*", "CostButton", true, false):
			var row := (b as Control).get_parent() as HBoxContainer
			if row == null or row.get_child_count() != 3:
				continue
			rows += 1
			var w0 := (row.get_child(0) as Control).size.x
			for k in 3:
				if absf((row.get_child(k) as Control).size.x - w0) > 1.0:
					failures.append("layout: %s upgrade buttons of different widths" % name)
			break
		if p[0] != "facility" or String(p[1]["facility"]) != "generator":
			if rows == 0:
				failures.append("layout: %s has no upgrade button row" % name)
		await _shot("layout_%s" % name.replace(" ", "_"))
		ui.close_panel(panel)
		await _frames(8)
	var vals := widths.values()
	if vals.size() == 3 and (absf(float(vals[0]) - float(vals[1])) > 1.0 or absf(float(vals[0]) - float(vals[2])) > 1.0):
		failures.append("layout: content width changes between scrolling and short panels: %s" % str(widths))
	log_lines.append("panel_layout_even")


## Graphics presets switch live in the open mine (Settings > Graphics).
func _switch_quality() -> void:
	var settings = root.get_node("Settings")
	var gq: GDScript = load("res://game/core/graphics_quality.gd")      # reads autoloads: loaded at run time
	var q0 := int(settings.get_value("quality", 1))
	var auto0 := bool(settings.get_value("quality_auto", true))
	var w = main.world_ref()
	for q in [0, 1, 2]:
		settings.choose_quality(q)
		await _frames(20)
		var want := float(gq.value(q, "render_scale", 1.0))
		if absf(root.scaling_3d_scale - want) > 1e-4:
			failures.append("quality %d: 3D scale %.2f, expected %.2f" % [q, root.scaling_3d_scale, want])
		if w.atmosphere.sun.shadow_enabled != bool(gq.value(q, "shadows", true)):
			failures.append("quality %d: sun shadows not applied" % q)
	settings.choose_quality(q0)
	settings.values["quality_auto"] = auto0
	await _frames(10)
	log_lines.append("graphics_presets_live")
