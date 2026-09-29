extends Node
## Runtime access to the generated asset library through
## res://assets/generated/catalog.json (built by tools/assets/build_catalog.py
## from the pipeline manifest). Scenes are cached; static props get their
## pipeline LODs as visibility-range levels; missing assets never crash the
## game - a correctly sized placeholder is used and the error is reported.

const CATALOG := "res://assets/generated/catalog.json"
const LOD_DISTANCES := [38.0, 70.0, 120.0]   # LOD0 -> LOD1 -> LOD2 -> LOD3 switch distances (m)
const LOD_MARGIN := 3.0

var catalog: Dictionary = {}
var assets: Dictionary = {}
var humanoid: Dictionary = {}
var missing: Array = []
var _scenes: Dictionary = {}
var _pending: Array = []
var _placeholder_mat: StandardMaterial3D


func _init() -> void:
	# Loaded at construction so the catalog is usable before the first frame
	# (tools and tests running as SceneTree scripts build scenes in _initialize).
	reload()


func reload() -> void:
	var data = JsonUtil.load_file(CATALOG)
	catalog = data if data is Dictionary else {}
	assets = catalog.get("assets", {})
	humanoid = catalog.get("humanoid", {})
	if assets.is_empty():
		push_warning("Assets: catalog missing or empty (%s) - using placeholders" % CATALOG)


func has(id: String) -> bool:
	return assets.has(id)


func info(id: String) -> Dictionary:
	return assets.get(id, {})


func dims(id: String) -> Vector3:
	var d: Array = info(id).get("dims", [1, 1, 1])
	return Vector3(float(d[0]), float(d[1]), float(d[2]))


func bounds(id: String) -> AABB:
	var a := info(id)
	if a.is_empty():
		return AABB(Vector3(-0.5, 0, -0.5), Vector3.ONE)
	var lo: Array = a["bounds_min"]
	var hi: Array = a["bounds_max"]
	var vlo := Vector3(float(lo[0]), float(lo[1]), float(lo[2]))
	return AABB(vlo, Vector3(float(hi[0]), float(hi[1]), float(hi[2])) - vlo)


func socket(id: String, name: String) -> Transform3D:
	var s: Dictionary = info(id).get("sockets", {}).get(name, {})
	if s.is_empty():
		return Transform3D.IDENTITY
	var p: Array = s["pos"]
	var q: Array = s["rot"]
	return Transform3D(Basis(Quaternion(float(q[0]), float(q[1]), float(q[2]), float(q[3])).normalized()),
		Vector3(float(p[0]), float(p[1]), float(p[2])))


func has_socket(id: String, name: String) -> bool:
	return info(id).get("sockets", {}).has(name)


func model_path(id: String, state: String = "") -> String:
	var a := info(id)
	if a.is_empty():
		return ""
	if state != "" and a.get("states", {}).has(state):
		return String(a["states"][state]["model"])
	return String(a.get("model", ""))


func scene(path: String) -> PackedScene:
	if path == "":
		return null
	if _scenes.has(path):
		return _scenes[path]
	var ps: PackedScene = null
	if ResourceLoader.exists(path):
		ps = ResourceLoader.load(path) as PackedScene
	if ps == null and not path in missing:
		missing.append(path)
		push_error("Assets: cannot load " + path)
	_scenes[path] = ps
	return ps


## Starts background loading of the given assets' main scenes (loading screen).
func preload_assets(ids: Array) -> void:
	for id in ids:
		var p := model_path(String(id))
		if p != "" and not _scenes.has(p) and ResourceLoader.exists(p):
			if ResourceLoader.load_threaded_request(p, "PackedScene", true) == OK:
				_pending.append(p)


## 0..1 progress of preload_assets(); collects finished scenes into the cache.
func preload_progress() -> float:
	if _pending.is_empty():
		return 1.0
	var done := 0
	for p in _pending.duplicate():
		var st := ResourceLoader.load_threaded_get_status(p)
		if st == ResourceLoader.THREAD_LOAD_LOADED:
			_scenes[p] = ResourceLoader.load_threaded_get(p)
			_pending.erase(p)
			done += 1
		elif st == ResourceLoader.THREAD_LOAD_FAILED or st == ResourceLoader.THREAD_LOAD_INVALID_RESOURCE:
			_pending.erase(p)
			if not p in missing:
				missing.append(p)
	return 1.0 - float(_pending.size()) / maxf(1.0, float(_pending.size() + done))


## Instances an asset. `lod`: attach the pipeline LOD levels with visibility
## ranges (static props only - animated assets use the per-mesh LODs Godot
## generates at import, so skeletons are never duplicated).
func instantiate(id: String, state: String = "", lod: bool = true) -> Node3D:
	var path := model_path(id, state)
	var ps := scene(path)
	var root := Node3D.new()
	root.name = id if state == "" else "%s_%s" % [id, state]
	root.set_meta("asset_id", id)
	if ps == null:
		root.add_child(_placeholder(id))
		return root
	var inst := ps.instantiate() as Node3D
	inst.name = "LOD0"
	root.add_child(inst)
	var a := info(id)
	var lods: Array = []
	if state != "" and a.get("states", {}).has(state):
		lods = a["states"][state].get("lods", [])
	else:
		for l in a.get("lods", []):
			lods.append(l["model"])
	# Phones use Godot's automatic mesh LOD instead of the pipeline's LOD
	# models (smaller download; mipmaps cover the distant textures).
	if lod and not lods.is_empty() and not _is_animated(inst) and not OS.has_feature("mobile"):
		_set_range(inst, 0.0, LOD_DISTANCES[0])
		for i in lods.size():
			var lps := scene(String(lods[i]))
			if lps == null:
				continue
			var li := lps.instantiate() as Node3D
			li.name = "LOD%d" % (i + 1)
			root.add_child(li)
			var end: float = LOD_DISTANCES[i + 1] if i + 1 < LOD_DISTANCES.size() and i + 1 < lods.size() else 0.0
			_set_range(li, LOD_DISTANCES[i], end)
	return root


func _is_animated(n: Node) -> bool:
	return not n.find_children("*", "AnimationPlayer", true, false).is_empty() or \
		not n.find_children("*", "Skeleton3D", true, false).is_empty()


func _set_range(n: Node, begin: float, end: float) -> void:
	for gi in n.find_children("*", "GeometryInstance3D", true, false):
		var g := gi as GeometryInstance3D
		g.visibility_range_begin = begin
		g.visibility_range_begin_margin = LOD_MARGIN if begin > 0.0 else 0.0
		g.visibility_range_end = end
		g.visibility_range_end_margin = LOD_MARGIN if end > 0.0 else 0.0
		g.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_DISABLED


func _placeholder(id: String) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var box := BoxMesh.new()
	var b := bounds(id)
	box.size = b.size.max(Vector3(0.2, 0.2, 0.2))
	mi.mesh = box
	mi.position = b.get_center()
	if _placeholder_mat == null:
		_placeholder_mat = StandardMaterial3D.new()
		_placeholder_mat.albedo_color = Color(1.0, 0.0, 0.8)
	mi.material_override = _placeholder_mat
	mi.name = "MissingAsset"
	return mi


## Every asset file the game can load (APK verification / preloading).
func referenced_models(ids: Array) -> Array:
	var out := []
	for id in ids:
		var a := info(String(id))
		if a.is_empty():
			continue
		out.append(a["model"])
		for st in a.get("states", {}).values():
			out.append(st["model"])
	return out
