class_name Icon
extends Control
## Resolution-independent vector icons drawn with canvas primitives (no
## image files): crisp at every screen density and tintable. Shapes are
## defined in a unit square.

@export var kind := "coin":
	set(v):
		kind = v
		queue_redraw()
@export var color := Color("f4efe4"):
	set(v):
		color = v
		queue_redraw()
@export var accent := Color("f5b93a"):
	set(v):
		accent = v
		queue_redraw()


static func make(k: String, size: float = 40.0, c: Color = Color("f4efe4"), a: Color = Color("f5b93a")) -> Icon:
	var i := Icon.new()
	i.kind = k
	i.color = c
	i.accent = a
	i.custom_minimum_size = Vector2(size, size)
	i.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return i


func _s() -> float:
	return minf(size.x, size.y)


func _o() -> Vector2:
	return (size - Vector2(_s(), _s())) * 0.5


func P(x: float, y: float) -> Vector2:
	return _o() + Vector2(x, y) * _s()


func _poly(pts: Array, c: Color) -> void:
	var arr := PackedVector2Array()
	for p in pts:
		arr.append(P(p[0], p[1]))
	draw_colored_polygon(arr, c)


func _line(pts: Array, c: Color, w: float) -> void:
	var arr := PackedVector2Array()
	for p in pts:
		arr.append(P(p[0], p[1]))
	draw_polyline(arr, c, w * _s(), true)


func _circle(x: float, y: float, r: float, c: Color) -> void:
	draw_circle(P(x, y), r * _s(), c, true, -1.0, true)


func _ring(x: float, y: float, r: float, c: Color, w: float, a0: float = 0.0, a1: float = TAU) -> void:
	draw_arc(P(x, y), r * _s(), a0, a1, 32, c, w * _s(), true)


func _rect(x: float, y: float, w: float, h: float, c: Color) -> void:
	draw_rect(Rect2(P(x, y), Vector2(w, h) * _s()), c)


func _draw() -> void:
	var c := color
	var a := accent
	match kind:
		"coin":
			_circle(0.5, 0.5, 0.42, a)
			_ring(0.5, 0.5, 0.31, a.darkened(0.3), 0.06)
			_line([[0.6, 0.36], [0.44, 0.36], [0.4, 0.44], [0.6, 0.56], [0.56, 0.64], [0.4, 0.64]], a.darkened(0.45), 0.07)
			_line([[0.5, 0.28], [0.5, 0.72]], a.darkened(0.45), 0.06)
		"gem":
			_poly([[0.18, 0.38], [0.34, 0.18], [0.66, 0.18], [0.82, 0.38], [0.5, 0.86]], a)
			_poly([[0.18, 0.38], [0.82, 0.38], [0.5, 0.86]], a.darkened(0.2))
			_line([[0.34, 0.18], [0.42, 0.38], [0.5, 0.86], [0.58, 0.38], [0.66, 0.18]], a.lightened(0.35), 0.03)
		"pick":
			_line([[0.24, 0.86], [0.64, 0.3]], Color("b98a5a"), 0.1)
			_poly([[0.26, 0.2], [0.5, 0.16], [0.74, 0.22], [0.92, 0.42], [0.86, 0.46], [0.7, 0.34], [0.5, 0.29], [0.3, 0.3]], c)
		"gear":
			for i in 8:
				var ang := TAU * float(i) / 8.0
				var d := Vector2(cos(ang), sin(ang))
				var q := Vector2(-d.y, d.x) * 0.07
				var p0 := Vector2(0.5, 0.5) + d * 0.28
				var p1 := Vector2(0.5, 0.5) + d * 0.45
				_poly([[p0.x + q.x, p0.y + q.y], [p1.x + q.x, p1.y + q.y], [p1.x - q.x, p1.y - q.y], [p0.x - q.x, p0.y - q.y]], c)
			_circle(0.5, 0.5, 0.32, c)
			_circle(0.5, 0.5, 0.13, Color(0, 0, 0, 0.55))
		"worker":
			_circle(0.5, 0.4, 0.15, Color("e0b48c"))
			_poly([[0.3, 0.33], [0.34, 0.2], [0.5, 0.14], [0.66, 0.2], [0.7, 0.33]], a)
			_rect(0.27, 0.32, 0.46, 0.05, a.darkened(0.2))
			_poly([[0.22, 0.92], [0.28, 0.64], [0.4, 0.58], [0.6, 0.58], [0.72, 0.64], [0.78, 0.92]], c)
		"flask":
			_poly([[0.4, 0.12], [0.6, 0.12], [0.6, 0.4], [0.84, 0.84], [0.16, 0.84], [0.4, 0.4]], c)
			_poly([[0.3, 0.6], [0.7, 0.6], [0.84, 0.84], [0.16, 0.84]], a)
			_rect(0.36, 0.1, 0.28, 0.06, c.darkened(0.2))
		"trophy":
			_poly([[0.24, 0.14], [0.76, 0.14], [0.72, 0.42], [0.6, 0.56], [0.4, 0.56], [0.28, 0.42]], a)
			_ring(0.24, 0.3, 0.1, a, 0.05, PI * 0.5, PI * 1.5)
			_ring(0.76, 0.3, 0.1, a, 0.05, -PI * 0.5, PI * 0.5)
			_rect(0.45, 0.56, 0.1, 0.16, a.darkened(0.2))
			_rect(0.3, 0.72, 0.4, 0.12, a.darkened(0.3))
		"star":
			var pts := []
			for i in 10:
				var ang := -PI * 0.5 + TAU * float(i) / 10.0
				var r := 0.44 if i % 2 == 0 else 0.19
				pts.append([0.5 + cos(ang) * r, 0.53 + sin(ang) * r])
			_poly(pts, a)
		"lock":
			_ring(0.5, 0.42, 0.18, c, 0.08, PI, TAU)
			_line([[0.32, 0.42], [0.32, 0.5]], c, 0.08)
			_line([[0.68, 0.42], [0.68, 0.5]], c, 0.08)
			_rect(0.22, 0.48, 0.56, 0.4, c)
			_circle(0.5, 0.64, 0.06, Color(0, 0, 0, 0.6))
		"up":
			_poly([[0.5, 0.12], [0.86, 0.52], [0.64, 0.52], [0.64, 0.88], [0.36, 0.88], [0.36, 0.52], [0.14, 0.52]], a)
		"down":
			_poly([[0.5, 0.88], [0.86, 0.48], [0.64, 0.48], [0.64, 0.12], [0.36, 0.12], [0.36, 0.48], [0.14, 0.48]], a)
		"lift":
			_line([[0.2, 0.92], [0.44, 0.2]], Color("d24a3a"), 0.07)
			_line([[0.8, 0.92], [0.56, 0.2]], Color("d24a3a"), 0.07)
			_line([[0.3, 0.62], [0.7, 0.62]], Color("d24a3a"), 0.05)
			_ring(0.5, 0.18, 0.1, c, 0.05)
			_line([[0.5, 0.28], [0.5, 0.5]], c, 0.03)
			_rect(0.4, 0.5, 0.2, 0.22, a)
		"truck":
			_rect(0.08, 0.3, 0.56, 0.36, a)
			_poly([[0.64, 0.42], [0.8, 0.42], [0.92, 0.56], [0.92, 0.66], [0.64, 0.66]], c)
			_circle(0.26, 0.72, 0.1, Color("222"))
			_circle(0.76, 0.72, 0.1, Color("222"))
		"clock":
			_circle(0.5, 0.5, 0.42, c)
			_circle(0.5, 0.5, 0.34, Color("1f252d"))
			_line([[0.5, 0.26], [0.5, 0.5], [0.68, 0.6]], a, 0.07)
		"book":
			_rect(0.2, 0.14, 0.6, 0.74, a)
			_rect(0.2, 0.14, 0.1, 0.74, a.darkened(0.3))
			_rect(0.38, 0.3, 0.32, 0.05, Color(0, 0, 0, 0.4))
			_rect(0.38, 0.42, 0.26, 0.05, Color(0, 0, 0, 0.4))
		"map":
			_poly([[0.12, 0.22], [0.36, 0.14], [0.64, 0.24], [0.88, 0.16], [0.88, 0.8], [0.64, 0.88], [0.36, 0.78], [0.12, 0.86]], a)
			_line([[0.36, 0.14], [0.36, 0.78]], a.darkened(0.3), 0.03)
			_line([[0.64, 0.24], [0.64, 0.88]], a.darkened(0.3), 0.03)
		"crown":
			_poly([[0.14, 0.8], [0.14, 0.3], [0.34, 0.52], [0.5, 0.2], [0.66, 0.52], [0.86, 0.3], [0.86, 0.8]], a)
			_rect(0.14, 0.74, 0.72, 0.1, a.darkened(0.25))
		"bolt":
			_poly([[0.58, 0.08], [0.2, 0.56], [0.46, 0.56], [0.38, 0.92], [0.8, 0.4], [0.54, 0.4]], a)
		"drop":
			_poly([[0.5, 0.1], [0.74, 0.5], [0.72, 0.7], [0.5, 0.86], [0.28, 0.7], [0.26, 0.5]], Color("5aa8ff"))
			_circle(0.5, 0.64, 0.23, Color("5aa8ff"))
		"hammer":
			_line([[0.3, 0.88], [0.6, 0.4]], Color("b98a5a"), 0.1)
			_poly([[0.42, 0.24], [0.66, 0.1], [0.9, 0.4], [0.66, 0.54]], c)
		"close":
			_line([[0.24, 0.24], [0.76, 0.76]], c, 0.1)
			_line([[0.76, 0.24], [0.24, 0.76]], c, 0.1)
		"back":
			_line([[0.62, 0.18], [0.3, 0.5], [0.62, 0.82]], c, 0.11)
		"next":
			_line([[0.38, 0.18], [0.7, 0.5], [0.38, 0.82]], c, 0.11)
		"check":
			_line([[0.18, 0.52], [0.42, 0.76], [0.84, 0.26]], a, 0.12)
		"plus":
			_line([[0.5, 0.18], [0.5, 0.82]], c, 0.12)
			_line([[0.18, 0.5], [0.82, 0.5]], c, 0.12)
		"chart":
			_rect(0.14, 0.56, 0.16, 0.3, a)
			_rect(0.42, 0.36, 0.16, 0.5, a)
			_rect(0.7, 0.16, 0.16, 0.7, a)
			_rect(0.1, 0.86, 0.8, 0.04, c)
		"surface":
			_circle(0.72, 0.28, 0.13, a)
			_poly([[0.04, 0.86], [0.34, 0.4], [0.54, 0.66], [0.66, 0.52], [0.96, 0.86]], c)
		"sound":
			_poly([[0.12, 0.38], [0.3, 0.38], [0.52, 0.18], [0.52, 0.82], [0.3, 0.62], [0.12, 0.62]], c)
			_ring(0.52, 0.5, 0.18, c, 0.06, -PI * 0.35, PI * 0.35)
			_ring(0.52, 0.5, 0.32, c, 0.06, -PI * 0.35, PI * 0.35)
		"warning":
			_poly([[0.5, 0.1], [0.92, 0.86], [0.08, 0.86]], a)
			_rect(0.46, 0.34, 0.08, 0.28, Color("1b1b1b"))
			_circle(0.5, 0.73, 0.05, Color("1b1b1b"))
		"quest":
			_rect(0.22, 0.12, 0.56, 0.76, c)
			_rect(0.36, 0.08, 0.28, 0.1, a)
			for i in 3:
				_rect(0.32, 0.32 + 0.16 * i, 0.36, 0.05, Color(0, 0, 0, 0.45))
		"shirt":
			_poly([[0.34, 0.14], [0.66, 0.14], [0.92, 0.3], [0.8, 0.48], [0.72, 0.42], [0.72, 0.88], [0.28, 0.88], [0.28, 0.42], [0.2, 0.48], [0.08, 0.3]], a)
		"pause":
			_rect(0.26, 0.2, 0.16, 0.6, c)
			_rect(0.58, 0.2, 0.16, 0.6, c)
		"menu":
			for i in 3:
				_rect(0.18, 0.24 + 0.22 * i, 0.64, 0.09, c)
		"factory":
			_poly([[0.08, 0.88], [0.08, 0.46], [0.32, 0.6], [0.32, 0.46], [0.56, 0.6], [0.56, 0.3], [0.7, 0.3], [0.7, 0.12], [0.84, 0.12], [0.84, 0.88]], c)
			_rect(0.16, 0.7, 0.1, 0.08, a)
			_rect(0.4, 0.7, 0.1, 0.08, a)
		"cart":
			_poly([[0.12, 0.3], [0.88, 0.3], [0.78, 0.7], [0.22, 0.7]], a)
			_circle(0.32, 0.78, 0.09, Color("222"))
			_circle(0.68, 0.78, 0.09, Color("222"))
			_circle(0.4, 0.26, 0.1, c)
			_circle(0.58, 0.24, 0.12, c)
		"people":
			_circle(0.34, 0.36, 0.12, c)
			_circle(0.66, 0.36, 0.12, c)
			_poly([[0.12, 0.86], [0.16, 0.6], [0.34, 0.52], [0.5, 0.6], [0.5, 0.86]], c)
			_poly([[0.5, 0.86], [0.5, 0.6], [0.66, 0.52], [0.84, 0.6], [0.88, 0.86]], c.darkened(0.15))
		"down_level":
			_rect(0.3, 0.08, 0.4, 0.5, c)
			_poly([[0.5, 0.92], [0.8, 0.58], [0.2, 0.58]], a)
		_:
			_circle(0.5, 0.5, 0.36, c)
