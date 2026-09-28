extends TestCase
## Offline progression: timestamp guards, caps, efficiency, only automated
## stages running, and agreement between coarse offline steps and live play.


func _automated(seed_value: int = 21, seconds: float = 1500.0) -> Simulation:
	var sim := make_sim(seed_value)
	AutoplayBot.new(sim).play(seconds, 0.25)
	return sim


func test_guards() -> void:
	var sim := make_sim()
	sim.state.meta["last_save_unix"] = 0
	assert_eq(String(OfflineSimulator.evaluate(sim, 1_800_000_000)["status"]), "no_timestamp")
	sim.state.meta["last_save_unix"] = 1_800_000_000
	sim.state.meta["max_seen_unix"] = 1_800_000_000
	var back := OfflineSimulator.evaluate(sim, 1_799_000_000)
	assert_eq(String(back["status"]), "clock_rollback", "clock moved back")
	assert_eq(float(back["credited"]), 0.0, "no time granted for rollback")
	var short := OfflineSimulator.evaluate(sim, 1_800_000_030)
	assert_eq(String(short["status"]), "too_short")
	var ok := OfflineSimulator.evaluate(sim, 1_800_003_600)
	assert_eq(String(ok["status"]), "ok")
	assert_near(float(ok["credited"]), 3600.0 * Economy.offline_efficiency(sim), 1e-6, "efficiency applied")
	var huge := OfflineSimulator.evaluate(sim, 1_800_000_000 + 30 * 86400)
	assert_true(huge["capped"], "a month away is capped")
	assert_near(float(huge["credited"]), Economy.offline_cap_s(sim) * Economy.offline_efficiency(sim), 1e-6)


func test_high_water_mark_prevents_double_reward() -> void:
	var sim := make_sim()
	sim.state.meta["last_save_unix"] = 1_800_000_000
	sim.state.meta["max_seen_unix"] = 1_800_010_000
	var r := OfflineSimulator.evaluate(sim, 1_800_010_030)
	assert_eq(String(r["status"]), "too_short", "time already rewarded is not rewarded again")


func test_manual_stages_do_not_run_offline() -> void:
	var sim := make_sim()
	for i in 40:
		var slots := MiningSystem.active_slots(sim.state.depth(1))
		sim.execute({"type": "manual_swing", "depth": 1, "slot": slots[0]})
	sim.execute({"type": "call_lift"})
	var rep := OfflineSimulator.simulate(sim, 3600.0)
	assert_eq(float(rep["earned"]), 0.0, "no trucks were dispatched while away")
	assert_near(float(sim.state.lift["manual_s"]), 0.0, 1e-9, "manual lift call does not persist")


func test_offline_matches_live_play() -> void:
	## Coarse offline steps must agree with fine live ticks on the same state.
	var a := _automated()
	var b := Simulation.new(content(), SaveCodec.decode(SaveCodec.encode(a.state, 1))["state"])
	var ea := float(a.state.run_stats.get("earned", 0.0))
	a.advance(2 * 3600.0, 0.25)
	var live := float(a.state.run_stats.get("earned", 0.0)) - ea
	var rep := OfflineSimulator.simulate(b, 2 * 3600.0)
	assert_gt(live, 0.0, "live earned")
	assert_rel(float(rep["earned"]), live, 0.05, "offline earnings within 5%% of live play")
	assert_gt(float(rep["mined_units"]), 0.0, "report mined")
	assert_gt(float(rep["sold_units"]), 0.0, "report sold")
	assert_finite_state(b, "after offline")


func test_offline_report_contents() -> void:
	var sim := _automated(5, 900.0)
	var rep := OfflineSimulator.simulate(sim, 1800.0)
	for k in ["seconds", "steps", "mined", "mined_units", "processed_units", "sold_units", "earned", "discoveries", "compute_ms"]:
		assert_true(rep.has(k), "report has %s" % k)
	assert_true(rep["mined"] is Dictionary and not (rep["mined"] as Dictionary).is_empty(), "per-resource breakdown")
	assert_ge(float(sim.state.life_stats.get("offline_best_s", 0.0)), 1800.0, "offline stat recorded")
