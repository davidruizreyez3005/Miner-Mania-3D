class_name Modifiers
extends RefCounted
## Aggregated permanent modifiers for the current state: technologies, legacy
## upgrades, achievement bonuses and the region. Rebuilt whenever one of
## those changes (Simulation.invalidate_modifiers). Temporary boosts are
## applied by the systems on top.

var mult: Dictionary = {}        # stat -> multiplier
var add: Dictionary = {}         # stat -> additive amount
var flags: Dictionary = {}       # flag -> true
var mitigated: Dictionary = {}   # hazard -> true
var unlocked: Dictionary = {}    # "facility:x" / "tool:2" / "role:x" / "feature:x" -> true
var class_value: Dictionary = {} # resource class -> sale value multiplier (region)
var income_mult: float = 1.0     # prestige legacy income multiplier


func rebuild(state: SimState, content: ContentDB) -> void:
	mult.clear()
	add.clear()
	flags.clear()
	mitigated.clear()
	unlocked.clear()
	class_value.clear()
	for tid in state.techs:
		var t: Dictionary = content.tech_by_id.get(tid, {})
		for e in t.get("effects", []):
			_apply(e, 1)
	for uid in state.prestige.get("upgrades", {}):
		var lvl := int(state.prestige["upgrades"][uid])
		if lvl <= 0:
			continue
		var u: Dictionary = content.legacy_by_id.get(uid, {})
		for e in u.get("effects", []):
			match String(e.get("type", "")):
				"mult_per_level":
					_mul(String(e["stat"]), 1.0 + float(e["value"]) * lvl)
				"add_per_level":
					_add(String(e["stat"]), float(e["value"]) * lvl)
				"flag":
					flags[String(e["flag"])] = true
	for stat in state.bonuses:
		_mul(String(stat), float(state.bonuses[stat]))
	var reg: Dictionary = content.region_by_id.get(state.region, {})
	var rm: Dictionary = reg.get("modifiers", {})
	for k in rm:
		var key := String(k)
		if key.contains(":"):
			var parts := key.split(":")
			if parts[0] == "sale_value":
				class_value[parts[1]] = float(class_value.get(parts[1], 1.0)) * float(rm[k])
		else:
			_mul(key, float(rm[k]))
	var per_lp := float(content.legacy_cfg.get("formula", {}).get("income_per_lp", 0.05))
	income_mult = 1.0 + per_lp * float(state.prestige.get("lp_total", 0))


func _apply(e: Dictionary, _times: int) -> void:
	match String(e.get("type", "")):
		"mult":
			_mul(String(e["stat"]), float(e["value"]))
		"add":
			_add(String(e["stat"]), float(e["value"]))
		"unlock":
			unlocked[String(e["what"])] = true
		"mitigate":
			mitigated[String(e["hazard"])] = true
		"flag":
			flags[String(e["flag"])] = true


func _mul(stat: String, v: float) -> void:
	mult[stat] = float(mult.get(stat, 1.0)) * v


func _add(stat: String, v: float) -> void:
	add[stat] = float(add.get(stat, 0.0)) + v


func m(stat: String) -> float:
	return float(mult.get(stat, 1.0))


func a(stat: String) -> float:
	return float(add.get(stat, 0.0))


func has_flag(f: String) -> bool:
	return flags.has(f)


func is_unlocked(what: String) -> bool:
	return unlocked.has(what)
