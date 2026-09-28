class_name TerrainBuilder
extends RefCounted
## The valley around the mine: a heightfield mesh (flat camp plateau, hills
## rising behind and beside it, the straight cut edge at z = 0 where the
## cutaway face begins), painted with splat weights (grass / dirt road /
## gravel pads / rock) from the layout: roads and facility pads are gravel,
## paths are dirt. A second low-detail mesh forms the distant mountain range.

const CELL := 2.0

var layout: WorldLayout
var rng_noise := FastNoiseLite.new()
var x_range := Vector2(-60.0, 64.0)
var z_range := Vector2(-96.0, 0.0)
var camp_z := -44.0
var pads: Array = []            # [Rect2 in xz] gravel pads under facilities
var roads: Array = []           # [PackedVector2Array polyline, width]


func _init(l: WorldLayout) -> void:
	layout = l
	rng_noise.seed = 991
	rng_noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	rng_noise.frequency = 0.02
	rng_noise.fractal_octaves = 4
	var b: Dictionary = l.data.get("bounds", {})
	var bx: Array = b.get("x", [-46.0, 50.0])
	x_range = Vector2(float(bx[0]) - 14.0, float(bx[1]) + 14.0)


func add_pad(center: Vector2, size: Vector2) -> void:
	pads.append(Rect2(center - size * 0.5, size))


func add_road(points: PackedVector2Array, width: float) -> void:
	roads.append([points, width])


func height(x: float, z: float) -> float:
	## 0 on the camp plateau (and exactly 0 along the cut edge), hills beyond.
	var n := rng_noise.get_noise_2d(x, z)
	var back := clampf((camp_z - z) / 30.0, 0.0, 1.0)
	var left := clampf((x_range.x + 16.0 - x) / 14.0, 0.0, 1.0)
	var right := clampf((x - (x_range.y - 14.0)) / 14.0, 0.0, 1.0)
	var rise := back * back * (16.0 + 10.0 * n) + (left * left + right * right) * (8.0 + 5.0 * n)
	var ripple := 0.18 * rng_noise.get_noise_2d(x * 3.0, z * 3.0)
	var edge := clampf(-z / 3.0, 0.0, 1.0)            # 0 at the cut edge
	var flat := 1.0 - _pad_weight(Vector2(x, z), 3.0)
	return (rise + ripple * flat) * edge


func _pad_weight(p: Vector2, feather: float) -> float:
	var w := 0.0
	for r in pads:
		var rr: Rect2 = r
		var dx := maxf(maxf(rr.position.x - p.x, p.x - rr.end.x), 0.0)
		var dz := maxf(maxf(rr.position.y - p.y, p.y - rr.end.y), 0.0)
		var d := sqrt(dx * dx + dz * dz)
		w = maxf(w, 1.0 - clampf(d / feather, 0.0, 1.0))
	return w


func _road_weight(p: Vector2) -> float:
	var w := 0.0
	for rd in roads:
		var pts: PackedVector2Array = rd[0]
		var width: float = rd[1]
		for i in pts.size() - 1:
			var q := Geometry2D.get_closest_point_to_segment(p, pts[i], pts[i + 1])
			var d := p.distance_to(q)
			w = maxf(w, 1.0 - smoothstep(width * 0.5, width * 0.5 + 1.5, d))
	return w


func weights(x: float, z: float, h: float) -> Color:
	var p := Vector2(x, z)
	var pad := _pad_weight(p, 1.5)
	var road := _road_weight(p)
	var n := 0.5 + 0.5 * rng_noise.get_noise_2d(x * 2.3 + 40.0, z * 2.3)
	var dirt := clampf(road + (1.0 - pad) * 0.35 * smoothstep(0.55, 0.8, n) * (1.0 - clampf(h / 6.0, 0.0, 1.0)), 0.0, 1.0)
	var gravel := pad
	var rock := clampf((h - 12.0) / 10.0, 0.0, 1.0) * 0.6
	var grass := clampf(1.0 - dirt - gravel - rock, 0.0, 1.0)
	# Worn camp ground: less grass inside the camp.
	if z > camp_z and h < 1.0:
		var worn := 0.45 * smoothstep(0.3, 0.7, n)
		grass *= 1.0 - worn
		dirt += worn * 0.6
		gravel += worn * 0.4
	return Color(grass, dirt, gravel, rock)


func build() -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var nx := int(ceilf((x_range.y - x_range.x) / CELL))
	var nz := int(ceilf((z_range.y - z_range.x) / CELL))
	var verts: Array = []
	for iz in nz + 1:
		var row: Array = []
		for ix in nx + 1:
			var x := x_range.x + float(ix) * CELL
			var z := z_range.x + float(iz) * CELL
			var h := height(x, z)
			row.append(Vector3(x, h, z))
		verts.append(row)
	for iz in nz:
		for ix in nx:
			var a: Vector3 = verts[iz][ix]
			var b: Vector3 = verts[iz][ix + 1]
			var c: Vector3 = verts[iz + 1][ix + 1]
			var d: Vector3 = verts[iz + 1][ix]
			for p in [a, b, c, a, c, d]:
				st.set_color(weights(p.x, p.z, p.y))
				st.add_vertex(p)
	st.generate_normals()
	return st.commit()


## Distant mountains: a coarse ring of peaks behind the valley.
func build_mountains() -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var n := FastNoiseLite.new()
	n.seed = 4242
	n.frequency = 0.008
	n.fractal_octaves = 5
	n.fractal_type = FastNoiseLite.FRACTAL_RIDGED
	var step := 10.0
	var xs := range(-320, 330, int(step))
	var zs := range(-330, -88, int(step))
	var grid: Array = []
	for z in zs:
		var row: Array = []
		for x in xs:
			var far := clampf((-88.0 - float(z)) / 120.0, 0.0, 1.0)
			var side := clampf((absf(float(x)) - 60.0) / 140.0, 0.0, 1.0)
			var h := (0.5 + 0.5 * n.get_noise_2d(float(x), float(z))) * (40.0 + 110.0 * maxf(far, side * 0.8))
			h = h * smoothstep(0.0, 0.25, far + side * 0.3) + 14.0 * far
			row.append(Vector3(float(x), h, float(z)))
		grid.append(row)
	for iz in grid.size() - 1:
		for ix in (grid[iz] as Array).size() - 1:
			var a: Vector3 = grid[iz][ix]
			var b: Vector3 = grid[iz][ix + 1]
			var c: Vector3 = grid[iz + 1][ix + 1]
			var d: Vector3 = grid[iz + 1][ix]
			for p in [a, b, c, a, c, d]:
				var rockw := clampf((p.y - 25.0) / 30.0, 0.0, 1.0)
				st.set_color(Color(1.0 - rockw, 0.0, 0.0, rockw))
				st.add_vertex(p)
	st.generate_normals()
	return st.commit()
