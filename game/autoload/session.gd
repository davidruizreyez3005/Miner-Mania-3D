extends Node
## Owns the content database and the running Simulation, and bridges them to
## the engine: fixed-step ticking while the game state allows it, the command
## entry point for UI and input, forwarding of simulation events, autosave,
## app lifecycle saves and the offline catch-up on load.

const TICK := 0.1
const MAX_TICKS_PER_FRAME := 8
const OFFLINE_TICKS_PER_FRAME := 40

var content: ContentDB
var sim: Simulation
var content_errors: Array = []
var offline_report: Dictionary = {}
var offline_pending: Dictionary = {}     # {"credited", "done", ...} while catching up
var load_notice: String = ""             # e.g. "backup restored" for the UI
var _acc := 0.0
var _autosave_left := 30.0
var _frame_sim_ms := 0.0


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	content = ContentDB.load_default()
	if OS.is_debug_build() or OS.has_feature("editor"):
		content_errors = content.validate()
		for e in content_errors:
			push_error("content: " + str(e))
	_autosave_left = float(content.bal("sim", "autosave_s", 30.0))


static func now_unix() -> int:
	return int(Time.get_unix_time_from_system())


# ----------------------------------------------------------------- game life

func has_game() -> bool:
	return sim != null


func new_game(seed_value: int = -1) -> void:
	var s := seed_value if seed_value >= 0 else int(content.bal("start", "seed", 1)) ^ (now_unix() & 0xFFFFFF)
	sim = Simulation.new(content)
	sim.new_game(s)
	var now := now_unix()
	sim.state.meta["created_unix"] = now
	sim.state.meta["last_save_unix"] = now
	sim.state.meta["max_seen_unix"] = now
	offline_report = {}
	offline_pending = {}
	load_notice = ""
	Telemetry.track("new_game", {"seed": s})


## Loads the save (falling back to the backup). Returns false when there is
## no usable save; `load_notice` explains a recovery for the UI.
func load_game() -> bool:
	var r := SaveService.read()
	load_notice = ""
	if not r.get("ok", false):
		if r.get("error", "") == "corrupt":
			load_notice = "Your save could not be read and was set aside. A new claim has been started."
			SaveService.quarantine()
			Telemetry.track("save_corrupt", {"detail": r.get("detail", "")})
		return false
	sim = Simulation.new(content, r["state"])
	if r.get("source", "main") == "backup":
		load_notice = "The last save was damaged - restored the previous one."
		Telemetry.track("save_backup_used", {"errors": r.get("recovered_from", [])})
	if int(r.get("migrated_from", SaveCodec.CURRENT)) != SaveCodec.CURRENT:
		Telemetry.track("save_migrated", {"from": r["migrated_from"]})
	_prepare_offline()
	return true


func _prepare_offline() -> void:
	offline_report = {}
	offline_pending = {}
	var ev := OfflineSimulator.evaluate(sim, now_unix())
	var meta := sim.state.meta
	meta["max_seen_unix"] = maxi(int(meta.get("max_seen_unix", 0)), now_unix())
	if ev.get("status", "") != "ok" or float(ev.get("credited", 0.0)) <= 0.0:
		if ev.get("status", "") == "clock_rollback":
			Telemetry.track("clock_rollback", {})
		return
	offline_pending = ev.duplicate()
	offline_pending["left"] = float(ev["credited"])
	offline_pending["before"] = _snapshot()
	var target_steps := float(content.bal("offline", "target_steps", 1200))
	offline_pending["step"] = clampf(float(ev["credited"]) / target_steps, float(content.bal("offline", "min_step_s", 1.0)),
		float(content.bal("offline", "max_step_s", 30.0)))
	sim.offline_mode = true
	sim.state.lift["manual_s"] = 0.0
	sim.state.sales["manual_s"] = 0.0


func offline_in_progress() -> bool:
	return not offline_pending.is_empty()


## Advances the offline catch-up by one frame's worth of ticks; returns the
## completed fraction (1.0 when done - then offline_report is filled).
func step_offline() -> float:
	if offline_pending.is_empty():
		return 1.0
	var step := float(offline_pending["step"])
	var n := 0
	while float(offline_pending["left"]) > 1e-9 and n < OFFLINE_TICKS_PER_FRAME:
		var dt := minf(step, float(offline_pending["left"]))
		sim.tick(dt)
		offline_pending["left"] = float(offline_pending["left"]) - dt
		n += 1
	var total := float(offline_pending["credited"])
	var frac := 1.0 - float(offline_pending["left"]) / maxf(total, 1e-9)
	if float(offline_pending["left"]) <= 1e-9:
		sim.offline_mode = false
		offline_report = _report(offline_pending["before"], offline_pending)
		sim.state.stat_max("offline_best_s", total)
		sim.state.meta["offline_claimed_unix"] = now_unix()
		offline_pending = {}
		sim.drain_events()
		EventBus.offline_report.emit(offline_report)
		Telemetry.track("offline_reward", {"seconds": total, "earned": offline_report.get("earned", 0.0)})
		return 1.0
	return frac


func _snapshot() -> Dictionary:
	return {"run_stats": sim.state.run_stats.duplicate(), "money": sim.state.money, "disc": sim.state.discoveries.keys()}


func _report(before: Dictionary, ev: Dictionary) -> Dictionary:
	var s := sim.state
	var b: Dictionary = before["run_stats"]
	var mined := {}
	for k in s.run_stats:
		if String(k).begins_with("mined.") and float(s.run_stats[k]) - float(b.get(k, 0.0)) > 1e-6:
			mined[String(k).substr(6)] = float(s.run_stats[k]) - float(b.get(k, 0.0))
	var disc := []
	for k in s.discoveries:
		if not k in before["disc"]:
			disc.append(k)
	return {
		"away_s": float(ev.get("elapsed", 0.0)), "credited_s": float(ev.get("credited", 0.0)),
		"capped": bool(ev.get("capped", false)), "efficiency": float(ev.get("efficiency", 1.0)),
		"mined": mined,
		"mined_units": float(s.run_stats.get("mined_units", 0.0)) - float(b.get("mined_units", 0.0)),
		"processed_units": float(s.run_stats.get("processed_units", 0.0)) - float(b.get("processed_units", 0.0)),
		"sold_units": float(s.run_stats.get("sold_units", 0.0)) - float(b.get("sold_units", 0.0)),
		"earned": float(s.run_stats.get("earned", 0.0)) - float(b.get("earned", 0.0)),
		"money_delta": s.money - float(before["money"]),
		"discoveries": disc,
	}


func save_now() -> bool:
	if sim == null or offline_in_progress():
		return false
	var now := now_unix()
	var meta := sim.state.meta
	meta["last_save_unix"] = now
	meta["max_seen_unix"] = maxi(int(meta.get("max_seen_unix", 0)), now)
	return SaveService.write(sim.state, now)


# ------------------------------------------------------------------ running

func _process(delta: float) -> void:
	if sim == null or offline_in_progress():
		return
	if not GameState.sim_running():
		return
	var t0 := Time.get_ticks_usec()
	_acc += minf(delta, 0.5)
	var n := 0
	while _acc >= TICK and n < MAX_TICKS_PER_FRAME:
		sim.tick(TICK)
		_acc -= TICK
		n += 1
	if _acc > TICK * MAX_TICKS_PER_FRAME:
		_acc = 0.0
	sim.state.meta["play_s"] = float(sim.state.meta.get("play_s", 0.0)) + delta
	_flush_events()
	_frame_sim_ms = float(Time.get_ticks_usec() - t0) / 1000.0
	_autosave_left -= delta
	if _autosave_left <= 0.0:
		_autosave_left = float(content.bal("sim", "autosave_s", 30.0))
		save_now()


func sim_frame_ms() -> float:
	return _frame_sim_ms


func _flush_events() -> void:
	for ev in sim.drain_events():
		EventBus.sim_event.emit(ev)


## The single entry point for player intent (UI buttons, taps, gestures).
func command(cmd: Dictionary) -> Dictionary:
	if sim == null:
		return {"ok": false, "error": "no_game"}
	var r := sim.execute(cmd)
	_flush_events()
	EventBus.command_result.emit(cmd, r)
	if r.get("ok", false):
		match String(cmd.get("type", "")):
			"manual_swing":
				EventBus.tutorial("manual_swing")
			"call_lift":
				EventBus.tutorial("lift_called")
			"dispatch":
				EventBus.tutorial("sales_dispatched")
			"hire":
				EventBus.tutorial("worker_hired")
			"upgrade", "upgrade_equipment", "buy_tool":
				EventBus.tutorial("upgrade_bought")
			"prestige":
				save_now()
	return r


func _notification(what: int) -> void:
	match what:
		NOTIFICATION_APPLICATION_PAUSED, NOTIFICATION_APPLICATION_FOCUS_OUT, NOTIFICATION_WM_GO_BACK_REQUEST:
			if sim != null and GameState.fsm.base == GameStateMachine.State.PLAYING:
				save_now()
		NOTIFICATION_WM_CLOSE_REQUEST:
			if sim != null and GameState.fsm.base == GameStateMachine.State.PLAYING:
				save_now()
		NOTIFICATION_APPLICATION_RESUMED:
			# Coming back from the background: credit the time away like a fresh load.
			if sim != null and GameState.fsm.base == GameStateMachine.State.PLAYING and not offline_in_progress():
				_prepare_offline()
