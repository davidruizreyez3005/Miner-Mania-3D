class_name MineNav
extends RefCounted
## Navigation for agents: one walkable grid for the surface camp and one per
## dug-out gallery, plus the cage in the shaft that links the levels. A route
## is a list of legs - walk (a polyline with floor heights), wait (for the
## cage) and ride (vertical in the shaft) - that agents play back. Grids are
## rebuilt when the world changes (a facility is built, a depth is dug).
##
## Levels: 0 = surface, d >= 1 = depth d.

const CELL := 0.5
const EDGE_MARGIN := 0.8          # keep agents this far from the open cut face
const HEADROOM := 2.0             # minimum gallery height to walk (m)
const CAGE_WAIT := 1.2            # visual wait at the cage before a ride (s)

var world: MineWorld
var layout: WorldLayout
var grids: Dictionary = {}        # level -> NavGrid
var ride_mps := 5.0
var cage_x := -16.0
var cage_z := -4.0
var surface_rect := Rect2(Vector2(-44.0, -48.0), Vector2(92.0, 48.0))
var extra_obstacles: Array = []   # [Vector2 centre, Vector2 half] on the surface (decor)


func _init(w: MineWorld) -> void:
	world = w
	layout = w.layout
	var sh: Dictionary = layout.data.get("shaft", {})
	ride_mps = float(sh.get("ride_mps", 5.0))
	cage_x = float(sh.get("x", -16.0))
	cage_z = float(sh.get("z", -4.0))


# -------------------------------------------------------------- building

func rebuild_all() -> void:
	grids.clear()
	build_surface()
	for d in world.unlocked_depths():
		build_depth(int(d))


func build_surface() -> NavGrid:
	var g := NavGrid.new(surface_rect, CELL)
	# The open cut face in front of the camp.
	g.block_rect(Rect2(Vector2(surface_rect.position.x, -EDGE_MARGIN), Vector2(surface_rect.size.x, EDGE_MARGIN + 1.0)))
	for fv in world.facility_views.values():
		for b in (fv as FacilityView).blocked_boxes():
			g.block_box(b[0], b[1], float(b[2]))
	if world.lift_view:
		for b in world.lift_view.blocked_boxes():
			g.block_box(b[0], b[1], float(b[2]))
	for r in world.modules.records:
		# Placed props block; reservations (future facility tiers, roads,
		# footpaths, walk stops) only keep dressing away.
		if r["zone"] == "surface" and r["solid"] and not r.get("nav_ignore", false):
			g.block_rect((r["rect"] as Rect2).grow(0.15))
	for o in extra_obstacles:
		g.block_box(o[0], o[1], 0.0)
	# Keep the named stops reachable even if a footprint grazes them.
	for loc in ["surface:landing", "surface:rest", "surface:gate", "plant"]:
		var p := layout.position(loc)
		g.set_solid(g.to_cell(Vector2(p.x, p.z)), false)
	grids[0] = g
	return g


func build_depth(d: int) -> NavGrid:
	var rock := world.rock
	var rect := Rect2(Vector2(rock.gal_x0, -rock.gal_depth), Vector2(rock.gal_x1 - rock.gal_x0, rock.gal_depth))
	var g := NavGrid.new(rect, CELL)
	for cx in g.size.x:
		for cy in g.size.y:
			var p := g.to_world(Vector2i(cx, cy))
			var solid := p.y > -EDGE_MARGIN or p.y < -rock.back_depth(p.x) + 0.45
			if not solid:
				solid = rock.ceiling_at(d, p.x, p.y) - rock.floor_at(d, p.x) < HEADROOM
			if solid:
				g.set_solid(Vector2i(cx, cy), true)
	for r in world.modules.records:
		if int(r["depth"]) == d and r["solid"] and String(r["zone"]).begins_with("gallery"):
			var rr: Rect2 = r["rect"]
			# Rails and other low pieces can be stepped over.
			if float(r["y1"]) - float(r["y0"]) < 0.3:
				continue
			g.block_rect(rr.grow(0.12))
	for loc in ["landing", "station", "rest", "face"]:
		var p := layout.position("depth:%d:%s" % [d, loc])
		g.set_solid(g.nearest_free(g.to_cell(Vector2(p.x, p.z))), false)
	grids[d] = g
	return g


func grid(level: int) -> NavGrid:
	if not grids.has(level):
		if level == 0:
			return build_surface()
		return build_depth(level)
	return grids[level]


# ------------------------------------------------------------------ floors

func floor_y(level: int, x: float, z: float) -> float:
	if level <= 0:
		return world.ground_height(x, z)
	return world.rock.floor_at(level, x)


func landing(level: int) -> Vector3:
	var p := layout.landing(level)
	return Vector3(p.x, floor_y(level, p.x, p.z), p.z)


## Where riders stand in the cage (spread a little so groups do not overlap).
func cage_spot(level: int, slot: int = 0) -> Vector3:
	var off := Vector2(float(slot % 3) - 1.0, float(int(slot / 3) % 2) - 0.5) * Vector2(0.7, 0.8)
	var y := 0.35 if level <= 0 else world.content.depth_floor_y(level)
	return Vector3(cage_x + off.x, y, cage_z + off.y)


# ------------------------------------------------------------------ routes

## Legs from a point on one level to a point on another.
func route(from: Vector3, from_level: int, to: Vector3, to_level: int, rider_slot: int = 0) -> Array:
	var legs: Array = []
	if from_level == to_level:
		legs.append(walk_leg(from_level, from, to))
		return legs
	var la := landing(from_level)
	var lb := landing(to_level)
	legs.append(walk_leg(from_level, from, la))
	var ca := cage_spot(from_level, rider_slot)
	var cb := cage_spot(to_level, rider_slot)
	legs.append({"kind": "walk", "level": from_level, "pts": PackedVector3Array([la, ca]), "len": la.distance_to(ca)})
	legs.append({"kind": "wait", "level": from_level, "time": CAGE_WAIT, "pos": ca})
	legs.append({"kind": "ride", "from": ca, "to": cb, "from_level": from_level, "to_level": to_level,
		"time": absf(ca.y - cb.y) / ride_mps})
	legs.append({"kind": "walk", "level": to_level, "pts": PackedVector3Array([cb, lb]), "len": cb.distance_to(lb)})
	legs.append(walk_leg(to_level, lb, to))
	return legs


func walk_leg(level: int, a: Vector3, b: Vector3) -> Dictionary:
	var g := grid(level)
	var p2 := g.path(Vector2(a.x, a.z), Vector2(b.x, b.z))
	# Densify to ~1 m steps so the floor height follows the terrain / rock.
	var pts := PackedVector3Array()
	var total := 0.0
	for i in p2.size():
		if i == 0:
			pts.append(Vector3(p2[0].x, floor_y(level, p2[0].x, p2[0].y), p2[0].y))
			continue
		var s := p2[i - 1]
		var e := p2[i]
		var seg := s.distance_to(e)
		var n := maxi(1, ceili(seg / 1.0))
		for k in range(1, n + 1):
			var q := s.lerp(e, float(k) / float(n))
			pts.append(Vector3(q.x, floor_y(level, q.x, q.y), q.y))
		total += seg
	if pts.size() == 1:
		pts.append(pts[0])
	return {"kind": "walk", "level": level, "pts": pts, "len": total}


## Seconds a route takes at walking speed `mps` (rides and waits included).
static func route_time(legs: Array, mps: float) -> float:
	var t := 0.0
	for l in legs:
		match String(l["kind"]):
			"walk":
				t += float(l["len"]) / maxf(mps, 0.1)
			"wait", "ride":
				t += float(l["time"])
	return t


static func route_walk_len(legs: Array) -> float:
	var t := 0.0
	for l in legs:
		if String(l["kind"]) == "walk":
			t += float(l["len"])
	return t
