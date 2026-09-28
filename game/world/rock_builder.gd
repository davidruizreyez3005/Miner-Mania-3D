class_name RockBuilder
extends RefCounted
## Procedural geometry for the mountain cutaway: the cut face (the plane
## z = 0 through the mountain, seen by the camera), the gallery interiors
## (one per unlocked depth) and the main shaft. Everything is generated from
## the layout data and seeded noise, so it is deterministic, and the openings
## in the face use exactly the same boundary functions as the interior
## meshes, so floors and ceilings meet the face without gaps.
##
## Frame: X right, Y up, Z toward the camera; the face is at z = 0 and the
## rock lies at z < 0. Galleries run along X.

const STRIP := 1.0          # face strip width (m); layout x boundaries are integers
const FACE_ROW := 1.5       # max vertical segment of the face (m)
const SWEEP_STEP := 0.75    # gallery sweep step along x (m)
const END_TAPER := 4.5      # length of the rounded far end of a gallery (m)

var layout: WorldLayout
var content: ContentDB
var face_x := Vector2(-60.0, 64.0)
var bottom_y := -110.0
var gal_x0 := -13.0
var gal_x1 := 23.0
var gal_depth := 9.0
var gal_h := 6.5
var shaft_x0 := -19.0
var shaft_x1 := -13.0
var shaft_z0 := -7.0
var _noise := FastNoiseLite.new()


func _init(l: WorldLayout) -> void:
	layout = l
	content = l.content
	var g: Dictionary = l.data.get("gallery", {})
	gal_x0 = float(g.get("x_min", -13.0))
	gal_x1 = float(g.get("x_max", 23.0))
	gal_depth = -float(g.get("z_back", -9.0))
	gal_h = float(g.get("height", 6.5))
	var sh: Dictionary = l.data.get("shaft", {})
	var cx: Array = sh.get("cells_x", [-19.0, -13.0])
	shaft_x0 = float(cx[0])
	shaft_x1 = float(cx[1])
	shaft_z0 = -float(sh.get("depth", 7.0))
	var b: Dictionary = l.data.get("bounds", {})
	var bx: Array = b.get("x", [-46.0, 50.0])
	face_x = Vector2(float(bx[0]) - 14.0, float(bx[1]) + 14.0)
	bottom_y = content.depth_floor_y(content.depth_count()) - 16.0
	_noise.seed = 7117
	_noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	_noise.frequency = 0.35
	_noise.fractal_type = FastNoiseLite.FRACTAL_FBM
	_noise.fractal_octaves = 3


func n2(x: float, y: float, salt: float) -> float:
	return _noise.get_noise_2d(x + salt * 97.0, y + salt * 57.0)


# ------------------------------------------------------------ gallery shape

func taper(x: float) -> float:
	return smoothstep(gal_x1 - END_TAPER, gal_x1, x)


## Floor height offset of gallery d at the face (z = 0) for x.
func floor_front(d: int, x: float) -> float:
	var t := taper(x)
	return 0.12 * n2(x * 0.7, 0.0, float(d)) + t * t * gal_h * 0.18


## Ceiling height of gallery d at the face (z = 0), relative to its floor.
func ceil_front(d: int, x: float) -> float:
	var t := taper(x)
	var land := 1.0 - smoothstep(gal_x0, gal_x0 + 2.5, x)          # square landing mouth at the shaft
	var c := gal_h + 0.45 * n2(x * 0.45, 3.0, float(d)) * (1.0 - land)
	return c - (1.0 - sqrt(maxf(0.0, 1.0 - t * t))) * gal_h * 0.62


## Walkable floor height of gallery d at x (world y).
func floor_at(d: int, x: float) -> float:
	return content.depth_floor_y(d) + floor_front(d, x)


## Ceiling height of gallery d at (x, z) (world y), including the vault.
func ceiling_at(d: int, x: float, z: float) -> float:
	var D := back_depth(x)
	var vault := 0.35 * sin(PI * clampf(-z / maxf(D, 0.1), 0.0, 1.0)) * (1.0 - smoothstep(-1.2, 0.0, z))
	return content.depth_floor_y(d) + ceil_front(d, x) + vault


func back_depth(x: float) -> float:
	var t := taper(x)
	return gal_depth * (1.0 - 0.8 * (1.0 - sqrt(maxf(0.0, 1.0 - t * t))))


## Gallery cross-section at x: points (z, y) from the front floor edge, along
## the floor, round the lower corner, up the back wall, round the upper
## corner, along the (slightly vaulted) ceiling to the front ceiling edge;
## plus per-point displacement amplitude along the normal into the rock.
func profile(d: int, x: float) -> Array:
	var D := back_depth(x)
	var yf := floor_front(d, x)
	var yc := ceil_front(d, x)
	var H := yc - yf
	var r := minf(1.4, H * 0.25)
	var pts: Array = []
	var amp: Array = []
	var nf := 7
	for i in nf:
		var z := -(D - r) * float(i) / float(nf - 1)
		pts.append(Vector2(z, yf))
		amp.append(0.06 * smoothstep(0.0, 1.5, -z))
	var c1 := Vector2(-D + r, yf + r)                     # lower back corner, from straight down to -z
	for i in range(1, 4):
		var th := deg_to_rad(-90.0 - 90.0 * float(i) / 4.0)
		pts.append(c1 + Vector2(cos(th), sin(th)) * r)
		amp.append(0.25)
	var nw := 6
	for i in nw:
		pts.append(Vector2(-D, yf + r + (H - 2.0 * r) * float(i) / float(nw - 1)))
		amp.append(0.5)
	var c2 := Vector2(-D + r, yc - r)                     # upper back corner, from -z to straight up
	for i in range(1, 4):
		var th2 := deg_to_rad(180.0 - 90.0 * float(i) / 4.0)
		pts.append(c2 + Vector2(cos(th2), sin(th2)) * r)
		amp.append(0.3)
	var nc := 7
	for i in nc:
		var z2 := -(D - r) + (D - r) * float(i) / float(nc - 1)
		var vault := 0.35 * sin(PI * clampf(-z2 / maxf(D, 0.1), 0.0, 1.0)) * (1.0 - smoothstep(-1.2, 0.0, z2))
		pts.append(Vector2(z2, yc + vault))
		amp.append(0.3 * smoothstep(0.0, 1.5, -z2))
	return [pts, amp]


# ----------------------------------------------------------------- the face

func build_face(unlocked: Array, shaft_bottom: float) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var x := face_x.x
	while x < face_x.y - 1e-4:
		var xa := x
		var xb := minf(x + STRIP, face_x.y)
		# Openings are defined per strip (between xa and xb) using the strip's inner edges.
		var inside_shaft := xa >= shaft_x0 - 1e-4 and xb <= shaft_x1 + 1e-4
		var ia: Array = []
		var ib: Array = []
		if inside_shaft:
			ia = [Vector2(shaft_bottom, 0.0)]
			ib = [Vector2(shaft_bottom, 0.0)]
		elif xa >= gal_x0 - 1e-4 and xb <= gal_x1 + 1e-4:
			var deepest_first := unlocked.duplicate()
			deepest_first.sort()
			deepest_first.reverse()                  # openings must run bottom-up like the spans
			for d in deepest_first:
				var fy := content.depth_floor_y(int(d))
				ia.append(Vector2(fy + floor_front(int(d), xa), fy + ceil_front(int(d), xa)))
				ib.append(Vector2(fy + floor_front(int(d), xb), fy + ceil_front(int(d), xb)))
		# Solid spans between openings.
		var ya := bottom_y
		var yb := bottom_y
		for k in ia.size():
			_face_span(st, xa, xb, ya, yb, ia[k].x, ib[k].x, unlocked)
			ya = ia[k].y
			yb = ib[k].y
		_face_span(st, xa, xb, ya, yb, 0.0, 0.0, unlocked)
		x = xb
	st.generate_normals()
	return st.commit()


func _face_span(st: SurfaceTool, xa: float, xb: float, y0a: float, y0b: float, y1a: float, y1b: float, unlocked: Array) -> void:
	var h := maxf(y1a - y0a, y1b - y0b)
	if h <= 0.01:
		return
	var rows := maxi(1, int(ceilf(h / FACE_ROW)))
	for r in rows:
		var fa0 := lerpf(y0a, y1a, float(r) / rows)
		var fa1 := lerpf(y0a, y1a, float(r + 1) / rows)
		var fb0 := lerpf(y0b, y1b, float(r) / rows)
		var fb1 := lerpf(y0b, y1b, float(r + 1) / rows)
		var p00 := Vector3(xa, fa0, 0.0)
		var p01 := Vector3(xa, fa1, 0.0)
		var p10 := Vector3(xb, fb0, 0.0)
		var p11 := Vector3(xb, fb1, 0.0)
		# Godot front faces are clockwise as seen by the camera (looking along -Z).
		for tri in [[p00, p11, p10], [p00, p01, p11]]:
			for p in tri:
				st.set_color(_face_color(p, unlocked))
				st.add_vertex(p)


func _face_color(p: Vector3, _unlocked: Array) -> Color:
	## Each depth's band of the cut face takes that depth's strata colour
	## (blended across band boundaries), darkening toward the bottom.
	var spacing := content.level_spacing
	var f := clampf(-p.y / spacing, 0.0, float(content.depth_count()) - 0.001)
	var d0 := int(floorf(f)) + 1
	var t := f - floorf(f)
	var c0 := _band_tint(d0)
	var c1 := _band_tint(mini(d0 + 1, content.depth_count()))
	var blend := smoothstep(0.8, 1.0, t)
	var c := c0.lerp(c1, blend)
	var deepest := bottom_y + 16.0
	var ao := clampf(1.0 - (deepest - p.y) / 16.0 * 0.7, 0.3, 1.0) if p.y < deepest else 1.0
	return Color(c.r * ao, c.g * ao, c.b * ao, 0.0)


var _tints: Dictionary = {}


func _band_tint(d: int) -> Color:
	if _tints.has(d):
		return _tints[d]
	var env: Dictionary = content.depth(d).get("environment", {})
	var c := Color(String(env.get("strata_tint", "#6e5842")))
	var lum := maxf(0.05, (c.r + c.g + c.b) / 3.0)
	# Keep hue, normalise brightness (the texture carries tone), fade deeper.
	var n := Color(c.r / lum, c.g / lum, c.b / lum) * (1.0 - 0.06 * float(d - 1))
	var out := Color(1, 1, 1).lerp(n, 0.55)
	_tints[d] = out
	return out


# ------------------------------------------------------------ gallery mesh

func build_gallery(d: int) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var fy := content.depth_floor_y(d)
	var rings: Array = []
	var x := gal_x0
	var xs: Array = []
	while x < gal_x1 - 1e-4:
		xs.append(x)
		x += SWEEP_STEP
	xs.append(gal_x1 - 0.02)
	var wet := 0.0
	if "water" in content.depth(d).get("hazards", []):
		wet = 0.6
	for xv in xs:
		var pr := profile(d, xv)
		var pts: Array = pr[0]
		var amps: Array = pr[1]
		var ring: Array = []
		for i in pts.size():
			var p: Vector2 = pts[i]
			var prev: Vector2 = pts[maxi(i - 1, 0)]
			var nxt: Vector2 = pts[mini(i + 1, pts.size() - 1)]
			var tang := (nxt - prev).normalized()
			var outward := Vector2(tang.y, -tang.x)          # into the rock
			var disp := float(amps[i]) * n2(xv * 0.55, float(i) * 0.37, float(d) + 11.0)
			var q := p + outward * disp
			ring.append(Vector3(xv, fy + q.y, q.x))
		rings.append(ring)
	for k in rings.size() - 1:
		var ra: Array = rings[k]
		var rb: Array = rings[k + 1]
		for i in ra.size() - 1:
			var a0: Vector3 = ra[i]
			var a1: Vector3 = ra[i + 1]
			var b0: Vector3 = rb[i]
			var b1: Vector3 = rb[i + 1]
			# Winding faces the cavity (the camera looks in from +Z).
			for tri in [[a0, a1, b1], [a0, b1, b0]]:
				for p in tri:
					st.set_color(_gallery_color(p, fy, wet))
					st.add_vertex(p)
	# Far-end cap closing the tapered profile.
	var last: Array = rings[rings.size() - 1]
	var c := Vector3.ZERO
	for p in last:
		c += p
	c /= float(last.size())
	c.x = gal_x1 + 0.35
	for i in last.size() - 1:
		for tri in [[last[i], last[i + 1], c], [last[i + 1], last[i], c]]:     # both sides
			for p in tri:
				st.set_color(_gallery_color(p, fy, wet))
				st.add_vertex(p)
	st.generate_normals()
	return st.commit()


func _gallery_color(p: Vector3, fy: float, wet: float) -> Color:
	var rel := p.y - fy
	var ao := 1.0
	ao *= 1.0 - 0.35 * smoothstep(-gal_depth * 0.6, -gal_depth, p.z) * smoothstep(0.8, 0.0, rel)   # back-floor corner
	ao *= 1.0 - 0.25 * smoothstep(gal_h * 0.7, gal_h, rel) * smoothstep(-2.0, -gal_depth, p.z)     # ceiling
	var w := wet * (1.0 - smoothstep(0.0, 1.2, rel))
	return Color(ao, ao, ao, w)


# --------------------------------------------------------------- the shaft

func build_shaft(shaft_bottom: float, unlocked: Array) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var zb := shaft_z0
	var ystep := 2.0
	var y := shaft_bottom
	while y < -0.01:
		var y2 := minf(y + ystep, 0.0)
		# back wall
		_quad(st, Vector3(shaft_x0, y, zb), Vector3(shaft_x1, y, zb), Vector3(shaft_x1, y2, zb), Vector3(shaft_x0, y2, zb))
		# left wall (faces +X)
		_quad(st, Vector3(shaft_x0, y, 0.0), Vector3(shaft_x0, y, zb), Vector3(shaft_x0, y2, zb), Vector3(shaft_x0, y2, 0.0))
		# right wall (faces -X), leaving the gallery mouths open
		var open := false
		for d in unlocked:
			var fy := content.depth_floor_y(int(d))
			if y2 > fy + 0.01 and y < fy + gal_h - 0.01:
				open = true
		if not open:
			_quad(st, Vector3(shaft_x1, y, zb), Vector3(shaft_x1, y, 0.0), Vector3(shaft_x1, y2, 0.0), Vector3(shaft_x1, y2, zb))
		y = y2
	# Sump floor.
	_quad(st, Vector3(shaft_x0, shaft_bottom, 0.0), Vector3(shaft_x1, shaft_bottom, 0.0), Vector3(shaft_x1, shaft_bottom, zb), Vector3(shaft_x0, shaft_bottom, zb))
	st.generate_normals()
	return st.commit()


## Quad given counter-clockwise as seen from its visible side; emitted with
## Godot's clockwise front-face winding.
func _quad(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, e: Vector3) -> void:
	for p in [a, c, b, a, e, c]:
		st.set_color(Color(0.8, 0.8, 0.8, 0.0))
		st.add_vertex(p)
