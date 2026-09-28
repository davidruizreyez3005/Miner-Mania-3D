class_name NavGrid
extends RefCounted
## Walkable area of one floor (the surface camp or one gallery) as a grid of
## cells with A* paths (AStarGrid2D, 8-way without corner cutting) and
## line-of-sight smoothing. Obstacles come from facility footprints and the
## validated module placements, so agents walk around machines and props.
## Coordinates are world x/z packed in Vector2 (x, z).

var origin := Vector2.ZERO
var cell := 0.5
var size := Vector2i.ZERO
var astar := AStarGrid2D.new()


func _init(rect: Rect2, cell_size: float = 0.5) -> void:
	cell = cell_size
	origin = rect.position
	size = Vector2i(maxi(1, ceili(rect.size.x / cell)), maxi(1, ceili(rect.size.y / cell)))
	astar.region = Rect2i(Vector2i.ZERO, size)
	astar.cell_size = Vector2(cell, cell)
	astar.diagonal_mode = AStarGrid2D.DIAGONAL_MODE_ONLY_IF_NO_OBSTACLES
	astar.default_compute_heuristic = AStarGrid2D.HEURISTIC_OCTILE
	astar.default_estimate_heuristic = AStarGrid2D.HEURISTIC_OCTILE
	astar.update()


func to_cell(p: Vector2) -> Vector2i:
	return Vector2i(floori((p.x - origin.x) / cell), floori((p.y - origin.y) / cell))


func to_world(c: Vector2i) -> Vector2:
	return origin + (Vector2(c) + Vector2(0.5, 0.5)) * cell


func in_bounds(c: Vector2i) -> bool:
	return c.x >= 0 and c.y >= 0 and c.x < size.x and c.y < size.y


func is_free_cell(c: Vector2i) -> bool:
	return in_bounds(c) and not astar.is_point_solid(c)


func is_free(p: Vector2) -> bool:
	return is_free_cell(to_cell(p))


func set_solid(c: Vector2i, solid: bool = true) -> void:
	if in_bounds(c):
		astar.set_point_solid(c, solid)


## Blocks every cell whose centre lies inside the axis-aligned world rect.
func block_rect(r: Rect2) -> void:
	var a := to_cell(r.position)
	var b := to_cell(r.end)
	for x in range(maxi(a.x, 0), mini(b.x, size.x - 1) + 1):
		for y in range(maxi(a.y, 0), mini(b.y, size.y - 1) + 1):
			if r.has_point(to_world(Vector2i(x, y))):
				astar.set_point_solid(Vector2i(x, y), true)


## Blocks a rotated rectangle: centre, half extents (local x/z) and yaw.
func block_box(center: Vector2, half: Vector2, yaw: float) -> void:
	var c := cos(yaw)
	var s := sin(yaw)
	var ext := Vector2(absf(half.x * c) + absf(half.y * s), absf(half.x * s) + absf(half.y * c))
	var a := to_cell(center - ext)
	var b := to_cell(center + ext)
	for x in range(maxi(a.x, 0), mini(b.x, size.x - 1) + 1):
		for y in range(maxi(a.y, 0), mini(b.y, size.y - 1) + 1):
			var d := to_world(Vector2i(x, y)) - center
			# Into the box frame (rotation about +Y maps local (x, z) to world).
			var lx := d.x * c - d.y * s
			var lz := d.x * s + d.y * c
			if absf(lx) <= half.x and absf(lz) <= half.y:
				astar.set_point_solid(Vector2i(x, y), true)


func free_count() -> int:
	var n := 0
	for x in size.x:
		for y in size.y:
			if not astar.is_point_solid(Vector2i(x, y)):
				n += 1
	return n


## Nearest walkable cell (ring search), or the cell itself when none is near.
func nearest_free(c: Vector2i, max_r: int = 12) -> Vector2i:
	c = Vector2i(clampi(c.x, 0, size.x - 1), clampi(c.y, 0, size.y - 1))
	if not astar.is_point_solid(c):
		return c
	for r in range(1, max_r + 1):
		var best := Vector2i(-1, -1)
		var best_d := INF
		for dx in range(-r, r + 1):
			for dy in [-r, r]:
				for q in [Vector2i(c.x + dx, c.y + dy), Vector2i(c.x + dy, c.y + dx)]:
					var cc: Vector2i = q
					if is_free_cell(cc):
						var dd := Vector2(cc - c).length_squared()
						if dd < best_d:
							best_d = dd
							best = cc
		if best.x >= 0:
			return best
	return c


func snap(p: Vector2) -> Vector2:
	var c := to_cell(p)
	if is_free_cell(c):
		return p
	return to_world(nearest_free(c))


## True when the straight segment only crosses walkable cells.
func line_free(a: Vector2, b: Vector2) -> bool:
	var d := b - a
	var n := maxi(1, ceili(d.length() / (cell * 0.45)))
	for i in n + 1:
		if not is_free(a + d * (float(i) / float(n))):
			return false
	return true


## Smoothed walking path from a to b (both snapped onto walkable cells).
## Never empty: without a route it returns the straight segment.
func path(a: Vector2, b: Vector2) -> PackedVector2Array:
	var sa := snap(a)
	var sb := snap(b)
	var out := PackedVector2Array([a])
	if sa.distance_to(a) > 0.01:
		out.append(sa)
	if line_free(sa, sb):
		out.append(sb)
	else:
		var ids := astar.get_id_path(to_cell(sa), to_cell(sb), true)
		if ids.is_empty():
			out.append(sb)
		else:
			var anchor := sa
			for i in range(1, ids.size()):
				var here := to_world(ids[i])
				var nxt := sb if i == ids.size() - 1 else to_world(ids[i + 1])
				if not line_free(anchor, nxt):
					out.append(here)
					anchor = here
			out.append(sb)
	if sb.distance_to(b) > 0.01:
		out.append(b)
	return out


static func length(pts: PackedVector2Array) -> float:
	var l := 0.0
	for i in range(1, pts.size()):
		l += pts[i - 1].distance_to(pts[i])
	return l
