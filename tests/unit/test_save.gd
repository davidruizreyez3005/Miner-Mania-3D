extends TestCase
## Save system: round trip, integrity checking, corruption handling,
## migrations from every older version, and determinism across save/load.


func _played(seconds: float = 900.0, seed_value: int = 11) -> Simulation:
	var sim := make_sim(seed_value)
	var bot := AutoplayBot.new(sim)
	bot.play(seconds, 0.25)
	return sim


func test_round_trip_is_lossless() -> void:
	var sim := _played()
	var text := SaveCodec.encode(sim.state, 1_790_000_000)
	var r := SaveCodec.decode(text)
	assert_true(r.get("ok", false), "decode: %s" % str(r))
	var a := JsonUtil.canonical(sim.state.to_dict())
	var b := JsonUtil.canonical((r["state"] as SimState).to_dict())
	assert_eq(b, a, "canonical state identical after round trip")
	assert_eq(int(r["saved_unix"]), 1_790_000_000)
	assert_eq(int(r["migrated_from"]), SaveCodec.CURRENT)


func test_continuing_after_load_is_deterministic() -> void:
	var sim := _played(600.0)
	var loaded := Simulation.new(content(), (SaveCodec.decode(SaveCodec.encode(sim.state, 1)) ["state"]))
	for i in 600:
		sim.tick(0.1)
		loaded.tick(0.1)
	assert_eq(JsonUtil.canonical(loaded.state.to_dict()), JsonUtil.canonical(sim.state.to_dict()), "loaded game evolves identically")


func _payload(doc: Dictionary) -> Dictionary:
	return bytes_to_var(Marshalls.base64_to_raw(String(doc["payload_b64"])))


func _set_payload(doc: Dictionary, payload: Dictionary, fix_checksum: bool) -> String:
	var bytes := var_to_bytes(payload)
	doc["payload_b64"] = Marshalls.raw_to_base64(bytes)
	if fix_checksum:
		var ctx := HashingContext.new()
		ctx.start(HashingContext.HASH_SHA256)
		ctx.update(bytes)
		doc["checksum"] = ctx.finish().hex_encode()
	return JSON.stringify(doc)


func test_checksum_mismatch_detected() -> void:
	var sim := _played(120.0)
	var doc: Dictionary = JSON.parse_string(SaveCodec.encode(sim.state, 5))
	var p := _payload(doc)
	p["economy"]["money"] = 1e30
	var r := SaveCodec.decode(_set_payload(doc, p, false))
	assert_eq(String(r.get("error", "")), "checksum_mismatch", "tampered money rejected")
	var doc2: Dictionary = JSON.parse_string(SaveCodec.encode(sim.state, 5))
	var b64 := String(doc2["payload_b64"])
	doc2["payload_b64"] = b64.substr(0, 40) + ("A" if b64[40] != "A" else "B") + b64.substr(41)
	assert_eq(String(SaveCodec.decode(JSON.stringify(doc2)).get("error", "")), "checksum_mismatch", "flipped byte rejected")


func test_corrupted_inputs_rejected() -> void:
	var sim := _played(60.0)
	var good := SaveCodec.encode(sim.state, 5)
	assert_eq(String(SaveCodec.decode("").get("error", "")), "empty")
	assert_eq(String(SaveCodec.decode("{not json").get("error", "")), "not_json")
	assert_eq(String(SaveCodec.decode(good.substr(0, good.length() / 2)).get("error", "")), "not_json", "truncated file")
	assert_eq(String(SaveCodec.decode("{\"format\": \"other\"}").get("error", "")), "wrong_format")
	var doc: Dictionary = JSON.parse_string(good)
	doc["version"] = SaveCodec.CURRENT + 1
	assert_eq(String(SaveCodec.decode(JSON.stringify(doc)).get("error", "")), "future_version")
	var doc2: Dictionary = JSON.parse_string(good)
	var p2 := _payload(doc2)
	p2["economy"]["money"] = -5.0
	assert_eq(String(SaveCodec.decode(_set_payload(doc2, p2, true)).get("error", "")), "invalid_payload", "negative money rejected even with a valid checksum")
	var doc3: Dictionary = JSON.parse_string(good)
	var p3 := _payload(doc3)
	p3.erase("workers")
	assert_eq(String(SaveCodec.decode(_set_payload(doc3, p3, true)).get("error", "")), "invalid_payload", "missing section")
	var doc4: Dictionary = JSON.parse_string(good)
	doc4["payload_b64"] = Marshalls.raw_to_base64(var_to_bytes([1, 2, 3]))
	doc4.erase("checksum")
	assert_eq(String(SaveCodec.decode(JSON.stringify(doc4)).get("error", "")), "checksum_mismatch", "missing checksum rejected")


func _wrap(version: int, payload: Dictionary) -> String:
	var parsed = JsonUtil.parse(JSON.stringify(payload, "", false, true))
	return JSON.stringify({"format": SaveCodec.FORMAT, "version": version, "saved_unix": 1700000000,
		"checksum": JsonUtil.sha256(JsonUtil.canonical(parsed)), "payload": parsed}, "", false, true)


func test_migrate_v1() -> void:
	var v1 := {"cash": 1234.5, "seed": 99, "play_time": 3600.0, "depths_unlocked": 2,
		"depth_levels": {"1": 12, "2": 4}, "staff": [{"role": "miner", "depth": 1, "name": "Old Gus"}, {"role": "operator", "post": "headframe"}],
		"techs": {"steel_picks": true}, "quests": {"q_first_swing": "claimed"}, "prestige": 0, "saved_at": 1690000000}
	var r := SaveCodec.decode(_wrap(1, v1))
	assert_true(r.get("ok", false), "v1 decodes: %s" % str(r))
	if not r.get("ok", false):
		return
	assert_eq(int(r["migrated_from"]), 1)
	var sim := Simulation.new(content(), r["state"])
	var s := sim.state
	assert_near(s.money, 1234.5, 1e-9, "cash -> money")
	assert_eq(s.depth(1)["levels"]["mining"], 12)
	assert_true(s.depth(2)["unlocked"], "depth 2 open")
	assert_eq(s.depth(1)["nodes"].size(), 3, "veins rebuilt for open depths")
	assert_eq(s.workers.size(), 2)
	assert_eq(String(s.workers[0]["post"]), "depth:1")
	assert_near(float(s.workers[0]["energy"]), 1.0, 1e-9, "v3 worker fields added")
	assert_true(s.techs.has("steel_picks"))
	assert_eq(s.depths.size(), content().depth_count(), "all depths present")
	sim.advance(60.0, 0.1)
	assert_finite_state(sim, "migrated game runs")


func test_migrate_v2() -> void:
	var sim := _played(300.0, 3)
	var p: Dictionary = JsonUtil.parse(JSON.stringify(sim.state.to_dict(), "", false, true))
	# Recreate the v2 shape: cash instead of money, no worker energy/xp, cosmetics at top level.
	p["economy"]["cash"] = p["economy"]["money"]
	p["economy"].erase("money")
	for w in p["workers"]["list"]:
		w.erase("energy")
		w.erase("xp")
		w.erase("resting")
	p["cosmetics"] = p["legacy"]["cosmetics"]
	p["legacy"].erase("cosmetics")
	var r := SaveCodec.decode(_wrap(2, p))
	assert_true(r.get("ok", false), "v2 decodes: %s" % str(r))
	if not r.get("ok", false):
		return
	var s: SimState = r["state"]
	assert_near(s.money, sim.state.money, 1e-6, "money kept")
	assert_eq(s.workers.size(), sim.state.workers.size())
	assert_true(s.cosmetics["unlocked"].size() >= 1, "cosmetics moved under legacy")


func test_offline_timestamps_in_save() -> void:
	var sim := _played(60.0)
	sim.state.meta["last_save_unix"] = 1_800_000_000
	sim.state.meta["max_seen_unix"] = 1_800_000_000
	var r := SaveCodec.decode(SaveCodec.encode(sim.state, 1_800_000_000))
	assert_eq(int((r["state"] as SimState).meta["max_seen_unix"]), 1_800_000_000, "high-water mark persisted")
