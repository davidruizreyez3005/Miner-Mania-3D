class_name ProgressionSystem
extends RefCounted
## Objectives and long-term progression: quests (claim for rewards),
## achievements (permanent bonuses and cosmetics), rotating delivery
## contracts, and the automation stage (Manual -> Semi-Automated ->
## Automated -> Industrial). Objectives are evaluated from state only, so
## they complete identically online and during offline catch-up.


static func tick(sim: Simulation) -> void:
	sim.rt["stage"] = compute_stage(sim)
	_check_quests(sim)
	_check_achievements(sim)
	_tick_contract(sim)


static func research_remaining(sim: Simulation) -> bool:
	return sim.state.techs.size() < sim.content.techs.size()


# ------------------------------------------------------------- automation

static func compute_stage(sim: Simulation) -> int:
	var s := sim.state
	var miners := false
	for w in s.workers:
		if w["role"] == "miner":
			miners = true
			break
	if not miners:
		return 0
	var lift_auto := TransportSystem.lift_automatic(sim)
	var sales_auto := SalesSystem.automatic(sim)
	var plant_auto := true
	for fid in sim.content.processing_facilities():
		if sim.facility_built(fid) and sim.workers_at(fid, "operator").is_empty() and not sim.mods.has_flag("machines_self_run"):
			plant_auto = false
	if not (lift_auto and sales_auto and plant_auto):
		return 1
	var tier3 := false
	for dep in s.depths:
		if dep["unlocked"] and int(dep["tool_tier"]) >= 3:
			tier3 = true
	var plant_ok := sim.facility_built("crusher") and sim.facility_built("washer") and sim.facility_built("smelter")
	if tier3 and plant_ok and sim.facility_level("conveyor") >= 25 and sim.facility_built("generator"):
		return 3
	return 2


# ------------------------------------------------------------- objectives

static func objective_progress(sim: Simulation, o: Dictionary) -> Array:
	## Returns [current, target] for any objective.
	var s := sim.state
	var t := String(o.get("type", ""))
	var target := float(o.get("target", 1.0))
	match t:
		"stat":
			var src: Dictionary = s.life_stats if String(o.get("scope", "run")) == "lifetime" else s.run_stats
			return [float(src.get(String(o["stat"]), 0.0)), target]
		"money":
			return [s.money, target]
		"workers":
			var n := 0
			for w in s.workers:
				var role_ok: bool = String(o.get("role", "any")) == "any" or w["role"] == o.get("role")
				var post_ok: bool = not o.has("post") or w["post"] == o["post"]
				if role_ok and post_ok:
					n += 1
			return [float(n), target]
		"roles":
			var roles := {}
			for w in s.workers:
				roles[w["role"]] = true
			return [float(roles.size()), target]
		"depth_unlocked":
			var dep := s.depth(int(o.get("depth", 0)))
			return [1.0 if not dep.is_empty() and dep["unlocked"] else 0.0, 1.0]
		"facility_built":
			return [1.0 if sim.facility_built(String(o.get("facility", ""))) else 0.0, 1.0]
		"facilities_built":
			var n2 := 0
			for fac in sim.content.facilities:
				if fac.get("category", "") == o.get("category", "") and sim.facility_built(String(fac["id"])):
					n2 += 1
			return [float(n2), target]
		"facility_level":
			var fid := String(o.get("facility", ""))
			return [float(sim.facility_level(fid)) if sim.facility_built(fid) else 0.0, target]
		"equipment_level":
			var best := 0
			for dep in s.depths:
				if not dep["unlocked"]:
					continue
				if int(o.get("depth", 0)) != 0 and int(dep["index"]) != int(o["depth"]):
					continue
				best = maxi(best, int(dep["levels"].get(String(o.get("equipment", "")), 0)))
			return [float(best), target]
		"tool_tier":
			var tier := 0
			for dep in s.depths:
				if dep["unlocked"]:
					tier = maxi(tier, int(dep["tool_tier"]))
			return [float(tier), target]
		"tech":
			return [1.0 if s.techs.has(String(o.get("tech", ""))) else 0.0, 1.0]
		"techs":
			return [float(s.techs.size()), target]
		"discovered":
			return [1.0 if s.discoveries.has(String(o.get("resource", ""))) else 0.0, 1.0]
		"discoveries":
			return [float(s.discoveries.size()), target]
		"income":
			return [float(sim.rt.get("income_per_min", 0.0)), target]
		"prestige":
			return [float(s.prestige.get("count", 0)), target]
		"automation":
			return [float(compute_stage(sim)), target]
		"quests":
			var n3 := 0
			for q in s.quests:
				if s.quests[q] == "claimed":
					n3 += 1
			return [float(n3), target]
	return [0.0, target]


static func objective_done(sim: Simulation, o: Dictionary) -> bool:
	var p := objective_progress(sim, o)
	return float(p[0]) >= float(p[1]) - 1e-9


static func refresh_quests(sim: Simulation) -> void:
	## Activates quests whose prerequisites are all claimed.
	var s := sim.state
	for q in sim.content.quests:
		var qid := String(q["id"])
		if s.quests.has(qid):
			continue
		var ok := true
		for req in q.get("requires", []):
			if s.quests.get(req, "") != "claimed":
				ok = false
				break
		if ok:
			s.quests[qid] = "active"
			sim.emit("quest_active", {"quest": qid})


static func _check_quests(sim: Simulation) -> void:
	var s := sim.state
	for q in sim.content.quests:
		var qid := String(q["id"])
		if s.quests.get(qid, "") == "active" and objective_done(sim, q.get("objective", {})):
			s.quests[qid] = "done"
			sim.emit("quest_done", {"quest": qid})


static func claim_quest(sim: Simulation, qid: String) -> Dictionary:
	var s := sim.state
	if s.quests.get(qid, "") != "done":
		return {"ok": false, "error": "quest_not_done"}
	var q: Dictionary = sim.content.quest_by_id.get(qid, {})
	var rw: Dictionary = q.get("reward", {})
	s.money += float(rw.get("money", 0.0))
	s.research_points += float(rw.get("rp", 0.0))
	s.quests[qid] = "claimed"
	s.stat_add("quests_claimed", 1.0)
	sim.emit("quest_claimed", {"quest": qid, "reward": rw})
	refresh_quests(sim)
	_check_quests(sim)
	return {"ok": true, "reward": rw}


static func _check_achievements(sim: Simulation) -> void:
	var s := sim.state
	for a in sim.content.achievements:
		var aid := String(a["id"])
		if s.achievements.has(aid):
			continue
		if objective_done(sim, a.get("objective", {})):
			s.achievements[aid] = s.total_time
			var rw: Dictionary = a.get("reward", {})
			s.money += float(rw.get("money", 0.0))
			if rw.has("bonus"):
				var st := String(rw["bonus"]["stat"])
				s.bonuses[st] = float(s.bonuses.get(st, 1.0)) * float(rw["bonus"]["value"])
				sim.invalidate_modifiers()
			if rw.has("cosmetic"):
				s.cosmetics["unlocked"][rw["cosmetic"]] = true
			sim.emit("achievement", {"achievement": aid, "reward": rw})


# -------------------------------------------------------------- contracts

static func contracts_unlocked(sim: Simulation) -> bool:
	var uq := String(sim.content.contracts_cfg.get("unlock_quest", ""))
	return uq == "" or sim.state.quests.get(uq, "") == "claimed"


static func _tick_contract(sim: Simulation) -> void:
	var s := sim.state
	var cfg := sim.content.contracts_cfg
	if cfg.is_empty() or not contracts_unlocked(sim):
		return
	var c := s.contract
	if not c.is_empty():
		if float(c.get("progress", 0.0)) >= float(c.get("target", 1.0)):
			s.money += float(c["reward"])
			s.stat_add("contracts", 1.0)
			sim.emit("contract_done", {"contract": c.duplicate()})
			s.contract = {"next_at": s.run_time + float(cfg.get("interval_s", 120))}
		elif s.run_time >= float(c.get("deadline", 0.0)) and c.has("item"):
			sim.emit("contract_failed", {"contract": c.duplicate()})
			s.contract = {"next_at": s.run_time + float(cfg.get("interval_s", 120))}
		if s.contract.has("item") or s.run_time < float(s.contract.get("next_at", 0.0)):
			return
	var sold_rate: Dictionary = s.sold_ema
	if sold_rate.is_empty():
		return
	var ids := sold_rate.keys()
	ids.sort()
	var rng := DetRng.new(0)
	rng.set_state(s.rng_state)
	var weights := {}
	for id in ids:
		weights[id] = float(sold_rate[id]) * maxf(1.0, Economy.item_price(sim, id))
	var item := rng.weighted_key(weights)
	s.rng_state = rng.get_state()
	var rate := float(sold_rate.get(item, 0.0))
	if rate <= 0.0:
		return
	var target := maxf(10.0, ceilf(rate * float(cfg.get("target_seconds_of_production", 180))))
	var reward := target * Economy.item_price(sim, item) * float(cfg.get("reward_mult", 1.5))
	s.contract = {"item": item, "target": target, "progress": 0.0, "reward": reward,
		"deadline": s.run_time + float(cfg.get("duration_s", 600)), "started": s.run_time}
	sim.emit("contract_new", {"contract": s.contract.duplicate()})


static func on_sold(sim: Simulation, item: String, units: float) -> void:
	var c := sim.state.contract
	if c.get("item", "") == item:
		c["progress"] = float(c.get("progress", 0.0)) + units


## Exponential moving average of units sold per second per item (tau 60 s),
## used to size delivery contracts to what the mine actually produces.
static func update_sold_ema(sim: Simulation, sold: Dictionary, dt: float) -> void:
	var ema: Dictionary = sim.state.sold_ema
	var alpha := 1.0 - exp(-dt / 60.0)
	for item in sold:
		if not ema.has(item):
			ema[item] = 0.0
	for item in ema.keys():
		var r := float(sold.get(item, 0.0)) / dt
		ema[item] = float(ema[item]) + alpha * (r - float(ema[item]))
		if float(ema[item]) < 1e-6 and not sold.has(item):
			ema.erase(item)
