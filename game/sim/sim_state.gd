class_name SimState
extends RefCounted
## The complete mutable state of one save: the current claim (run) plus
## everything that survives prestige. Pure data - no engine nodes - so it can
## be simulated, serialised and tested headlessly. Only Simulation (through
## its systems and commands) mutates it.

const VERSION := 3

# ---- identity / time
var seed: int = 1
var rng_state: Array = []            # DetRng state for run-level rolls (contracts)
var run_time: float = 0.0            # seconds simulated in this claim
var total_time: float = 0.0          # seconds simulated across all claims
var tick_count: int = 0

# ---- economy
var money: float = 0.0
var research_points: float = 0.0
var region: String = "timberline_valley"

# ---- world
var depths: Array = []               # Array[Dictionary] (see new_depth)
var facilities: Dictionary = {}      # id -> {built, level, condition, util}
var surface_bin: Dictionary = {}     # resource id -> units (ore silos)
var warehouse: Dictionary = {}       # item id -> units (finished goods)
var lift: Dictionary = {"manual_s": 0.0, "moved": 0.0}
var sales: Dictionary = {"manual_s": 0.0, "sold": 0.0}

# ---- people
var workers: Array = []              # Array[Dictionary] (see new_worker)
var next_worker_id: int = 1

# ---- progression (current claim)
var techs: Dictionary = {}           # id -> true
var quests: Dictionary = {}          # id -> "active" | "done" | "claimed"
var contract: Dictionary = {}        # active delivery contract
var run_stats: Dictionary = {}       # counters for this claim
var boosts: Dictionary = {"rally_until": 0.0, "rally_ready_at": 0.0}
var income_buckets: Array = []       # money earned per second, last N seconds
var income_bucket_t: float = 0.0
var timers: Dictionary = {"job": 0.0, "objective": 0.0}   # system cadence (saved so a loaded game evolves identically)
var sold_ema: Dictionary = {}        # item -> units/s sold (moving average; sizes contracts)

# ---- persistent across prestige
var life_stats: Dictionary = {}
var achievements: Dictionary = {}    # id -> total_time when unlocked
var bonuses: Dictionary = {}         # stat -> multiplier (achievement rewards)
var discoveries: Dictionary = {}     # resource id -> {depth, time, count}
var prestige: Dictionary = {"count": 0, "lp": 0, "lp_total": 0, "upgrades": {}, "best_run": 0.0}
var cosmetics: Dictionary = {"unlocked": {}, "equipped": {}}
var meta: Dictionary = {"tutorial_step": 0, "tutorial_done": false, "created_unix": 0, "last_save_unix": 0,
	"max_seen_unix": 0, "offline_claimed_unix": 0, "play_s": 0.0}


static func new_depth(index: int) -> Dictionary:
	return {"index": index, "unlocked": false, "levels": {"mining": 1, "haulage": 1, "station": 1}, "tool_tier": 1,
		"face": {}, "station": {}, "nodes": [], "manual_queue": 0.0}


static func new_node(slot: int, resource: String, hp: float) -> Dictionary:
	return {"slot": slot, "resource": resource, "hp": hp, "max_hp": hp, "respawns": 0, "respawn_at": -1.0}


static func new_worker(id: int, role: String, post: String, variant: String, name: String, t: float) -> Dictionary:
	return {"id": id, "role": role, "post": post, "variant": variant, "name": name, "level": 1, "xp": 0.0,
		"energy": 1.0, "job": "idle", "target": "", "location": "", "arrive_at": t, "hired_at": t, "resting": false}


static func new_facility(built: bool) -> Dictionary:
	return {"built": built, "level": 1, "condition": 1.0, "util": 0.0}


func depth(index: int) -> Dictionary:
	if index < 1 or index > depths.size():
		return {}
	return depths[index - 1]


func deepest_unlocked() -> int:
	var d := 0
	for dep in depths:
		if dep["unlocked"]:
			d = int(dep["index"])
	return d


func stat_add(key: String, amount: float) -> void:
	run_stats[key] = float(run_stats.get(key, 0.0)) + amount
	life_stats[key] = float(life_stats.get(key, 0.0)) + amount


func stat_max(key: String, value: float) -> void:
	run_stats[key] = maxf(float(run_stats.get(key, 0.0)), value)
	life_stats[key] = maxf(float(life_stats.get(key, 0.0)), value)


# ------------------------------------------------------------ serialisation

func to_dict() -> Dictionary:
	return {
		"seed": seed, "rng_state": rng_state.duplicate(), "run_time": run_time, "total_time": total_time,
		"tick_count": tick_count,
		"economy": {"money": money, "research_points": research_points, "region": region},
		"world": {"depths": depths.duplicate(true), "facilities": facilities.duplicate(true),
			"surface_bin": surface_bin.duplicate(), "warehouse": warehouse.duplicate(),
			"lift": lift.duplicate(), "sales": sales.duplicate()},
		"workers": {"list": workers.duplicate(true), "next_id": next_worker_id},
		"progress": {"techs": techs.duplicate(), "quests": quests.duplicate(), "contract": contract.duplicate(true),
			"run_stats": run_stats.duplicate(), "boosts": boosts.duplicate(),
			"income_buckets": income_buckets.duplicate(), "income_bucket_t": income_bucket_t,
			"timers": timers.duplicate(), "sold_ema": sold_ema.duplicate()},
		"legacy": {"life_stats": life_stats.duplicate(), "achievements": achievements.duplicate(),
			"bonuses": bonuses.duplicate(), "discoveries": discoveries.duplicate(true),
			"prestige": prestige.duplicate(true), "cosmetics": cosmetics.duplicate(true)},
		"meta": meta.duplicate(),
	}


static func from_dict(d: Dictionary) -> SimState:
	var s := SimState.new()
	s.seed = int(d.get("seed", 1))
	s.rng_state = (d.get("rng_state", []) as Array).duplicate()
	s.run_time = float(d.get("run_time", 0.0))
	s.total_time = float(d.get("total_time", 0.0))
	s.tick_count = int(d.get("tick_count", 0))
	var eco: Dictionary = d.get("economy", {})
	s.money = float(eco.get("money", 0.0))
	s.research_points = float(eco.get("research_points", 0.0))
	s.region = String(eco.get("region", "timberline_valley"))
	var w: Dictionary = d.get("world", {})
	s.depths = _int_keys_fix((w.get("depths", []) as Array).duplicate(true))
	s.facilities = (w.get("facilities", {}) as Dictionary).duplicate(true)
	s.surface_bin = _floats((w.get("surface_bin", {}) as Dictionary))
	s.warehouse = _floats((w.get("warehouse", {}) as Dictionary))
	s.lift = (w.get("lift", {"manual_s": 0.0, "moved": 0.0}) as Dictionary).duplicate()
	s.sales = (w.get("sales", {"manual_s": 0.0, "sold": 0.0}) as Dictionary).duplicate()
	var wk: Dictionary = d.get("workers", {})
	s.workers = (wk.get("list", []) as Array).duplicate(true)
	for worker in s.workers:
		worker["id"] = int(worker.get("id", 0))
		worker["level"] = int(worker.get("level", 1))
	s.next_worker_id = int(wk.get("next_id", s.workers.size() + 1))
	var p: Dictionary = d.get("progress", {})
	s.techs = (p.get("techs", {}) as Dictionary).duplicate()
	s.quests = (p.get("quests", {}) as Dictionary).duplicate()
	s.contract = (p.get("contract", {}) as Dictionary).duplicate(true)
	s.run_stats = _floats(p.get("run_stats", {}))
	s.boosts = (p.get("boosts", {"rally_until": 0.0, "rally_ready_at": 0.0}) as Dictionary).duplicate()
	s.income_buckets = (p.get("income_buckets", []) as Array).duplicate()
	s.income_bucket_t = float(p.get("income_bucket_t", 0.0))
	s.timers = _floats(p.get("timers", {"job": 0.0, "objective": 0.0}))
	s.sold_ema = _floats(p.get("sold_ema", {}))
	var lg: Dictionary = d.get("legacy", {})
	s.life_stats = _floats(lg.get("life_stats", {}))
	s.achievements = (lg.get("achievements", {}) as Dictionary).duplicate()
	s.bonuses = _floats(lg.get("bonuses", {}))
	s.discoveries = (lg.get("discoveries", {}) as Dictionary).duplicate(true)
	var pr: Dictionary = lg.get("prestige", {})
	s.prestige = {"count": int(pr.get("count", 0)), "lp": int(pr.get("lp", 0)), "lp_total": int(pr.get("lp_total", 0)),
		"upgrades": (pr.get("upgrades", {}) as Dictionary).duplicate(), "best_run": float(pr.get("best_run", 0.0))}
	for k in s.prestige["upgrades"]:
		s.prestige["upgrades"][k] = int(s.prestige["upgrades"][k])
	s.cosmetics = (lg.get("cosmetics", {"unlocked": {}, "equipped": {}}) as Dictionary).duplicate(true)
	var m: Dictionary = d.get("meta", {})
	for k in s.meta:
		if m.has(k):
			s.meta[k] = m[k]
	s.meta["tutorial_step"] = int(s.meta["tutorial_step"])
	for k in ["created_unix", "last_save_unix", "max_seen_unix", "offline_claimed_unix"]:
		s.meta[k] = int(s.meta[k])
	return s


static func _floats(src: Dictionary) -> Dictionary:
	var out := {}
	for k in src:
		out[String(k)] = float(src[k])
	return out


## JSON turns every number into a float; restore the integer fields.
static func _int_keys_fix(depths_in: Array) -> Array:
	for dep in depths_in:
		dep["index"] = int(dep.get("index", 0))
		dep["tool_tier"] = int(dep.get("tool_tier", 1))
		var lv: Dictionary = dep.get("levels", {})
		for k in lv:
			lv[k] = int(lv[k])
		dep["face"] = _floats(dep.get("face", {}))
		dep["station"] = _floats(dep.get("station", {}))
		for n in dep.get("nodes", []):
			n["slot"] = int(n.get("slot", 0))
			n["respawns"] = int(n.get("respawns", 0))
			n["hp"] = float(n.get("hp", 0.0))
			n["max_hp"] = float(n.get("max_hp", 1.0))
			n["respawn_at"] = float(n.get("respawn_at", -1.0))
	return depths_in
