class_name SimCommands
extends RefCounted
## The only way player intent changes the simulation. Every command is
## validated against the current state and either applied atomically or
## rejected with an error code; nothing else in the game mutates SimState.
##
##   {"type": "manual_swing", "depth": 1, "slot": 0} | {"type": "manual_repair", "facility": "crusher"}
##   {"type": "call_lift"} | {"type": "dispatch"}
##   {"type": "hire", "role": "miner", "post": "depth:1"} | {"type": "fire", "worker": 3}
##   {"type": "reassign", "worker": 3, "post": "depth:2"}
##   {"type": "build", "facility": "crusher"} | {"type": "upgrade", "facility": "headframe", "count": 1}
##   {"type": "upgrade_equipment", "depth": 1, "equipment": "mining", "count": 1}
##   {"type": "buy_tool", "depth": 1} | {"type": "unlock_depth", "depth": 2}
##   {"type": "research", "tech": "crushing"} | {"type": "claim_quest", "quest": "q_first_swing"}
##   {"type": "rally"} | {"type": "prestige", "region": "red_rock_canyon"} | {"type": "buy_legacy", "upgrade": "veteran_crews"}
##   {"type": "equip_cosmetic", "cosmetic": "outfit_miner_02"} | {"type": "set_tutorial", "step": 3, "done": false}

const TYPES := ["manual_swing", "manual_repair", "call_lift", "dispatch", "hire", "fire", "reassign", "build", "upgrade",
	"upgrade_equipment", "buy_tool", "unlock_depth", "research", "claim_quest", "rally", "prestige", "buy_legacy",
	"equip_cosmetic", "set_tutorial"]


static func run(sim: Simulation, cmd: Dictionary) -> Dictionary:
	var t := String(cmd.get("type", ""))
	var r: Dictionary
	match t:
		"manual_swing":
			r = MiningSystem.manual_swing(sim, int(cmd.get("depth", 0)), int(cmd.get("slot", -1)))
		"manual_repair":
			r = _manual_repair(sim, String(cmd.get("facility", "")))
		"call_lift":
			r = TransportSystem.call_lift(sim)
		"dispatch":
			r = SalesSystem.dispatch(sim)
		"hire":
			r = _hire(sim, String(cmd.get("role", "")), String(cmd.get("post", "")))
		"fire":
			r = _fire(sim, int(cmd.get("worker", -1)))
		"reassign":
			r = _reassign(sim, int(cmd.get("worker", -1)), String(cmd.get("post", "")))
		"build":
			r = _build(sim, String(cmd.get("facility", "")))
		"upgrade":
			r = _upgrade(sim, String(cmd.get("facility", "")), maxi(1, int(cmd.get("count", 1))))
		"upgrade_equipment":
			r = _upgrade_equipment(sim, int(cmd.get("depth", 0)), String(cmd.get("equipment", "")), maxi(1, int(cmd.get("count", 1))))
		"buy_tool":
			r = _buy_tool(sim, int(cmd.get("depth", 0)))
		"unlock_depth":
			r = _unlock_depth(sim, int(cmd.get("depth", 0)))
		"research":
			r = _research(sim, String(cmd.get("tech", "")))
		"claim_quest":
			r = ProgressionSystem.claim_quest(sim, String(cmd.get("quest", "")))
		"rally":
			r = _rally(sim)
		"prestige":
			r = PrestigeSystem.prestige(sim, String(cmd.get("region", sim.state.region)))
		"buy_legacy":
			r = PrestigeSystem.buy_upgrade(sim, String(cmd.get("upgrade", "")))
		"equip_cosmetic":
			r = _equip(sim, String(cmd.get("cosmetic", "")))
		"set_tutorial":
			sim.state.meta["tutorial_step"] = int(cmd.get("step", 0))
			sim.state.meta["tutorial_done"] = bool(cmd.get("done", false))
			r = {"ok": true}
		_:
			r = {"ok": false, "error": "unknown_command"}
	r["type"] = t
	if r.get("ok", false):
		WorkforceSystem.update_crews(sim)
	return r


## The foreman patches a worn machine by hand (before mechanics exist).
static func _manual_repair(sim: Simulation, fid: String) -> Dictionary:
	var fac := sim.content.facility(fid)
	var fs: Dictionary = sim.state.facilities.get(fid, {})
	if fac.is_empty() or not fs.get("built", false) or not fac.get("repairable", false):
		return {"ok": false, "error": "not_repairable"}
	var cond := float(fs.get("condition", 1.0))
	if cond >= 0.999:
		return {"ok": false, "error": "not_worn"}
	var after := minf(1.0, cond + float(sim.content.bal("condition", "manual_repair", 0.25)))
	fs["condition"] = after
	sim.state.stat_add("manual_repairs", 1.0)
	if after >= float(sim.content.bal("condition", "repaired_at", 0.999)) and fs.get("repairing", false):
		fs["repairing"] = false
		fs["condition"] = 1.0
		sim.state.stat_add("repairs", 1.0)
		sim.emit("repair_done", {"facility": fid, "manual": true})
	sim.emit("manual_repair", {"facility": fid, "condition": fs["condition"]})
	return {"ok": true, "condition": fs["condition"]}


static func _pay(sim: Simulation, cost: float) -> bool:
	if is_nan(cost) or cost < 0.0 or sim.state.money + 1e-6 < cost:
		return false
	sim.state.money = maxf(0.0, sim.state.money - cost)
	return true


static func role_unlocked(sim: Simulation, role_id: String) -> bool:
	var role: Dictionary = sim.content.role_by_id.get(role_id, {})
	if role.is_empty():
		return false
	var un: Dictionary = role.get("unlock", {})
	if un.has("quest") and sim.state.quests.get(un["quest"], "") != "claimed":
		return false
	if un.has("tech") and not sim.state.techs.has(un["tech"]):
		return false
	if un.has("facility") and not sim.facility_built(String(un["facility"])):
		return false
	return true


static func post_valid(sim: Simulation, role_id: String, post: String) -> bool:
	var role: Dictionary = sim.content.role_by_id.get(role_id, {})
	var kind := post.split(":")[0]
	if not kind in role.get("posts", []):
		return false
	if kind == "depth":
		var dep := sim.state.depth(int(post.split(":")[1]))
		return not dep.is_empty() and dep["unlocked"]
	if sim.content.facility_by_id.has(kind):
		return sim.facility_built(kind)
	return true


static func post_free(sim: Simulation, role_id: String, post: String, exclude_id: int = -1) -> int:
	var used := 0
	for w in sim.state.workers:
		if w["post"] == post and w["role"] == role_id and int(w["id"]) != exclude_id:
			used += 1
	return Economy.post_capacity(sim, post, role_id) - used


static func _hire(sim: Simulation, role_id: String, post: String) -> Dictionary:
	if not role_unlocked(sim, role_id):
		return {"ok": false, "error": "role_locked"}
	if not post_valid(sim, role_id, post):
		return {"ok": false, "error": "invalid_post"}
	if post_free(sim, role_id, post) <= 0:
		return {"ok": false, "error": "post_full"}
	if sim.state.workers.size() >= Economy.worker_capacity(sim):
		return {"ok": false, "error": "housing_full"}
	var cost := Economy.hire_cost(sim, role_id)
	if not _pay(sim, cost):
		return {"ok": false, "error": "no_money", "cost": cost}
	var w := sim.add_worker(role_id, post)
	sim.state.stat_add("hired", 1.0)
	sim.emit("worker_hired", {"worker": w["id"], "role": role_id, "post": post})
	WorkforceSystem.assign_jobs(sim, true)
	return {"ok": true, "worker": w["id"], "cost": cost}


static func _fire(sim: Simulation, id: int) -> Dictionary:
	for i in sim.state.workers.size():
		if int(sim.state.workers[i]["id"]) == id:
			var w: Dictionary = sim.state.workers[i]
			sim.state.workers.remove_at(i)
			sim.emit("worker_fired", {"worker": id, "role": w["role"]})
			return {"ok": true}
	return {"ok": false, "error": "no_worker"}


static func _reassign(sim: Simulation, id: int, post: String) -> Dictionary:
	var w := sim.worker_by_id(id)
	if w.is_empty():
		return {"ok": false, "error": "no_worker"}
	if w["post"] == post:
		return {"ok": true}
	if not post_valid(sim, String(w["role"]), post):
		return {"ok": false, "error": "invalid_post"}
	if post_free(sim, String(w["role"]), post, id) <= 0:
		return {"ok": false, "error": "post_full"}
	w["post"] = post
	sim.emit("worker_reassigned", {"worker": id, "post": post})
	WorkforceSystem.assign_jobs(sim, true)
	return {"ok": true}


static func facility_requirement_met(sim: Simulation, fid: String) -> bool:
	var req: Dictionary = sim.content.facility(fid).get("requires", {})
	if req.has("tech") and not sim.state.techs.has(req["tech"]):
		return false
	return true


static func _build(sim: Simulation, fid: String) -> Dictionary:
	var fac := sim.content.facility(fid)
	if fac.is_empty():
		return {"ok": false, "error": "unknown_facility"}
	if sim.facility_built(fid):
		return {"ok": false, "error": "already_built"}
	if not facility_requirement_met(sim, fid):
		return {"ok": false, "error": "locked"}
	var cost := float(fac.get("build_cost", 0.0))
	if not _pay(sim, cost):
		return {"ok": false, "error": "no_money", "cost": cost}
	var fs: Dictionary = sim.state.facilities[fid]
	fs["built"] = true
	fs["level"] = 1
	fs["condition"] = 1.0
	sim.state.stat_add("built", 1.0)
	sim.emit("facility_built", {"facility": fid})
	return {"ok": true, "cost": cost}


static func _upgrade(sim: Simulation, fid: String, count: int) -> Dictionary:
	var fac := sim.content.facility(fid)
	if fac.is_empty() or not sim.facility_built(fid):
		return {"ok": false, "error": "not_built"}
	var fs: Dictionary = sim.state.facilities[fid]
	var room := int(fac.get("max_level", 1)) - int(fs["level"])
	if room <= 0:
		return {"ok": false, "error": "max_level"}
	count = mini(count, room)
	var cost := Economy.facility_upgrade_cost(sim, fid, count)
	if not _pay(sim, cost):
		return {"ok": false, "error": "no_money", "cost": cost}
	var before := int(fs["level"])
	fs["level"] = before + count
	sim.state.stat_add("upgrades", float(count))
	sim.emit("upgrade_bought", {"facility": fid, "from": before, "level": fs["level"]})
	return {"ok": true, "cost": cost, "level": fs["level"]}


static func _upgrade_equipment(sim: Simulation, d: int, kind: String, count: int) -> Dictionary:
	var dep := sim.state.depth(d)
	if dep.is_empty() or not dep["unlocked"]:
		return {"ok": false, "error": "depth_locked"}
	var eq: Dictionary = sim.content.equipment.get(kind, {})
	if eq.is_empty() or not dep["levels"].has(kind):
		return {"ok": false, "error": "unknown_equipment"}
	var lvl := int(dep["levels"][kind])
	var gates: Dictionary = eq.get("requires_tech_above_level", {})
	for k in gates:
		if lvl + count > int(k) and not sim.state.techs.has(gates[k]):
			if lvl >= int(k):
				return {"ok": false, "error": "locked", "tech": gates[k]}
			count = int(k) - lvl
	var room := int(eq.get("max_level", 1)) - lvl
	if room <= 0:
		return {"ok": false, "error": "max_level"}
	count = mini(count, room)
	var cost := Economy.equipment_cost(sim, d, kind, count)
	if not _pay(sim, cost):
		return {"ok": false, "error": "no_money", "cost": cost}
	dep["levels"][kind] = lvl + count
	sim.state.stat_add("upgrades", float(count))
	sim.emit("upgrade_bought", {"depth": d, "equipment": kind, "from": lvl, "level": lvl + count})
	return {"ok": true, "cost": cost, "level": lvl + count}


static func _buy_tool(sim: Simulation, d: int) -> Dictionary:
	var dep := sim.state.depth(d)
	if dep.is_empty() or not dep["unlocked"]:
		return {"ok": false, "error": "depth_locked"}
	var next := int(dep["tool_tier"]) + 1
	var t := sim.content.tool_tier(next)
	if t.is_empty():
		return {"ok": false, "error": "max_tier"}
	if not sim.mods.is_unlocked("tool:%d" % next):
		return {"ok": false, "error": "locked", "tech": t.get("requires_tech", "")}
	var cost := Economy.tool_cost(sim, d, next)
	if not _pay(sim, cost):
		return {"ok": false, "error": "no_money", "cost": cost}
	dep["tool_tier"] = next
	sim.emit("tool_upgraded", {"depth": d, "tier": next})
	return {"ok": true, "cost": cost, "tier": next}


static func depth_unlockable(sim: Simulation, d: int) -> String:
	## "" when depth d can be bought now (money aside), else the reason.
	var dep := sim.state.depth(d)
	if dep.is_empty():
		return "unknown_depth"
	if dep["unlocked"]:
		return "already_unlocked"
	var prev := sim.state.depth(d - 1)
	if d > 1 and (prev.is_empty() or not prev["unlocked"]):
		return "previous_locked"
	var ddef := sim.content.depth(d)
	if int(ddef.get("requires_prestige", 0)) > int(sim.state.prestige.get("count", 0)):
		return "requires_prestige"
	if int(ddef.get("requires_prestige", 0)) > 0 and not sim.mods.has_flag("deep_charter"):
		return "requires_charter"
	return ""


static func _unlock_depth(sim: Simulation, d: int) -> Dictionary:
	var why := depth_unlockable(sim, d)
	if why != "":
		return {"ok": false, "error": why}
	var cost := Economy.depth_unlock_cost(sim, d)
	if not _pay(sim, cost):
		return {"ok": false, "error": "no_money", "cost": cost}
	sim.unlock_depth_internal(d)
	return {"ok": true, "cost": cost}


static func tech_available(sim: Simulation, tid: String) -> bool:
	var t: Dictionary = sim.content.tech_by_id.get(tid, {})
	if t.is_empty() or sim.state.techs.has(tid):
		return false
	for req in t.get("requires", []):
		if not sim.state.techs.has(req):
			return false
	return true


static func _research(sim: Simulation, tid: String) -> Dictionary:
	var t: Dictionary = sim.content.tech_by_id.get(tid, {})
	if t.is_empty():
		return {"ok": false, "error": "unknown_tech"}
	if sim.state.techs.has(tid):
		return {"ok": false, "error": "already_researched"}
	if not tech_available(sim, tid):
		return {"ok": false, "error": "prerequisites"}
	var rp := float(t.get("rp", 0.0))
	if sim.state.research_points + 1e-6 < rp:
		return {"ok": false, "error": "no_research_points", "rp": rp}
	var cost := float(t.get("cost", 0.0))
	if not _pay(sim, cost):
		return {"ok": false, "error": "no_money", "cost": cost}
	sim.state.research_points = maxf(0.0, sim.state.research_points - rp)
	sim.state.techs[tid] = true
	sim.state.stat_add("research_done", 1.0)
	sim.invalidate_modifiers()
	sim.emit("tech_researched", {"tech": tid})
	return {"ok": true, "cost": cost}


static func rally_unlocked(sim: Simulation) -> bool:
	var q := String(sim.content.bal("rally", "unlock_quest", ""))
	return q == "" or sim.state.quests.get(q, "") == "claimed"


static func _rally(sim: Simulation) -> Dictionary:
	if not rally_unlocked(sim):
		return {"ok": false, "error": "locked"}
	var s := sim.state
	if s.run_time < float(s.boosts.get("rally_ready_at", 0.0)):
		return {"ok": false, "error": "cooldown", "ready_in": float(s.boosts["rally_ready_at"]) - s.run_time}
	s.boosts["rally_until"] = s.run_time + float(sim.content.bal("rally", "duration_s", 45))
	s.boosts["rally_ready_at"] = s.run_time + float(sim.content.bal("rally", "cooldown_s", 240))
	sim.emit("rally", {"until": s.boosts["rally_until"]})
	return {"ok": true}


static func _equip(sim: Simulation, cid: String) -> Dictionary:
	var c: Dictionary = sim.content.cosmetic_by_id.get(cid, {})
	if c.is_empty():
		return {"ok": false, "error": "unknown_cosmetic"}
	if not sim.state.cosmetics["unlocked"].has(cid):
		return {"ok": false, "error": "locked"}
	sim.state.cosmetics["equipped"][c["kind"]] = cid
	sim.emit("cosmetic_equipped", {"cosmetic": cid, "kind": c["kind"]})
	return {"ok": true}
