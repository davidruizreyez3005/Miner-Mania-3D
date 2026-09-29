class_name UiText
extends RefCounted
## Player-facing names, units and descriptions for simulation values.

const STATS := {
	"capacity": ["Cage load", "units"], "speed_mps": ["Cage speed", "m/s"], "buffer_s": ["Buffer", "s"],
	"throughput": ["Throughput", "/s"], "power_kw": ["Power", "kW"], "truck_capacity": ["Truck load", "units"],
	"trucks": ["Trucks", ""], "trip_s": ["Round trip", "s"], "worker_capacity": ["Camp beds", "workers"],
	"research": ["Research", "RP/s"], "engineer_slots": ["Engineer desks", ""], "repair_mult": ["Repair speed", "x"],
	"mechanic_slots": ["Mechanic bays", ""], "miner_rate": ["Work per miner", "/s"], "miner_slots": ["Miner slots", ""],
	"cart_rate": ["Mine carts", "/s"], "hauler_slots": ["Hauler slots", ""],
}

const JOBS := {
	"mine": "Mining", "haul": "Hauling ore", "operate": "Operating", "repair": "Repairing", "research": "Researching",
	"survey": "Surveying veins", "supervise": "Supervising", "manage": "Managing sales", "idle": "Waiting",
}

const IDLE_REASONS := {"full": "station full - waiting for the lift", "depleted": "veins exhausted - waiting for regrowth"}

const FLAGS := {"auto_sales": "Trucks leave on their own", "machines_self_run": "Machines run at full speed unattended",
	"deep_charter": "Charter for the deepest levels"}

const RARITY_NAMES := {"common": "Common", "uncommon": "Uncommon", "rare": "Rare", "very_rare": "Very rare", "exotic": "Exotic"}

const CATEGORY_ICONS := {"transport": "lift", "storage": "factory", "processing": "factory", "utility": "bolt", "sales": "truck",
	"management": "book", "maintenance": "hammer"}

const ROLE_ICONS := {"miner": "pick", "hauler": "cart", "operator": "gear", "mechanic": "hammer", "engineer": "flask",
	"geologist": "gem", "supervisor": "quest"}


static func stat_name(key: String) -> String:
	return String(STATS.get(key, [key.capitalize(), ""])[0])


static func stat_value(key: String, v: float) -> String:
	var unit := String(STATS.get(key, ["", ""])[1])
	var n := Num.short(v, 2) if absf(v) >= 10.0 or v == floorf(v) else ("%.2f" % v).rstrip("0").trim_suffix(".")
	if unit == "":
		return n
	if unit == "x":
		return "x" + n
	if unit.begins_with("/"):
		return n + unit
	return n + " " + unit


static func location(sim: Simulation, loc: String) -> String:
	var p := loc.split(":")
	match p[0]:
		"depth":
			var name := String(sim.content.depth(int(p[1])).get("name", "Depth %s" % p[1]))
			if p.size() > 2:
				match p[2]:
					"node":
						return "%s, vein %d" % [name, int(p[3]) + 1]
					"station":
						return "%s station" % name
					"rest":
						return "%s rest corner" % name
					"face":
						return "%s rock face" % name
			return name
		"facility":
			return String(sim.content.facility(p[1]).get("name", p[1]))
		"surface":
			return {"rest": "camp rest area", "gate": "the camp gate", "landing": "the shaft collar"}.get(p[1], "the camp")
		"plant":
			return "the processing plant"
	return loc


static func post(sim: Simulation, post: String) -> String:
	var p := post.split(":")
	if p[0] == "depth":
		return String(sim.content.depth(int(p[1])).get("name", post))
	if p[0] == "plant":
		return "Processing plant"
	return String(sim.content.facility(p[0]).get("name", post))


static func worker_status(sim: Simulation, w: Dictionary) -> String:
	if bool(w.get("resting", false)):
		return "Resting at %s" % location(sim, String(w["location"]))
	var job := String(w.get("job", "idle"))
	var txt := String(JOBS.get(job, job.capitalize()))
	if job == "idle" and IDLE_REASONS.has(String(w.get("target", ""))):
		return "Idle - " + String(IDLE_REASONS[String(w["target"])])
	if float(w.get("arrive_at", 0.0)) > sim.state.run_time:
		return "Walking to %s" % location(sim, String(w["location"]))
	return "%s at %s" % [txt, location(sim, String(w["location"]))]


static func effect(sim: Simulation, e: Dictionary) -> String:
	match String(e.get("type", "")):
		"mult":
			var v := float(e.get("value", 1.0))
			return "%s %s%d%%" % [String(e.get("stat", "")).capitalize(), "+" if v >= 1.0 else "", roundi((v - 1.0) * 100.0)]
		"add":
			return "%s +%s" % [String(e.get("stat", "")).capitalize(), Num.short(float(e.get("value", 0.0)))]
		"unlock":
			var w := String(e.get("what", "")).split(":")
			match w[0]:
				"facility":
					return "Unlocks %s" % String(sim.content.facility(w[1]).get("name", w[1]))
				"tool":
					return "Unlocks %s" % String(sim.content.tool_tier(int(w[1])).get("name", "new tools"))
				"role":
					return "Unlocks %s" % String(sim.content.role_by_id.get(w[1], {}).get("plural", w[1]))
				_:
					return "Unlocks %s" % w[w.size() - 1].capitalize()
		"mitigate":
			return "Protects against %s" % String(e.get("hazard", "")).capitalize()
		"flag":
			return String(FLAGS.get(String(e.get("flag", "")), String(e.get("flag", "")).capitalize()))
	return ""


static func reward(sim: Simulation, rw: Dictionary) -> String:
	var parts := []
	if float(rw.get("money", 0.0)) > 0.0:
		parts.append(Num.money(float(rw["money"])))
	if float(rw.get("rp", 0.0)) > 0.0:
		parts.append("%s RP" % Num.short(float(rw["rp"])))
	if rw.has("bonus"):
		var b: Dictionary = rw["bonus"]
		parts.append("%s x%s" % [String(b.get("stat", "")).capitalize(), Num.short(float(b.get("value", 1.0)))])
	if rw.has("cosmetic"):
		parts.append("Outfit: %s" % String(sim.content.cosmetic_by_id.get(String(rw["cosmetic"]), {}).get("name", "")))
	if rw.has("boost"):
		parts.append("Boost")
	return ", ".join(parts)
