class_name TransportSystem
extends RefCounted
## Moving ore: haulage inside each gallery (face pile -> shaft station, by
## haulers and rail carts) and the shaft lift (every station -> surface ore
## silos). The lift runs by itself once an operator is hired for it -
## whether the operator is winding, waiting for ore or on a break (then the
## winder runs at its slower relief pace); without one each "Call lift" runs
## it for one full round trip. Throughput is capacity per trip over the
## round-trip time to the deepest open level, so digging deeper makes the
## lift slower until it is upgraded.


static func haul_rate(sim: Simulation, d: int) -> float:
	var key := "haul%d" % d
	if sim.memo.has(key):
		return sim.memo[key]
	var v := _haul_rate(sim, d)
	sim.memo[key] = v
	return v


static func _haul_rate(sim: Simulation, d: int) -> float:
	var dep := sim.state.depth(d)
	if dep.is_empty() or not dep["unlocked"]:
		return 0.0
	var post := "depth:%d" % d
	var hauler := float(sim.content.role_by_id.get("hauler", {}).get("stats", {}).get("rate", 0.9))
	var sup := sim.crew(post, "supervisor") * float(sim.content.role_by_id.get("supervisor", {}).get("stats", {}).get("area_bonus", 0.15))
	var equiv := sim.crew(post, "hauler") * hauler * (1.0 + sup)
	equiv += sim.content.equipment_stat("haulage", "cart_rate", int(dep["levels"]["haulage"]))
	if equiv <= 0.0:
		return 0.0
	return equiv * Economy.miner_work_rate(sim, d) * sim.mods.m("haul_rate") * sim.boost_mult()


## Haulage the depth can count on (units/s): rail carts plus every hauler
## posted there who is not resting - on the job or still walking to it.
## Miners send that much of their ore to the face pile (so haulers find work
## when they arrive) and carry the rest to the station themselves.
static func haul_capacity(sim: Simulation, d: int) -> float:
	var key := "hcap%d" % d
	if sim.memo.has(key):
		return sim.memo[key]
	var v := 0.0
	var dep := sim.state.depth(d)
	if not dep.is_empty() and dep["unlocked"]:
		var post := "depth:%d" % d
		var hauler := float(sim.content.role_by_id.get("hauler", {}).get("stats", {}).get("rate", 0.9))
		var sup := float(sim.rt.get("posted", {}).get(post, {}).get("supervisor", 0.0)) \
			* float(sim.content.role_by_id.get("supervisor", {}).get("stats", {}).get("area_bonus", 0.15))
		var equiv := float(sim.rt.get("posted", {}).get(post, {}).get("hauler", 0.0)) * hauler * (1.0 + sup)
		equiv += sim.content.equipment_stat("haulage", "cart_rate", int(dep["levels"]["haulage"]))
		if equiv > 0.0:
			v = equiv * Economy.miner_work_rate(sim, d) * sim.mods.m("haul_rate") * sim.boost_mult()
	sim.memo[key] = v
	return v


static func tick_haulage(sim: Simulation, dt: float) -> void:
	var out := {}
	for dep in sim.state.depths:
		if not dep["unlocked"]:
			continue
		var d := int(dep["index"])
		var rate := haul_rate(sim, d)
		var moved := 0.0
		if rate > 0.0:
			var free := maxf(0.0, Economy.station_capacity(sim, d) - Simulation.inv_total(dep["station"]))
			var amount := minf(rate * dt, minf(Simulation.inv_total(dep["face"]), free))
			if amount > 0.0:
				var taken := Simulation.inv_take(dep["face"], amount)
				for k in taken:
					Simulation.inv_add(dep["station"], k, taken[k])
				moved = amount
		out[d] = {"rate": rate, "moved_rate": moved / dt}
	sim.rt["haul"] = out


static func lift_stats(sim: Simulation) -> Dictionary:
	var fs: Dictionary = sim.state.facilities.get("headframe", {})
	var lvl := int(fs.get("level", 1))
	var cond := Economy.condition_factor(sim, float(fs.get("condition", 1.0)))
	var cap := sim.content.facility_stat("headframe", "capacity", lvl) * sim.mods.m("lift_capacity") * cond * sim.boost_mult()
	var speed := maxf(0.1, sim.content.facility_stat("headframe", "speed_mps", lvl) * sim.mods.m("lift_speed"))
	var deepest := maxi(1, sim.state.deepest_unlocked())
	var dist := absf(sim.layout.surface_y - sim.layout.floor_y(deepest))
	var cycle := 2.0 * dist / speed + float(sim.content.bal("lift", "load_s", 2.0)) + float(sim.content.bal("lift", "unload_s", 2.0)) + 0.5 * float(deepest - 1)
	# The operator on a break (or still on the way): the winder keeps going at
	# its relief pace instead of stopping and waiting for the player.
	var relief := lift_automatic(sim) and sim.on_duty("headframe", "operator") <= 0.0
	if relief:
		cycle /= clampf(float(sim.content.bal("lift", "relief_pace", 0.5)), 0.05, 1.0)
	return {"capacity": cap, "speed": speed, "cycle_s": cycle, "rate": cap / cycle, "deepest": deepest, "relief": relief}


## The lift runs by itself while an operator is hired for it.
static func lift_automatic(sim: Simulation) -> bool:
	for w in sim.state.workers:
		if w["post"] == "headframe" and w["role"] == "operator":
			return true
	return false


static func stations_total(sim: Simulation) -> float:
	var t := 0.0
	for dep in sim.state.depths:
		if dep["unlocked"]:
			t += Simulation.inv_total(dep["station"])
	return t


## Ore waits at a station, or arrives as fast as the lift takes it (the
## stations are empty between steps then), and the silo has room.
static func lift_has_work(sim: Simulation) -> bool:
	var flowing := float(sim.rt.get("lift", {}).get("moved_rate", 0.0)) > 0.0
	return (stations_total(sim) > 0.01 or flowing) and Simulation.inv_total(sim.state.surface_bin) < Economy.bin_capacity(sim) - 0.01


static func tick_lift(sim: Simulation, dt: float) -> void:
	var ls := lift_stats(sim)
	var auto := lift_automatic(sim)
	var manual := float(sim.state.lift.get("manual_s", 0.0))
	var running := auto or manual > 0.0
	var moved := 0.0
	if running:
		var avail := stations_total(sim)
		var free := maxf(0.0, Economy.bin_capacity(sim) - Simulation.inv_total(sim.state.surface_bin))
		var amount := minf(float(ls["rate"]) * dt, minf(avail, free))
		if amount > 0.0:
			# The cage serves the most valuable station first (deep ore before shallow).
			var order := []
			for dep in sim.state.depths:
				if dep["unlocked"] and Simulation.inv_total(dep["station"]) > 0.0:
					order.append(dep)
			order.sort_custom(func(a, b):
				var va := _avg_value(sim, a["station"])
				var vb := _avg_value(sim, b["station"])
				return va > vb if va != vb else int(a["index"]) > int(b["index"]))
			var left := amount
			for dep in order:
				if left <= 1e-12:
					break
				var have := Simulation.inv_total(dep["station"])
				var take := Simulation.inv_take(dep["station"], minf(have, left))
				for k in take:
					Simulation.inv_add(sim.state.surface_bin, k, take[k])
					left -= float(take[k])
			moved = amount - maxf(0.0, left)
			sim.state.stat_add("lifted", moved)
			sim.state.lift["moved"] = float(sim.state.lift.get("moved", 0.0)) + moved
	if manual > 0.0:
		sim.state.lift["manual_s"] = maxf(0.0, manual - dt)
	ls["auto"] = auto
	ls["running"] = running
	ls["moved_rate"] = moved / dt
	sim.rt["lift"] = ls


static func _avg_value(sim: Simulation, inv: Dictionary) -> float:
	var total := 0.0
	var value := 0.0
	for k in inv:
		total += float(inv[k])
		value += float(inv[k]) * sim.unit_value(k)
	return value / total if total > 0.0 else 0.0


static func call_lift(sim: Simulation) -> Dictionary:
	if lift_automatic(sim):
		return {"ok": true, "auto": true}
	var ls := lift_stats(sim)
	var max_s := float(ls["cycle_s"]) * float(sim.content.bal("lift", "manual_trips_max", 3))
	var cur := float(sim.state.lift.get("manual_s", 0.0))
	if cur >= max_s - 0.01:
		return {"ok": false, "error": "lift_busy"}
	sim.state.lift["manual_s"] = minf(max_s, cur + float(ls["cycle_s"]))
	sim.emit("lift_called", {"cycle_s": ls["cycle_s"]})
	return {"ok": true, "cycle_s": ls["cycle_s"]}
