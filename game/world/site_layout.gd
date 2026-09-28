class_name SiteLayout
extends RefCounted
## Where every facility unit of the surface camp stands, for any level tier,
## computed from data (layout plots + asset bounds) without building nodes -
## shared by the facility views, the navigation grid and the automated
## layout validation (no unit of one facility may clip another facility, the
## road, the headframe, the camp's walk stops or the cut face, at any tier).

## Level at which each extra visual tier appears (index = tier - 1).
const TIER_LEVELS := {"silo": [1, 10, 25, 50], "conveyor": [1, 25, 100], "generator": [1, 25, 100],
	"pump": [1, 25], "crusher": [1, 50], "washer": [1, 50], "sorter": [1, 50], "smelter": [1, 50], "refinery": [1, 50],
	"warehouse": [1, 10, 50], "office": [1, 20], "workshop": [1], "depot": [1, 10]}
## Processing machines add a second machine behind the first at tier 2.
const TWINS := ["crusher", "washer", "sorter", "smelter", "refinery"]
const TWIN_GAP := 1.2
const ROAD_WIDTH := 6.0


static func tier_for_level(fid: String, level: int, built: bool) -> int:
	if not built:
		return 0
	var t := 0
	for lv in TIER_LEVELS.get(fid, [1]):
		if level >= int(lv):
			t += 1
	return t


static func max_tier(fid: String) -> int:
	return (TIER_LEVELS.get(fid, [1]) as Array).size()


## Axis-aligned footprint (x, z) of an asset rotated by yaw about its origin.
static func footprint(asset_id: String, yaw_deg: float) -> Rect2:
	var b := Assets.bounds(asset_id)
	var corners := [Vector3(b.position.x, 0, b.position.z), Vector3(b.end.x, 0, b.position.z),
		Vector3(b.end.x, 0, b.end.z), Vector3(b.position.x, 0, b.end.z)]
	var basis := Basis(Vector3.UP, deg_to_rad(yaw_deg))
	var lo := Vector2(INF, INF)
	var hi := Vector2(-INF, -INF)
	for c in corners:
		var r: Vector3 = basis * c
		lo = Vector2(minf(lo.x, r.x), minf(lo.y, r.z))
		hi = Vector2(maxf(hi.x, r.x), maxf(hi.y, r.z))
	return Rect2(lo, hi - lo)


## Unit offsets in the facility's local space for a visual tier.
static func unit_offsets(fid: String, plot: Dictionary, asset_id: String, tier: int) -> Array:
	var out: Array = []
	if tier <= 0:
		return out
	var yaw := float(plot.get("yaw", 0.0))
	match fid:
		"silo":
			var sp: Array = plot.get("spacing", [3.8, 0.0])
			var counts: Array = plot.get("count_by_tier", [1, 2, 3, 4])
			var n := int(counts[clampi(tier - 1, 0, counts.size() - 1)])
			for i in n:
				out.append(Vector3(float(sp[0]) * i, 0, float(sp[1]) * i))
		"conveyor":
			var seg := float(plot.get("segment", 6.77))
			var segs := int(plot.get("segments", 2))
			for i in segs:
				out.append(Vector3(0, 0, -seg * i))
			if tier >= 2:
				for i in segs:
					out.append(Vector3(2.2, 0, -seg * i))
		"depot":
			pass                          # the yard is empty; SalesView drives the trucks
		_:
			out.append(Vector3.ZERO)
			if tier >= 2 and fid in TWINS:
				# The twin stands directly behind the first machine (world -z),
				# so production rows never grow into their neighbours.
				var fp := footprint(asset_id, yaw)
				var back := Vector3(0, 0, -(fp.size.y + TWIN_GAP))
				out.append(Basis(Vector3.UP, -deg_to_rad(yaw)) * back)
	return out


## World transform of a facility's plot (y from the terrain when given).
static func plot_transform(plot: Dictionary, ground_y: float = 0.0) -> Transform3D:
	var pos: Array = plot.get("pos", [0, 0])
	return Transform3D(Basis(Vector3.UP, deg_to_rad(float(plot.get("yaw", 0.0)))), Vector3(float(pos[0]), ground_y, float(pos[1])))


## World-space xz rects of every unit of a facility at a tier.
static func unit_rects(fid: String, plot: Dictionary, asset_id: String, tier: int) -> Array:
	var out: Array = []
	var xf := plot_transform(plot)
	var fp := footprint(asset_id, float(plot.get("yaw", 0.0)))
	for off in unit_offsets(fid, plot, asset_id, tier):
		var o: Vector3 = xf.basis * (off as Vector3)
		out.append(Rect2(fp.position + Vector2(xf.origin.x + o.x, xf.origin.z + o.z), fp.size))
	return out


## The road band trucks drive along (xz rects, one per polyline segment).
static func road_rects(layout: WorldLayout) -> Array:
	return _band_rects(layout.data.get("surface", {}).get("road", []), ROAD_WIDTH)


## The camp's footpaths (xz rects), which must stay clear of machines.
static func path_rects(layout: WorldLayout) -> Array:
	var out: Array = []
	for p in layout.data.get("surface", {}).get("paths", []):
		out.append_array(_band_rects(p.get("points", []), float(p.get("width", 2.4))))
	return out


static func _band_rects(pts: Array, width: float) -> Array:
	var out: Array = []
	for i in range(1, pts.size()):
		var a := Vector2(float(pts[i - 1][0]), float(pts[i - 1][1]))
		var b := Vector2(float(pts[i][0]), float(pts[i][1]))
		var lo := Vector2(minf(a.x, b.x), minf(a.y, b.y)) - Vector2.ONE * width * 0.5
		var hi := Vector2(maxf(a.x, b.x), maxf(a.y, b.y)) + Vector2.ONE * width * 0.5
		out.append(Rect2(lo, hi - lo))
	return out


## Every problem with the camp layout at maximum tiers (empty = valid).
static func problems(content: ContentDB, layout: WorldLayout) -> Array:
	var e: Array = []
	var units: Array = []            # [fid, Rect2]
	for fac in content.facilities:
		var fid := String(fac["id"])
		var plot := layout.plot(String(fac.get("plot", fid)))
		if plot.is_empty():
			e.append("facility %s has no plot" % fid)
			continue
		var aid := String(fac.get("asset", ""))
		if not Assets.has(aid):
			e.append("facility %s: asset %s missing" % [fid, aid])
			continue
		var tier := max_tier(fid)
		if fid == "headframe":
			tier = 1
		for r in unit_rects(fid, plot, aid, tier):
			units.append([fid, r])
	var b: Dictionary = layout.data.get("bounds", {})
	var bx: Array = b.get("x", [-46, 50])
	var bz: Array = b.get("z", [-62, 0])
	var bounds := Rect2(Vector2(float(bx[0]), float(bz[0])), Vector2(float(bx[1]) - float(bx[0]), float(bz[1]) - float(bz[0])))
	for u in units:
		var r: Rect2 = u[1]
		if not bounds.encloses(r):
			e.append("facility %s unit %s leaves the site bounds" % [u[0], r])
		if r.end.y > float(layout.data.get("cut_face_z", 0.0)) - 0.3:
			e.append("facility %s unit reaches over the cut face (z end %.2f)" % [u[0], r.end.y])
	for i in units.size():
		for j in range(i + 1, units.size()):
			if units[i][0] == units[j][0]:
				continue
			var inter := (units[i][1] as Rect2).intersection(units[j][1])
			if inter.get_area() > 0.01:
				e.append("facility %s clips %s (%.2f m2)" % [units[i][0], units[j][0], inter.get_area()])
	for rr in road_rects(layout):
		for u in units:
			if u[0] == "depot":
				continue
			var inter2 := (u[1] as Rect2).intersection(rr)
			if inter2.get_area() > 0.01:
				e.append("facility %s stands on the road (%.2f m2)" % [u[0], inter2.get_area()])
	for pr in path_rects(layout):
		for u in units:
			var inter3 := (u[1] as Rect2).intersection(pr)
			if inter3.get_area() > 0.01:
				e.append("facility %s blocks a footpath (%.2f m2)" % [u[0], inter3.get_area()])
	for loc in ["surface:landing", "surface:rest", "surface:gate", "plant"]:
		var p := layout.position(loc)
		for u in units:
			if (u[1] as Rect2).grow(0.2).has_point(Vector2(p.x, p.z)):
				e.append("walk stop %s is inside facility %s" % [loc, u[0]])
	for fac in content.facilities:
		var fid := String(fac["id"])
		var plot := layout.plot(String(fac.get("plot", fid)))
		for key in ["work", "repair"]:
			var w: Array = plot.get(key, [0, 0])
			var xf := plot_transform(plot)
			var p2: Vector3 = xf.origin + Vector3(float(w[0]), 0, float(w[1]))
			for u in units:
				if u[0] != fid and (u[1] as Rect2).has_point(Vector2(p2.x, p2.z)):
					e.append("%s %s point is inside facility %s" % [fid, key, u[0]])
	return e
