extends Node
## Autoload wrapper around GameStateMachine: the only place the global game
## state changes. Every transition is validated, logged ("[state] A -> B" on
## stdout / logcat) and broadcast on the EventBus; refused transitions are
## reported to the console and telemetry.

const State := GameStateMachine.State

var fsm := GameStateMachine.new()
var payload: Dictionary = {}          # data attached to the latest transition (e.g. the offline report)


func current() -> int:
	return fsm.current()


func is_state(s: int) -> bool:
	return fsm.current() == s


func has(s: int) -> bool:
	return fsm.has(s)


func sim_running() -> bool:
	return fsm.sim_running()


func request(to: int, data: Dictionary = {}) -> bool:
	var from := fsm.current()
	if not fsm.request(to):
		push_warning("GameState: " + fsm.last_error)
		Telemetry.track("state_refused", {"from": GameStateMachine.name_of(from), "to": GameStateMachine.name_of(to)})
		return false
	payload = data
	_changed(from, to)
	return true


func back() -> bool:
	var from := fsm.current()
	if not fsm.back():
		return false
	_changed(from, fsm.current())
	return true


func close(s: int) -> bool:
	var from := fsm.current()
	if not fsm.close(s):
		return false
	_changed(from, fsm.current())
	return true


## Opens an overlay if possible, otherwise closes overlays until it is.
func open_overlay(s: int, data: Dictionary = {}) -> bool:
	if fsm.has(s):
		return true
	while not fsm.overlays.is_empty() and not fsm.can(s):
		back()
	return request(s, data)


## Closes every overlay (e.g. before leaving to the title screen).
func clear_overlays() -> void:
	while not fsm.overlays.is_empty():
		back()


func fail(message: String) -> void:
	push_error("GameState ERROR: " + message)
	payload = {"message": message}
	if not fsm.request(State.ERROR):
		fsm.overlays.clear()
		fsm.base = State.ERROR
	_changed(-1, State.ERROR)


func _changed(from: int, to: int) -> void:
	print("[state] %s -> %s" % [GameStateMachine.name_of(from) if from >= 0 else "-", GameStateMachine.name_of(to)])
	EventBus.state_changed.emit(from, to)
