extends TestCase
## Prestige, legacy upgrades, regions, achievements, contracts, automation
## stages and determinism.


func test_prestige_requires_earnings() -> void:
	var sim := make_sim()
	var r := sim.execute({"type": "prestige", "region": "timberline_valley"})
	assert_err(r, "not_enough_earnings")
	assert_eq(Economy.lp_gain(content(), 999_999_999.0), 0, "below minimum")
	assert_eq(Economy.lp_gain(content(), 1e9), 3, "3 LP at $1B")
	assert_gt(float(Economy.lp_gain(content(), 1e12)), 40.0, "~47 LP at $1T")


func test_prestige_resets_and_keeps() -> void:
	var sim := make_sim(8)
	AutoplayBot.new(sim).play(600.0, 0.5)
	var ach_before := sim.state.achievements.size()
	var disc_before := sim.state.discoveries.size()
	sim.state.run_stats["earned"] = 1e12
	var r := sim.execute({"type": "prestige", "region": "red_rock_canyon"})
	assert_ok(r, "prestige")
	var s := sim.state
	assert_eq(int(s.prestige["count"]), 1)
	assert_eq(int(s.prestige["lp"]), int(r["gain"]))
	assert_eq(s.region, "red_rock_canyon", "moved to the new claim")
	assert_eq(s.workers.size(), 0, "workers reset")
	assert_true(s.techs.is_empty(), "techs reset")
	assert_false(s.depth(2)["unlocked"], "depths reset")
	assert_eq(float(s.run_stats.get("earned", 0.0)), 0.0, "run stats reset")
	assert_eq(s.achievements.size(), ach_before, "achievements kept")
	assert_eq(s.discoveries.size(), disc_before, "codex kept")
	assert_gt(sim.mods.income_mult, 3.0, "legacy income multiplier applied")
	assert_gt(float(sim.mods.class_value.get("metal", 1.0)), 1.2, "region modifier applied")
	assert_eq(s.quests.get("q_first_swing", ""), "active", "quests restart for the new claim")


func test_region_lock() -> void:
	var sim := make_sim()
	sim.state.run_stats["earned"] = 1e12
	assert_err(sim.execute({"type": "prestige", "region": "volcanic_rift"}), "region_locked", "needs 4 prestiges")


func test_legacy_upgrades() -> void:
	var sim := make_sim()
	sim.state.prestige["lp"] = 100
	var m0 := sim.mods.m("worker_efficiency")
	assert_ok(sim.execute({"type": "buy_legacy", "upgrade": "veteran_crews"}))
	assert_near(sim.mods.m("worker_efficiency"), m0 * 1.1, 1e-9, "+10% crew efficiency")
	assert_ok(sim.execute({"type": "buy_legacy", "upgrade": "seed_capital"}))
	assert_ok(sim.execute({"type": "buy_legacy", "upgrade": "automation_blueprints"}))
	assert_err(sim.execute({"type": "buy_legacy", "upgrade": "automation_blueprints"}), "max_level")
	sim.state.run_stats["earned"] = 2e9
	assert_ok(sim.execute({"type": "prestige", "region": "timberline_valley"}))
	assert_near(sim.state.money, 500.0, 1e-9, "seed capital")
	assert_eq(sim.workers_at("headframe", "operator").size(), 1, "blueprint operator")
	assert_eq(sim.workers_at("office", "supervisor").size(), 1, "blueprint manager")


func test_second_run_is_faster() -> void:
	## Prestige must feel significant: the same bot reaches depth 3 sooner after one prestige.
	var sim := make_sim(31)
	var bot := AutoplayBot.new(sim)
	bot.play(80 * 60.0, 0.5)
	var first: float = bot.milestones.get("depth_3", 1e9)
	assert_lt(first, 1e9, "first run reached depth 3")
	sim.state.run_stats["earned"] = maxf(float(sim.state.run_stats.get("earned", 0.0)), 5e10)
	var t0 := sim.state.total_time
	assert_ok(sim.execute({"type": "prestige", "region": "timberline_valley"}))
	bot._buy_legacy()
	bot.milestones.erase("depth_3")
	bot.play(80 * 60.0, 0.5)
	var second: float = float(bot.milestones.get("depth_3", 1e9)) - t0
	assert_lt(second, first * 0.8, "second run reaches depth 3 at least 20%% faster (%.0f s vs %.0f s)" % [second, first])


func test_achievements_apply_bonuses() -> void:
	var sim := make_sim()
	var before := sim.mods.m("manual_yield")
	sim.state.life_stats["manual_units"] = 150.0
	sim.tick(0.6)
	assert_true(sim.state.achievements.has("a_swing_100"), "achievement unlocked")
	assert_near(sim.mods.m("manual_yield"), before * 1.1, 1e-9, "permanent bonus applied")
	var evs := sim.drain_events()
	var found := false
	for e in evs:
		if e["type"] == "achievement" and e["achievement"] == "a_swing_100":
			found = true
	assert_true(found, "achievement event emitted")


func test_contract_flow() -> void:
	var sim := make_sim(4)
	AutoplayBot.new(sim).play(1500.0, 0.5)
	assert_true(ProgressionSystem.contracts_unlocked(sim), "contracts unlocked by the sales quest")
	sim.advance(400.0, 0.5)
	var c := sim.state.contract
	assert_true(c.has("item") or c.has("next_at"), "contract scheduled or active: %s" % str(c))


func test_automation_stages() -> void:
	var sim := make_sim()
	assert_eq(ProgressionSystem.compute_stage(sim), 0, "manual")
	sim.state.money = 1e6
	assert_ok(sim.execute({"type": "hire", "role": "miner", "post": "depth:1"}))
	assert_eq(ProgressionSystem.compute_stage(sim), 1, "semi-automated")
	assert_ok(sim.execute({"type": "hire", "role": "operator", "post": "headframe"}))
	sim.state.quests["q_sell_goods"] = "claimed"
	assert_ok(sim.execute({"type": "hire", "role": "supervisor", "post": "office"}))
	assert_eq(ProgressionSystem.compute_stage(sim), 2, "automated")


func test_determinism_same_seed_same_result() -> void:
	var a := make_sim(99)
	var b := make_sim(99)
	AutoplayBot.new(a).play(1200.0, 0.25)
	AutoplayBot.new(b).play(1200.0, 0.25)
	assert_eq(JsonUtil.canonical(a.state.to_dict()), JsonUtil.canonical(b.state.to_dict()), "identical runs")
	var c := make_sim(100)
	AutoplayBot.new(c).play(1200.0, 0.25)
	assert_true(JsonUtil.canonical(a.state.to_dict()) != JsonUtil.canonical(c.state.to_dict()), "different seed differs")


func test_discovery_rarity_scaling() -> void:
	## Rare-vein weighting is data driven: geologists and discovery modifiers raise rare odds.
	var sim := make_sim(5)
	sim.state.money = 1e15
	for d in range(2, 6):
		assert_ok(sim.execute({"type": "unlock_depth", "depth": d}))
	var count := func(sim2: Simulation) -> int:
		var n := 0
		for i in 400:
			var node := MiningSystem.roll_node(sim2, 5, 0, 1000 + i)
			if String(content().resource_by_id[node["resource"]]["rarity"]) in ["rare", "very_rare", "exotic"]:
				n += 1
		return n
	var base: int = count.call(sim)
	sim.state.bonuses["discovery_chance"] = 3.0
	sim.invalidate_modifiers()
	sim._refresh_modifiers()
	var boosted: int = count.call(sim)
	assert_gt(float(boosted), float(base), "rare veins more likely with discovery bonus (%d vs %d)" % [boosted, base])
