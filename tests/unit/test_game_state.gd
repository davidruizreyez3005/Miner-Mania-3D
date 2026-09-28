extends TestCase
## The centralised game-state machine: legal paths, refused transitions,
## overlay stacking and when the simulation may run.

const S := GameStateMachine.State


func test_boot_to_playing() -> void:
	var fsm := GameStateMachine.new()
	assert_eq(fsm.current(), S.BOOT)
	assert_true(fsm.request(S.MAIN_MENU))
	assert_true(fsm.request(S.LOADING))
	assert_false(fsm.sim_running(), "no simulation while loading")
	assert_true(fsm.request(S.PLAYING))
	assert_true(fsm.sim_running())


func test_illegal_transitions_refused() -> void:
	var fsm := GameStateMachine.new()
	assert_false(fsm.request(S.PLAYING), "cannot skip loading")
	assert_eq(fsm.current(), S.BOOT, "state unchanged after a refused request")
	assert_true(fsm.last_error.contains("BOOT -> PLAYING"))
	fsm.request(S.MAIN_MENU)
	assert_false(fsm.request(S.PRESTIGE), "no prestige from the menu")
	assert_false(fsm.request(S.MAIN_MENU), "no self transition")


func test_overlays_stack_and_back() -> void:
	var fsm := _playing()
	assert_true(fsm.request(S.UPGRADE))
	assert_true(fsm.sim_running(), "idle game keeps running with a panel open")
	assert_true(fsm.request(S.DISCOVERY), "discovery popup over a panel")
	assert_eq(fsm.current(), S.DISCOVERY)
	assert_true(fsm.back())
	assert_eq(fsm.current(), S.UPGRADE)
	assert_true(fsm.back())
	assert_eq(fsm.current(), S.PLAYING)
	assert_false(fsm.back(), "nothing to go back from")


func test_pause_stops_simulation() -> void:
	var fsm := _playing()
	assert_true(fsm.request(S.PAUSED))
	assert_false(fsm.sim_running())
	assert_true(fsm.request(S.SETTINGS), "settings from the pause menu")
	assert_false(fsm.sim_running(), "still paused underneath")
	assert_false(fsm.request(S.UPGRADE), "no upgrades while paused")
	fsm.back()
	fsm.back()
	assert_true(fsm.sim_running())


func test_every_state_reachable_and_error_recovery() -> void:
	var fsm := _playing()
	for s in [S.UPGRADE, S.PROCESSING, S.OFFLINE_REWARD, S.PRESTIGE, S.SAVE, S.SETTINGS, S.TUTORIAL, S.DISCOVERY, S.QUEST, S.PAUSED]:
		assert_true(fsm.request(s), "PLAYING -> %s" % GameStateMachine.name_of(s))
		assert_true(fsm.back(), "back from %s" % GameStateMachine.name_of(s))
	assert_true(fsm.request(S.ERROR))
	assert_false(fsm.sim_running())
	assert_false(fsm.back(), "error is a base state")
	assert_true(fsm.request(S.MAIN_MENU), "recover to the menu")
	assert_true(fsm.overlays.is_empty())


func test_overlay_limit_and_close() -> void:
	var fsm := _playing()
	fsm.request(S.TUTORIAL)
	fsm.request(S.UPGRADE)
	fsm.request(S.QUEST)
	fsm.request(S.DISCOVERY)
	assert_false(fsm.request(S.SAVE), "stack capped at %d overlays" % GameStateMachine.MAX_OVERLAYS)
	assert_true(fsm.close(S.UPGRADE), "close a covered overlay")
	assert_false(fsm.has(S.UPGRADE))
	assert_eq(fsm.current(), S.DISCOVERY)


func _playing() -> GameStateMachine:
	var fsm := GameStateMachine.new()
	fsm.request(S.MAIN_MENU)
	fsm.request(S.LOADING)
	fsm.request(S.PLAYING)
	return fsm
