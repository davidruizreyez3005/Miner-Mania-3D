extends SceneTree
## Runtime smoke test of the real game: boots main.tscn, waits for the title
## screen, starts a new claim, plays (taps veins, winds the lift, sells),
## opens every panel and popup, pauses, quits to the title - failing on any
## script/engine error or a missed state transition. With a display it also
## saves screenshots of every step (SHOTDIR env or --shots <dir>).
##
##   godot --headless --path . --script res://tools/godot/ui_smoke.gd -- [--shots <dir>] [--report <path>]

const PANELS := [["depth", {"depth": 1}], ["facility", {"facility": "headframe"}], ["facility", {"facility": "crusher"}],
	["crew", {}], ["research", {}], ["quests", {}], ["quests", {"tab": "achievements"}], ["stats", {}], ["codex", {}],
	["prestige", {}], ["cosmetics", {}], ["settings", {}], ["more", {}], ["pause", {}], ["worker", {"worker": 1}],
	["discovery", {"resource": "gold", "depth": 3}]]


class Capture extends Logger:
	var errors: Array = []
	var mutex := Mutex.new()

	func _log_error(function: String, file: String, line: int, code: String, rationale: String, _editor_notify: bool,
			error_type: int, _script_backtraces: Array) -> void:
		mutex.lock()
		errors.append("%s %s:%d %s %s" % ["SCRIPT ERROR" if error_type == ERROR_TYPE_SCRIPT else "ERROR", file, line, function, rationale if rationale != "" else code])
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
	var report := {"failures": failures, "errors": cap.errors, "steps": log_lines}
	var rp := _arg("--report")
	if rp != "":
		var f := FileAccess.open(rp, FileAccess.WRITE)
		if f:
			f.store_string(JSON.stringify(report, "  "))
	print("ui_smoke: %d steps, %d failures, %d engine errors" % [log_lines.size(), failures.size(), cap.errors.size()])
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
	var sim: Simulation = root.get_node("Session").sim
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
