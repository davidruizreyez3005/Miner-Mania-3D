class_name ProcessingSystem
extends RefCounted
## The surface plant. The conveyor pulls ore from the silos (hard limit: belt
## throughput and warehouse space) through every built machine in plant order
## (crusher -> washer -> sorter -> smelter -> refinery). Each resource advances
## along its own processing chain while the next machine is built and has
## spare capacity; the share a machine cannot take bypasses it and leaves as
## the product reached so far. Machines therefore never block the belt - they
## decide how much of the flow is refined and so how much it is worth.
## Machines run slower without an operator, when worn, or when the power
## does not reach them (UtilitySystem feeds the belt first, then the line).


static func reachable_steps(sim: Simulation, res_id: String) -> Array:
	var out := []
	for st in sim.content.chains.get(res_id, []):
		if not sim.facility_built(String(st["facility"])):
			break
		out.append(st)
	return out


static func output_item(sim: Simulation, res_id: String) -> String:
	var steps := reachable_steps(sim, res_id)
	return res_id if steps.is_empty() else String(steps[steps.size() - 1]["product"])


static func operator_factor(sim: Simulation, fid: String) -> float:
	if sim.crew(fid, "operator") > 0.0:
		return 1.0
	var fac := sim.content.facility(fid)
	if sim.mods.has_flag("machines_self_run"):
		return 0.75
	return float(fac.get("unoperated_speed", 0.35))


## Units/s the machine can process now. `with_power` false gives its
## full-power capacity (what it would do with all the power it asks for).
static func machine_capacity(sim: Simulation, fid: String, with_power: bool = true) -> float:
	var fs: Dictionary = sim.state.facilities.get(fid, {})
	if not fs.get("built", false):
		return 0.0
	var sup := sim.crew("plant", "supervisor") * float(sim.content.role_by_id.get("supervisor", {}).get("stats", {}).get("area_bonus", 0.15))
	return sim.content.facility_stat(fid, "throughput", int(fs["level"])) * sim.mods.m("processing_rate") \
		* Economy.condition_factor(sim, float(fs["condition"])) * (UtilitySystem.power_factor(sim, fid) if with_power else 1.0) \
		* operator_factor(sim, fid) * (1.0 + sup) * sim.boost_mult()


static func conveyor_rate(sim: Simulation) -> float:
	return sim.content.facility_stat("conveyor", "throughput", sim.facility_level("conveyor")) * sim.mods.m("conveyor_rate") \
		* UtilitySystem.power_factor(sim, "conveyor") * sim.boost_mult()


static func machine_has_work(sim: Simulation, fid: String) -> bool:
	if Simulation.inv_total(sim.state.surface_bin) <= 0.01:
		return false
	for rid in sim.state.surface_bin:
		for st in reachable_steps(sim, rid):
			if st["facility"] == fid:
				return true
	return false


static func tick(sim: Simulation, dt: float) -> void:
	var s := sim.state
	var machines: Array = sim.content.processing_facilities()
	for fid in machines:
		if s.facilities.has(fid):
			s.facilities[fid]["util"] = 0.0
			s.facilities[fid]["need"] = 0.0
	var plant := {"rate": 0.0, "capacity": conveyor_rate(sim), "bottleneck": "", "util": {}, "processed_share": 1.0, "short": ""}
	var total := Simulation.inv_total(s.surface_bin)
	if total <= 1e-9:
		plant["bottleneck"] = "input"
		sim.rt["plant"] = plant
		return
	var free := maxf(0.0, Economy.warehouse_capacity(sim) - Simulation.inv_total(s.warehouse))
	var amount := minf(conveyor_rate(sim) * dt, minf(total, free))
	plant["bottleneck"] = "warehouse" if free <= 0.01 else ("conveyor" if amount >= conveyor_rate(sim) * dt - 1e-9 else "input")
	if amount <= 0.0:
		sim.rt["plant"] = plant
		return
	# Flow through the plant: each resource advances along its chain while the
	# next machine is built and has capacity; overflow bypasses the machine and
	# leaves as the product it has reached so far (never blocks the belt).
	var taken := Simulation.inv_take_priority(s.surface_bin, amount, sim.unit_value)
	var flows := {}          # resource id -> [amount, step index reached]
	var keys := taken.keys()
	keys.sort()
	for rid in keys:
		flows[rid] = [float(taken[rid]), 0]
	var worst := 1.0
	for fid in machines:
		var demand := 0.0
		var waiting := []
		for rid in keys:
			var chain: Array = sim.content.chains.get(rid, [])
			var st := int(flows[rid][1])
			if st < chain.size() and String(chain[st]["facility"]) == fid and sim.facility_built(fid):
				demand += float(flows[rid][0])
				waiting.append(rid)
		if waiting.is_empty():
			continue
		var cap := machine_capacity(sim, fid) * dt
		var frac := clampf(cap / demand, 0.0, 1.0) if demand > 0.0 else 1.0
		if frac < worst:
			worst = frac
			plant["short"] = fid
		# Shares of the full-power capacity: "need" is the work waiting (what
		# the machine asks the power system for - a shortage never inflates
		# its own demand), "util" the work done (wear, load, animation).
		var full := maxf(machine_capacity(sim, fid, false) * dt, 1e-9)
		s.facilities[fid]["need"] = clampf(demand / full, 0.0, 1.0)
		s.facilities[fid]["util"] = clampf(minf(demand, cap) / full, 0.0, 1.0)
		plant["util"][fid] = s.facilities[fid]["util"]
		for rid in waiting:
			var amt := float(flows[rid][0])
			var bypass := amt * (1.0 - frac)
			if bypass > 1e-12:
				var item := _item_at(sim, rid, int(flows[rid][1]))
				Simulation.inv_add(s.warehouse, item, bypass)
				_count(s, rid, item, bypass)
			flows[rid] = [amt * frac, int(flows[rid][1]) + 1]
	for rid in keys:
		var amt2 := float(flows[rid][0])
		if amt2 <= 1e-12:
			continue
		var item2 := _item_at(sim, rid, int(flows[rid][1]))
		Simulation.inv_add(s.warehouse, item2, amt2)
		_count(s, rid, item2, amt2)
	plant["rate"] = amount / dt
	plant["processed_share"] = worst
	sim.rt["plant"] = plant


static func _item_at(sim: Simulation, rid: String, step: int) -> String:
	if step <= 0:
		return rid
	var chain: Array = sim.content.chains.get(rid, [])
	return String(chain[mini(step, chain.size()) - 1]["product"])


static func _count(s: SimState, rid: String, item: String, amount: float) -> void:
	if item != rid:
		s.stat_add("processed." + item, amount)
		s.stat_add("processed_units", amount)
