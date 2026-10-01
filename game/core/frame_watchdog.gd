class_name FrameWatchdog
extends Node
## Keeps the automatic graphics choice honest: once the mine has been on
## screen for a few seconds, the average frame rate over a window must reach
## a share of the frame cap (data/performance.json "graphics.watchdog"), or
## the quality steps down one level and a toast says so. Only while the
## player has not picked a quality themselves; never below Low.

var _settle := 0.0
var _time := 0.0
var _frames := 0


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	EventBus.quality_changed.connect(func(_q: int) -> void: _restart())


func _restart() -> void:
	_settle = 0.0
	_time = 0.0
	_frames = 0


func _process(delta: float) -> void:
	if not bool(Settings.get_value("quality_auto", true)) or GraphicsQuality.current() <= GraphicsQuality.LOW \
			or GameState.fsm.base != GameStateMachine.State.PLAYING or Session.offline_in_progress():
		_restart()
		return
	var cfg: Dictionary = GraphicsQuality.data().get("watchdog", {})
	_settle += delta
	if _settle < float(cfg.get("settle_s", 6.0)):
		return
	_time += delta
	_frames += 1
	if _time < float(cfg.get("window_s", 15.0)):
		return
	var fps := float(_frames) / _time
	var cap := float(Engine.max_fps) if Engine.max_fps > 0 else 60.0
	_restart()
	if fps < cap * float(cfg.get("min_share", 0.8)):
		Telemetry.track("quality_lowered", {"fps": snappedf(fps, 0.1), "cap": cap, "from": GraphicsQuality.current()})
		if Settings.lower_quality():
			EventBus.notify("Graphics set to %s for smoother play (Settings)" % String(GraphicsQuality.current_value("name", "")), "info")
