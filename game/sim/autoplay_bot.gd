class_name AutoplayBot
extends RefCounted
## A deterministic "reasonable player" that drives a Simulation purely through
## commands. Used by the balance/pacing tests, the long-run stability tests
## and the runtime smoke test. It taps while the mine is manual, automates
## the lift and trucks, hires into free posts, researches what it can afford,
## fixes the current bottleneck and digs deeper when it can.

var sim: Simulation
var decide_every_s: float = 2.0
var tap_rate: float = 3.0
var spend_fraction: float = 0.5
var allow_prestige: bool = false
var prestige_min_lp: int = 30
var log: Array = []
var milestones: Dictionary = {}
var _timer: float = 0.0
var _tap_acc: float = 0.0


func _init(s: Simulation) -> void:
	sim = s


## Plays `seconds` of game time with fixed `dt` steps.
func play(seconds: float, dt: float = 0.25) -> void:
	var left := seconds
	while left > 1e-9:
		var step := minf(dt, left)
		_manual_taps(step)
		sim.tick(step)
		left -= step
		_timer -= step
		if _timer <= 0.0:
			_timer = decide_every_s
			decide()
		_track()


func _track() -> void:
	var s := sim.state
	var t := s.total_time
	for dep in s.depths:
		var key := "depth_%d" % int(dep["index"])
		if dep["unlocked"] and not milestones.has(key):
			milestones[key] = t
	for fid in ["crusher", "washer", "sorter", "smelter", "refinery", "generator", "pump", "workshop"]:
		if sim.facility_built(fid) and not milestones.has("built_" + fid):
			milestones["built_" + fid] = t
	var stage := sim.automation_stage()
	if not milestones.has("stage_%d" % stage):
		milestones["stage_%d" % stage] = t
	for thr in [1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10, 1e11, 1e12]:
		var k := "earned_%s" % Num.short(thr)
		if float(s.run_stats.get("earned", 0.0)) >= thr and not milestones.has(k):
			milestones[k] = t
	if int(s.prestige.get("count", 0)) > 0 and not milestones.has("prestige_%d" % s.prestige["count"]):
		milestones["prestige_%d" % s.prestige["count"]] = t


func _manual_taps(dt: float) -> void:
	## Taps while depth 1 has fewer than two miners (like a real player early
	## on: the first miner alone digs slower than a tapping finger).
	if sim.workers_at("depth:1", "miner").size() >= 2:
		return
	_tap_acc += tap_rate * dt
	while _tap_acc >= 1.0:
		_tap_acc -= 1.0
		var dep := sim.state.depth(1)
		var slots := MiningSystem.active_slots(dep)
		if not slots.is_empty():
			sim.execute({"type": "manual_swing", "depth": 1, "slot": slots[0]})


func _do(cmd: Dictionary) -> bool:
	var r := sim.execute(cmd)
	if r.get("ok", false):
		log.append([snappedf(sim.state.total_time, 0.1), cmd])
		if log.size() > 4000:
			log.remove_at(0)
	return r.get("ok", false)


func budget() -> float:
	return sim.state.money * spend_fraction


func decide() -> void:
	var s := sim.state
	for q in s.quests.keys():
		if s.quests[q] == "done":
			_do({"type": "claim_quest", "quest": q})
	if not TransportSystem.lift_automatic(sim) and TransportSystem.stations_total(sim) > 0.5:
		_do({"type": "call_lift"})
	if not SalesSystem.automatic(sim) and Simulation.inv_total(s.warehouse) > 0.5:
		_do({"type": "dispatch"})
	if SimCommands.rally_unlocked(sim):
		_do({"type": "rally"})
	for fid in sim.state.facilities:
		var fs: Dictionary = sim.state.facilities[fid]
		if fs.get("built", false) and float(fs.get("condition", 1.0)) < 0.6 and sim.workers_at("workshop", "mechanic").is_empty():
			_do({"type": "manual_repair", "facility": fid})
	_research()
	_automation_hires()
	_unlock_depth()
	_build()
	_tools()
	_upgrade_bottleneck()
	_fill_posts()
	if allow_prestige:
		var pv := PrestigeSystem.preview(sim)
		if int(pv["gain"]) >= prestige_min_lp:
			var region := s.region
			for reg in sim.content.regions:
				if PrestigeSystem.region_available(sim, String(reg["id"]), int(s.prestige["count"]) + 1):
					region = String(reg["id"])
			_do({"type": "prestige", "region": region})
			_buy_legacy()


func _research() -> void:
	var best := ""
	var best_cost := INF
	for t in sim.content.techs:
		var tid := String(t["id"])
		if not SimCommands.tech_available(sim, tid):
			continue
		if sim.state.research_points < float(t["rp"]):
			continue
		var cost := float(t["cost"])
		if cost <= sim.state.money * 0.7 and cost < best_cost:
			best = tid
			best_cost = cost
	if best != "":
		_do({"type": "research", "tech": best})


func _automation_hires() -> void:
	var s := sim.state
	if sim.workers_at("depth:1", "miner").is_empty():
		_do({"type": "hire", "role": "miner", "post": "depth:1"})
	if sim.workers_at("headframe", "operator").is_empty() and s.money > Economy.hire_cost(sim, "operator"):
		_do({"type": "hire", "role": "operator", "post": "headframe"})
	if sim.workers_at("office", "supervisor").is_empty() and not sim.mods.has_flag("auto_sales"):
		_do({"type": "hire", "role": "supervisor", "post": "office"})


func _unlock_depth() -> void:
	var s := sim.state
	var d := s.deepest_unlocked() + 1
	if d > sim.content.depth_count():
		return
	if SimCommands.depth_unlockable(sim, d) != "":
		return
	if s.money >= Economy.depth_unlock_cost(sim, d):
		_do({"type": "unlock_depth", "depth": d})


func _build() -> void:
	for fac in sim.content.facilities:
		var fid := String(fac["id"])
		if sim.facility_built(fid) or not SimCommands.facility_requirement_met(sim, fid):
			continue
		if float(fac.get("build_cost", 0.0)) <= sim.state.money * 0.6:
			_do({"type": "build", "facility": fid})


func _tools() -> void:
	for dep in sim.state.depths:
		if not dep["unlocked"]:
			continue
		var next := int(dep["tool_tier"]) + 1
		var t := sim.content.tool_tier(next)
		if t.is_empty() or not sim.mods.is_unlocked("tool:%d" % next):
			continue
		if Economy.tool_cost(sim, int(dep["index"]), next) <= budget():
			_do({"type": "buy_tool", "depth": dep["index"]})


func _fill_posts() -> void:
	var s := sim.state
	if s.workers.size() >= Economy.worker_capacity(sim):
		if Economy.facility_upgrade_cost(sim, "office") <= budget():
			_do({"type": "upgrade", "facility": "office"})
		return
	var deepest := s.deepest_unlocked()
	for d in range(deepest, 0, -1):
		var post := "depth:%d" % d
		while SimCommands.post_free(sim, "miner", post) > 0 and Economy.hire_cost(sim, "miner") <= budget():
			if not _do({"type": "hire", "role": "miner", "post": post}):
				break
	for d in range(deepest, 0, -1):
		var post2 := "depth:%d" % d
		var dep := s.depth(d)
		if Simulation.inv_total(dep["face"]) > Economy.face_capacity(sim, d) * 0.5 and SimCommands.post_free(sim, "hauler", post2) > 0:
			_do({"type": "hire", "role": "hauler", "post": post2})
		if SimCommands.role_unlocked(sim, "geologist") and d >= 3 and SimCommands.post_free(sim, "geologist", post2) > 0:
			if Economy.hire_cost(sim, "geologist") <= budget() * 0.3:
				_do({"type": "hire", "role": "geologist", "post": post2})
		if SimCommands.role_unlocked(sim, "supervisor") and d >= 2 and SimCommands.post_free(sim, "supervisor", post2) > 0:
			if Economy.hire_cost(sim, "supervisor") <= budget() * 0.2:
				_do({"type": "hire", "role": "supervisor", "post": post2})
	for fid in sim.content.processing_facilities():
		if sim.facility_built(fid) and SimCommands.post_free(sim, "operator", fid) > 0:
			_do({"type": "hire", "role": "operator", "post": fid})
	if SimCommands.role_unlocked(sim, "engineer"):
		while SimCommands.post_free(sim, "engineer", "office") > 0 and Economy.hire_cost(sim, "engineer") <= budget() * 0.5:
			if not _do({"type": "hire", "role": "engineer", "post": "office"}):
				break
	if SimCommands.role_unlocked(sim, "mechanic") and SimCommands.post_free(sim, "mechanic", "workshop") > 0:
		if Economy.hire_cost(sim, "mechanic") <= budget() * 0.3:
			_do({"type": "hire", "role": "mechanic", "post": "workshop"})


## Throughput of every stage (units/s) so the bot upgrades the weakest one.
func stage_rates() -> Dictionary:
	var mining := 0.0
	var haul_deficit := ""
	for dep in sim.state.depths:
		if not dep["unlocked"]:
			continue
		var d := int(dep["index"])
		var dr: Dictionary = sim.rt.get("depth", {}).get(d, {})
		mining += float(dr.get("units_rate", 0.0))
		if bool(dr.get("stalled", false)):
			haul_deficit = "depth:%d" % d
	var lift: Dictionary = sim.rt.get("lift", {})
	var plant: Dictionary = sim.rt.get("plant", {})
	var sales: Dictionary = sim.rt.get("sales", {})
	return {"mining": mining, "stalled": haul_deficit, "lift": float(lift.get("rate", 0.0)),
		"plant": float(plant.get("capacity", ProcessingSystem.conveyor_rate(sim))), "sales": float(sales.get("rate", 0.0)),
		"bottleneck": String(plant.get("bottleneck", ""))}


func _upgrade_bottleneck() -> void:
	var s := sim.state
	var r := stage_rates()
	var mining: float = r["mining"]
	# Storage that is full blocks everything upstream.
	if Simulation.inv_total(s.warehouse) > Economy.warehouse_capacity(sim) * 0.8:
		_buy_facility("warehouse", 3)
	if Simulation.inv_total(s.surface_bin) > Economy.bin_capacity(sim) * 0.8:
		_buy_facility("silo", 3)
	if float(r["sales"]) < float(r["plant"]) * 0.9 or float(r["sales"]) < mining:
		_buy_facility("depot", 5)
	if float(r["lift"]) < mining * 1.1:
		_buy_facility("headframe", 5)
	if float(r["plant"]) < mining * 1.05 or String(r["bottleneck"]) == "conveyor":
		_buy_facility("conveyor", 5)
	# Soft plant: upgrade the machine that lets the most ore bypass it.
	var plant: Dictionary = sim.rt.get("plant", {})
	if float(plant.get("processed_share", 1.0)) < 0.95 and String(plant.get("short", "")) != "":
		_buy_facility(String(plant["short"]), 5)
	if sim.facility_built("generator") and float(sim.rt.get("power_factor", 1.0)) < 0.99:
		_buy_facility("generator", 5)
	if sim.facility_built("pump") and float(sim.rt.get("pump", {}).get("ratio", 1.0)) < 0.999:
		_buy_facility("pump", 5)
	for dep in s.depths:
		if not dep["unlocked"]:
			continue
		var d := int(dep["index"])
		var dr: Dictionary = sim.rt.get("depth", {}).get(d, {})
		if bool(dr.get("stalled", false)):
			if bool(dr.get("to_face", false)) or s.techs.has("rail_carts"):
				_buy_equipment(d, "haulage", 3)
			_buy_equipment(d, "station", 3)
		if Simulation.inv_total(dep["station"]) > Economy.station_capacity(sim, d) * 0.7:
			_buy_equipment(d, "station", 3)
	# Mining levels: spend on the deepest depths first (they are worth the most per unit).
	for d in range(s.deepest_unlocked(), 0, -1):
		_buy_equipment(d, "mining", 5)


func _buy_facility(fid: String, max_count: int) -> void:
	if not sim.facility_built(fid):
		return
	var n := mini(max_count, Economy.facility_affordable(sim, fid))
	while n > 0 and Economy.facility_upgrade_cost(sim, fid, n) > budget():
		n -= 1
	if n > 0:
		_do({"type": "upgrade", "facility": fid, "count": n})


func _buy_equipment(d: int, kind: String, max_count: int) -> void:
	var n := mini(max_count, Economy.equipment_affordable(sim, d, kind))
	while n > 0 and Economy.equipment_cost(sim, d, kind, n) > budget():
		n -= 1
	if n > 0:
		_do({"type": "upgrade_equipment", "depth": d, "equipment": kind, "count": n})


func _buy_legacy() -> void:
	var order := ["automation_blueprints", "seed_capital", "market_contacts", "veteran_crews", "efficient_logistics",
		"research_archive", "offline_mastery", "geological_memory", "head_start", "deep_charter"]
	var bought := true
	while bought:
		bought = false
		for uid in order:
			if _do({"type": "buy_legacy", "upgrade": uid}):
				bought = true
