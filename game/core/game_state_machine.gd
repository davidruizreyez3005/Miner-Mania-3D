class_name GameStateMachine
extends RefCounted
## Centralised game-state machine (pure logic; the GameState autoload wraps
## it and broadcasts changes). A base state (BOOT, MAIN_MENU, LOADING,
## PLAYING, ERROR) carries a stack of overlay states (PAUSED, UPGRADE,
## PROCESSING, OFFLINE_REWARD, PRESTIGE, SAVE, SETTINGS, TUTORIAL,
## DISCOVERY, QUEST). Every change goes through request()/back() and is
## checked against an explicit transition table; anything else is refused.
##
##   BOOT -> MAIN_MENU -> LOADING -> PLAYING <-> overlays
##   any -> ERROR -> MAIN_MENU

enum State { BOOT, MAIN_MENU, LOADING, PLAYING, PAUSED, UPGRADE, PROCESSING, OFFLINE_REWARD, PRESTIGE, SAVE,
	ERROR, SETTINGS, TUTORIAL, DISCOVERY, QUEST }

const BASE_STATES := [State.BOOT, State.MAIN_MENU, State.LOADING, State.PLAYING, State.ERROR]
const MAX_OVERLAYS := 4

## Allowed transitions: from (current top) -> [to]. Overlays are pushed on
## top of the current state; base states replace the base and clear overlays.
const TRANSITIONS := {
	State.BOOT: [State.MAIN_MENU, State.ERROR],
	State.MAIN_MENU: [State.LOADING, State.SETTINGS, State.ERROR],
	State.LOADING: [State.PLAYING, State.ERROR, State.MAIN_MENU],
	State.PLAYING: [State.PAUSED, State.UPGRADE, State.PROCESSING, State.OFFLINE_REWARD, State.PRESTIGE, State.SAVE,
		State.SETTINGS, State.TUTORIAL, State.DISCOVERY, State.QUEST, State.MAIN_MENU, State.LOADING, State.ERROR],
	State.PAUSED: [State.SETTINGS, State.SAVE, State.MAIN_MENU, State.ERROR],
	State.UPGRADE: [State.DISCOVERY, State.QUEST, State.TUTORIAL, State.SAVE, State.PROCESSING, State.ERROR],
	State.PROCESSING: [State.DISCOVERY, State.QUEST, State.TUTORIAL, State.SAVE, State.UPGRADE, State.ERROR],
	State.OFFLINE_REWARD: [State.DISCOVERY, State.SAVE, State.ERROR],
	State.PRESTIGE: [State.SAVE, State.LOADING, State.ERROR],
	State.SAVE: [State.ERROR],
	State.ERROR: [State.MAIN_MENU],
	State.SETTINGS: [State.SAVE, State.ERROR],
	State.TUTORIAL: [State.UPGRADE, State.QUEST, State.DISCOVERY, State.SAVE, State.ERROR],
	State.DISCOVERY: [State.SAVE, State.ERROR],
	State.QUEST: [State.DISCOVERY, State.SAVE, State.ERROR],
}

## States in which the simulation keeps running (idle games keep producing
## while menus are open; only pause/settings-from-pause, saving-from-menu and
## non-gameplay states stop it).
const SIM_RUNS_IN := [State.PLAYING, State.UPGRADE, State.PROCESSING, State.TUTORIAL, State.DISCOVERY, State.QUEST,
	State.OFFLINE_REWARD, State.SAVE, State.SETTINGS]

var base: int = State.BOOT
var overlays: Array[int] = []
var history: Array = []              # recent [from, to, ok] for diagnostics
var last_error: String = ""


static func name_of(s: int) -> String:
	return State.keys()[s]


func current() -> int:
	return overlays[overlays.size() - 1] if not overlays.is_empty() else base


func is_overlay(s: int) -> bool:
	return not s in BASE_STATES


func can(to: int) -> bool:
	var from := current()
	if to == from:
		return false
	return to in TRANSITIONS.get(from, [])


## Requests a transition. Overlays are pushed; base states replace the base
## (clearing overlays). Returns false (and changes nothing) when not allowed.
func request(to: int) -> bool:
	var from := current()
	if not can(to):
		last_error = "transition %s -> %s not allowed" % [name_of(from), name_of(to)]
		_log(from, to, false)
		return false
	if is_overlay(to):
		if overlays.size() >= MAX_OVERLAYS:
			last_error = "overlay stack full"
			_log(from, to, false)
			return false
		overlays.append(to)
	else:
		overlays.clear()
		base = to
	_log(from, to, true)
	return true


## Closes the top overlay (returns to the state beneath). The ERROR state and
## base states cannot be "backed" out of - they need an explicit transition.
func back() -> bool:
	if overlays.is_empty():
		last_error = "nothing to go back from"
		return false
	var from: int = overlays.pop_back()
	_log(from, current(), true)
	return true


## Closes a specific overlay wherever it is in the stack (e.g. a popup that
## was covered by another one).
func close(s: int) -> bool:
	var i := overlays.rfind(s)
	if i < 0:
		return false
	overlays.remove_at(i)
	_log(s, current(), true)
	return true


func has(s: int) -> bool:
	return s == base or s in overlays


func sim_running() -> bool:
	if base != State.PLAYING:
		return false
	if State.PAUSED in overlays:
		return false
	for s in overlays:
		if not s in SIM_RUNS_IN:
			return false
	return true


func _log(from: int, to: int, ok: bool) -> void:
	history.append([name_of(from), name_of(to), ok])
	if history.size() > 64:
		history.remove_at(0)
