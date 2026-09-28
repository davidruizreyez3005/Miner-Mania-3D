class_name PrestigeSystem
extends RefCounted
## "Sell the Claim": trade the current claim's progress for Legacy Points.
## LP are earned from this claim's total earnings (square-root curve, so
## longer runs pay off with diminishing returns); every LP ever earned adds a
## permanent income multiplier, and LP buy legacy upgrades (starting cash,
## crew efficiency, market contacts, head starts, automation blueprints,
## offline mastery, the Deep Core charter). New regions unlock with prestige
## count. Achievements, discoveries, cosmetics and lifetime stats persist.


static func preview(sim: Simulation) -> Dictionary:
	var earned := float(sim.state.run_stats.get("earned", 0.0))
	var gain := Economy.lp_gain(sim.content, earned)
	var f: Dictionary = sim.content.legacy_cfg.get("formula", {})
	var per_lp := float(f.get("income_per_lp", 0.05))
	var total_after := int(sim.state.prestige.get("lp_total", 0)) + gain
	return {"gain": gain, "earned": earned, "min_earned": float(f.get("min_earned", 0.0)),
		"can": gain > 0, "income_mult_now": sim.mods.income_mult, "income_mult_after": 1.0 + per_lp * total_after}


static func region_available(sim: Simulation, region_id: String, prestige_count: int) -> bool:
	var reg: Dictionary = sim.content.region_by_id.get(region_id, {})
	return not reg.is_empty() and int(reg.get("requires_prestige", 0)) <= prestige_count


static func prestige(sim: Simulation, region_id: String) -> Dictionary:
	var pv := preview(sim)
	if not pv["can"]:
		return {"ok": false, "error": "not_enough_earnings", "min_earned": pv["min_earned"]}
	var count_after := int(sim.state.prestige.get("count", 0)) + 1
	if not region_available(sim, region_id, count_after):
		return {"ok": false, "error": "region_locked"}
	var old := sim.state
	var gain := int(pv["gain"])
	old.prestige["lp"] = int(old.prestige.get("lp", 0)) + gain
	old.prestige["lp_total"] = int(old.prestige.get("lp_total", 0)) + gain
	old.prestige["count"] = count_after
	old.prestige["best_run"] = maxf(float(old.prestige.get("best_run", 0.0)), float(pv["earned"]))
	old.life_stats["prestiges"] = float(old.life_stats.get("prestiges", 0.0)) + 1.0
	var keep_tier := _kept_tech_tier(sim)
	var kept_techs := {}
	if keep_tier > 0:
		for tid in old.techs:
			if int(sim.content.tech_by_id.get(tid, {}).get("tier", 99)) <= keep_tier:
				kept_techs[tid] = true
	var new_seed := DetRng.mix32(old.seed ^ (count_after * 0x9E3779B9)) | (old.seed & ~0xFFFFFFFF)
	sim.new_game(new_seed, old)
	sim.state.region = region_id
	sim.state.techs = kept_techs
	sim.invalidate_modifiers()
	sim._refresh_modifiers()
	ProgressionSystem.refresh_quests(sim)
	sim.emit("prestige", {"gain": gain, "count": count_after, "region": region_id})
	return {"ok": true, "gain": gain, "count": count_after}


static func _kept_tech_tier(sim: Simulation) -> int:
	var lvl := int(sim.state.prestige.get("upgrades", {}).get("research_archive", 0))
	for e in sim.content.legacy_by_id.get("research_archive", {}).get("effects", []):
		if e.get("type", "") == "keep_techs_tier" and lvl >= int(e.get("at_level", 99)):
			return int(e.get("tier", 0))
	return 0


static func buy_upgrade(sim: Simulation, uid: String) -> Dictionary:
	var u: Dictionary = sim.content.legacy_by_id.get(uid, {})
	if u.is_empty():
		return {"ok": false, "error": "unknown_upgrade"}
	var ups: Dictionary = sim.state.prestige["upgrades"]
	var lvl := int(ups.get(uid, 0))
	if lvl >= int(u.get("max_level", 1)):
		return {"ok": false, "error": "max_level"}
	var cost := Economy.legacy_cost(sim.content, uid, lvl)
	if int(sim.state.prestige.get("lp", 0)) < cost:
		return {"ok": false, "error": "no_lp", "cost": cost}
	sim.state.prestige["lp"] = int(sim.state.prestige["lp"]) - cost
	ups[uid] = lvl + 1
	sim.invalidate_modifiers()
	sim.emit("legacy_bought", {"upgrade": uid, "level": lvl + 1})
	return {"ok": true, "cost": cost, "level": lvl + 1}
