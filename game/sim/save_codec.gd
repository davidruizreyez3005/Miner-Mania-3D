class_name SaveCodec
extends RefCounted
## Versioned save format with integrity checking and migrations.
##
##   {"format": "miner-mania-3d-save", "version": 3, "saved_unix": 1790000000,
##    "encoding": "var-b64", "checksum": sha256(payload bytes), "payload_b64": base64(var_to_bytes(state))}
##
## The v3 payload uses Godot's binary Variant encoding so every double
## round-trips bit-exactly (JSON text does not), which keeps a loaded game
## evolving identically to one that never stopped. Object decoding is never
## enabled, so a crafted file cannot instantiate code. Versions 1 and 2 stored
## a plain JSON "payload" with a checksum over its canonical form; they are
## still read and migrated.
##
## decode() never throws: malformed JSON, a wrong format tag, a checksum
## mismatch, a version from the future or a payload that fails sanity checks
## all return {"ok": false, "error": ...} so the caller can fall back to the
## backup save. Older versions are migrated step by step (v1 -> v2 -> v3).

const FORMAT := "miner-mania-3d-save"
const CURRENT := SimState.VERSION


static func encode(state: SimState, saved_unix: int) -> String:
	var bytes := var_to_bytes(state.to_dict())
	var doc := {
		"format": FORMAT,
		"version": CURRENT,
		"saved_unix": saved_unix,
		"encoding": "var-b64",
		"checksum": _sha256_bytes(bytes),
		"payload_b64": Marshalls.raw_to_base64(bytes),
	}
	return JSON.stringify(doc)


static func _sha256_bytes(bytes: PackedByteArray) -> String:
	var ctx := HashingContext.new()
	ctx.start(HashingContext.HASH_SHA256)
	ctx.update(bytes)
	return ctx.finish().hex_encode()


static func decode(text: String) -> Dictionary:
	if text.strip_edges() == "":
		return {"ok": false, "error": "empty"}
	var doc = JsonUtil.parse(text)
	if not doc is Dictionary:
		return {"ok": false, "error": "not_json"}
	if doc.get("format", "") != FORMAT:
		return {"ok": false, "error": "wrong_format"}
	var version := int(doc.get("version", 0))
	if version < 1:
		return {"ok": false, "error": "bad_version"}
	if version > CURRENT:
		return {"ok": false, "error": "future_version", "version": version}
	var expected := String(doc.get("checksum", ""))
	var payload = null
	if doc.has("payload_b64"):
		var bytes := Marshalls.base64_to_raw(String(doc["payload_b64"]))
		if bytes.is_empty():
			return {"ok": false, "error": "no_payload"}
		if expected == "" or _sha256_bytes(bytes) != expected:
			return {"ok": false, "error": "checksum_mismatch"}
		payload = bytes_to_var(bytes)
	else:
		payload = doc.get("payload", null)
		if payload is Dictionary and (expected == "" or JsonUtil.sha256(JsonUtil.canonical(payload)) != expected):
			return {"ok": false, "error": "checksum_mismatch"}
	if not payload is Dictionary:
		return {"ok": false, "error": "no_payload"}
	var migrated_from := version
	var p: Dictionary = payload
	while version < CURRENT:
		match version:
			1:
				p = migrate_1_to_2(p)
			2:
				p = migrate_2_to_3(p)
		version += 1
	var problem := sanity_check(p)
	if problem != "":
		return {"ok": false, "error": "invalid_payload", "detail": problem}
	var state := SimState.from_dict(p)
	return {"ok": true, "state": state, "migrated_from": migrated_from, "saved_unix": int(doc.get("saved_unix", 0))}


## Structural and numeric sanity: corrupted values must not enter the game.
static func sanity_check(p: Dictionary) -> String:
	for k in ["economy", "world", "workers", "progress", "legacy", "meta"]:
		if not p.get(k, null) is Dictionary:
			return "missing section '%s'" % k
	var eco: Dictionary = p["economy"]
	for k in ["money", "research_points"]:
		var v = eco.get(k, 0.0)
		if not (v is float or v is int) or is_nan(float(v)) or is_inf(float(v)) or float(v) < 0.0:
			return "economy.%s invalid" % k
	var depths = p["world"].get("depths", null)
	if not depths is Array or (depths as Array).is_empty():
		return "world.depths invalid"
	for dep in depths:
		if not dep is Dictionary or not dep.has("levels") or not dep.has("nodes"):
			return "depth entry invalid"
		for inv_key in ["face", "station"]:
			var inv = dep.get(inv_key, {})
			if not inv is Dictionary:
				return "depth inventory invalid"
			for r in inv:
				if is_nan(float(inv[r])) or float(inv[r]) < 0.0:
					return "negative inventory"
	var workers = p["workers"].get("list", null)
	if not workers is Array:
		return "workers invalid"
	for w in workers:
		if not w is Dictionary or not w.has("role") or not w.has("post"):
			return "worker entry invalid"
	var rt := float(p.get("run_time", 0.0))
	if is_nan(rt) or rt < 0.0:
		return "run_time invalid"
	return ""


## v1 (first public format): flat document with "cash", "depth_levels"
## ({index: mining level}) and "staff" ([{role, depth}]).
static func migrate_1_to_2(v1: Dictionary) -> Dictionary:
	var depths := []
	var levels: Dictionary = v1.get("depth_levels", {})
	var unlocked := int(v1.get("depths_unlocked", 1))
	for i in range(1, maxi(unlocked, levels.size()) + 1):
		var dep := SimState.new_depth(i)
		dep["unlocked"] = i <= unlocked
		dep["levels"]["mining"] = int(levels.get(str(i), 1))
		depths.append(dep)
	var staff := []
	var next_id := 1
	for s in v1.get("staff", []):
		var post := "depth:%d" % int(s.get("depth", 1)) if s.has("depth") else String(s.get("post", "office"))
		staff.append({"id": next_id, "role": String(s.get("role", "miner")), "post": post, "variant": "",
			"name": String(s.get("name", "Worker %d" % next_id)), "level": 1, "job": "idle", "target": "",
			"location": "", "arrive_at": 0.0, "hired_at": 0.0})
		next_id += 1
	return {
		"seed": int(v1.get("seed", 1)), "run_time": float(v1.get("play_time", 0.0)), "total_time": float(v1.get("play_time", 0.0)),
		"economy": {"cash": float(v1.get("cash", 0.0)), "research_points": 0.0, "region": "timberline_valley"},
		"world": {"depths": depths, "facilities": v1.get("facilities", {}), "surface_bin": {}, "warehouse": v1.get("warehouse", {})},
		"workers": {"list": staff, "next_id": next_id},
		"progress": {"techs": v1.get("techs", {}), "quests": v1.get("quests", {})},
		"legacy": {"prestige": {"count": int(v1.get("prestige", 0)), "lp": 0, "lp_total": 0, "upgrades": {}}},
		"meta": {"last_save_unix": int(v1.get("saved_at", 0))},
	}


## v2 -> v3: "cash" renamed to "money"; workers gained energy/xp/resting;
## cosmetics and discoveries moved under "legacy".
static func migrate_2_to_3(v2: Dictionary) -> Dictionary:
	var p := v2.duplicate(true)
	var eco: Dictionary = p.get("economy", {})
	if eco.has("cash") and not eco.has("money"):
		eco["money"] = float(eco["cash"])
		eco.erase("cash")
	p["economy"] = eco
	var wk: Dictionary = p.get("workers", {})
	for w in wk.get("list", []):
		if not w.has("energy"):
			w["energy"] = 1.0
		if not w.has("xp"):
			w["xp"] = 0.0
		if not w.has("resting"):
			w["resting"] = false
	p["workers"] = wk
	var lg: Dictionary = p.get("legacy", {})
	if not lg.has("cosmetics"):
		lg["cosmetics"] = p.get("cosmetics", {"unlocked": {}, "equipped": {}})
	if not lg.has("discoveries"):
		lg["discoveries"] = p.get("discoveries", {})
	p.erase("cosmetics")
	p.erase("discoveries")
	p["legacy"] = lg
	if not p.has("meta"):
		p["meta"] = {}
	return p
