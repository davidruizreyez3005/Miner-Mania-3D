extends TestCase
## The core loop through commands: mine by hand, lift, sell, hire, upgrade,
## automate, build, process, research, unlock depths.


func _swing_until(sim: Simulation, units: float, d: int = 1) -> float:
	var got := 0.0
	var guard := 0
	while got < units and guard < 2000:
		guard += 1
		var dep := sim.state.depth(d)
		var slots := MiningSystem.active_slots(dep)
		if slots.is_empty():
			sim.tick(0.5)
			continue
		var r := sim.execute({"type": "manual_swing", "depth": d, "slot": slots[0]})
		if r.get("ok", false):
			got += float(r["units"])
		else:
			sim.tick(0.1)
	return got


func test_new_game_state() -> void:
	var sim := make_sim()
	var s := sim.state
	assert_eq(s.money, float(content().bal("start", "money", 0.0)), "start money")
	# The tips ask for a miner and then a Mining Operations upgrade.
	assert_ge(s.money, Economy.hire_cost(sim, "miner") + Economy.equipment_cost(sim, 1, "mining", 1), "the first tips are affordable")
	assert_true(s.depth(1)["unlocked"], "depth 1 open")
	assert_false(s.depth(2)["unlocked"], "depth 2 closed")
	assert_eq(s.depth(1)["nodes"].size(), 3, "depth 1 veins")
	assert_true(sim.facility_built("headframe") and sim.facility_built("warehouse"), "prebuilt facilities")
	assert_false(sim.facility_built("crusher"), "crusher not built")
	assert_eq(s.quests.get("q_first_swing", ""), "active", "first quest active")
	assert_true(s.discoveries.size() >= 1, "initial veins are discovered")


func test_manual_mining_goes_to_station() -> void:
	var sim := make_sim()
	var got := _swing_until(sim, 5.0)
	assert_ge(got, 5.0, "mined")
	assert_near(Simulation.inv_total(sim.state.depth(1)["station"]), got, 1e-6, "station holds manual ore")
	assert_near(float(sim.state.run_stats.get("manual_units", 0)), got, 1e-6, "stat")


func test_full_manual_loop_earns_money() -> void:
	var sim := make_sim()
	_swing_until(sim, 12.0)
	assert_ok(sim.execute({"type": "call_lift"}), "call lift")
	sim.advance(40.0, 0.1)
	assert_gt(float(sim.state.run_stats.get("lifted", 0)), 5.0, "lifted")
	assert_gt(Simulation.inv_total(sim.state.warehouse), 5.0, "conveyor delivered to warehouse")
	var before := sim.state.money
	assert_ok(sim.execute({"type": "dispatch"}), "dispatch")
	sim.advance(40.0, 0.1)
	assert_gt(sim.state.money, before + 5.0, "sold goods for money")
	assert_finite_state(sim)


func test_trucks_sent_early_sell_ore_on_its_way() -> void:
	var sim := make_sim()
	assert_err(sim.execute({"type": "dispatch"}), "warehouse_empty", "nothing mined yet")
	_swing_until(sim, 6.0)
	assert_err(sim.execute({"type": "dispatch"}), "warehouse_empty", "ore still at the station, the cage idle")
	assert_ok(sim.execute({"type": "call_lift"}), "call lift")
	assert_ok(sim.execute({"type": "dispatch"}), "the trucks wait for ore the cage is bringing up")
	var before := sim.state.money
	sim.advance(40.0, 0.1)
	assert_gt(float(sim.state.run_stats.get("sold_units", 0.0)), 1.0, "sold as it arrived")
	assert_gt(sim.state.money, before, "earned")


func test_lift_without_operator_stops() -> void:
	var sim := make_sim()
	_swing_until(sim, 20.0)
	sim.advance(30.0, 0.1)
	assert_eq(float(sim.state.run_stats.get("lifted", 0.0)), 0.0, "manual lift does not run by itself")


func test_quest_claim_and_hire_miner() -> void:
	var sim := make_sim()
	_swing_until(sim, 12.0)
	sim.tick(0.6)
	assert_eq(sim.state.quests["q_first_swing"], "done", "quest completed")
	var m0 := sim.state.money
	var r := sim.execute({"type": "claim_quest", "quest": "q_first_swing"})
	assert_ok(r, "claim")
	assert_near(sim.state.money, m0 + 15.0, 1e-6, "reward paid")
	assert_eq(sim.state.quests.get("q_first_lift", ""), "active", "next quest unlocked")
	assert_err(sim.execute({"type": "claim_quest", "quest": "q_first_swing"}), "quest_not_done", "no double claim")
	sim.state.money = 100.0
	var cost := Economy.hire_cost(sim, "miner")
	var hire := sim.execute({"type": "hire", "role": "miner", "post": "depth:1"})
	assert_ok(hire, "hire miner")
	assert_eq(sim.state.workers.size(), 1)
	assert_near(sim.state.money, 100.0 - cost, 1e-6, "paid for hire")
	assert_gt(Economy.hire_cost(sim, "miner"), cost, "next hire costs more")


func test_hire_validation() -> void:
	var sim := make_sim()
	sim.state.money = 0.0
	assert_err(sim.execute({"type": "hire", "role": "miner", "post": "depth:1"}), "no_money")
	sim.state.money = 1e6
	assert_err(sim.execute({"type": "hire", "role": "miner", "post": "depth:2"}), "invalid_post", "locked depth")
	assert_err(sim.execute({"type": "hire", "role": "mechanic", "post": "workshop"}), "role_locked")
	assert_err(sim.execute({"type": "hire", "role": "miner", "post": "office"}), "invalid_post", "wrong post kind")
	assert_ok(sim.execute({"type": "hire", "role": "miner", "post": "depth:1"}))
	assert_ok(sim.execute({"type": "hire", "role": "miner", "post": "depth:1"}))
	assert_err(sim.execute({"type": "hire", "role": "miner", "post": "depth:1"}), "post_full", "2 slots at level 1")


func test_miners_produce_automatically() -> void:
	var sim := make_sim()
	sim.state.money = 1e5
	assert_ok(sim.execute({"type": "hire", "role": "miner", "post": "depth:1"}))
	sim.advance(120.0, 0.1)
	var mined := float(sim.state.run_stats.get("mined_units", 0.0))
	assert_gt(mined, 10.0, "miner produced ore")
	var w: Dictionary = sim.state.workers[0]
	assert_true(w["job"] in ["mine", "idle", "rest"], "miner job %s" % w["job"])
	assert_true(String(w["location"]).begins_with("depth:1"), "miner went underground: %s" % w["location"])


func test_operator_automates_lift_and_manager_sales() -> void:
	var sim := make_sim()
	sim.state.money = 1e6
	for q in ["q_first_swing", "q_first_lift", "q_first_sale", "q_first_miner", "q_mining_5", "q_lift_operator", "q_sell_goods"]:
		sim.state.quests[q] = "claimed"
	ProgressionSystem.refresh_quests(sim)
	assert_ok(sim.execute({"type": "hire", "role": "miner", "post": "depth:1"}))
	assert_ok(sim.execute({"type": "hire", "role": "operator", "post": "headframe"}))
	assert_ok(sim.execute({"type": "hire", "role": "supervisor", "post": "office"}))
	var m0 := sim.state.money
	sim.advance(600.0, 0.1)
	assert_gt(float(sim.state.run_stats.get("lifted", 0.0)), 1.0, "lift ran automatically")
	assert_gt(sim.state.money, m0, "trucks sold automatically")
	assert_eq(sim.automation_stage(), 2, "fully automated (no plant yet)")


func test_upgrades_increase_throughput() -> void:
	var sim := make_sim()
	sim.state.money = 1e9
	var r1 := Economy.miner_work_rate(sim, 1)
	assert_ok(sim.execute({"type": "upgrade_equipment", "depth": 1, "equipment": "mining", "count": 9}))
	assert_eq(sim.state.depth(1)["levels"]["mining"], 10)
	assert_gt(Economy.miner_work_rate(sim, 1), r1 * 3.0, "milestone at 10 doubles")
	var lift1: float = TransportSystem.lift_stats(sim)["rate"]
	assert_ok(sim.execute({"type": "upgrade", "facility": "headframe", "count": 20}))
	assert_gt(float(TransportSystem.lift_stats(sim)["rate"]), lift1 * 3.0, "lift upgrades")
	var cap1 := Economy.warehouse_capacity(sim)
	assert_ok(sim.execute({"type": "upgrade", "facility": "warehouse", "count": 5}))
	assert_gt(Economy.warehouse_capacity(sim), cap1, "warehouse grows")


func test_upgrade_costs_charged_exactly() -> void:
	var sim := make_sim()
	sim.state.money = 1000.0
	var cost := Economy.equipment_cost(sim, 1, "mining", 3)
	var r := sim.execute({"type": "upgrade_equipment", "depth": 1, "equipment": "mining", "count": 3})
	assert_ok(r)
	assert_near(sim.state.money, 1000.0 - cost, 1e-6, "charged cost_n")
	sim.state.money = 0.0
	assert_err(sim.execute({"type": "upgrade_equipment", "depth": 1, "equipment": "mining"}), "no_money")
	assert_err(sim.execute({"type": "upgrade_equipment", "depth": 1, "equipment": "haulage"}), "locked", "rail carts tech gate")


func test_unlock_depth_and_hazard_pump() -> void:
	var sim := make_sim()
	sim.state.money = 1e8
	assert_err(sim.execute({"type": "unlock_depth", "depth": 3}), "previous_locked")
	assert_ok(sim.execute({"type": "unlock_depth", "depth": 2}))
	assert_ok(sim.execute({"type": "unlock_depth", "depth": 3}))
	sim.tick(0.1)
	var hz := MiningSystem.hazard_factor(sim, 3)
	assert_lt(hz, 0.99, "depth 3 floods without pumps")
	for t in ["crushing", "diesel_power", "dewatering_pumps"]:
		sim.state.techs[t] = true
	sim.invalidate_modifiers()
	assert_ok(sim.execute({"type": "build", "facility": "pump"}))
	sim.tick(0.1)
	assert_near(MiningSystem.hazard_factor(sim, 3), 1.0, 1e-6, "pump capacity covers depth 3 inflow")
	assert_near(MiningSystem.hazard_factor(sim, 1), 1.0, 1e-9, "depth 1 dry")


func test_research_and_build_crusher_increases_value() -> void:
	var sim := make_sim()
	sim.state.money = 1e6
	assert_err(sim.execute({"type": "build", "facility": "crusher"}), "locked")
	assert_err(sim.execute({"type": "research", "tech": "crushing"}), "no_research_points")
	sim.state.research_points = 100.0
	assert_err(sim.execute({"type": "research", "tech": "washing"}), "prerequisites")
	assert_ok(sim.execute({"type": "research", "tech": "crushing"}))
	assert_ok(sim.execute({"type": "build", "facility": "crusher"}))
	assert_ok(sim.execute({"type": "upgrade", "facility": "crusher", "count": 30}))
	sim.state.surface_bin = {"stone": 10.0}
	sim.advance(30.0, 0.1)
	assert_gt(float(sim.state.warehouse.get("stone_aggregate", 0.0)), 9.9, "an upgraded crusher crushes all the stone")
	assert_lt(float(sim.state.warehouse.get("stone", 0.0)), 0.001, "no raw stone bypassed")
	var p_raw := Economy.item_price(sim, "stone")
	var p_agg := Economy.item_price(sim, "stone_aggregate")
	assert_rel(p_agg / p_raw, 2.5, 1e-9, "aggregate value multiplier")


func test_processing_overflow_bypasses() -> void:
	## A short machine never blocks the belt: the share it cannot take leaves unprocessed.
	var sim := make_sim()
	sim.state.money = 1e9
	sim.state.techs["crushing"] = true
	sim.invalidate_modifiers()
	assert_ok(sim.execute({"type": "build", "facility": "crusher"}))
	assert_ok(sim.execute({"type": "upgrade", "facility": "conveyor", "count": 40}))
	sim.state.surface_bin = {"copper": 5000.0}
	sim.tick(0.1)
	var plant: Dictionary = sim.rt["plant"]
	assert_eq(String(plant["short"]), "crusher", "crusher is the short machine")
	assert_lt(float(plant["processed_share"]), 0.5, "most copper bypasses a level-1 crusher")
	assert_gt(float(sim.state.warehouse.get("copper", 0.0)), 0.0, "bypassed as raw copper")
	assert_gt(float(sim.state.warehouse.get("copper_crushed", 0.0)), 0.0, "some was crushed")
	var belt := float(plant["rate"])
	assert_near(belt, ProcessingSystem.conveyor_rate(sim), belt * 1e-6, "belt runs at full speed regardless")


func test_processing_operator_speeds_machine() -> void:
	var sim := make_sim()
	sim.state.money = 1e9
	sim.state.techs["crushing"] = true
	sim.invalidate_modifiers()
	assert_ok(sim.execute({"type": "build", "facility": "crusher"}))
	assert_ok(sim.execute({"type": "upgrade", "facility": "conveyor", "count": 40}))
	sim.state.surface_bin = {"copper": 1e6}
	sim.tick(0.1)
	var share0 := float(sim.rt["plant"]["processed_share"])
	sim.state.quests["q_first_miner"] = "claimed"
	assert_ok(sim.execute({"type": "hire", "role": "operator", "post": "crusher"}))
	sim.advance(15.0, 0.1)
	assert_lt(float(sim.rt["plant"]["processed_share"]), share0 * 1.2, "no speed-up while the operator is still walking over")
	sim.advance(15.0, 0.1)
	assert_gt(float(sim.rt["plant"]["processed_share"]), share0 * 2.0, "operator speeds the crusher up")


func test_wear_and_repair() -> void:
	var sim := make_sim()
	sim.state.money = 1e9
	for t in ["crushing", "counterweights", "workshop_tools"]:
		sim.state.techs[t] = true
	sim.invalidate_modifiers()
	assert_ok(sim.execute({"type": "build", "facility": "crusher"}))
	sim.state.facilities["crusher"]["condition"] = 0.5
	sim.state.surface_bin = {"stone": 50.0}
	sim.tick(0.1)
	var worn_rate := ProcessingSystem.machine_capacity(sim, "crusher")
	assert_ok(sim.execute({"type": "build", "facility": "workshop"}))
	assert_ok(sim.execute({"type": "hire", "role": "mechanic", "post": "workshop"}))
	sim.advance(90.0, 0.1)
	assert_gt(float(sim.state.facilities["crusher"]["condition"]), 0.95, "mechanic repaired the crusher")
	assert_ge(float(sim.state.run_stats.get("repairs", 0.0)), 1.0, "repair counted")
	sim.state.surface_bin = {"stone": 50.0}
	sim.tick(0.1)
	assert_gt(ProcessingSystem.machine_capacity(sim, "crusher"), worn_rate, "repaired machine is faster")


func test_manual_repair() -> void:
	var sim := make_sim()
	sim.state.money = 1e6
	sim.state.techs["crushing"] = true
	sim.invalidate_modifiers()
	assert_err(sim.execute({"type": "manual_repair", "facility": "crusher"}), "not_repairable", "not built")
	assert_ok(sim.execute({"type": "build", "facility": "crusher"}))
	assert_err(sim.execute({"type": "manual_repair", "facility": "crusher"}), "not_worn")
	sim.state.facilities["crusher"]["condition"] = 0.3
	sim.tick(0.1)
	assert_true(sim.state.facilities["crusher"].get("repairing", false), "flagged for repair")
	for i in 3:
		assert_ok(sim.execute({"type": "manual_repair", "facility": "crusher"}))
	assert_near(float(sim.state.facilities["crusher"]["condition"]), 1.0, 1e-9, "fully repaired by hand")
	assert_eq(float(sim.state.run_stats.get("repairs", 0.0)), 1.0, "counts as a repair")
	assert_err(sim.execute({"type": "manual_repair", "facility": "warehouse"}), "not_repairable")


## A plant with a workshop: crusher, washer and generator built, techs given.
func _plant_sim() -> Simulation:
	var sim := make_sim()
	sim.state.money = 1e9
	for t in ["crushing", "washing", "diesel_power", "counterweights", "workshop_tools"]:
		sim.state.techs[t] = true
	sim.invalidate_modifiers()
	for f in ["crusher", "washer", "generator", "workshop"]:
		assert_ok(sim.execute({"type": "build", "facility": f}))
	return sim


func test_mechanics_walk_their_round_and_keep_machines_in_shape() -> void:
	var sim := _plant_sim()
	assert_ok(sim.execute({"type": "hire", "role": "mechanic", "post": "workshop"}))
	# Light wear everywhere: above the service mark, so no rush - the round
	# alone must find and top up every machine.
	for f in ["headframe", "crusher", "washer", "generator"]:
		sim.state.facilities[f]["condition"] = 0.985
	var stops := {}
	var moves := 0
	var last := ""
	for i in 3000:
		sim.tick(0.1)
		var w: Dictionary = sim.state.workers[0]
		if String(w["location"]) != last:
			last = String(w["location"])
			moves += 1
		if String(w["job"]) == "service" or String(w["job"]) == "repair":
			stops[String(w["target"])] = true
	assert_true(stops.has("workshop") and stops.has("headframe") and stops.has("crusher") and stops.has("washer") and stops.has("generator"),
		"the round visits the workshop and every machine: %s" % str(stops.keys()))
	assert_gt(float(moves), 6.0, "the mechanic keeps moving between stops (%d moves)" % moves)
	for f in ["headframe", "crusher", "washer", "generator"]:
		assert_gt(float(sim.state.facilities[f]["condition"]), 0.995, "%s topped up to full condition" % f)
	assert_true(String(UiText.worker_status(sim, sim.state.workers[0])) != "", "status text")


func test_mechanic_rushes_to_a_worn_machine() -> void:
	var sim := _plant_sim()
	assert_ok(sim.execute({"type": "hire", "role": "mechanic", "post": "workshop"}))
	sim.advance(30.0, 0.1)
	sim.state.facilities["washer"]["condition"] = 0.6
	sim.advance(1.5, 0.1)
	var w: Dictionary = sim.state.workers[0]
	assert_eq(String(w["job"]), "repair", "drops the round for the worn machine")
	assert_eq(String(w["target"]), "washer")
	assert_eq(String(w["location"]), "facility:washer:repair")
	sim.advance(60.0, 0.1)
	assert_gt(float(sim.state.facilities["washer"]["condition"]), 0.99, "repaired to full condition")
	assert_false(bool(sim.state.facilities["washer"].get("repairing", false)), "no longer flagged worn")
	assert_ge(float(sim.state.run_stats.get("repairs", 0.0)), 2.0, "restoring 40% counts as two repairs")


func test_two_mechanics_split_the_work() -> void:
	var sim := _plant_sim()
	assert_ok(sim.execute({"type": "upgrade", "facility": "workshop", "count": 10}))
	assert_ok(sim.execute({"type": "hire", "role": "mechanic", "post": "workshop"}))
	assert_ok(sim.execute({"type": "hire", "role": "mechanic", "post": "workshop"}))
	sim.state.facilities["crusher"]["condition"] = 0.5
	sim.state.facilities["washer"]["condition"] = 0.55
	sim.advance(1.5, 0.1)
	var targets := {}
	for w in sim.state.workers:
		targets[String(w["target"])] = String(w["job"])
	assert_eq(targets.get("crusher", ""), "repair", "one mechanic on the crusher")
	assert_eq(targets.get("washer", ""), "repair", "the other on the washer")


func test_power_grid_and_generator_add_up() -> void:
	var sim := _plant_sim()
	sim.state.facilities["generator"]["built"] = false
	sim.tick(0.1)
	var grid := float(content().bal("power", "grid_kw", 0.0))
	assert_near(float(sim.rt["power"]["supply"]), grid, 1e-6, "the grid alone")
	sim.state.facilities["generator"]["built"] = true
	sim.tick(0.1)
	var gen := content().facility_stat("generator", "power_kw", 1)
	assert_near(float(sim.rt["power"]["supply"]), grid + gen, 1e-3, "the generator adds to the grid, never replaces it")
	assert_near(float(sim.rt["power"]["grid"]), grid, 1e-6, "the grid's share is still there")
	assert_ok(sim.execute({"type": "upgrade", "facility": "generator", "count": 4}))
	sim.tick(0.1)
	assert_near(float(sim.rt["power"]["supply"]), grid + content().facility_stat("generator", "power_kw", 5), 1e-3, "upgrades add on top")


func test_power_feeds_the_line_in_order() -> void:
	## A shortage slows only the machines the supply does not reach - never
	## the belt, never the machines already running before a new one.
	var sim := make_sim()
	sim.state.money = 1e12
	sim.state.research_points = 1e6
	for t in ["crushing", "washing", "diesel_power", "smelting", "counterweights", "workshop_tools"]:
		sim.state.techs[t] = true
	sim.invalidate_modifiers()
	assert_ok(sim.execute({"type": "upgrade", "facility": "conveyor", "count": 20}))
	for f in ["crusher", "washer"]:
		assert_ok(sim.execute({"type": "build", "facility": f}))
		assert_ok(sim.execute({"type": "upgrade", "facility": f, "count": 30}))
	sim.state.surface_bin = {"copper": 1e7}
	sim.advance(3.0, 0.1)
	var belt := ProcessingSystem.conveyor_rate(sim)
	var crusher := ProcessingSystem.machine_capacity(sim, "crusher")
	var washer := ProcessingSystem.machine_capacity(sim, "washer")
	assert_near(UtilitySystem.power_factor(sim, "washer"), 1.0, 1e-6, "the grid runs a crusher and a washer")
	assert_ok(sim.execute({"type": "build", "facility": "workshop"}))
	assert_ok(sim.execute({"type": "build", "facility": "smelter"}))
	sim.drain_events()
	sim.advance(3.0, 0.1)
	assert_near(ProcessingSystem.conveyor_rate(sim), belt, 1e-6, "the belt keeps its speed")
	assert_near(ProcessingSystem.machine_capacity(sim, "crusher"), crusher, crusher * 0.01, "the crusher keeps its power")
	assert_near(ProcessingSystem.machine_capacity(sim, "washer"), washer, washer * 0.01, "the washer keeps its power")
	assert_lt(UtilitySystem.power_factor(sim, "smelter"), 0.5, "the new smelter is short")
	var sm: Dictionary = sim.state.facilities["smelter"]
	assert_lt(float(sm["util"]), float(sm["need"]), "a machine short of power does less than it is asked (and wears only for that)")
	assert_eq(String(sim.rt["power"]["short"]), "smelter", "the shortage is reported at the smelter")
	var warned := false
	for e in sim.drain_events():
		warned = warned or (e["type"] == "power_short" and e["facility"] == "smelter")
	assert_true(warned, "the player is told the smelter is short of power")
	assert_ok(sim.execute({"type": "build", "facility": "generator"}))
	sim.advance(3.0, 0.1)
	assert_near(UtilitySystem.power_factor(sim, "smelter"), 1.0, 1e-6, "the generator powers the smelter")
	assert_false(float(sim.rt["power"]["draw"].get("workshop", 0.0)) > 0.0, "the workshop draws no power")


func test_node_depletion_respawn_and_discovery() -> void:
	var sim := make_sim(77)
	sim.state.money = 1e12
	assert_ok(sim.execute({"type": "unlock_depth", "depth": 2}))
	assert_ok(sim.execute({"type": "unlock_depth", "depth": 3}))
	var events := sim.drain_events()
	var disc := 0
	for e in events:
		if e["type"] == "discovery":
			disc += 1
	assert_gt(float(disc), 0.0, "new depths reveal new resources")
	var dep := sim.state.depth(1)
	var n: Dictionary = dep["nodes"][0]
	n["hp"] = 0.5
	sim.state.money = 1e6
	assert_ok(sim.execute({"type": "hire", "role": "miner", "post": "depth:1"}))
	assert_ok(sim.execute({"type": "hire", "role": "miner", "post": "depth:1"}))
	sim.advance(60.0, 0.1)
	var types := {}
	for e in sim.drain_events():
		types[e["type"]] = true
	assert_true(types.has("node_depleted"), "a vein was mined out")
	assert_true(types.has("node_respawned"), "a new vein appeared")


func test_rally_boost() -> void:
	var sim := make_sim()
	assert_err(sim.execute({"type": "rally"}), "locked")
	sim.state.quests["q_first_miner"] = "claimed"
	assert_ok(sim.execute({"type": "rally"}))
	assert_near(sim.boost_mult(), 2.0, 1e-9)
	assert_err(sim.execute({"type": "rally"}), "cooldown")
	sim.advance(50.0, 0.5)
	assert_near(sim.boost_mult(), 1.0, 1e-9, "boost expired")


func test_unknown_command_rejected() -> void:
	var sim := make_sim()
	assert_err(sim.execute({"type": "print_money"}), "unknown_command")
	assert_err(sim.execute({"type": "upgrade", "facility": "crusher"}), "not_built")
