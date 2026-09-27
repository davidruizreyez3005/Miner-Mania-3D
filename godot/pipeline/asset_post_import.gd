@tool
extends EditorScenePostImport
## Post-import step for every generated GLB (set as the scene importer default
## in project.godot).
##
## glTF has no loop flag, so imported clips would all play once. The asset
## manifest is the source of truth: machine/vehicle/building clips carry their
## loop flag in the entry's metadata, humanoid clips in animations.json. The
## asset id is stored as scene metadata for game code and the validator.

const MANIFESTS := ["res://assets/manifests/asset_manifest.json", "res://assets/manifests/asset_manifest.partial.json"]
const ANIMATIONS := ["res://assets/manifests/animations.json", "res://assets/manifests/animations.partial.json"]


func _post_import(scene: Node) -> Object:
	var source := get_source_file()
	var info := _lookup(source.trim_prefix("res://"))
	if info.is_empty():
		return scene
	scene.set_meta("mm_asset_id", info["id"])
	var loops: Dictionary = info["loops"]
	for player in scene.find_children("*", "AnimationPlayer", true, false):
		for lib_name in player.get_animation_library_list():
			var lib: AnimationLibrary = player.get_animation_library(lib_name)
			for anim_name in lib.get_animation_list():
				if loops.has(String(anim_name)):
					var anim: Animation = lib.get_animation(anim_name)
					anim.loop_mode = Animation.LOOP_LINEAR if loops[String(anim_name)] else Animation.LOOP_NONE
	return scene


static func _read_json(candidates: Array) -> Dictionary:
	for path in candidates:
		if FileAccess.file_exists(path):
			var data = JSON.parse_string(FileAccess.get_file_as_string(path))
			if data is Dictionary:
				return data
	return {}


## Returns {"id": asset id, "loops": {clip: bool}} for a generated file path.
static func _lookup(rel_path: String) -> Dictionary:
	var manifest := _read_json(MANIFESTS)
	var humanoid := {}
	var anim_doc := _read_json(ANIMATIONS)
	for clip_name in anim_doc.get("clips", {}):
		humanoid[clip_name] = bool(anim_doc["clips"][clip_name].get("loop", false))
	for entry in manifest.get("assets", []):
		if not rel_path in files_of(entry):
			continue
		var loops := {}
		var meta: Dictionary = entry.get("metadata", {})
		for clip in meta.get("clips", []):
			loops[clip["name"]] = bool(clip.get("loop", false))
		if entry.get("type", "") in ["character", "animation"]:
			loops.merge(humanoid, true)
		return {"id": entry["id"], "loops": loops}
	return {}


static func files_of(entry: Dictionary) -> Array:
	var out := []
	if entry.get("model"):
		out.append(entry["model"])
	for lod in entry.get("lod_models", []):
		out.append(lod["model"])
	if entry.get("collision_model"):
		out.append(entry["collision_model"])
	for state in entry.get("states", {}).values():
		out.append(state["model"])
		for lod in state.get("lod_models", []):
			out.append(lod)
		if state.get("collision_model"):
			out.append(state["collision_model"])
	for clip in entry.get("clip_models", {}).values():
		out.append(clip)
	return out
