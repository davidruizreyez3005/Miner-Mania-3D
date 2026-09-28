class_name VfxLibrary
extends RefCounted
## Particle effects, built in code (no external assets) and tuned for mobile:
## small particle counts, CPU-free GPU particles, short lifetimes, additive or
## alpha quads with a soft round texture generated once. One-shots are
## pooled per effect so bursts never allocate during play.

const MAX_POOL := 6

static var _pools: Dictionary = {}      # effect id -> Array[GPUParticles3D]
static var _soft: GradientTexture2D
static var _materials: Dictionary = {}


static func _soft_tex() -> GradientTexture2D:
	if _soft == null:
		_soft = GradientTexture2D.new()
		_soft.width = 64
		_soft.height = 64
		_soft.fill = GradientTexture2D.FILL_RADIAL
		_soft.fill_from = Vector2(0.5, 0.5)
		_soft.fill_to = Vector2(1.0, 0.5)
		var g := Gradient.new()
		g.set_color(0, Color(1, 1, 1, 1))
		g.set_color(1, Color(1, 1, 1, 0))
		_soft.gradient = g
	return _soft


static func _draw_mat(additive: bool) -> StandardMaterial3D:
	var key := "add" if additive else "alpha"
	if _materials.has(key):
		return _materials[key]
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.blend_mode = BaseMaterial3D.BLEND_MODE_ADD if additive else BaseMaterial3D.BLEND_MODE_MIX
	m.albedo_texture = _soft_tex()
	m.vertex_color_use_as_albedo = true
	m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	m.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	_materials[key] = m
	return m


## Effect definitions: amount, lifetime, velocity, spread, gravity, scale, colours, additive.
const DEFS := {
	"rock_chips": {"amount": 14, "life": 0.7, "vel": [2.0, 4.5], "spread": 55.0, "gravity": -9.8, "scale": [0.06, 0.14], "colors": ["#8a7a68", "#4a4038"], "additive": false, "one_shot": true, "dir": [0, 1, 0.6]},
	"sparks": {"amount": 16, "life": 0.45, "vel": [3.0, 6.0], "spread": 70.0, "gravity": -6.0, "scale": [0.03, 0.06], "colors": ["#ffe9a8", "#ff8a1e"], "additive": true, "one_shot": true, "dir": [0, 1, 0.5]},
	"dust": {"amount": 10, "life": 1.4, "vel": [0.4, 1.2], "spread": 80.0, "gravity": 0.3, "scale": [0.5, 1.2], "colors": ["#b8a890", "#8a7a6a"], "additive": false, "one_shot": true, "dir": [0, 1, 0]},
	"construct_dust": {"amount": 24, "life": 2.0, "vel": [1.0, 3.0], "spread": 90.0, "gravity": 0.2, "scale": [0.9, 2.2], "colors": ["#c8b8a0", "#9a8a78"], "additive": false, "one_shot": true, "dir": [0, 1, 0]},
	"blast_dust": {"amount": 40, "life": 2.6, "vel": [2.0, 7.0], "spread": 75.0, "gravity": 0.4, "scale": [1.0, 2.8], "colors": ["#a89880", "#6a5e52"], "additive": false, "one_shot": true, "dir": [0, 0.4, 1]},
	"worn_smoke": {"amount": 8, "life": 3.0, "vel": [0.5, 1.2], "spread": 18.0, "gravity": 0.25, "scale": [0.6, 1.6], "colors": ["#5a5550", "#2e2b28"], "additive": false, "one_shot": false, "dir": [0, 1, 0]},
	"steam": {"amount": 10, "life": 2.2, "vel": [0.6, 1.4], "spread": 20.0, "gravity": 0.3, "scale": [0.5, 1.3], "colors": ["#e8eef2", "#b8c2c8"], "additive": false, "one_shot": false, "dir": [0, 1, 0]},
	"discovery": {"amount": 36, "life": 1.6, "vel": [1.5, 4.0], "spread": 180.0, "gravity": -1.0, "scale": [0.08, 0.2], "colors": ["#fff6c8", "#b070ff"], "additive": true, "one_shot": true, "dir": [0, 1, 0]},
	"coins": {"amount": 18, "life": 1.1, "vel": [2.5, 5.0], "spread": 35.0, "gravity": -9.0, "scale": [0.1, 0.18], "colors": ["#ffe27a", "#d99a1e"], "additive": true, "one_shot": true, "dir": [0, 1, 0]},
	"motes": {"amount": 24, "life": 5.0, "vel": [0.05, 0.25], "spread": 180.0, "gravity": 0.02, "scale": [0.05, 0.12], "colors": ["#ffffff", "#ffffff"], "additive": true, "one_shot": false, "dir": [0, 1, 0]},
	"drips": {"amount": 6, "life": 1.1, "vel": [0.0, 0.2], "spread": 5.0, "gravity": -9.8, "scale": [0.03, 0.05], "colors": ["#bfe0ff", "#7fb0dd"], "additive": true, "one_shot": false, "dir": [0, -1, 0]},
	"exhaust": {"amount": 8, "life": 1.6, "vel": [0.4, 0.9], "spread": 15.0, "gravity": 0.3, "scale": [0.3, 0.8], "colors": ["#6a6662", "#3a3836"], "additive": false, "one_shot": false, "dir": [0, 1, 0]},
}


static func make(effect: String, tint: Color = Color(0, 0, 0, 0)) -> GPUParticles3D:
	var d: Dictionary = DEFS.get(effect, DEFS["dust"])
	var p := GPUParticles3D.new()
	p.name = "Vfx_" + effect
	p.amount = int(d["amount"])
	p.lifetime = float(d["life"])
	p.one_shot = bool(d["one_shot"])
	p.explosiveness = 0.9 if p.one_shot else 0.0
	p.emitting = false
	p.local_coords = false
	p.visibility_aabb = AABB(Vector3(-6, -6, -6), Vector3(12, 12, 12))
	var pm := ParticleProcessMaterial.new()
	var dir: Array = d["dir"]
	pm.direction = Vector3(float(dir[0]), float(dir[1]), float(dir[2]))
	pm.spread = float(d["spread"])
	var vel: Array = d["vel"]
	pm.initial_velocity_min = float(vel[0])
	pm.initial_velocity_max = float(vel[1])
	pm.gravity = Vector3(0, float(d["gravity"]), 0)
	var sc: Array = d["scale"]
	pm.scale_min = float(sc[0])
	pm.scale_max = float(sc[1])
	var cols: Array = d["colors"]
	var g := Gradient.new()
	var c0 := Color(String(cols[0]))
	var c1 := Color(String(cols[1]))
	if tint.a > 0.0:
		c0 = c0.lerp(tint, 0.6)
		c1 = c1.lerp(tint, 0.8)
	g.set_color(0, c0)
	g.set_color(1, Color(c1.r, c1.g, c1.b, 0.0))
	var gt := GradientTexture1D.new()
	gt.gradient = g
	pm.color_ramp = gt
	var curve := Curve.new()
	curve.add_point(Vector2(0, 0.6))
	curve.add_point(Vector2(0.3, 1.0))
	curve.add_point(Vector2(1, 0.8))
	var ct := CurveTexture.new()
	ct.curve = curve
	pm.scale_curve = ct
	pm.damping_min = 0.5
	pm.damping_max = 1.5
	p.process_material = pm
	var quad := QuadMesh.new()
	quad.size = Vector2(1, 1)
	quad.material = _draw_mat(bool(d["additive"]))
	p.draw_pass_1 = quad
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return p


## Fires a pooled one-shot effect at a world position.
static func spawn(parent: Node, effect: String, at: Vector3, tint: Color = Color(0, 0, 0, 0)) -> void:
	if parent == null or not parent.is_inside_tree():
		return
	if Settings.get_value("reduce_motion", false) and effect in ["blast_dust", "discovery"]:
		return
	var pool: Array = _pools.get_or_add(effect + str(tint), [])
	var p: GPUParticles3D = null
	for q in pool:
		if is_instance_valid(q) and not (q as GPUParticles3D).emitting:
			p = q
			break
	if p == null:
		pool = pool.filter(func(q): return is_instance_valid(q))
		_pools[effect + str(tint)] = pool
		if pool.size() >= MAX_POOL:
			p = pool[0]
		else:
			p = make(effect, tint)
			parent.get_tree().current_scene.add_child(p) if parent.get_tree().current_scene else parent.add_child(p)
			pool.append(p)
	p.global_position = at
	p.restart()
	p.emitting = true


## Attaches a continuous effect to a node (returns it; caller toggles emitting).
static func attach(parent: Node3D, effect: String, offset: Vector3, tint: Color = Color(0, 0, 0, 0)) -> GPUParticles3D:
	var p := make(effect, tint)
	p.position = offset
	p.local_coords = false
	parent.add_child(p)
	p.emitting = true
	return p
