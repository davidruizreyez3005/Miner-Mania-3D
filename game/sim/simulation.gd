class_name Simulation
extends RefCounted
## Deterministic mine simulation, independent of rendering.
##
## tick(dt) advances the economy by a fixed step in a fixed system order:
##   workforce -> utilities (power, pumps, hazards) -> mining -> haulage ->
##   lift -> processing -> sales -> maintenance/research -> progression.
## Player intent enters only through execute(command) (see SimCommands), so
## the same state + the same command sequence always yields the same result.
## Presentation reads `state` and the runtime metrics in `rt`, and drains
## `events`. The same tick() drives online play (0.1 s steps) and offline
## catch-up (coarse steps), so idle earnings are real simulation.

const TICK_ORDER := ["workforce", "utilities", "mining", "haulage", "lift", "processing", "sales", "maintenance", "progression"]

var content: ContentDB
var state: SimState
var layout: WorldLayout
var mods: Modifiers = Modifiers.new()
var events: Array = []
var rt: Dictionary = {}
var offline_mode: bool = false
var memo: Dictionary = {}              # per-tick memo of derived rates/capacities (cleared every tick and command)
var _mods_dirty: bool = true


func _init(db: ContentDB, st: SimState = null) -> void:
	content = db
	layout = WorldLayout.new(db)
	if st == null:
		new_game(int(db.bal("start", "seed", 1)))
	else:
		state = st
		invalidate_modifiers()
		_refresh_modifiers()
		_ensure_structure()
		WorkforceSystem.update_crews(self)


# ----------------------------------------------------------------- lifecycle

func new_game(seed_value: int, keep: SimState = null) -> void:
	var s := SimState.new()
	s.seed = seed_value
	s.rng_state = DetRng.new(seed_value).get_state()
	s.region = String(content.bal("start", "region", "timberline_valley"))
	if keep != null:
		s.life_stats = keep.life_stats
		s.achievements = keep.achievements
		s.bonuses = keep.bonuses
		s.discoveries = keep.discoveries
		s.prestige = keep.prestige
		s.cosmetics = keep.cosmetics
		s.meta = keep.meta
		s.total_time = keep.total_time
	state = s
	_ensure_structure()
	invalidate_modifiers()
	_refresh_modifiers()
	state.money = float(content.bal("start", "money", 0.0)) + _legacy_start_money()
	unlock_depth_internal(1)
	for d in _legacy_start_depths():
		unlock_depth_internal(d)
	for c in content.cosmetics:
		if c.get("default", false):
			state.cosmetics["unlocked"][c["id"]] = true
			if not state.cosmetics["equipped"].has(c["kind"]):
				state.cosmetics["equipped"][c["kind"]] = c["id"]
	ProgressionSystem.refresh_quests(self)
	_start_workers()
	WorkforceSystem.update_crews(self)


## Makes sure every content entry has state (new content in an old save).
func _ensure_structure() -> void:
	for i in range(state.depths.size(), content.depth_count()):
		state.depths.append(SimState.new_depth(i + 1))
	for fac in content.facilities:
		var fid := String(fac["id"])
		if not state.facilities.has(fid):
			state.facilities[fid] = SimState.new_facility(bool(fac.get("prebuilt", false)))
		elif bool(fac.get("prebuilt", false)):
			state.facilities[fid]["built"] = true
	for dep in state.depths:
		if dep["unlocked"]:
			var slots := int(content.depth(int(dep["index"])).get("node_slots", 3))
			while dep["nodes"].size() < slots:
				dep["nodes"].append(MiningSystem.roll_node(self, int(dep["index"]), dep["nodes"].size(), 0))


func _legacy_level(uid: String) -> int:
	return int(state.prestige.get("upgrades", {}).get(uid, 0))


func _legacy_effect(uid: String, type: String) -> Dictionary:
	for e in content.legacy_by_id.get(uid, {}).get("effects", []):
		if e.get("type", "") == type:
			return e
	return {}


func _legacy_start_money() -> float:
	var lvl := _legacy_level("seed_capital")
	if lvl <= 0:
		return 0.0
	var e := _legacy_effect("seed_capital", "start_money")
	var arr: Array = e.get("per_level", [])
	return float(arr[mini(lvl, arr.size()) - 1]) if not arr.is_empty() else 0.0


func _legacy_start_depths() -> Array:
	var lvl := _legacy_level("head_start")
	var out := []
	if lvl <= 0:
		return out
	var e := _legacy_effect("head_start", "start_depths")
	var arr: Array = e.get("per_level", [])
	var n := int(arr[mini(lvl, arr.size()) - 1]) if not arr.is_empty() else 1
	for d in range(2, mini(n, content.depth_count()) + 1):
		out.append(d)
	return out


func _start_workers() -> void:
	if _legacy_level("automation_blueprints") <= 0:
		return
	var e := _legacy_effect("automation_blueprints", "start_workers")
	for w in e.get("workers", []):
		add_worker(String(w["role"]), String(w["post"]))


# ---------------------------------------------------------------- modifiers

func invalidate_modifiers() -> void:
	_mods_dirty = true


func _refresh_modifiers() -> void:
	if _mods_dirty:
		mods.rebuild(state, content)
		_mods_dirty = false


func rally_active() -> bool:
	return state.run_time < float(state.boosts.get("rally_until", 0.0))


func boost_mult() -> float:
	return float(content.bal("rally", "mult", 2.0)) if rally_active() else 1.0


# --------------------------------------------------------------------- tick

func tick(dt: float) -> void:
	if dt <= 0.0:
		return
	memo.clear()
	_refresh_modifiers()
	state.tick_count += 1
	var job_iv := float(content.bal("sim", "job_interval_s", 1.0))
	state.timers["job"] = float(state.timers.get("job", 0.0)) - dt
	if float(state.timers["job"]) <= 0.0:
		state.timers["job"] = maxf(float(state.timers["job"]) + job_iv, 0.0)
		if float(state.timers["job"]) <= 0.0:
			state.timers["job"] = job_iv
		WorkforceSystem.assign_jobs(self)
	WorkforceSystem.tick(self, dt)
	UtilitySystem.tick(self, dt)
	MiningSystem.tick(self, dt)
	TransportSystem.tick_haulage(self, dt)
	TransportSystem.tick_lift(self, dt)
	ProcessingSystem.tick(self, dt)
	SalesSystem.tick(self, dt)
	UtilitySystem.tick_maintenance(self, dt)
	state.run_time += dt
	state.total_time += dt
	state.timers["objective"] = float(state.timers.get("objective", 0.0)) - dt
	if float(state.timers["objective"]) <= 0.0:
		state.timers["objective"] = float(content.bal("sim", "objective_interval_s", 0.5))
		ProgressionSystem.tick(self)
	_refresh_modifiers()


## Advances `seconds` of game time in steps of at most `step` seconds.
func advance(seconds: float, step: float) -> void:
	var left := seconds
	while left > 1e-9:
		var dt := minf(step, left)
		tick(dt)
		left -= dt


func execute(cmd: Dictionary) -> Dictionary:
	memo.clear()
	_refresh_modifiers()
	var result := SimCommands.run(self, cmd)
	if result.get("ok", false):
		rt["jobs_dirty"] = true
	memo.clear()
	_refresh_modifiers()
	return result


func emit(type: String, data: Dictionary = {}) -> void:
	if offline_mode and type in ["node_depleted", "node_respawned", "repair_done", "truck_trip", "power_short"]:
		return
	var ev := data.duplicate()
	ev["type"] = type
	ev["t"] = state.run_time
	events.append(ev)
	if events.size() > 512:
		events.remove_at(0)


func drain_events() -> Array:
	var out := events
	events = []
	return out


# ------------------------------------------------------------ world helpers

func unlock_depth_internal(d: int) -> void:
	var dep := state.depth(d)
	if dep.is_empty() or dep["unlocked"]:
		return
	dep["unlocked"] = true
	dep["nodes"] = []
	var slots := int(content.depth(d).get("node_slots", 3))
	for i in slots:
		dep["nodes"].append(MiningSystem.roll_node(self, d, i, 0))
	emit("depth_unlocked", {"depth": d})


func add_worker(role_id: String, post: String) -> Dictionary:
	var id := state.next_worker_id
	state.next_worker_id += 1
	var variants: Array = content.role_variants(role_id)
	var variant := String(variants[(id + variants.size() - 1) % variants.size()]) if not variants.is_empty() else ""
	var w := SimState.new_worker(id, role_id, post, variant, worker_name(id), state.run_time)
	w["location"] = "surface:gate"
	state.workers.append(w)
	return w


func worker_name(id: int) -> String:
	var names: Dictionary = content.workers_cfg.get("names", {})
	var rng := DetRng.from_key(state.seed, "name:%d" % id)
	var first: Array = names.get("first", ["Sam"])
	var last: Array = names.get("last", ["Stone"])
	var nick: Array = names.get("nicknames", [])
	var n := String(first[rng.range_i(0, first.size() - 1)])
	if not nick.is_empty() and rng.next_float() < 0.35:
		n += " \"%s\"" % nick[rng.range_i(0, nick.size() - 1)]
	return n + " " + String(last[rng.range_i(0, last.size() - 1)])


func worker_by_id(id: int) -> Dictionary:
	for w in state.workers:
		if int(w["id"]) == id:
			return w
	return {}


func workers_at(post: String, role_id: String = "") -> Array:
	var out := []
	for w in state.workers:
		if w["post"] == post and (role_id == "" or w["role"] == role_id):
			out.append(w)
	return out


func crew(post: String, role_id: String) -> float:
	return float(rt.get("crew", {}).get(post, {}).get(role_id, 0.0))


func facility_built(fid: String) -> bool:
	return bool(state.facilities.get(fid, {}).get("built", false))


func facility_level(fid: String) -> int:
	return int(state.facilities.get(fid, {}).get("level", 1))


func automation_stage() -> int:
	return int(rt.get("stage", 0))


# ------------------------------------------------------------- inventories

static func inv_total(inv: Dictionary) -> float:
	var t := 0.0
	for k in inv:
		t += float(inv[k])
	return t


static func inv_add(inv: Dictionary, id: String, amount: float) -> void:
	if amount <= 0.0:
		return
	inv[id] = float(inv.get(id, 0.0)) + amount


## Removes `amount` spread proportionally over the contents; returns {id: taken}.
static func inv_take(inv: Dictionary, amount: float) -> Dictionary:
	var out := {}
	var total := inv_total(inv)
	if total <= 0.0 or amount <= 0.0:
		return out
	var frac := minf(1.0, amount / total)
	var keys := inv.keys()
	keys.sort()
	for k in keys:
		var have := float(inv[k])
		var take := have * frac
		if take > 0.0:
			out[k] = take
			var left := have - take
			if left <= 1e-9:
				inv.erase(k)
			else:
				inv[k] = left
	return out


## Removes up to `amount`, most valuable items first (ties by id); returns {id: taken}.
static func inv_take_priority(inv: Dictionary, amount: float, value_of: Callable) -> Dictionary:
	var out := {}
	if amount <= 0.0:
		return out
	var pairs := []
	for k in inv:
		pairs.append([float(value_of.call(k)), String(k)])
	pairs.sort_custom(func(a, b): return a[0] > b[0] if a[0] != b[0] else a[1] < b[1])
	var left := amount
	for pr in pairs:
		var k: String = pr[1]
		if left <= 1e-12:
			break
		var have := float(inv[k])
		var take := minf(have, left)
		if take <= 0.0:
			continue
		out[k] = take
		left -= take
		if have - take <= 1e-9:
			inv.erase(k)
		else:
			inv[k] = have - take
	return out


## Unit value of an inventory item (for priority ordering).
func unit_value(item_id: String) -> float:
	return float(content.item(item_id).get("value", 0.0))

