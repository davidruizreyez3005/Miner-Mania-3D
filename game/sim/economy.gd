class_name Economy
extends RefCounted
## Pure economic formulas: costs, prices, production rates and prestige
## rewards. Stateless and deterministic; every number the UI shows comes from
## here or from the simulation's runtime metrics.


static func market_mult(content: ContentDB, res_id: String, t: float) -> float:
	var mk: Dictionary = content.resource_by_id.get(res_id, {}).get("market", {})
	var amp := float(mk.get("amplitude", 0.0))
	var period := maxf(1.0, float(mk.get("period_s", 1000.0)))
	return 1.0 + amp * sin(TAU * t / period + float(mk.get("phase", 0.0)))


static func item_price(sim: Simulation, item_id: String) -> float:
	var key := "price:" + item_id
	if sim.memo.has(key):
		return sim.memo[key]
	var it := sim.content.item(item_id)
	if it.is_empty():
		return 0.0
	var res := String(it["resource"])
	var cls := sim.content.resource_class(res)
	var p := float(it["value"]) * market_mult(sim.content, res, sim.state.total_time)
	p *= sim.mods.m("sale_value") * float(sim.mods.class_value.get(cls, 1.0)) * sim.mods.income_mult
	sim.memo[key] = p
	return p


static func hire_cost(sim: Simulation, role_id: String) -> float:
	var role: Dictionary = sim.content.role_by_id.get(role_id, {})
	var n := 0
	for w in sim.state.workers:
		if w["role"] == role_id:
			n += 1
	return float(role.get("base_cost", 0.0)) * pow(float(role.get("growth", 1.0)), n) * sim.mods.m("hire_cost")


static func facility_upgrade_cost(sim: Simulation, fid: String, count: int = 1) -> float:
	var fac := sim.content.facility(fid)
	var st: Dictionary = sim.state.facilities.get(fid, {})
	return Curves.cost_n(fac.get("cost", {}), int(st.get("level", 1)), count) * sim.mods.m("upgrade_cost")


static func facility_affordable(sim: Simulation, fid: String) -> int:
	var fac := sim.content.facility(fid)
	var st: Dictionary = sim.state.facilities.get(fid, {})
	var lvl := int(st.get("level", 1))
	var room := int(fac.get("max_level", 1)) - lvl
	return Curves.affordable(fac.get("cost", {}), lvl, sim.state.money / sim.mods.m("upgrade_cost"), room)


static func equipment_cost(sim: Simulation, depth_index: int, kind: String, count: int = 1) -> float:
	var eq: Dictionary = sim.content.equipment.get(kind, {})
	var dep := sim.state.depth(depth_index)
	var scale := float(sim.content.depth(depth_index).get("cost_scale", 1.0))
	return Curves.cost_n(eq.get("cost", {}), int(dep["levels"][kind]), count, scale) * sim.mods.m("upgrade_cost")


static func equipment_affordable(sim: Simulation, depth_index: int, kind: String) -> int:
	var eq: Dictionary = sim.content.equipment.get(kind, {})
	var dep := sim.state.depth(depth_index)
	var scale := float(sim.content.depth(depth_index).get("cost_scale", 1.0))
	var lvl := int(dep["levels"][kind])
	var room := int(eq.get("max_level", 1)) - lvl
	return Curves.affordable(eq.get("cost", {}), lvl, sim.state.money / sim.mods.m("upgrade_cost"), room, scale)


static func tool_cost(sim: Simulation, depth_index: int, tier: int) -> float:
	var t := sim.content.tool_tier(tier)
	return float(t.get("cost", 0.0)) * float(sim.content.depth(depth_index).get("cost_scale", 1.0)) * sim.mods.m("upgrade_cost")


static func depth_unlock_cost(sim: Simulation, depth_index: int) -> float:
	return float(sim.content.depth(depth_index).get("unlock_cost", 0.0))


static func lp_gain(content: ContentDB, run_earned: float) -> int:
	var f: Dictionary = content.legacy_cfg.get("formula", {})
	if run_earned < float(f.get("min_earned", 1e18)):
		return 0
	var x := run_earned / float(f.get("divisor", 1.0))
	return int(floorf(float(f.get("scale", 1.0)) * pow(x, float(f.get("exponent", 0.5)))))


static func legacy_cost(content: ContentDB, uid: String, level: int) -> int:
	var u: Dictionary = content.legacy_by_id.get(uid, {})
	var c: Dictionary = u.get("cost", {})
	return int(ceilf(float(c.get("base", 1)) * pow(float(c.get("growth", 1.0)), level)))


## Per-miner mining work per second at a depth (before crew, hazard and boost factors).
static func miner_work_rate(sim: Simulation, depth_index: int) -> float:
	var key := "mwr%d" % depth_index
	if sim.memo.has(key):
		return sim.memo[key]
	var v := _miner_work_rate(sim, depth_index)
	sim.memo[key] = v
	return v


static func _miner_work_rate(sim: Simulation, depth_index: int) -> float:
	var dep := sim.state.depth(depth_index)
	if dep.is_empty():
		return 0.0
	var lvl := int(dep["levels"]["mining"])
	var tool := sim.content.tool_tier(int(dep["tool_tier"]))
	return sim.content.equipment_stat("mining", "miner_rate", lvl) * float(tool.get("mult", 1.0)) * sim.mods.m("mining_rate")


## Storage is sized in seconds of the upstream stage's nominal throughput, so
## buffers grow with production; storage upgrades lengthen the buffer (how
## long a stage keeps working while the next one is paused or manual).
static func station_capacity(sim: Simulation, depth_index: int) -> float:
	var key := "stc%d" % depth_index
	if sim.memo.has(key):
		return sim.memo[key]
	var dep := sim.state.depth(depth_index)
	var buf := sim.content.equipment_stat("station", "buffer_s", int(dep["levels"]["station"]))
	var slots := sim.content.equipment_stat("mining", "miner_slots", int(dep["levels"]["mining"]))
	var inflow := miner_work_rate(sim, depth_index) * slots
	var v := maxf(float(sim.content.bal("storage", "min_station", 30.0)), buf * inflow) * sim.mods.m("storage_capacity")
	sim.memo[key] = v
	return v


## The face pile at the rock face holds `face.buffer_s` seconds of the
## depth's full mining output (>= the longest offline step, so coarse steps
## never cap extraction).
static func face_capacity(sim: Simulation, depth_index: int) -> float:
	var key := "fcc%d" % depth_index
	if sim.memo.has(key):
		return sim.memo[key]
	var dep := sim.state.depth(depth_index)
	var slots := sim.content.equipment_stat("mining", "miner_slots", int(dep["levels"]["mining"]))
	var buf := float(sim.content.bal("face", "buffer_s", 30.0))
	var v := maxf(float(sim.content.bal("face", "min_capacity", 10.0)), buf * slots * miner_work_rate(sim, depth_index) * 2.0)
	sim.memo[key] = v
	return v


static func lift_nominal_rate(sim: Simulation) -> float:
	if sim.memo.has("lnr"):
		return sim.memo["lnr"]
	var lvl := sim.facility_level("headframe")
	var cap := sim.content.facility_stat("headframe", "capacity", lvl) * sim.mods.m("lift_capacity")
	var speed := maxf(0.1, sim.content.facility_stat("headframe", "speed_mps", lvl) * sim.mods.m("lift_speed"))
	var deepest := maxi(1, sim.state.deepest_unlocked())
	var dist := absf(sim.layout.surface_y - sim.layout.floor_y(deepest))
	var cycle := 2.0 * dist / speed + float(sim.content.bal("lift", "load_s", 2.0)) + float(sim.content.bal("lift", "unload_s", 2.0)) + 0.5 * float(deepest - 1)
	sim.memo["lnr"] = cap / cycle
	return cap / cycle


static func conveyor_nominal_rate(sim: Simulation) -> float:
	return sim.content.facility_stat("conveyor", "throughput", sim.facility_level("conveyor")) * sim.mods.m("conveyor_rate")


static func bin_capacity(sim: Simulation) -> float:
	if sim.memo.has("binc"):
		return sim.memo["binc"]
	var buf := sim.content.facility_stat("silo", "buffer_s", sim.facility_level("silo"))
	var v := maxf(float(sim.content.bal("storage", "min_silo", 60.0)), buf * lift_nominal_rate(sim)) * sim.mods.m("storage_capacity")
	sim.memo["binc"] = v
	return v


static func warehouse_capacity(sim: Simulation) -> float:
	if sim.memo.has("whc"):
		return sim.memo["whc"]
	var buf := sim.content.facility_stat("warehouse", "buffer_s", sim.facility_level("warehouse"))
	var v := maxf(float(sim.content.bal("storage", "min_warehouse", 60.0)), buf * conveyor_nominal_rate(sim)) * sim.mods.m("storage_capacity")
	sim.memo["whc"] = v
	return v


static func condition_factor(sim: Simulation, cond: float) -> float:
	var mn := float(sim.content.bal("condition", "min_factor", 0.4))
	return mn + (1.0 - mn) * clampf(cond, 0.0, 1.0)


static func post_capacity(sim: Simulation, post: String, role_id: String) -> int:
	var parts := post.split(":")
	var kind := parts[0]
	var limits: Dictionary = sim.content.workers_cfg.get("post_limits", {}).get(kind, {})
	if not limits.has(role_id):
		return 0
	var v = limits[role_id]
	if v is String:
		var sp := String(v).split(".")
		if kind == "depth":
			var dep := sim.state.depth(int(parts[1]))
			if dep.is_empty():
				return 0
			return int(sim.content.equipment_stat(sp[0], sp[1], int(dep["levels"].get(sp[0], 1))))
		var fst: Dictionary = sim.state.facilities.get(sp[0], {})
		if not fst.get("built", false):
			return 0
		return int(sim.content.facility_stat(sp[0], sp[1], int(fst.get("level", 1))))
	return int(v)


static func worker_capacity(sim: Simulation) -> int:
	var st: Dictionary = sim.state.facilities.get("office", {})
	return int(sim.content.facility_stat("office", "worker_capacity", int(st.get("level", 1))))


static func offline_cap_s(sim: Simulation) -> float:
	var base := float(sim.content.bal("offline", "base_cap_h", 2.0))
	var mx := float(sim.content.bal("offline", "max_cap_h", 24.0))
	return clampf(base + sim.mods.a("offline_cap_h"), 0.0, mx) * 3600.0


static func offline_efficiency(sim: Simulation) -> float:
	var base := float(sim.content.bal("offline", "base_efficiency", 0.6))
	var mx := float(sim.content.bal("offline", "max_efficiency", 1.0))
	return clampf((base + sim.mods.a("offline_efficiency")) * sim.mods.m("offline_efficiency_mult"), 0.0, mx)
