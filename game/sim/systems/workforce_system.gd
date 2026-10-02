class_name WorkforceSystem
extends RefCounted
## Worker AI at the simulation level. Every job interval each worker's post
## (home assignment) plus the current production needs decide its job:
## miners take free rock faces, haulers only move when there is ore to move,
## operators run machines that have input, mechanics rush to machines that
## need work and otherwise walk their service round (every machine in turn,
## topping it up to full condition, and back to the workshop), and anyone
## with nothing to do idles (or rests when tired). Changing location costs
## real travel time (walking + riding the cage), during which the worker
## produces nothing. Scales linearly with workforce; no per-frame work.

const PRODUCTIVE := ["mine", "haul", "operate", "repair", "service", "research", "survey", "manage", "supervise"]

static var _post_cache: Dictionary = {}


## "depth:3" -> ["depth", 3]; "crusher" -> ["crusher", 0] (cached: posts are few, workers many).
static func parse_post(post: String) -> Array:
	var p = _post_cache.get(post)
	if p == null:
		var parts := post.split(":")
		p = [parts[0], int(parts[1]) if parts.size() > 1 else 0]
		_post_cache[post] = p
	return p


static func efficiency(sim: Simulation, w: Dictionary) -> float:
	var bonus := float(sim.content.workers_cfg.get("level_bonus", 0.06))
	return (1.0 + bonus * float(int(w["level"]) - 1)) * sim.mods.m("worker_efficiency")


static func on_job(sim: Simulation, w: Dictionary) -> bool:
	return String(w["job"]) in PRODUCTIVE and not w["resting"] and sim.state.run_time >= float(w["arrive_at"]) - 1e-6


## Sums each post's on-the-job efficiency. With `dt` > 0 a worker who arrives
## part-way through the coming step is credited for the fraction of the step
## after arrival, so coarse (offline) steps integrate travel time exactly.
static func update_crews(sim: Simulation, dt: float = 0.0) -> void:
	var crew := {}
	var repair := {}
	var t := sim.state.run_time
	for w in sim.state.workers:
		if not String(w["job"]) in PRODUCTIVE or w["resting"]:
			continue
		var arrive := float(w["arrive_at"])
		var frac := 1.0
		if t < arrive - 1e-6:
			if dt <= 0.0:
				continue
			frac = clampf((t + dt - arrive) / dt, 0.0, 1.0)
			if frac <= 0.0:
				continue
		var e := efficiency(sim, w) * frac
		var post := String(w["post"])
		if not crew.has(post):
			crew[post] = {}
		crew[post][w["role"]] = float(crew[post].get(w["role"], 0.0)) + e
		if w["job"] == "repair" or w["job"] == "service":
			repair[w["target"]] = float(repair.get(w["target"], 0.0)) + e
	sim.rt["crew"] = crew
	sim.rt["repair_crew"] = repair


static func tick(sim: Simulation, dt: float) -> void:
	var cfg: Dictionary = sim.content.workers_cfg
	var en: Dictionary = cfg.get("energy", {})
	var drain := float(en.get("work_drain_per_s", 0.004)) * sim.mods.m("fatigue")
	var rec := float(en.get("rest_recover_per_s", 0.05))
	var xp_lvl := float(cfg.get("xp_per_level_s", 600.0))
	var max_lvl := int(cfg.get("max_level", 10))
	var t := sim.state.run_time
	for w in sim.state.workers:
		var arrived := t >= float(w["arrive_at"])
		if w["resting"]:
			if arrived:
				w["energy"] = minf(1.0, float(w["energy"]) + rec * dt)
				if float(w["energy"]) >= 1.0:
					w["resting"] = false
					sim.rt["jobs_dirty"] = true
		elif String(w["job"]) in PRODUCTIVE and arrived:
			w["energy"] = float(w["energy"]) - drain * dt
			w["xp"] = float(w["xp"]) + dt * sim.mods.m("xp_rate")
			var lvl := mini(max_lvl, 1 + int(floorf(sqrt(float(w["xp"]) / xp_lvl))))
			if lvl > int(w["level"]):
				w["level"] = lvl
				sim.emit("worker_level", {"worker": w["id"], "level": lvl})
			if float(w["energy"]) <= 0.0:
				w["energy"] = 0.0
				w["resting"] = true
				sim.rt["jobs_dirty"] = true
				_apply(sim, w, ["rest", "", rest_location(sim, w)])
	update_crews(sim, dt)


static func rest_location(sim: Simulation, w: Dictionary) -> String:
	var pp := parse_post(String(w["post"]))
	if pp[0] == "depth":
		var d: int = pp[1]
		if sim.state.depth(d).get("unlocked", false):
			return "depth:%d:rest" % d
	return "surface:rest"


## Machines that need a mechanic now (below the service mark, or flagged
## worn), most worn first.
static func repair_queue(sim: Simulation) -> Array:
	var service_at := float(sim.content.bal("condition", "service_at", 0.97))
	var q := []
	var ids := sim.state.facilities.keys()
	ids.sort()
	for fid in ids:
		var fs: Dictionary = sim.state.facilities[fid]
		var fac := sim.content.facility(fid)
		if fs.get("built", false) and fac.get("repairable", false) and (float(fs["condition"]) < service_at or fs.get("repairing", false)):
			q.append(fid)
	q.sort_custom(func(a, b):
		var ca := float(sim.state.facilities[a]["condition"])
		var cb := float(sim.state.facilities[b]["condition"])
		return ca < cb if ca != cb else String(a) < String(b))
	return q


## The mechanics' service round: the workshop (parts), then every built
## machine that wears, in camp order.
static func service_stops(sim: Simulation) -> Array:
	var out := []
	if sim.facility_built("workshop"):
		out.append("workshop")
	for fac in sim.content.facilities:
		if fac.get("repairable", false) and sim.facility_built(String(fac["id"])):
			out.append(String(fac["id"]))
	return out


## Where a mechanic works on `fid`: the machine's repair spot, or the bench.
static func service_location(fid: String) -> String:
	return "facility:workshop" if fid == "workshop" else "facility:%s:repair" % fid


## A service stop is done once the mechanic has spent the service time
## there and the machine is back in full condition.
static func stop_done(sim: Simulation, w: Dictionary) -> bool:
	if sim.state.run_time < float(w["arrive_at"]) + float(sim.content.bal("condition", "service_s", 6.0)):
		return false
	return _serviced(sim, String(w["target"]))


## True when `fid` needs nothing more (full condition, or not a machine).
static func _serviced(sim: Simulation, fid: String) -> bool:
	if not sim.content.facility(fid).get("repairable", false):
		return true
	return float(sim.state.facilities.get(fid, {}).get("condition", 1.0)) >= float(sim.content.bal("condition", "repaired_at", 0.999))


## A mechanic's job in hand is finished: the repaired machine is back in
## full condition, or the service stop is done.
static func _mechanic_done(sim: Simulation, w: Dictionary) -> bool:
	match String(w["job"]):
		"repair":
			return _serviced(sim, String(w["target"]))
		"service":
			return stop_done(sim, w)
	return true


static func _round_due(sim: Simulation) -> bool:
	for w in sim.state.workers:
		if w["role"] == "mechanic" and not w["resting"] and (w["job"] == "repair" or w["job"] == "service") and _mechanic_done(sim, w):
			return true
	return false


## Re-decides every worker's job. Skipped when nothing that influences a
## decision changed since the last pass (steady state) and no mechanic has
## finished a stop of the service round, unless forced.
static func assign_jobs(sim: Simulation, force: bool = false) -> void:
	var queue := repair_queue(sim)
	var ctx := _context(sim)
	var sig := _signature(sim, ctx, queue)
	if not force and not sim.rt.get("jobs_dirty", true) and sim.rt.get("job_sig", "") == sig and not _round_due(sim):
		return
	sim.rt["job_sig"] = sig
	sim.rt["jobs_dirty"] = false
	var taken := {"_ctx": ctx, "_claims": _mechanic_claims(sim)}
	var miner_index := {}
	# Miners keep their vein while it stays active; displaced miners go to the
	# least crowded active vein (ties: lowest slot). Few walks when a vein
	# collapses - on screen and in the travel-time accounting.
	var load := {}
	for w in sim.state.workers:
		if w["role"] == "miner" and w["job"] == "mine" and not w["resting"]:
			var key := String(w["location"])
			load[key] = int(load.get(key, 0)) + 1
	taken["_load"] = load
	for w in sim.state.workers:
		var job: Array
		if w["resting"]:
			job = ["rest", "", rest_location(sim, w)]
		else:
			job = desired_job(sim, w, queue, taken, miner_index)
		_apply(sim, w, job)


static func _signature(sim: Simulation, ctx: Dictionary, queue: Array) -> String:
	var parts := PackedStringArray([str(sim.state.workers.size()), str(ctx["lift_work"]), str(ctx["research"]), ",".join(PackedStringArray(queue))])
	for d in ctx["depth"]:
		var dc: Dictionary = ctx["depth"][d]
		parts.append("%d%s%s%s" % [d, dc["space"], dc["haul"], str(dc["active"])])
	for fid in ctx["machine"]:
		parts.append(fid + str(ctx["machine"][fid]))
	return "|".join(parts)


## Facts every worker's decision needs, computed once per assignment pass.
static func _context(sim: Simulation) -> Dictionary:
	var ctx := {"depth": {}, "lift_work": TransportSystem.lift_has_work(sim), "research": ProgressionSystem.research_remaining(sim), "machine": {}}
	for dep in sim.state.depths:
		if not dep["unlocked"]:
			continue
		var d := int(dep["index"])
		var nodes := {}
		for slot in MiningSystem.active_slots(dep):
			nodes[slot] = ["node:%d" % slot, "depth:%d:node:%d" % [d, slot]]
		ctx["depth"][d] = {
			"space": MiningSystem.has_space(sim, d),
			"active": MiningSystem.active_slots(dep),
			"nodes": nodes,
			"haul": Simulation.inv_total(dep["face"]) > 0.01 and Simulation.inv_total(dep["station"]) < Economy.station_capacity(sim, d) - 0.01,
			"rest": "depth:%d:rest" % d, "face": "depth:%d:face" % d, "station": "depth:%d:station" % d, "tag": "depth:%d" % d,
		}
	for fid in sim.content.processing_facilities():
		ctx["machine"][fid] = sim.facility_built(fid) and ProcessingSystem.machine_has_work(sim, fid)
	return ctx


static func desired_job(sim: Simulation, w: Dictionary, queue: Array, taken: Dictionary, miner_index: Dictionary) -> Array:
	var s := sim.state
	if not taken.has("_ctx"):
		taken["_ctx"] = _context(sim)
	var ctx: Dictionary = taken["_ctx"]
	var post := String(w["post"])
	var pp := parse_post(post)
	var role := String(w["role"])
	if pp[0] == "depth":
		var d: int = pp[1]
		var dep := s.depth(d)
		if dep.is_empty() or not dep["unlocked"]:
			return ["idle", "", "surface:rest"]
		var dc: Dictionary = ctx["depth"].get(d, {})
		var rest: String = dc.get("rest", "surface:rest")
		match role:
			"miner":
				if not dc.get("space", false):
					return ["idle", "full", rest]
				var active: Array = dc.get("active", [])
				if active.is_empty():
					return ["idle", "depleted", rest]
				var nodes: Dictionary = dc["nodes"]
				if w["job"] == "mine" and String(w["location"]).begins_with(dc["tag"] + ":node:"):
					var cur := int(String(w["location"]).get_slice(":", 3))
					if nodes.has(cur):
						return ["mine", nodes[cur][0], nodes[cur][1]]
				var loads: Dictionary = taken["_load"]
				var best := -1
				var best_n := 1 << 30
				for slot in active:
					var n: int = loads.get(nodes[slot][1], 0)
					if n < best_n:
						best_n = n
						best = int(slot)
				loads[nodes[best][1]] = best_n + 1
				return ["mine", nodes[best][0], nodes[best][1]]
			"hauler":
				if dc.get("haul", false):
					return ["haul", dc["tag"], dc["face"]]
				return ["idle", "", rest]
			"geologist":
				return ["survey", dc["tag"], dc["face"]]
			"supervisor":
				return ["supervise", dc["tag"], dc["station"]]
		return ["idle", "", rest]
	match role:
		"operator":
			if post == "headframe":
				if ctx["lift_work"]:
					return ["operate", "headframe", "facility:headframe"]
				return ["idle", "headframe", "facility:headframe"]
			if not sim.facility_built(post):
				return ["idle", "", "surface:rest"]
			if ctx["machine"].get(post, false):
				return ["operate", post, "facility:" + post]
			return ["idle", post, "facility:" + post]
		"mechanic":
			return _mechanic_job(sim, w, queue, taken)
		"engineer":
			if ctx["research"]:
				return ["research", "office", "facility:office"]
			return ["idle", "", "facility:office"]
		"supervisor":
			if post == "office":
				return ["manage", "office", "facility:office"]
			if post == "plant":
				return ["supervise", "plant", "plant"]
	return ["idle", "", "surface:rest"]


## What each mechanic is busy with and keeps until it is finished: a
## repair (until the machine is back in full condition) or a service stop.
## Claimed before anyone is assigned, so mechanics never swap machines with
## each other mid-job.
static func _mechanic_claims(sim: Simulation) -> Dictionary:
	var claims := {}
	for w in sim.state.workers:
		if w["role"] != "mechanic" or w["resting"] or not (w["job"] == "repair" or w["job"] == "service"):
			continue
		var fid := String(w["target"])
		if not claims.has(fid) and not _mechanic_done(sim, w):
			claims[fid] = int(w["id"])
	return claims


## Mechanics: finish the job in hand, rush to a machine that needs work and
## has nobody on it, else walk on to the next stop of the service round.
static func _mechanic_job(sim: Simulation, w: Dictionary, queue: Array, taken: Dictionary) -> Array:
	var claims: Dictionary = taken.get_or_add("_claims", {})
	var me := int(w["id"])
	var cur := String(w["target"])
	var mine := int(claims.get(cur, -1)) == me
	if mine and (w["job"] == "repair" or cur in queue):
		return ["repair", cur, service_location(cur)]
	for fid in queue:
		if not claims.has(String(fid)):
			if mine:
				claims.erase(cur)
			claims[String(fid)] = me
			return ["repair", fid, service_location(String(fid))]
	if mine:
		return ["service", cur, service_location(cur)]
	var stops := service_stops(sim)
	if stops.is_empty():
		return ["idle", "", "surface:rest"]
	var n := stops.size()
	var i := stops.find(cur)
	var start := (i + 1) % n if i >= 0 else me % n
	for k in n:
		var st := String(stops[(start + k) % n])
		if not claims.has(st):
			claims[st] = me
			return ["service", st, service_location(st)]
	return ["service", String(stops[start]), service_location(String(stops[start]))]


static func _apply(sim: Simulation, w: Dictionary, job: Array) -> void:
	if w["job"] == job[0] and w["target"] == job[1] and w["location"] == job[2]:
		return
	var from := String(w["location"])
	w["job"] = job[0]
	w["target"] = job[1]
	if String(job[2]) != from:
		w["arrive_at"] = sim.state.run_time + sim.layout.travel_time(from, String(job[2]))
		w["location"] = job[2]
