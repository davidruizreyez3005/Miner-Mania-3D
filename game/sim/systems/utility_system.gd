class_name UtilitySystem
extends RefCounted
## Site utilities and upkeep:
##  * power - the grid plus the generator supply the plant; when demand
##    exceeds supply every powered machine slows proportionally;
##  * dewatering - flooded depths need surface pump capacity >= inflow;
##  * hazards - unmitigated hazards throttle extraction at their depth;
##  * wear and repair - working machines wear out and run slower; mechanics
##    on site restore them;
##  * research - the office and engineers produce research points.


static func tick(sim: Simulation, dt: float) -> void:
	_power(sim)
	_hazards(sim)


static func _power(sim: Simulation) -> void:
	var s := sim.state
	var supply := float(sim.content.bal("power", "grid_kw", 30.0))
	if sim.facility_built("generator"):
		var g: Dictionary = s.facilities["generator"]
		supply += sim.content.facility_stat("generator", "power_kw", int(g["level"])) * Economy.condition_factor(sim, float(g["condition"]))
	supply *= sim.mods.m("power_supply")
	var demand := 0.0
	for fac in sim.content.facilities:
		var fid := String(fac["id"])
		var kw := float(fac.get("power_kw", 0.0))
		if kw <= 0.0 or not sim.facility_built(fid):
			continue
		var util := 1.0
		if fac.get("category", "") == "processing":
			util = float(s.facilities[fid].get("util", 0.0))
		elif fid == "pump":
			util = clampf(float(sim.rt.get("pump", {}).get("load", 0.0)), 0.0, 1.0)
		elif fid == "conveyor":
			util = 1.0 if Simulation.inv_total(s.surface_bin) > 0.01 else 0.1
		demand += kw * util
	var factor := 1.0 if demand <= supply else supply / maxf(demand, 1e-9)
	sim.rt["power"] = {"supply": supply, "demand": demand}
	sim.rt["power_factor"] = clampf(factor, 0.05, 1.0)
	if sim.facility_built("generator"):
		s.facilities["generator"]["util"] = clampf(demand / maxf(supply, 1e-9), 0.0, 1.0)


static func _hazards(sim: Simulation) -> void:
	var s := sim.state
	var water_cfg: Dictionary = sim.content.hazards.get("water", {}).get("mitigation", {})
	var inflow := 0.0
	for dep in s.depths:
		if dep["unlocked"] and "water" in sim.content.depth(int(dep["index"])).get("hazards", []):
			var d := int(dep["index"])
			inflow += float(water_cfg.get("inflow_base", 1.0)) + float(water_cfg.get("inflow_per_depth", 1.0)) * float(d - int(water_cfg.get("from_depth", 3)))
	var cap := 0.0
	if sim.facility_built("pump"):
		var p: Dictionary = s.facilities["pump"]
		cap = sim.content.facility_stat("pump", "capacity", int(p["level"])) * Economy.condition_factor(sim, float(p["condition"])) \
			* float(sim.rt.get("power_factor", 1.0)) * sim.mods.m("pump_capacity")
		p["util"] = clampf(inflow / maxf(cap, 1e-9), 0.0, 1.0)
	var water_ratio := 1.0 if inflow <= 0.0 else clampf(cap / inflow, 0.0, 1.0)
	sim.rt["pump"] = {"capacity": cap, "inflow": inflow, "load": inflow / maxf(cap, 1e-9) if cap > 0.0 else 1.0, "ratio": water_ratio}
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
		var cond := float(fs["condition"]) - wear
		if float(repair_crew.get(fid, 0.0)) > 0.0:
			cond += mech_rate * float(repair_crew[fid]) * ws_mult * sim.mods.m("repair_rate") * dt
		cond = clampf(cond, 0.0, 1.0)
		if cond < threshold and not fs.get("repairing", false):
			fs["repairing"] = true
			sim.emit("machine_worn", {"facility": fid})
		if fs.get("repairing", false) and cond >= done_at:
			fs["repairing"] = false
			cond = 1.0
			s.stat_add("repairs", 1.0)
			sim.emit("repair_done", {"facility": fid})
		fs["condition"] = cond
	# Research.
	var office_rate := sim.content.facility_stat("office", "research", sim.facility_level("office"))
	var eng := float(sim.content.role_by_id.get("engineer", {}).get("stats", {}).get("research_per_s", 0.35))
	var rp_rate := (office_rate + sim.crew("office", "engineer") * eng) * sim.mods.m("research_rate")
	s.research_points += rp_rate * dt
	sim.rt["research_rate"] = rp_rate
