extends TestCase
## Data integrity: the shipped content validates, and the validator catches
## duplicate ids, missing references, invalid costs and dependency cycles.


func _mutated(fn: Callable) -> Array:
	var data := {}
	for key in ContentDB.FILES:
		data[key] = content().raw[key].duplicate(true)
	fn.call(data)
	var db := ContentDB.new()
	db.load_from_dicts(data)
	return db.validate()


func _has(errors: Array, needle: String) -> bool:
	for e in errors:
		if String(e).contains(needle):
			return true
	return false


func test_shipped_content_is_valid() -> void:
	var errors := content().validate()
	assert_true(errors.is_empty(), "content errors: %s" % str(errors))


func test_counts() -> void:
	assert_eq(content().resources.size(), 16, "resources")
	assert_eq(content().depth_count(), 8, "depths")
	assert_true(content().techs.size() >= 30, "at least 30 technologies")
	assert_true(content().quests.size() >= 30, "at least 30 quests")
	assert_true(content().achievements.size() >= 30, "at least 30 achievements")
	assert_eq(content().roles.size(), 7, "worker roles")


func test_duplicate_ids_detected() -> void:
	var errors := _mutated(func(d):
		d["resources"]["resources"].append(d["resources"]["resources"][0].duplicate(true)))
	assert_true(_has(errors, "duplicate resource id 'stone'"), str(errors))


func test_missing_reference_detected() -> void:
	var errors := _mutated(func(d):
		d["depths"]["depths"][0]["resources"]["unobtainium"] = 5)
	assert_true(_has(errors, "unknown resource 'unobtainium'"), str(errors))
	var errors2 := _mutated(func(d):
		d["technologies"]["technologies"][5]["requires"] = ["no_such_tech"])
	assert_true(_has(errors2, "unknown tech 'no_such_tech'"), str(errors2))


func test_invalid_costs_detected() -> void:
	var errors := _mutated(func(d):
		d["facilities"]["facilities"][0]["cost"] = {"base": -5, "growth": 0.5})
	assert_true(_has(errors, "invalid cost base"), str(errors))
	assert_true(_has(errors, "invalid cost growth"), str(errors))


func test_dependency_cycle_detected() -> void:
	var errors := _mutated(func(d):
		var techs: Array = d["technologies"]["technologies"]
		for t in techs:
			if t["id"] == "steel_picks":
				t["requires"] = ["pneumatic_drills"])
	assert_true(_has(errors, "same or a later tier") or _has(errors, "cycle"), str(errors))
	var errors2 := _mutated(func(d):
		var qs: Array = d["quests"]["quests"]
		qs[0]["requires"] = [qs[2]["id"]])
	assert_true(_has(errors2, "quest dependency cycle"), str(errors2))


func test_facility_tech_consistency() -> void:
	var errors := _mutated(func(d):
		for f in d["facilities"]["facilities"]:
			if f["id"] == "washer":
				f["requires"] = {"tech": "crushing"})
	assert_true(_has(errors, "does not unlock it"), str(errors))


func test_processing_order_enforced() -> void:
	var errors := _mutated(func(d):
		var r: Dictionary = d["resources"]["resources"][2]
		r["processing"] = [r["processing"][2], r["processing"][0]])
	assert_true(_has(errors, "out of plant order"), str(errors))


func test_items_table() -> void:
	var it := content().item("copper_ingot")
	assert_eq(it.get("resource", ""), "copper")
	assert_near(float(it["value"]), 7.0 * 1.6 * 1.4 * 2.4, 1e-6, "cumulative value")
	assert_eq(content().item("stone").get("step", -1), 0)


func test_manifest_cross_check() -> void:
	## Every asset the game references must exist in the generated manifest
	## (skipped when the asset library has not been built in this checkout).
	var path := "res://assets/manifests/asset_manifest.json"
	if not FileAccess.file_exists(path):
		return
	var m = JsonUtil.load_file(path)
	var ids := []
	for a in m.get("assets", []):
		ids.append(String(a["id"]))
	var missing := []
	for aid in content().all_asset_ids():
		if not aid in ids:
			missing.append(aid)
	# Assets added to the Blender registry by this game but not yet built are reported, not hidden.
	assert_true(missing.is_empty(), "assets missing from manifest: %s" % str(missing))
