class_name MiningSystem
extends RefCounted
## Extraction at every unlocked depth. Miners' work is shared by the active
## ore veins (nodes); each vein has a work budget (hp). A depleted vein
## collapses and, after a respawn delay, a new vein is rolled from the
## depth's weighted resource table with a deterministic RNG stream keyed by
## depth, slot and respawn count - so discoveries do not depend on the tick
## size. Output goes to the face pile when haulage exists, otherwise miners
## carry it to the shaft station themselves at reduced efficiency. Veins are
## stepped with sub-tick timing so coarse offline steps stay accurate.


static func roll_node(sim: Simulation, d: int, slot: int, respawns: int) -> Dictionary:
	var ddef := sim.content.depth(d)
	var rng := DetRng.from_key(sim.state.seed, "node:%d:%d:%d" % [d, slot, respawns])
	var rare: Array = sim.content.bal("discovery", "rare_rarities", [])
	var geo := sim.crew("depth:%d" % d, "geologist") * float(sim.content.role_by_id.get("geologist", {}).get("stats", {}).get("rare_bonus", 0.6))
	var disc := sim.mods.m("discovery_chance") * (1.0 + geo)
	var weights := {}
	var table: Dictionary = ddef.get("resources", {})
	for rid in table:
		var res: Dictionary = sim.content.resource_by_id.get(rid, {})
		if int(res.get("requires_prestige", 0)) > int(sim.state.prestige.get("count", 0)):
			continue
		var wgt := float(table[rid])
		if String(res.get("rarity", "")) in rare:
			wgt *= disc
		weights[rid] = wgt
	if weights.is_empty():
		weights = {String(table.keys()[0]): 1.0}
	var rid2 := rng.weighted_key(weights)
	var hp := float(ddef.get("node_hp", 60.0)) * rng.range_f(0.8, 1.25) * maxf(1.0, Economy.miner_work_rate(sim, d))
	var node := SimState.new_node(slot, rid2, hp)
	node["respawns"] = respawns
	_record_discovery(sim, rid2, d)
	return node


static func _record_discovery(sim: Simulation, rid: String, d: int) -> void:
	var disc := sim.state.discoveries
	var res: Dictionary = sim.content.resource_by_id.get(rid, {})
	if not disc.has(rid):
		disc[rid] = {"depth": d, "time": sim.state.total_time, "count": 1}
		sim.state.stat_add("discoveries", 1.0)
		sim.emit("discovery", {"resource": rid, "depth": d, "rarity": res.get("rarity", "common"), "first": true})
	else:
		disc[rid]["count"] = int(disc[rid].get("count", 0)) + 1
		if String(res.get("rarity", "")) in sim.content.bal("discovery", "rare_rarities", []):
			sim.emit("rare_vein", {"resource": rid, "depth": d, "rarity": res.get("rarity", "")})


static func active_slots(dep: Dictionary) -> Array:
	var out := []
	for n in dep["nodes"]:
		if float(n["respawn_at"]) < 0.0:
			out.append(int(n["slot"]))
	return out


static func respawn_s(sim: Simulation, d: int) -> float:
	var base := float(sim.content.bal("discovery", "respawn_s", 6.0))
	var geo := sim.crew("depth:%d" % d, "geologist") * float(sim.content.role_by_id.get("geologist", {}).get("stats", {}).get("regen_bonus", 0.35))
	return base / ((1.0 + geo) * sim.mods.m("node_regen"))


## Room for the miners' ore: at the face pile while there is haulage, or
## at the shaft station (they carry it there themselves).
static func has_space(sim: Simulation, d: int) -> bool:
	var dep := sim.state.depth(d)
	if TransportSystem.haul_capacity(sim, d) > 0.0 and Simulation.inv_total(dep["face"]) < Economy.face_capacity(sim, d) - 0.01:
		return true
	return Simulation.inv_total(dep["station"]) < Economy.station_capacity(sim, d) - 0.01


static func hazard_factor(sim: Simulation, d: int) -> float:
	return float(sim.rt.get("hazard", {}).get(d, 1.0))


static func tick(sim: Simulation, dt: float) -> void:
	var depth_rt := {}
	for dep in sim.state.depths:
		if dep["unlocked"]:
			depth_rt[int(dep["index"])] = _tick_depth(sim, dep, dt)
	sim.rt["depth"] = depth_rt


static func _tick_depth(sim: Simulation, dep: Dictionary, dt: float) -> Dictionary:
	var d := int(dep["index"])
	var post := "depth:%d" % d
	var t0 := sim.state.run_time
	var sup := sim.crew(post, "supervisor") * float(sim.content.role_by_id.get("supervisor", {}).get("stats", {}).get("area_bonus", 0.15))
	var rate := Economy.miner_work_rate(sim, d) * sim.crew(post, "miner") * hazard_factor(sim, d) * (1.0 + sup) * sim.boost_mult()
	# Haulers and carts take what they can from the face; the miners carry
	# the rest to the station themselves, slower (never less than without
	# haulage), and also whatever the face pile has no room for.
	var self_haul := float(sim.content.bal("face", "self_haul_factor", 0.55))
	var face_rate := minf(rate, TransportSystem.haul_capacity(sim, d))
	var face_space := maxf(0.0, Economy.face_capacity(sim, d) - Simulation.inv_total(dep["face"]))
	var p1 := _mine_pass(sim, dep, face_rate, dt, t0, dep["face"], face_space)
	# Work the full face pile turned away goes to the station by hand too.
	var unplaced := maxf(0.0, face_rate - float(p1[1]) / dt) if float(p1[2]) <= 0.01 else 0.0
	var self_rate := (rate - face_rate + unplaced) * self_haul
	var st_space := maxf(0.0, Economy.station_capacity(sim, d) - Simulation.inv_total(dep["station"]))
	var p2 := _mine_pass(sim, dep, self_rate, dt, t0, dep["station"], st_space)
	var produced := float(p1[0]) + float(p2[0])
	# Stalled: the miners' ore has nowhere to go (station full, and the face
	# full or no haulage) - the lift is the bottleneck.
	var stalled := rate > 0.0 and st_space <= 0.01 and (face_rate <= 0.0 or face_space <= 0.01)
	return {"work_rate": face_rate + self_rate, "units_rate": produced / dt, "to_face": face_rate > 0.0,
		"space": face_space + st_space, "stalled": stalled}


## Mines every active vein at `rate` (work/s, shared) into `target` with
## `space` room; returns [units placed, work done, room left]. Depleted veins
## regrow on schedule even when nobody mines (rate 0).
static func _mine_pass(sim: Simulation, dep: Dictionary, rate: float, dt: float, t0: float, target: Dictionary, space: float) -> Array:
	var r_node := maxf(rate, 0.0) / float(maxi(1, active_slots(dep).size()))
	var produced := 0.0
	var work := 0.0
	var nodes: Array = dep["nodes"]
	for i in nodes.size():
		var res := _mine_node(sim, dep, i, r_node, dt, t0, target, space)
		space = res[0]
		produced += res[1]
		work += res[2]
	return [produced, work, space]


## Mines one vein for `dt` (handling depletion and respawn inside the step).
## Returns [remaining space, units produced, work done].
static func _mine_node(sim: Simulation, dep: Dictionary, i: int, r_node: float, dt: float, t0: float, target: Dictionary, space: float) -> Array:
	var d := int(dep["index"])
	var node: Dictionary = dep["nodes"][i]
	var produced := 0.0
	var done := 0.0
	var tl := 0.0
	var guard := 0
	while tl < dt - 1e-9 and guard < 64:
		guard += 1
		if float(node["respawn_at"]) >= 0.0:
			var ready := float(node["respawn_at"])
			if ready > t0 + dt:
				break
			tl = maxf(tl, ready - t0)
			node = roll_node(sim, d, int(node["slot"]), int(node["respawns"]) + 1)
			dep["nodes"][i] = node
			sim.emit("node_respawned", {"depth": d, "slot": node["slot"], "resource": node["resource"]})
			continue
		if r_node <= 0.0 or space <= 1e-9:
			break
		var res: Dictionary = sim.content.resource_by_id.get(node["resource"], {})
		var diff := float(res.get("extraction_difficulty", 1.0))
		var pm := float(res.get("production_modifier", 1.0))
		var work_possible := r_node * (dt - tl)
		var work_space := space * diff / pm
		var work := minf(work_possible, minf(float(node["hp"]), work_space))
		var units := work / diff * pm
		Simulation.inv_add(target, String(node["resource"]), units)
		sim.state.stat_add("mined." + String(node["resource"]), units)
		sim.state.stat_add("mined_units", units)
		space -= units
		produced += units
		done += work
		node["hp"] = float(node["hp"]) - work
		tl += work / r_node
		if float(node["hp"]) <= 1e-6:
			node["hp"] = 0.0
			node["respawn_at"] = t0 + tl + respawn_s(sim, d)
			sim.emit("node_depleted", {"depth": d, "slot": node["slot"], "resource": node["resource"]})
		elif work < work_possible - 1e-9:
			break
	return [space, produced, done]


## One swing of the foreman's pick at a vein. Returns units mined.
static func manual_swing(sim: Simulation, d: int, slot: int) -> Dictionary:
	var dep := sim.state.depth(d)
	if dep.is_empty() or not dep["unlocked"]:
		return {"ok": false, "error": "depth_locked"}
	var idx := -1
	for i in dep["nodes"].size():
		if int(dep["nodes"][i]["slot"]) == slot:
			idx = i
	if idx < 0:
		return {"ok": false, "error": "no_node"}
	var node: Dictionary = dep["nodes"][idx]
	if float(node["respawn_at"]) >= 0.0:
		return {"ok": false, "error": "node_depleted"}
	var cap := Economy.station_capacity(sim, d)
	var space := maxf(0.0, cap - Simulation.inv_total(dep["station"]))
	if space <= 1e-6:
		return {"ok": false, "error": "station_full"}
	var lvl := int(dep["levels"]["mining"])
	var scale := sim.content.equipment_stat("mining", "miner_rate", lvl) / maxf(1e-9, sim.content.equipment_stat("mining", "miner_rate", 1))
	var work := float(sim.content.bal("manual", "swing_yield", 1.0)) * sim.mods.m("manual_yield") * scale * sim.boost_mult()
	var res: Dictionary = sim.content.resource_by_id.get(node["resource"], {})
	var diff := float(res.get("extraction_difficulty", 1.0))
	var pm := float(res.get("production_modifier", 1.0))
	work = minf(work, float(node["hp"]))
	var units := minf(work / diff * pm, space)
	work = units * diff / pm
	Simulation.inv_add(dep["station"], String(node["resource"]), units)
	node["hp"] = float(node["hp"]) - work
	sim.state.stat_add("manual_units", units)
	sim.state.stat_add("manual_swings", 1.0)
	sim.state.stat_add("mined." + String(node["resource"]), units)
	sim.state.stat_add("mined_units", units)
	if float(node["hp"]) <= 1e-6:
		node["hp"] = 0.0
		node["respawn_at"] = sim.state.run_time + respawn_s(sim, d)
		sim.emit("node_depleted", {"depth": d, "slot": slot, "resource": node["resource"]})
	sim.emit("manual_mined", {"depth": d, "slot": slot, "resource": node["resource"], "units": units})
	return {"ok": true, "units": units, "resource": node["resource"]}
