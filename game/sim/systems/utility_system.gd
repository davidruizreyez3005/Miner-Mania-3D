class_name UtilitySystem
extends RefCounted
## Site utilities and upkeep:
##  * power - the grid plus the generator supply the plant. Loads are fed
##    in priority order (balance "power.priority"): the belt and the pumps
##    first - they keep ore moving and the galleries dry - then the machines
##    along the line, crusher first. A machine the supply does not fully
##    reach runs at the share it gets and the ore it cannot take bypasses
##    it, so building a new machine never slows the ones already running;
##  * dewatering - flooded depths need surface pump capacity >= inflow;
##  * hazards - unmitigated hazards throttle extraction at their depth;
##  * wear and repair - working machines wear out and run slower; mechanics
##    service them on their rounds and rush to worn ones;
##  * research - the office and engineers produce research points.


static func tick(sim: Simulation, dt: float) -> void:
	_power(sim)
	_hazards(sim)


## Grid power (kW) after modifiers.
static func grid_kw(sim: Simulation) -> float:
	return float(sim.content.bal("power", "grid_kw", 65.0)) * sim.mods.m("power_supply")


## The generator's output (kW) at `level` and condition `cond`, after modifiers.
static func generator_kw(sim: Simulation, level: int, cond: float = 1.0) -> float:
	return sim.content.facility_stat("generator", "power_kw", level) * Economy.condition_factor(sim, cond) * sim.mods.m("power_supply")


## Built loads in feeding order: the priority list, then any other powered facility.
static func power_order(sim: Simulation) -> Array:
	var out := []
	for fid in sim.content.bal("power", "priority", []):
		if float(sim.content.facility(String(fid)).get("power_kw", 0.0)) > 0.0 and sim.facility_built(String(fid)):
			out.append(String(fid))
	for fac in sim.content.facilities:
		var fid := String(fac["id"])
		if float(fac.get("power_kw", 0.0)) > 0.0 and sim.facility_built(fid) and not fid in out:
			out.append(fid)
	return out


## What a built load needs now (kW): its rating times how much of its
## full-power capacity the work in front of it takes.
static func power_demand(sim: Simulation, fid: String) -> float:
	var fac := sim.content.facility(fid)
	var kw := float(fac.get("power_kw", 0.0))
	var util := 1.0
	if fac.get("category", "") == "processing":
		var fs: Dictionary = sim.state.facilities[fid]
		util = float(fs.get("need", fs.get("util", 0.0)))
	elif fid == "pump":
		util = clampf(float(sim.rt.get("pump", {}).get("load", 0.0)), 0.0, 1.0)
	elif fid == "conveyor":
		util = 1.0 if Simulation.inv_total(sim.state.surface_bin) > 0.01 else 0.1
	return kw * clampf(util, 0.0, 1.0)


## The share of its full-power capacity a load can use (1 = fully powered).
static func power_factor(sim: Simulation, fid: String) -> float:
	return float(sim.rt.get("power_factors", {}).get(fid, 1.0))


static func _power(sim: Simulation) -> void:
	var s := sim.state
	var grid := grid_kw(sim)
	var gen := 0.0
	if sim.facility_built("generator"):
		var g: Dictionary = s.facilities["generator"]
		gen = generator_kw(sim, int(g["level"]), float(g["condition"]))
	var supply := grid + gen
	var left := supply
	var demand := 0.0
	var factors := {}
	var draw := {}
	var lowest := 1.0
	var short := ""
	for fid in power_order(sim):
		var want := power_demand(sim, fid)
		var got := clampf(left, 0.0, want)
		left -= got
		demand += want
		draw[fid] = got
		# Fully fed: the whole capacity is there. Short: the power it gets
		# runs that share of its full-power capacity.
		var kw := float(sim.content.facility(fid).get("power_kw", 0.0))
		factors[fid] = 1.0 if got >= want - 1e-9 else clampf(got / maxf(kw, 1e-9), 0.0, 1.0)
		if float(factors[fid]) < lowest:
			lowest = float(factors[fid])
			short = fid
	sim.rt["power"] = {"supply": supply, "demand": demand, "grid": grid, "generator": gen, "draw": draw, "short": short}
	sim.rt["power_factors"] = factors
	sim.rt["power_factor"] = lowest
	if sim.facility_built("generator"):
		# The grid carries the base load; the generator works for the rest.
		s.facilities["generator"]["util"] = clampf((supply - left - grid) / maxf(gen, 1e-9), 0.0, 1.0)
	# Tell the player when a machine starts going short (hysteresis: short
	# below 95 %, back to normal at full power).
	var was: Dictionary = sim.rt.get("power_short", {})
	var now := {}
	for fid in factors:
		var f := float(factors[fid])
		if f < 0.95 or (was.has(fid) and f < 0.999):
			now[fid] = true
			if not was.has(fid) and sim.rt.has("power_short"):
				sim.emit("power_short", {"facility": fid, "factor": f})
	sim.rt["power_short"] = now


static func _hazards(sim: Simulation) -> void:
	var s := sim.state
	var water_cfg: Dictionary = sim.content.hazards.get("water", {}).get("mitigation", {})
	var inflow := 0.0
	for dep in s.depths:
		if dep["unlocked"] and "water" in sim.content.depth(int(dep["index"])).get("hazards", []):
			var d := int(dep["index"])
			inflow += float(water_cfg.get("inflow_base", 1.0)) + float(water_cfg.get("inflow_per_depth", 1.0)) * float(d - int(water_cfg.get("from_depth", 3)))
	var cap := 0.0
	var full := 0.0
	if sim.facility_built("pump"):
		var p: Dictionary = s.facilities["pump"]
		full = sim.content.facility_stat("pump", "capacity", int(p["level"])) * Economy.condition_factor(sim, float(p["condition"])) \
			* sim.mods.m("pump_capacity")
		cap = full * power_factor(sim, "pump")
		p["util"] = clampf(minf(inflow, cap) / maxf(full, 1e-9), 0.0, 1.0)
	var water_ratio := 1.0 if inflow <= 0.0 else clampf(cap / inflow, 0.0, 1.0)
	# Load is measured against the full-power capacity (what the pumps need
	# to draw), so a power shortage does not inflate its own demand.
	sim.rt["pump"] = {"capacity": cap, "inflow": inflow, "load": inflow / maxf(full, 1e-9) if full > 0.0 else 1.0, "ratio": water_ratio}
	var hz := {}
	var active := {}
	for dep in s.depths:
		if not dep["unlocked"]:
			continue
		var d := int(dep["index"])
		var f := 1.0
		var list := []
		for h in sim.content.depth(d).get("hazards", []):
			var pen := float(sim.content.hazards.get(h, {}).get("penalty", 0.5))
			if h == "water":
				var hf := pen + (1.0 - pen) * water_ratio
				f *= hf
				if water_ratio < 0.999:
					list.append(h)
			elif not sim.mods.mitigated.has(h):
				f *= pen
				list.append(h)
		hz[d] = f
		active[d] = list
	sim.rt["hazard"] = hz
	sim.rt["hazard_active"] = active


static func tick_maintenance(sim: Simulation, dt: float) -> void:
	var s := sim.state
	var threshold := float(sim.content.bal("condition", "repair_threshold", 0.8))
	var done_at := float(sim.content.bal("condition", "repaired_at", 0.999))
	var mech_rate := float(sim.content.role_by_id.get("mechanic", {}).get("stats", {}).get("repair_per_s", 0.035))
	var ws_mult := 1.0
	if sim.facility_built("workshop"):
		ws_mult = sim.content.facility_stat("workshop", "repair_mult", sim.facility_level("workshop"))
	var repair_crew: Dictionary = sim.rt.get("repair_crew", {})
	var lift_running := bool(sim.rt.get("lift", {}).get("running", false)) and float(sim.rt.get("lift", {}).get("moved_rate", 0.0)) > 0.0
	var per_repair := maxf(1.0 - threshold, 0.05)
	for fac in sim.content.facilities:
		var fid := String(fac["id"])
		var fs: Dictionary = s.facilities.get(fid, {})
		if not fs.get("built", false) or not fac.get("repairable", false):
			continue
		var util := float(fs.get("util", 0.0))
		if fid == "headframe":
			util = 1.0 if lift_running else 0.0
			fs["util"] = util
		var wear := float(fac.get("wear_per_s", 0.0)) * util * sim.mods.m("wear_rate") * dt
		var cond := clampf(float(fs["condition"]) - wear, 0.0, 1.0)
		if float(repair_crew.get(fid, 0.0)) > 0.0:
			var fixed := minf(mech_rate * float(repair_crew[fid]) * ws_mult * sim.mods.m("repair_rate") * dt, 1.0 - cond)
			cond += fixed
			# Every restored stretch as long as the worn margin counts as one
			# repair (achievements), however it was split over service visits.
			fs["serviced"] = float(fs.get("serviced", 0.0)) + fixed
			if float(fs["serviced"]) >= per_repair:
				fs["serviced"] = float(fs["serviced"]) - per_repair
				s.stat_add("repairs", 1.0)
		cond = clampf(cond, 0.0, 1.0)
		if cond < threshold and not fs.get("repairing", false):
			fs["repairing"] = true
			sim.emit("machine_worn", {"facility": fid})
		if fs.get("repairing", false) and cond >= done_at:
			fs["repairing"] = false
			cond = 1.0
			sim.emit("repair_done", {"facility": fid})
		fs["condition"] = cond
	# Research.
	var office_rate := sim.content.facility_stat("office", "research", sim.facility_level("office"))
	var eng := float(sim.content.role_by_id.get("engineer", {}).get("stats", {}).get("research_per_s", 0.35))
	var rp_rate := (office_rate + sim.crew("office", "engineer") * eng) * sim.mods.m("research_rate")
	s.research_points += rp_rate * dt
	sim.rt["research_rate"] = rp_rate
