extends SceneTree
## Headless Godot import validation of the generated asset library.
##
##   godot --headless --path . --import
##   godot --headless --path . --script res://godot/pipeline/validate_assets.gd -- \
##       [--manifest res://assets/manifests/asset_manifest.json] [--report res://assets/reports/godot_validation.json]
##
## For every file listed in the manifest (main models, LODs, collision files,
## state variants, per-clip animation files) it checks what Godot actually
## imported: the scene loads and instantiates; triangle counts equal the
## manifest; surfaces have materials and the baked textures; bounds match the
## manifest dimensions after the Blender Z-up -> Godot Y-up conversion; sockets
## exist where the manifest puts them; skeletons have the recorded bone count;
## every clip exists with the manifest loop mode (set by asset_post_import.gd)
## and length, every track binds to a real node/bone, and sampling it gives a
## finite pose; collision files became convex shapes with no visible mesh.
## Finally every humanoid clip must bind to every worker skeleton (shared rig).
## Exit code 0 = all passed, 1 = failures, 2 = setup error.

const DEFAULT_MANIFESTS := ["res://assets/manifests/asset_manifest.json", "res://assets/manifests/asset_manifest.partial.json"]
const ANIMATIONS := ["res://assets/manifests/animations.json", "res://assets/manifests/animations.partial.json"]
const DIM_TOL_ABS := 0.02
const DIM_TOL_REL := 0.01
const POS_TOL := 0.01

var _results: Array = []
var _expect: Dictionary = {}            # file -> build-time inspector expectations
var _humanoid_loops: Dictionary = {}
var _worker_scenes: Array = []          # [asset id, res path]
var _library_scenes: Array = []         # res paths holding humanoid clips


func _initialize() -> void:
	# The root viewport enters the tree on the first frame; instances added
	# before that have no global transforms and animation mixers stay idle.
	await process_frame
	var args := _parse_args(OS.get_cmdline_user_args())
	var manifest_path: String = args.get("manifest", "")
	if manifest_path == "":
		for p in DEFAULT_MANIFESTS:
			if FileAccess.file_exists(p):
				manifest_path = p
				break
	var manifest = _read_json(manifest_path) if manifest_path != "" else null
	if not manifest is Dictionary or not manifest.has("assets"):
		printerr("validate_assets.gd: no readable manifest (%s)" % manifest_path)
		quit(2)
		return
	var exp_path := manifest_path.replace("asset_manifest", "validation_expectations")
	var exp_doc = _read_json(exp_path)
	if exp_doc is Dictionary:
		_expect = exp_doc.get("files", {})
	else:
		printerr("validate_assets.gd: expectations sidecar %s missing" % exp_path)
		quit(2)
		return
	var anim_doc = null
	for p in ANIMATIONS:
		if FileAccess.file_exists(p):
			anim_doc = _read_json(p)
			break
	if anim_doc is Dictionary:
		for clip_name in anim_doc.get("clips", {}):
			_humanoid_loops[clip_name] = bool(anim_doc["clips"][clip_name].get("loop", false))

	for entry in manifest["assets"]:
		_check_entry(entry)
	_check_shared_rig()

	var failed := 0
	var n_err := 0
	for r in _results:
		if not r["errors"].is_empty():
			failed += 1
			n_err += r["errors"].size()
			for e in r["errors"]:
				printerr("ERROR %s: %s" % [r["path"], e])
	var report := {
		"manifest": manifest_path,
		"godot": Engine.get_version_info()["string"],
		"files_checked": _results.size(),
		"files_failed": failed,
		"errors": n_err,
		"status": "passed" if failed == 0 and _results.size() > 0 else "failed",
		"files": _results,
	}
	var out_path: String = args.get("report", "res://assets/reports/godot_validation.json")
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(out_path.get_base_dir()))
	var fh := FileAccess.open(ProjectSettings.globalize_path(out_path), FileAccess.WRITE)
	if fh:
		fh.store_string(JSON.stringify(report, "  "))
		fh.close()
	print("validate_assets.gd: %s: %d files, %d failed, %d errors -> %s" % [report["status"], _results.size(), failed, n_err, out_path])
	quit(0 if report["status"] == "passed" else 1)


# ------------------------------------------------------------------ per entry

func _check_entry(entry: Dictionary) -> void:
	var loops := {}
	var meta: Dictionary = entry.get("metadata", {})
	for clip in meta.get("clips", []):
		loops[clip["name"]] = bool(clip.get("loop", false))
	var humanoid: bool = entry.get("type", "") in ["character", "animation"]
	if humanoid:
		loops.merge(_humanoid_loops, true)
	var main_spec := {
		"triangles": entry.get("triangles", -1),
		"dimensions": entry.get("dimensions_m", []),
		"sockets": entry.get("socket_transforms", []),
		"bones": entry.get("bones", 0) if entry.get("skeleton", false) else 0,
		"animations": entry.get("animations", []),
		"loops": loops,
		"textured": true,
	}
	_check_scene(entry["id"], entry["model"], main_spec)
	if entry.get("type", "") == "character" and entry.get("skeleton", false) and not entry.get("animations", []).is_empty():
		_worker_scenes.append([entry["id"], "res://" + entry["model"]])
	for lod in entry.get("lod_models", []):
		_check_scene(entry["id"], lod["model"], {"triangles": lod.get("triangles", -1), "bones": main_spec["bones"],
			"animations": entry.get("animations", []), "loops": loops, "textured": true})
	if entry.get("collision_model"):
		_check_collision(entry["id"], entry["collision_model"], entry.get("collision_shapes", 0))
	var states: Dictionary = entry.get("states", {})
	for state_name in states:
		var st: Dictionary = states[state_name]
		if st["model"] == entry["model"]:
			continue
		_check_scene(entry["id"], st["model"], {"triangles": st.get("triangles", -1), "dimensions": st.get("dimensions_m", []),
			"textured": true})
		for lod_path in st.get("lod_models", []):
			_check_scene(entry["id"], lod_path, {"textured": true})
		if st.get("collision_model"):
			_check_collision(entry["id"], st["collision_model"], entry.get("collision_shapes", 0))
	var clips: Dictionary = entry.get("clip_models", {})
	for clip_name in clips:
		_check_scene(entry["id"], clips[clip_name], {"bones": main_spec["bones"], "animations": [clip_name], "loops": loops,
			"textured": false})
		_library_scenes.append("res://" + clips[clip_name])
	if entry.get("type", "") == "animation":
		_library_scenes.append("res://" + entry["model"])


func _new_result(asset_id: String, rel_path: String) -> Dictionary:
	var r := {"asset": asset_id, "path": rel_path, "errors": [], "info": {}}
	_results.append(r)
	return r


func _instantiate(r: Dictionary, rel_path: String) -> Node:
	var res_path := "res://" + rel_path
	if not ResourceLoader.exists(res_path):
		r["errors"].append("not imported (missing or rejected by the importer)")
		return null
	var packed = ResourceLoader.load(res_path)
	if not packed is PackedScene:
		r["errors"].append("did not import as a PackedScene")
		return null
	var inst: Node = packed.instantiate()
	if inst == null:
		r["errors"].append("instantiate() failed")
		return null
	root.add_child(inst)
	return inst


func _check_scene(asset_id: String, rel_path: String, spec: Dictionary) -> void:
	var r := _new_result(asset_id, rel_path)
	# Clip expectations follow the build's per-file contract (e.g. character
	# LODs are skin-only and borrow the main model's clips).
	var exp: Dictionary = _expect.get(rel_path, {}).get("expect", {})
	if exp.is_empty():
		r["errors"].append("no build expectations recorded for this file")
	elif exp.get("no_animations", false):
		spec["animations"] = []
	elif exp.has("animations"):
		spec["animations"] = exp["animations"]
		# Optional clips (in the clip spec but not required) may be present too.
		spec["allowed"] = exp.get("clips", {}).keys() if exp.has("clips") else exp["animations"]
	var inst := _instantiate(r, rel_path)
	if inst == null:
		return
	# Meshes, triangles, materials.
	var meshes := inst.find_children("*", "MeshInstance3D", true, false)
	if meshes.is_empty():
		r["errors"].append("no MeshInstance3D")
	var tris := 0
	var surfaces := 0
	var textured := 0
	var untextured_surfaces := []
	var aabb := AABB()
	var first := true
	for mi in meshes:
		var mesh: Mesh = mi.mesh
		if mesh == null:
			r["errors"].append("%s has no mesh" % mi.name)
			continue
		for s in mesh.get_surface_count():
			surfaces += 1
			var n_idx: int = mesh.surface_get_array_index_len(s)
			tris += (n_idx if n_idx > 0 else mesh.surface_get_array_len(s)) / 3
			var mat: Material = mi.get_active_material(s)
			if mat == null:
				r["errors"].append("%s surface %d has no material" % [mi.name, s])
			elif mat is BaseMaterial3D:
				if mat.albedo_texture != null:
					textured += 1
				elif mat.transparency == BaseMaterial3D.TRANSPARENCY_DISABLED:
					untextured_surfaces.append("%s/%d" % [mi.name, s])
		var box: AABB = mi.global_transform * mi.get_aabb()
		aabb = box if first else aabb.merge(box)
		first = false
	r["info"]["triangles"] = tris
	r["info"]["surfaces"] = surfaces
	if int(spec.get("triangles", -1)) >= 0 and tris != int(spec["triangles"]):
		r["errors"].append("imported %d triangles, manifest says %d" % [tris, int(spec["triangles"])])
	if spec.get("textured", false) and textured == 0:
		r["errors"].append("no surface carries the baked albedo texture")
	if spec.get("textured", false) and not untextured_surfaces.is_empty():
		r["errors"].append("opaque surfaces without textures: %s" % [untextured_surfaces])
	# Bounds: Blender (x, y, z) -> Godot (x, z, y) extents.
	var dims: Array = spec.get("dimensions", [])
	if dims.size() == 3 and not first:
		var expect := Vector3(dims[0], dims[2], dims[1])
		var got := aabb.size
		r["info"]["size_m"] = [snappedf(got.x, 0.001), snappedf(got.y, 0.001), snappedf(got.z, 0.001)]
		for i in 3:
			if absf(got[i] - expect[i]) > DIM_TOL_ABS + DIM_TOL_REL * expect[i]:
				r["errors"].append("bounds %s differ from manifest %s (axis conversion or scale)" % [got, expect])
				break
		if aabb.position.y < -0.5 * got.y - 0.05:
			r["errors"].append("model hangs below its origin (%s)" % aabb)
	# Sockets.
	for sock in spec.get("sockets", []):
		var node := inst.find_child("socket_" + sock["name"], true, false)
		if node == null:
			r["errors"].append("socket_%s missing" % sock["name"])
			continue
		if sock.get("bone") == null and node is Node3D:
			var want := Vector3(sock["godot_location_m"][0], sock["godot_location_m"][1], sock["godot_location_m"][2])
			var have: Vector3 = (node as Node3D).global_position
			if have.distance_to(want) > POS_TOL:
				r["errors"].append("socket_%s at %s, manifest (converted) %s" % [sock["name"], have, want])
	# Skeleton.
	var skels := inst.find_children("*", "Skeleton3D", true, false)
	var bones := int(spec.get("bones", 0))
	if bones > 0:
		if skels.size() != 1:
			r["errors"].append("expected one Skeleton3D, found %d" % skels.size())
		elif skels[0].get_bone_count() != bones:
			r["errors"].append("skeleton has %d bones, manifest says %d" % [skels[0].get_bone_count(), bones])
	# Animations.
	var wanted: Array = spec.get("animations", [])
	var players := inst.find_children("*", "AnimationPlayer", true, false)
	if not wanted.is_empty():
		if players.size() != 1:
			r["errors"].append("expected one AnimationPlayer, found %d" % players.size())
		else:
			_check_animations(r, players[0], wanted, spec.get("allowed", wanted), spec.get("loops", {}), skels)
	elif not players.is_empty():
		var extra := []
		for p in players:
			for a in p.get_animation_list():
				if String(a) != "RESET":
					extra.append(a)
		if not extra.is_empty():
			r["errors"].append("unexpected animations %s" % [extra])
	inst.queue_free()


func _check_animations(r: Dictionary, player: AnimationPlayer, wanted: Array, allowed: Array, loops: Dictionary,
		skels: Array) -> void:
	var have := []
	for a in player.get_animation_list():
		if String(a) != "RESET":
			have.append(String(a))
	for w in wanted:
		if not w in have:
			r["errors"].append("clip %s missing" % w)
	for h in have:
		if not h in allowed:
			r["errors"].append("unexpected clip %s" % h)
	var anim_root: Node = player.get_node_or_null(player.root_node)
	if anim_root == null:
		r["errors"].append("AnimationPlayer root_node does not resolve")
		return
	var skel: Skeleton3D = skels[0] if skels.size() == 1 else null
	var checked := 0
	for name in have:
		var anim: Animation = player.get_animation(name)
		if loops.has(name):
			var want_loop: bool = loops[name]
			if (anim.loop_mode != Animation.LOOP_NONE) != want_loop:
				r["errors"].append("clip %s loop mode %d, manifest loop=%s" % [name, anim.loop_mode, want_loop])
		else:
			r["errors"].append("clip %s has no loop flag in the manifest" % name)
		if anim.length <= 0.0 or anim.get_track_count() == 0:
			r["errors"].append("clip %s is empty" % name)
			continue
		var unbound := _unbound_tracks(anim, anim_root)
		if not unbound.is_empty():
			r["errors"].append("clip %s has %d unbound tracks, e.g. %s" % [name, unbound.size(), unbound[0]])
		player.play(name)
		player.seek(anim.length * 0.5, true)
		if skel != null:
			for b in skel.get_bone_count():
				var q := skel.get_bone_pose_rotation(b)
				var t := skel.get_bone_pose_position(b)
				if not (q.is_finite() and t.is_finite()):
					r["errors"].append("clip %s produced a non-finite pose on %s" % [name, skel.get_bone_name(b)])
					break
		player.stop()
		checked += 1
	r["info"]["clips_checked"] = checked


## Tracks whose node (or bone) does not exist under ``anim_root``.
func _unbound_tracks(anim: Animation, anim_root: Node) -> Array:
	var bad := []
	for t in anim.get_track_count():
		var path := anim.track_get_path(t)
		var node := anim_root.get_node_or_null(NodePath(path.get_concatenated_names()))
		if node == null:
			bad.append(String(path))
			continue
		if path.get_subname_count() > 0 and node is Skeleton3D:
			if (node as Skeleton3D).find_bone(path.get_concatenated_subnames()) < 0:
				bad.append(String(path))
	return bad


func _check_collision(asset_id: String, rel_path: String, expected_shapes: int) -> void:
	var r := _new_result(asset_id, rel_path)
	var inst := _instantiate(r, rel_path)
	if inst == null:
		return
	var shapes := inst.find_children("*", "CollisionShape3D", true, false)
	var convex := 0
	for cs in shapes:
		var shape = cs.shape
		if shape is ConvexPolygonShape3D and shape.points.size() >= 4:
			convex += 1
		else:
			r["errors"].append("%s is not a convex polygon shape" % cs.name)
	r["info"]["convex_shapes"] = convex
	if expected_shapes > 0 and convex != expected_shapes:
		r["errors"].append("%d convex shapes, manifest says %d" % [convex, expected_shapes])
	if convex == 0:
		r["errors"].append("no collision shapes were generated (missing -convcolonly suffix?)")
	var visible := 0
	for mi in inst.find_children("*", "MeshInstance3D", true, false):
		if mi.visible:
			visible += 1
	if visible > 0:
		r["errors"].append("%d visible meshes left in a collision-only file" % visible)
	if inst.find_children("*", "StaticBody3D", true, false).is_empty():
		r["errors"].append("no StaticBody3D")
	inst.queue_free()


## Every humanoid clip (library and per-clip files) must bind to every worker.
func _check_shared_rig() -> void:
	if _worker_scenes.is_empty() or _library_scenes.is_empty():
		return
	var anims := {}
	for lib_path in _library_scenes:
		var packed = ResourceLoader.load(lib_path)
		if not packed is PackedScene:
			continue
		var inst: Node = packed.instantiate()
		for p in inst.find_children("*", "AnimationPlayer", true, false):
			for a in p.get_animation_list():
				if String(a) != "RESET" and not anims.has(String(a)):
					anims[String(a)] = p.get_animation(a)
		inst.free()
	for w in _worker_scenes:
		var r := _new_result(w[0], w[1].trim_prefix("res://") + " <- humanoid clips")
		var packed = ResourceLoader.load(w[1])
		if not packed is PackedScene:
			r["errors"].append("worker scene did not load")
			continue
		var inst: Node = packed.instantiate()
		root.add_child(inst)
		var players := inst.find_children("*", "AnimationPlayer", true, false)
		var anim_root: Node = inst
		if not players.is_empty():
			anim_root = players[0].get_node_or_null(players[0].root_node)
		var bad := 0
		for name in anims:
			var unbound := _unbound_tracks(anims[name], anim_root)
			if not unbound.is_empty():
				bad += 1
				r["errors"].append("clip %s does not bind (%s)" % [name, unbound[0]])
		r["info"]["clips_bound"] = anims.size() - bad
		inst.queue_free()


# ------------------------------------------------------------------ utils

func _parse_args(argv: PackedStringArray) -> Dictionary:
	var out := {}
	var i := 0
	while i < argv.size():
		var a := argv[i]
		if a.begins_with("--") and i + 1 < argv.size():
			out[a.trim_prefix("--")] = argv[i + 1]
			i += 2
		else:
			i += 1
	return out


func _read_json(path: String):
	if not FileAccess.file_exists(path):
		return null
	return JSON.parse_string(FileAccess.get_file_as_string(path))
