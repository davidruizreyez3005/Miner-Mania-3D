class_name ModuleLibrary
extends RefCounted
## The modular world system: module definitions (data/world/modules.json)
## and validated placement. Definitions are checked against the generated
## asset catalog (the asset exists, positive dimensions, declared connection
## points exist as sockets inside the bounds, sane rotation/scale/LOD); every
## placement is checked before it is instanced: allowed zone and bounds,
## mount (floor contact within tolerance, ceiling contact, wall), rotation
## step, scale range, overlap with other solid pieces (with clearance) and
## the gallery walkway, which must stay clear for workers. Problems are
## collected in `errors` (the world validation test requires none).

var content: ContentDB
var data: Dictionary
var defs: Dictionary = {}
var errors: Array = []
var records: Array = []          # {module, zone, depth, xform, aabb(Rect2 xz), solid, y0, y1}
var rock: RockBuilder            # set by the world for floor/ceiling queries
var enforce := true              # skip invalid placements (always reported)


func _init(db: ContentDB) -> void:
	content = db
	data = db.modules
	for m in data.get("modules", []):
		defs[String(m["id"])] = m


func module(id: String) -> Dictionary:
	return defs.get(id, {})


# ------------------------------------------------------------ definitions

func validate_definitions() -> Array:
	var e: Array = []
	var seen := {}
	for m in data.get("modules", []):
		var id := String(m.get("id", ""))
		if id == "" or seen.has(id):
			e.append("module id missing or duplicate: '%s'" % id)
		seen[id] = true
		var aid := String(m.get("asset", ""))
		if not Assets.has(aid):
			e.append("module %s: asset '%s' not in the catalog" % [id, aid])
			continue
		var dims := Assets.dims(aid)
		if dims.x <= 0.0 or dims.y <= 0.0 or dims.z <= 0.0:
			e.append("module %s: non-positive dimensions %s" % [id, dims])
		var b := Assets.bounds(aid).grow(0.05)
		for cp in m.get("connection_points", []):
			if not Assets.has_socket(aid, String(cp)):
				e.append("module %s: connection point '%s' is not a socket of %s" % [id, cp, aid])
			elif not b.has_point(Assets.socket(aid, String(cp)).origin):
				e.append("module %s: connection point '%s' outside the asset bounds" % [id, cp])
		for z in m.get("zones", []):
			if not data.get("zones", {}).has(z):
				e.append("module %s: unknown zone '%s'" % [id, z])
		if not String(m.get("mount", "floor")) in ["floor", "ceiling", "wall"]:
			e.append("module %s: unknown mount" % id)
		var sc: Array = m.get("scale", [1, 1])
		if sc.size() != 2 or float(sc[0]) <= 0.0 or float(sc[1]) < float(sc[0]):
			e.append("module %s: invalid scale range" % id)
		if float(m.get("rotation_step_deg", 90)) <= 0.0:
			e.append("module %s: rotation step must be positive" % id)
		if float(m.get("lod", {}).get("visibility_end_m", 1.0)) <= 0.0:
			e.append("module %s: LOD visibility range must be positive" % id)
		if String(m.get("collision", "none")) == "asset" and String(Assets.info(aid).get("collision", "")) == "":
			e.append("module %s: asset collision requested but %s has none" % [id, aid])
		var col := String(Assets.info(aid).get("collision", ""))
		if col != "" and not col.ends_with("_collision.glb"):
			e.append("module %s: collision file naming '%s'" % [id, col])
	return e


# -------------------------------------------------------------- placement

## Checks one placement; returns a list of problems (empty = valid).
func check(module_id: String, xform: Transform3D, zone: String, depth: int) -> Array:
	var e: Array = []
	var m := module(module_id)
	if m.is_empty():
		return ["unknown module '%s'" % module_id]
	if not zone in m.get("zones", []):
		e.append("%s not allowed in zone %s" % [module_id, zone])
	var aid := String(m["asset"])
	var sc := xform.basis.get_scale()
	var srange: Array = m.get("scale", [1, 1])
	if sc.x < float(srange[0]) - 1e-3 or sc.x > float(srange[1]) + 1e-3:
		e.append("%s scale %.2f outside %s" % [module_id, sc.x, str(srange)])
	var step := float(m.get("rotation_step_deg", 90))
	if step > 1.0:
		var yaw := rad_to_deg(xform.basis.get_euler().y)
		var rem := fposmod(yaw + 1e-3, step)
		if rem > 0.05 and rem < step - 0.05:
			e.append("%s yaw %.1f not a multiple of %.0f" % [module_id, yaw, step])
	var box := _world_aabb(aid, xform)
	var zdef: Dictionary = data.get("zones", {}).get(zone, {})
	if not zdef.is_empty():
		var zx: Array = zdef["x"]
		var zz: Array = zdef["z"]
		var mg := float(zdef.get("margin_m", 0.0))
		if box.position.x < float(zx[0]) + mg - 1e-3 or box.end.x > float(zx[1]) - mg + 1e-3 \
				or box.position.z < float(zz[0]) + mg - 1e-3 or box.end.z > float(zz[1]) - mg + 1e-3:
			e.append("%s at %s leaves zone %s" % [module_id, _fmt(xform.origin), zone])
	var tol: Dictionary = data.get("tolerances", {})
	if rock != null and zone.begins_with("gallery") and depth > 0:
		match String(m.get("mount", "floor")):
			"floor":
				var fy := rock.floor_at(depth, xform.origin.x)
				if box.position.y > fy + float(tol.get("ground_m", 0.3)) or box.position.y < fy - float(tol.get("embed_m", 0.25)) - 0.2:
					e.append("%s floats or sinks: bottom %.2f vs floor %.2f" % [module_id, box.position.y, fy])
			"ceiling":
				var cy := rock.ceiling_at(depth, xform.origin.x, xform.origin.z)
				if absf(box.end.y - cy) > float(tol.get("ceiling_m", 0.45)):
					e.append("%s not on the ceiling: top %.2f vs ceiling %.2f" % [module_id, box.end.y, cy])
			"wall":
				pass
		if bool(m.get("solid", true)) and zone == "gallery":
			var wk: Dictionary = data.get("walkway", {})
			var wz: Array = wk.get("z", [-3.6, -2.6])
			var wx: Array = wk.get("x", [-11.0, 19.0])
			if box.end.z > float(wz[0]) and box.position.z < float(wz[1]) and box.end.x > float(wx[0]) and box.position.x < float(wx[1]):
				e.append("%s at %s blocks the gallery walkway" % [module_id, _fmt(xform.origin)])
	if bool(m.get("solid", true)):
		var clear := float(m.get("clearance_m", 0.1))
		var flat := Rect2(Vector2(box.position.x, box.position.z), Vector2(box.size.x, box.size.z)).grow(clear * 0.5)
		for r in records:
			if not r["solid"] or r["zone"] != zone or int(r["depth"]) != depth:
				continue
			var other: Rect2 = r["rect"]
			var y_overlap: bool = box.position.y < float(r["y1"]) and box.end.y > float(r["y0"])
			if y_overlap and flat.intersects(other.grow(float(r["clear"]) * 0.5)):
				var inter := flat.intersection(other)
				if inter.get_area() > 0.02:
					e.append("%s at %s intersects %s" % [module_id, _fmt(xform.origin), r["module"]])
	return e


func _world_aabb(aid: String, xform: Transform3D) -> AABB:
	return xform * Assets.bounds(aid)


static func _fmt(v: Vector3) -> String:
	return "(%.1f, %.1f, %.1f)" % [v.x, v.y, v.z]


## Registers a placement as solid space (without instancing), e.g. veins,
## facilities and the rails so later props avoid them.
func reserve(module_or_asset: String, xform: Transform3D, zone: String, depth: int, clearance: float = 0.1) -> void:
	var aid := String(module(module_or_asset).get("asset", module_or_asset))
	var box := _world_aabb(aid, xform)
	records.append({"module": module_or_asset, "zone": zone, "depth": depth, "solid": true, "clear": clearance,
		"rect": Rect2(Vector2(box.position.x, box.position.z), Vector2(box.size.x, box.size.z)), "y0": box.position.y, "y1": box.end.y})


## Validates and instances placements of one module under `parent`
## (batched as MultiMesh when the module allows it). Returns the node(s).
func place_many(parent: Node3D, module_id: String, xforms: Array, zone: String, depth: int) -> Array:
	var m := module(module_id)
	var ok: Array = []
	for x in xforms:
		var problems := check(module_id, x, zone, depth)
		if not problems.is_empty():
			for p in problems:
				errors.append("depth %d: %s" % [depth, p] if depth > 0 else p)
			if enforce:
				continue
		ok.append(x)
		var box := _world_aabb(String(m.get("asset", "")), x)
		records.append({"module": module_id, "zone": zone, "depth": depth, "solid": bool(m.get("solid", true)),
			"clear": float(m.get("clearance_m", 0.1)),
			"rect": Rect2(Vector2(box.position.x, box.position.z), Vector2(box.size.x, box.size.z)), "y0": box.position.y, "y1": box.end.y})
	if ok.is_empty() or m.is_empty():
		return []
	var layer := Atmosphere.LAYER_UNDERGROUND if zone.begins_with("gallery") else Atmosphere.LAYER_SURFACE
	var lod_end := float(m.get("lod", {}).get("visibility_end_m", 80.0))
	if bool(m.get("batch", true)) and not bool(m.get("animated", false)):
		return Scatter.place(parent, String(m["asset"]), ok, layer, zone == "surface", lod_end)
	var nodes: Array = []
	for x in ok:
		var inst := Assets.instantiate(String(m["asset"]), "", true)
		inst.transform = x
		parent.add_child(inst)
		nodes.append(inst)
	return nodes
