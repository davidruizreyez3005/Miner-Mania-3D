class_name ContentDB
extends RefCounted
## Loads every data file under res://data, indexes it and validates it.
##
## All gameplay content is data: resources, depths, facilities, worker roles,
## technologies, quests, achievements, legacy upgrades, regions, cosmetics,
## balance constants, the tutorial and the world layout/modules. Adding a new
## resource, machine or quest never requires engine code changes. validate()
## reports duplicate ids, missing references, invalid costs, dependency cycles
## and (when an asset manifest is supplied) missing assets.

const DATA_DIR := "res://data"
const FILES := {
	"resources": "resources.json", "depths": "depths.json", "facilities": "facilities.json",
	"workers": "workers.json", "technologies": "technologies.json", "quests": "quests.json",
	"achievements": "achievements.json", "legacy": "legacy.json", "regions": "regions.json",
	"cosmetics": "cosmetics.json", "balance": "balance.json", "tutorial": "tutorial.json",
	"layout": "world/layout.json", "modules": "world/modules.json",
}
const OBJECTIVE_TYPES := ["stat", "money", "workers", "roles", "depth_unlocked", "facility_built", "facilities_built",
	"facility_level", "equipment_level", "tool_tier", "tech", "techs", "discovered", "discoveries", "income",
	"prestige", "automation", "quests"]
const MODIFIER_STATS := ["mining_rate", "haul_rate", "lift_capacity", "lift_speed", "processing_rate", "conveyor_rate",
	"sales_rate", "truck_capacity", "sale_value", "research_rate", "repair_rate", "wear_rate", "power_supply",
	"pump_capacity", "worker_efficiency", "discovery_chance", "node_regen", "offline_efficiency",
	"offline_efficiency_mult", "offline_cap_h", "hire_cost", "upgrade_cost", "storage_capacity", "manual_yield",
	"fatigue", "xp_rate"]

var raw: Dictionary = {}
var load_errors: Array = []

var resources: Array = []
var resource_by_id: Dictionary = {}
var rarities: Dictionary = {}
var items: Dictionary = {}            # item id -> {id, name, resource, step, value, facility}
var chains: Dictionary = {}           # resource id -> Array of step dicts
var depths: Array = []
var hazards: Dictionary = {}
var level_spacing: float = 12.0
var first_floor_y: float = -10.0
var facilities: Array = []
var facility_by_id: Dictionary = {}
var default_milestones: Array = []
var equipment: Dictionary = {}
var tool_tiers: Array = []
var workers_cfg: Dictionary = {}
var roles: Array = []
var role_by_id: Dictionary = {}
var techs: Array = []
var tech_by_id: Dictionary = {}
var quests: Array = []
var quest_by_id: Dictionary = {}
var contracts_cfg: Dictionary = {}
var achievements: Array = []
var achievement_by_id: Dictionary = {}
var legacy_cfg: Dictionary = {}
var legacy_upgrades: Array = []
var legacy_by_id: Dictionary = {}
var regions: Array = []
var region_by_id: Dictionary = {}
var resource_classes: Dictionary = {}
var class_of: Dictionary = {}          # resource id -> class (derived)
var cosmetics: Array = []
var cosmetic_by_id: Dictionary = {}
var balance: Dictionary = {}
var tutorial: Array = []
var layout: Dictionary = {}
var modules: Dictionary = {}


static func load_default() -> ContentDB:
	var db := ContentDB.new()
	db.load_dir(DATA_DIR)
	return db


func load_dir(dir: String) -> void:
	load_errors.clear()
	for key in FILES:
		var data = JsonUtil.load_file(dir.path_join(FILES[key]), load_errors)
		raw[key] = data if data is Dictionary else {}
	_index()


func load_from_dicts(data: Dictionary) -> void:
	load_errors.clear()
	for key in FILES:
		raw[key] = data.get(key, {})
	_index()


func _index() -> void:
	var r: Dictionary = raw["resources"]
	rarities = r.get("rarities", {})
	resources = r.get("resources", [])
	resource_by_id = _by_id(resources)
	items.clear()
	chains.clear()
	for res in resources:
		var rid := String(res.get("id", ""))
		var value := float(res.get("value", 0.0))
		items[rid] = {"id": rid, "name": res.get("name", rid), "resource": rid, "step": 0, "value": value, "facility": ""}
		var steps: Array = res.get("processing", [])
		chains[rid] = steps
		var v := value
		var i := 0
		for st in steps:
			i += 1
			v *= float(st.get("value_mult", 1.0))
			var pid := String(st.get("product", ""))
			items[pid] = {"id": pid, "name": st.get("name", pid), "resource": rid, "step": i, "value": v,
				"facility": String(st.get("facility", ""))}
	var d: Dictionary = raw["depths"]
	depths = d.get("depths", [])
	hazards = d.get("hazards", {})
	level_spacing = float(d.get("level_spacing_m", 12.0))
	first_floor_y = float(d.get("first_floor_y_m", -10.0))
	var f: Dictionary = raw["facilities"]
	facilities = f.get("facilities", [])
	facility_by_id = _by_id(facilities)
	default_milestones = f.get("milestones_default", [])
	equipment = f.get("depth_equipment", {})
	tool_tiers = equipment.get("tools", {}).get("tiers", [])
	workers_cfg = raw["workers"]
	roles = workers_cfg.get("roles", [])
	role_by_id = _by_id(roles)
	techs = raw["technologies"].get("technologies", [])
	tech_by_id = _by_id(techs)
	quests = raw["quests"].get("quests", [])
	quest_by_id = _by_id(quests)
	contracts_cfg = raw["quests"].get("contracts", {})
	achievements = raw["achievements"].get("achievements", [])
	achievement_by_id = _by_id(achievements)
	legacy_cfg = raw["legacy"]
	legacy_upgrades = legacy_cfg.get("upgrades", [])
	legacy_by_id = _by_id(legacy_upgrades)
	regions = raw["regions"].get("regions", [])
	region_by_id = _by_id(regions)
	resource_classes = raw["regions"].get("resource_classes", {})
	class_of.clear()
	for cls in resource_classes:
		for rid in resource_classes[cls]:
			class_of[String(rid)] = String(cls)
	cosmetics = raw["cosmetics"].get("cosmetics", [])
	cosmetic_by_id = _by_id(cosmetics)
	balance = raw["balance"]
	tutorial = raw["tutorial"].get("steps", [])
	layout = raw["layout"]
	modules = raw["modules"]


static func _by_id(arr: Array) -> Dictionary:
	var out := {}
	for e in arr:
		if e is Dictionary and e.has("id"):
			out[String(e["id"])] = e
	return out


# ----------------------------------------------------------------- accessors

func bal(section: String, key: String, default: Variant = null) -> Variant:
	return balance.get(section, {}).get(key, default)


func depth_count() -> int:
	return depths.size()


func depth(index: int) -> Dictionary:
	if index < 1 or index > depths.size():
		return {}
	return depths[index - 1]


func depth_floor_y(index: int) -> float:
	return first_floor_y - level_spacing * float(index - 1)


func facility(id: String) -> Dictionary:
	return facility_by_id.get(id, {})


func facility_stat(id: String, stat_name: String, level: int) -> float:
	var fac := facility(id)
	var spec: Dictionary = fac.get("stats", {}).get(stat_name, {})
	if spec.is_empty():
		return 0.0
	return Curves.stat(spec, level, default_milestones)


func equipment_stat(kind: String, stat_name: String, level: int) -> float:
	var spec: Dictionary = equipment.get(kind, {}).get("stats", {}).get(stat_name, {})
	if spec.is_empty():
		return 0.0
	return Curves.stat(spec, level, default_milestones)


func tool_tier(tier: int) -> Dictionary:
	for t in tool_tiers:
		if int(t.get("tier", 0)) == tier:
			return t
	return {}


func processing_facilities() -> Array:
	var out := []
	for fac in facilities:
		if fac.get("category", "") == "processing":
			out.append(String(fac["id"]))
	return out


func item(id: String) -> Dictionary:
	return items.get(id, {})


func resource_class(res_id: String) -> String:
	return class_of.get(res_id, "")


func role_variants(role_id: String) -> Array:
	return role_by_id.get(role_id, {}).get("variants", [])


func tech_unlocks(what: String) -> String:
	## Returns the id of the technology whose effects unlock `what` ("facility:crusher", "tool:2", ...).
	for t in techs:
		for e in t.get("effects", []):
			if e.get("type", "") == "unlock" and String(e.get("what", "")) == what:
				return String(t["id"])
	return ""


func all_asset_ids() -> Array:
	## Every generated asset id the game references (for manifest cross-checks and APK verification).
	var out := []
	for res in resources:
		_add_unique(out, res.get("node_asset", ""))
	for fac in facilities:
		_add_unique(out, fac.get("asset", ""))
	for t in tool_tiers:
		_add_unique(out, t.get("tool_asset", ""))
		_add_unique(out, t.get("machine_asset", ""))
	for role in roles:
		for v in role.get("variants", []):
			_add_unique(out, v)
	for c in cosmetics:
		_add_unique(out, c.get("asset", ""))
	for reg in regions:
		for v in reg.get("look", {}).get("vegetation", []):
			_add_unique(out, v)
	for m in modules.get("modules", []):
		_add_unique(out, m.get("asset", ""))
	return out


static func _add_unique(arr: Array, v: Variant) -> void:
	var s := String(v) if v != null else ""
	if s != "" and not s in arr:
		arr.append(s)


# ---------------------------------------------------------------- validation

## Returns a list of human-readable problems (empty = valid). When
## `manifest_ids` is non-empty every referenced asset must be in it.
func validate(manifest_ids: Array = []) -> Array:
	var e: Array = load_errors.duplicate()
	for key in ["resources", "depths", "facilities", "workers", "technologies", "quests", "achievements", "legacy",
			"regions", "cosmetics", "balance"]:
		if (raw.get(key, {}) as Dictionary).is_empty():
			e.append("data/%s is missing or empty" % FILES[key])
	_check_ids("resource", resources, e)
	_check_ids("facility", facilities, e)
	_check_ids("role", roles, e)
	_check_ids("technology", techs, e)
	_check_ids("quest", quests, e)
	_check_ids("achievement", achievements, e)
	_check_ids("legacy upgrade", legacy_upgrades, e)
	_check_ids("region", regions, e)
	_check_ids("cosmetic", cosmetics, e)
	_validate_resources(e)
	_validate_depths(e)
	_validate_facilities(e)
	_validate_roles(e)
	_validate_techs(e)
	_validate_objectives("quest", quests, e)
	_validate_objectives("achievement", achievements, e)
	_validate_quest_graph(e)
	_validate_legacy(e)
	_validate_regions_cosmetics(e)
	_validate_balance(e)
	if not manifest_ids.is_empty():
		for aid in all_asset_ids():
			if not aid in manifest_ids:
				e.append("asset '%s' is referenced by game data but missing from the asset manifest" % aid)
	return e


func _check_ids(kind: String, arr: Array, e: Array) -> void:
	var seen := {}
	var id_re := RegEx.create_from_string("^[a-z][a-z0-9_]*$")
	for entry in arr:
		if not entry is Dictionary or not entry.has("id"):
			e.append("%s entry without id" % kind)
			continue
		var id := String(entry["id"])
		if seen.has(id):
			e.append("duplicate %s id '%s'" % [kind, id])
		seen[id] = true
		if id_re.search(id) == null:
			e.append("%s id '%s' is not snake_case" % [kind, id])


func _bad_number(v: Variant) -> bool:
	if not (v is float or v is int):
		return true
	var f := float(v)
	return is_nan(f) or is_inf(f)


func _check_cost(where: String, spec: Variant, e: Array, allow_zero: bool = false) -> void:
	if not spec is Dictionary:
		e.append("%s: cost spec missing" % where)
		return
	var base = spec.get("base", null)
	var growth = spec.get("growth", null)
	if _bad_number(base) or float(base) < 0.0 or (not allow_zero and float(base) <= 0.0):
		e.append("%s: invalid cost base %s" % [where, str(base)])
	if _bad_number(growth) or float(growth) < 1.0 or float(growth) > 5.0:
		e.append("%s: invalid cost growth %s (must be 1..5)" % [where, str(growth)])


func _check_stat(where: String, spec: Variant, e: Array) -> void:
	if not spec is Dictionary:
		e.append("%s: stat spec missing" % where)
		return
	if _bad_number(spec.get("base", null)):
		e.append("%s: stat base invalid" % where)
	var mode := String(spec.get("mode", "mult"))
	if not mode in ["mult", "add", "exp"]:
		e.append("%s: unknown stat mode '%s'" % [where, mode])
	if mode == "exp" and (float(spec.get("growth", 0.0)) < 1.0 or float(spec.get("growth", 0.0)) > 1.5):
		e.append("%s: exp stat growth must be in [1, 1.5]" % where)
	var ms = spec.get("milestones", [])
	if ms is Array:
		var last := 0
		for m in ms:
			if not m is Array or m.size() != 2 or int(m[0]) <= last or float(m[1]) <= 0.0:
				e.append("%s: invalid milestone %s" % [where, str(m)])
			else:
				last = int(m[0])
	elif not (ms is String and ms == "default"):
		e.append("%s: milestones must be a list or \"default\"" % where)
	var sv := Curves.stat(spec, 1, default_milestones)
	var sv2 := Curves.stat(spec, 200, default_milestones)
	if is_nan(sv) or is_nan(sv2) or sv < 0.0 or sv2 < sv - 1e-9:
		e.append("%s: stat curve must be non-negative and non-decreasing" % where)


func _validate_resources(e: Array) -> void:
	for rid in rarities:
		if not String(rarities[rid].get("color", "")).begins_with("#"):
			e.append("rarity '%s' needs a #color" % rid)
	var product_ids := {}
	for res in resources:
		var rid := String(res.get("id", "?"))
		if not rarities.has(res.get("rarity", "")):
			e.append("resource '%s' has unknown rarity '%s'" % [rid, res.get("rarity", "")])
		if _bad_number(res.get("value")) or float(res.get("value", 0)) <= 0.0:
			e.append("resource '%s' needs a positive value" % rid)
		if _bad_number(res.get("extraction_difficulty")) or float(res.get("extraction_difficulty", 0)) < 0.5:
			e.append("resource '%s' extraction_difficulty must be >= 0.5" % rid)
		var ud := int(res.get("unlock_depth", 0))
		if ud < 1 or ud > depths.size():
			e.append("resource '%s' unlock_depth %d out of range" % [rid, ud])
		if String(res.get("node_asset", "")) == "":
			e.append("resource '%s' has no node_asset" % rid)
		if not String(res.get("color", "")).begins_with("#"):
			e.append("resource '%s' needs a #color" % rid)
		var mk: Dictionary = res.get("market", {})
		if float(mk.get("amplitude", 0.0)) < 0.0 or float(mk.get("amplitude", 0.0)) > 0.5 or float(mk.get("period_s", 0.0)) <= 0.0:
			e.append("resource '%s' has an invalid market spec" % rid)
		var seen_fac := {}
		for st in res.get("processing", []):
			var fid := String(st.get("facility", ""))
			var fac := facility(fid)
			if fac.is_empty() or fac.get("category", "") != "processing":
				e.append("resource '%s' processing step uses unknown processing facility '%s'" % [rid, fid])
			if seen_fac.has(fid):
				e.append("resource '%s' uses facility '%s' twice" % [rid, fid])
			seen_fac[fid] = true
			var pid := String(st.get("product", ""))
			if pid == "" or product_ids.has(pid) or resource_by_id.has(pid):
				e.append("resource '%s' has a missing or duplicate product id '%s'" % [rid, pid])
			product_ids[pid] = true
			if float(st.get("value_mult", 0.0)) < 1.0:
				e.append("resource '%s' product '%s' value_mult must be >= 1" % [rid, pid])
		# Chain steps must follow the plant's physical order (crusher -> washer -> sorter -> smelter -> refinery).
		var order := processing_facilities()
		var last := -1
		for st in res.get("processing", []):
			var idx := order.find(String(st.get("facility", "")))
			if idx <= last:
				e.append("resource '%s' processing steps are out of plant order" % rid)
				break
			last = idx


func _validate_depths(e: Array) -> void:
	var last_cost := -1.0
	for i in depths.size():
		var d: Dictionary = depths[i]
		var idx := int(d.get("index", 0))
		if idx != i + 1:
			e.append("depth #%d has index %d (must be contiguous from 1)" % [i + 1, idx])
		var cost := float(d.get("unlock_cost", -1))
		if cost < 0.0 or (i > 0 and cost <= last_cost):
			e.append("depth %d unlock_cost must increase with depth" % idx)
		last_cost = cost
		if float(d.get("cost_scale", 0.0)) <= 0.0:
			e.append("depth %d needs a positive cost_scale" % idx)
		var slots := int(d.get("node_slots", 0))
		if slots < 1 or slots > 8:
			e.append("depth %d node_slots must be 1..8" % idx)
		var res_w: Dictionary = d.get("resources", {})
		if res_w.is_empty():
			e.append("depth %d has no resources" % idx)
		for rid in res_w:
			var res: Dictionary = resource_by_id.get(rid, {})
			if res.is_empty():
				e.append("depth %d references unknown resource '%s'" % [idx, rid])
			elif int(res.get("unlock_depth", 99)) > idx:
				e.append("depth %d lists '%s' before its unlock_depth" % [idx, rid])
			if float(res_w[rid]) <= 0.0:
				e.append("depth %d resource '%s' weight must be positive" % [idx, rid])
		for hz in d.get("hazards", []):
			if not hazards.has(hz):
				e.append("depth %d references unknown hazard '%s'" % [idx, hz])
	for hz in hazards:
		var mit: Dictionary = hazards[hz].get("mitigation", {})
		if mit.has("tech") and not tech_by_id.has(mit["tech"]):
			e.append("hazard '%s' mitigation references unknown tech '%s'" % [hz, mit["tech"]])
		if mit.has("tech"):
			var found := false
			for eff in tech_by_id.get(mit["tech"], {}).get("effects", []):
				if eff.get("type", "") == "mitigate" and eff.get("hazard", "") == hz:
					found = true
			if not found:
				e.append("hazard '%s': tech '%s' has no matching mitigate effect" % [hz, mit["tech"]])
		if mit.has("facility_capacity") and facility(mit["facility_capacity"]).is_empty():
			e.append("hazard '%s' mitigation references unknown facility" % hz)
		var pen := float(hazards[hz].get("penalty", -1))
		if pen <= 0.0 or pen >= 1.0:
			e.append("hazard '%s' penalty must be in (0, 1)" % hz)


func _validate_facilities(e: Array) -> void:
	for fac in facilities:
		var fid := String(fac.get("id", "?"))
		_check_cost("facility '%s'" % fid, fac.get("cost"), e)
		if float(fac.get("build_cost", -1)) < 0.0:
			e.append("facility '%s' build_cost must be >= 0" % fid)
		if int(fac.get("max_level", 0)) < 1:
			e.append("facility '%s' max_level must be >= 1" % fid)
		if String(fac.get("asset", "")) == "" or String(fac.get("plot", "")) == "":
			e.append("facility '%s' needs an asset and a plot" % fid)
		for s in fac.get("stats", {}):
			_check_stat("facility '%s' stat '%s'" % [fid, s], fac["stats"][s], e)
		var req: Dictionary = fac.get("requires", {})
		if req.has("tech"):
			var tid := String(req["tech"])
			if not tech_by_id.has(tid):
				e.append("facility '%s' requires unknown tech '%s'" % [fid, tid])
			elif tech_unlocks("facility:" + fid) != tid:
				e.append("facility '%s' requires tech '%s' but that tech does not unlock it" % [fid, tid])
		if fac.get("prebuilt", false) and not req.is_empty():
			e.append("facility '%s' is prebuilt but has requirements" % fid)
	for kind in ["mining", "haulage", "station"]:
		var eq: Dictionary = equipment.get(kind, {})
		if eq.is_empty():
			e.append("depth equipment '%s' missing" % kind)
			continue
		_check_cost("equipment '%s'" % kind, eq.get("cost"), e)
		for s in eq.get("stats", {}):
			_check_stat("equipment '%s' stat '%s'" % [kind, s], eq["stats"][s], e)
	var last_mult := 0.0
	for i in tool_tiers.size():
		var t: Dictionary = tool_tiers[i]
		if int(t.get("tier", 0)) != i + 1:
			e.append("tool tiers must be numbered 1..N")
		if float(t.get("mult", 0.0)) <= last_mult:
			e.append("tool tier %d multiplier must increase" % (i + 1))
		last_mult = float(t.get("mult", 0.0))
		var rt := String(t.get("requires_tech", ""))
		if i > 0 and (rt == "" or tech_unlocks("tool:%d" % (i + 1)) != rt):
			e.append("tool tier %d must be unlocked by its requires_tech '%s'" % [i + 1, rt])
		if String(t.get("tool_asset", "")) == "":
			e.append("tool tier %d needs a tool_asset" % (i + 1))
	var tech_for_carts := String(equipment.get("haulage", {}).get("requires_tech_above_level", {}).get("1", ""))
	if tech_for_carts != "" and not tech_by_id.has(tech_for_carts):
		e.append("haulage requires unknown tech '%s'" % tech_for_carts)


func _validate_roles(e: Array) -> void:
	for role in roles:
		var rid := String(role.get("id", "?"))
		_check_cost("role '%s'" % rid, {"base": role.get("base_cost"), "growth": role.get("growth")}, e)
		if (role.get("variants", []) as Array).is_empty():
			e.append("role '%s' has no character variants" % rid)
		for p in role.get("posts", []):
			if not workers_cfg.get("post_limits", {}).has(p):
				e.append("role '%s' post '%s' has no post limit" % [rid, p])
		var un: Dictionary = role.get("unlock", {})
		if un.has("quest") and not quest_by_id.has(un["quest"]):
			e.append("role '%s' unlock references unknown quest '%s'" % [rid, un["quest"]])
		if un.has("tech") and not tech_by_id.has(un["tech"]):
			e.append("role '%s' unlock references unknown tech '%s'" % [rid, un["tech"]])
		if un.has("facility") and facility(un["facility"]).is_empty():
			e.append("role '%s' unlock references unknown facility '%s'" % [rid, un["facility"]])
	for post in workers_cfg.get("post_limits", {}):
		var lim: Dictionary = workers_cfg["post_limits"][post]
		for role_id in lim:
			if not role_by_id.has(role_id):
				e.append("post '%s' limits unknown role '%s'" % [post, role_id])
			var v = lim[role_id]
			if v is String:
				var parts := String(v).split(".")
				var ok: bool = parts.size() == 2 and (
					(equipment.has(parts[0]) and equipment[parts[0]].get("stats", {}).has(parts[1])) or
					(facility_by_id.has(parts[0]) and facility_by_id[parts[0]].get("stats", {}).has(parts[1])))
				if not ok:
					e.append("post '%s' limit '%s' does not name a stat" % [post, v])


func _validate_techs(e: Array) -> void:
	for t in techs:
		var tid := String(t.get("id", "?"))
		if float(t.get("rp", -1)) < 0.0 or _bad_number(t.get("rp")) or float(t.get("cost", -1)) < 0.0:
			e.append("tech '%s' has invalid costs" % tid)
		for req in t.get("requires", []):
			if not tech_by_id.has(req):
				e.append("tech '%s' requires unknown tech '%s'" % [tid, req])
			elif int(tech_by_id[req].get("tier", 0)) >= int(t.get("tier", 0)):
				e.append("tech '%s' requires '%s' from the same or a later tier" % [tid, req])
		for eff in t.get("effects", []):
			_validate_effect("tech '%s'" % tid, eff, e)
	# Cycle detection (DFS).
	var state := {}
	for t in techs:
		if _tech_cycle(String(t["id"]), state):
			e.append("technology dependency cycle through '%s'" % t["id"])
			break


func _tech_cycle(id: String, state: Dictionary) -> bool:
	if state.get(id, 0) == 1:
		return true
	if state.get(id, 0) == 2:
		return false
	state[id] = 1
	for req in tech_by_id.get(id, {}).get("requires", []):
		if tech_by_id.has(req) and _tech_cycle(String(req), state):
			return true
	state[id] = 2
	return false


func _validate_effect(where: String, eff: Dictionary, e: Array) -> void:
	match String(eff.get("type", "")):
		"mult", "add":
			if not String(eff.get("stat", "")) in MODIFIER_STATS:
				e.append("%s: unknown modifier stat '%s'" % [where, eff.get("stat", "")])
			if _bad_number(eff.get("value")):
				e.append("%s: effect value invalid" % where)
			elif String(eff["type"]) == "mult" and float(eff["value"]) <= 0.0:
				e.append("%s: mult effect must be positive" % where)
		"unlock":
			var what := String(eff.get("what", ""))
			var parts := what.split(":")
			if parts.size() != 2:
				e.append("%s: unlock '%s' malformed" % [where, what])
			elif parts[0] == "facility" and facility(parts[1]).is_empty():
				e.append("%s: unlocks unknown facility '%s'" % [where, parts[1]])
			elif parts[0] == "tool" and tool_tier(int(parts[1])).is_empty():
				e.append("%s: unlocks unknown tool tier '%s'" % [where, parts[1]])
			elif parts[0] == "role" and not role_by_id.has(parts[1]):
				e.append("%s: unlocks unknown role '%s'" % [where, parts[1]])
			elif not parts[0] in ["facility", "tool", "role", "feature"]:
				e.append("%s: unknown unlock kind '%s'" % [where, parts[0]])
		"mitigate":
			if not hazards.has(eff.get("hazard", "")):
				e.append("%s: mitigates unknown hazard '%s'" % [where, eff.get("hazard", "")])
		"flag":
			if String(eff.get("flag", "")) == "":
				e.append("%s: flag effect without a flag" % where)
		_:
			e.append("%s: unknown effect type '%s'" % [where, eff.get("type", "")])


func _validate_objectives(kind: String, arr: Array, e: Array) -> void:
	for q in arr:
		var qid := String(q.get("id", "?"))
		var o: Dictionary = q.get("objective", {})
		var t := String(o.get("type", ""))
		if not t in OBJECTIVE_TYPES:
			e.append("%s '%s' has unknown objective type '%s'" % [kind, qid, t])
			continue
		match t:
			"depth_unlocked":
				if int(o.get("depth", 0)) < 1 or int(o.get("depth", 0)) > depths.size():
					e.append("%s '%s' references depth %s" % [kind, qid, o.get("depth")])
			"facility_built", "facility_level":
				if facility(String(o.get("facility", ""))).is_empty():
					e.append("%s '%s' references unknown facility '%s'" % [kind, qid, o.get("facility")])
			"equipment_level":
				if not equipment.has(String(o.get("equipment", ""))):
					e.append("%s '%s' references unknown equipment '%s'" % [kind, qid, o.get("equipment")])
			"tech":
				if not tech_by_id.has(String(o.get("tech", ""))):
					e.append("%s '%s' references unknown tech" % [kind, qid])
			"discovered":
				if not resource_by_id.has(String(o.get("resource", ""))):
					e.append("%s '%s' references unknown resource '%s'" % [kind, qid, o.get("resource")])
			"workers":
				var role := String(o.get("role", "any"))
				if role != "any" and not role_by_id.has(role):
					e.append("%s '%s' references unknown role '%s'" % [kind, qid, role])
			"stat":
				var st := String(o.get("stat", ""))
				if st.begins_with("mined."):
					if not resource_by_id.has(st.substr(6)):
						e.append("%s '%s' counts unknown resource '%s'" % [kind, qid, st])
		if t != "facility_built" and t != "tech" and t != "discovered" and t != "depth_unlocked":
			var target = o.get("target", null)
			if _bad_number(target) or float(target) <= 0.0:
				e.append("%s '%s' needs a positive target" % [kind, qid])
		var rw: Dictionary = q.get("reward", {})
		if rw.has("cosmetic") and not cosmetic_by_id.has(rw["cosmetic"]):
			e.append("%s '%s' rewards unknown cosmetic '%s'" % [kind, qid, rw["cosmetic"]])
		if rw.has("bonus"):
			var b: Dictionary = rw["bonus"]
			if not String(b.get("stat", "")) in MODIFIER_STATS or float(b.get("value", 0.0)) <= 0.0:
				e.append("%s '%s' has an invalid bonus reward" % [kind, qid])
		if float(rw.get("money", 0.0)) < 0.0 or float(rw.get("rp", 0.0)) < 0.0:
			e.append("%s '%s' has a negative reward" % [kind, qid])


func _validate_quest_graph(e: Array) -> void:
	for q in quests:
		for req in q.get("requires", []):
			if not quest_by_id.has(req):
				e.append("quest '%s' requires unknown quest '%s'" % [q.get("id", "?"), req])
	var state := {}
	for q in quests:
		if _quest_cycle(String(q["id"]), state):
			e.append("quest dependency cycle through '%s'" % q["id"])
			break
	if not quest_by_id.has(String(contracts_cfg.get("unlock_quest", ""))) and not contracts_cfg.is_empty():
		e.append("contracts unlock_quest is unknown")


func _quest_cycle(id: String, state: Dictionary) -> bool:
	if state.get(id, 0) == 1:
		return true
	if state.get(id, 0) == 2:
		return false
	state[id] = 1
	for req in quest_by_id.get(id, {}).get("requires", []):
		if quest_by_id.has(req) and _quest_cycle(String(req), state):
			return true
	state[id] = 2
	return false


func _validate_legacy(e: Array) -> void:
	var f: Dictionary = legacy_cfg.get("formula", {})
	for k in ["min_earned", "divisor", "exponent", "scale", "income_per_lp"]:
		if _bad_number(f.get(k)) or float(f.get(k, 0)) <= 0.0:
			e.append("legacy formula '%s' must be positive" % k)
	for u in legacy_upgrades:
		var uid := String(u.get("id", "?"))
		_check_cost("legacy '%s'" % uid, u.get("cost"), e)
		if int(u.get("max_level", 0)) < 1:
			e.append("legacy '%s' needs max_level >= 1" % uid)
		for eff in u.get("effects", []):
			match String(eff.get("type", "")):
				"mult_per_level", "add_per_level":
					if not String(eff.get("stat", "")) in MODIFIER_STATS:
						e.append("legacy '%s' unknown stat '%s'" % [uid, eff.get("stat", "")])
				"start_money", "start_depths":
					if (eff.get("per_level", []) as Array).size() != int(u.get("max_level", 0)):
						e.append("legacy '%s' per_level list must have max_level entries" % uid)
				"start_workers":
					for w in eff.get("workers", []):
						if not role_by_id.has(w.get("role", "")):
							e.append("legacy '%s' starts unknown role" % uid)
				"keep_techs_tier", "flag":
					pass
				_:
					e.append("legacy '%s' unknown effect '%s'" % [uid, eff.get("type", "")])


func _validate_regions_cosmetics(e: Array) -> void:
	if regions.is_empty() or int(regions[0].get("requires_prestige", 1)) != 0:
		e.append("the first region must be available without prestige")
	for reg in regions:
		for k in reg.get("modifiers", {}):
			var stat := String(k).split(":")[0]
			if not stat in MODIFIER_STATS:
				e.append("region '%s' modifies unknown stat '%s'" % [reg.get("id", "?"), k])
			if String(k).contains(":") and not resource_classes.has(String(k).split(":")[1]):
				e.append("region '%s' modifies unknown resource class '%s'" % [reg.get("id", "?"), k])
	for cls in resource_classes:
		for rid in resource_classes[cls]:
			if not resource_by_id.has(rid):
				e.append("resource class '%s' lists unknown resource '%s'" % [cls, rid])
	var kinds := {}
	for c in cosmetics:
		if c.get("default", false):
			if kinds.has(c.get("kind", "")):
				e.append("cosmetic kind '%s' has several defaults" % c.get("kind", ""))
			kinds[c.get("kind", "")] = true
		if c.get("kind", "") == "foreman_outfit" and String(c.get("asset", "")) == "":
			e.append("outfit '%s' needs an asset" % c.get("id", "?"))


func _validate_balance(e: Array) -> void:
	var tick := float(bal("sim", "tick_s", 0.0))
	if tick <= 0.0 or tick > 1.0:
		e.append("balance sim.tick_s must be in (0, 1]")
	if float(bal("offline", "base_cap_h", 0.0)) <= 0.0 or float(bal("offline", "max_cap_h", 0.0)) < float(bal("offline", "base_cap_h", 0.0)):
		e.append("balance offline caps invalid")
	if not region_by_id.has(String(bal("start", "region", ""))):
		e.append("balance start.region unknown")
	for step in tutorial:
		if String(step.get("complete_on", "")) == "":
			e.append("tutorial step '%s' needs complete_on" % step.get("id", "?"))
