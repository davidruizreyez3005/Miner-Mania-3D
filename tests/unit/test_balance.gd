extends TestCase
## Pacing and long-run stability with the autoplay bot. Bounds are wide on
## purpose: they catch broken economies (stalls, runaway inflation, NaN),
## not small tuning changes. See tools/godot/balance_report.gd for the
## full timeline.


func test_first_run_pacing() -> void:
	var sim := make_sim(1)
	var bot := AutoplayBot.new(sim)
	bot.play(3 * 3600.0, 0.5)
	var m := bot.milestones
	assert_true(m.has("depth_2") and float(m["depth_2"]) < 30 * 60.0, "depth 2 within 30 min: %s" % str(m.get("depth_2")))
	assert_true(float(m.get("depth_2", 0.0)) > 3 * 60.0, "depth 2 not trivially fast")
	assert_true(m.has("depth_3") and float(m["depth_3"]) < 90 * 60.0, "depth 3 within 90 min")
	assert_true(m.has("depth_4") and float(m["depth_4"]) < 150 * 60.0, "depth 4 within 2.5 h")
	assert_true(not m.has("depth_7"), "depth 7 needs prestige-level multipliers")
	assert_true(m.has("stage_2"), "reached the automated stage")
	assert_true(sim.state.techs.size() >= 10, "research progressed")
	assert_true(sim.state.workers.size() >= 20, "workforce grew")
	assert_finite_state(sim, "after 3 h")
	assert_lt(sim.state.money, 1e20, "no runaway inflation")


func test_long_run_stability() -> void:
	## Eight hours of play at coarse steps: no NaN, no negative stock, money keeps growing.
	var sim := make_sim(2)
	var bot := AutoplayBot.new(sim)
	var last := 0.0
	for block in 8:
		bot.play(3600.0, 2.0)
		var earned := float(sim.state.run_stats.get("earned", 0.0))
		assert_gt(earned, last, "earnings keep growing in hour %d" % (block + 1))
		last = earned
		if not assert_finite_state(sim, "hour %d" % (block + 1)):
			return
