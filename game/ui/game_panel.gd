class_name GamePanel
extends Control
## Base for every panel. A panel declares how it is framed (a bottom sheet
## for things in the world, a full screen for management, a centred popup),
## which game state it stands for (the UI opens and closes panels through the
## state machine), builds its content, and refreshes live numbers a few
## times a second. When `signature()` changes the content is rebuilt.

const State := GameStateMachine.State

var ui: UiRoot
var args: Dictionary = {}
var content: VBoxContainer
var frame: Control
var _sig := ""
var _t := 0.0


func sim() -> Simulation:
	return Session.sim


func frame_kind() -> String:
	return "sheet"


func game_state() -> int:
	return State.UPGRADE


func panel_id() -> String:
	return "panel"


func title() -> String:
	return ""


func icon_kind() -> String:
	return ""


## Changes when the content must be rebuilt (e.g. a list grew).
func signature() -> String:
	return ""


func build() -> void:
	pass


## Cheap per-refresh updates of numbers and button states.
func refresh() -> void:
	pass


func rebuild() -> void:
	UiKit.clear(content)
	build()
	refresh()


func _process(delta: float) -> void:
	if content == null or sim() == null:
		return
	_t -= delta
	if _t > 0.0:
		return
	_t = 0.25
	var s := signature()
	if s != _sig:
		_sig = s
		rebuild()
	else:
		refresh()


func close() -> void:
	if ui:
		ui.close_panel(self)


## Runs a player command and reports refusals as a toast.
func cmd(c: Dictionary) -> Dictionary:
	var r := Session.command(c)
	if not r.get("ok", false):
		ui.report_error(r)
	else:
		refresh()
	return r


func open(panel: String, a: Dictionary = {}) -> void:
	ui.open_panel(panel, a)


## Section heading inside the content.
func section(text: String) -> Label:
	var l := UiKit.label(text, "Heading")
	content.add_child(l)
	return l
