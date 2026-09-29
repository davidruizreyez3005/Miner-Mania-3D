class_name MenuDiorama
extends Node3D
## The title screen's backdrop: a little mine-head scene built from the
## generated assets (headframe, silos, a crew at a gold vein, pines,
## boulders) under the valley sky, with a slowly circling camera.

const PRELOAD := ["bld_headframe_01", "mach_silo_01", "env_tree_pine_01", "env_rock_large_01", "env_boulder_01",
	"res_ore_gold_01", "chr_worker_miner_01", "chr_worker_hauler_02", "prop_crate_wood_01", "env_lamp_post_01", "veh_mine_cart_01",
	"env_rail_straight_01", "env_bush_01", "prop_ore_sack_01"]

var camera := Camera3D.new()
var _t := 0.0


func build(region: Dictionary) -> void:
	name = "MenuDiorama"
	var atm := Atmosphere.new()
	add_child(atm)
	atm.setup(region)
	var ground := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(160, 160)
	pm.subdivide_width = 1
	pm.subdivide_depth = 1
	ground.mesh = pm
	var gm := StandardMaterial3D.new()
	var tex := load("res://assets/generated/textures/grass_albedo.png") as Texture2D
	gm.albedo_texture = tex
	gm.albedo_color = Color(String(region.get("look", {}).get("terrain_detail", "#6e7a4a"))).lightened(0.35)
	gm.uv1_scale = Vector3(40, 40, 1)
	gm.roughness = 1.0
	ground.material_override = gm
	add_child(ground)
	_put("bld_headframe_01", Vector3(0, 0, 0), 0.0)
	_put("mach_silo_01", Vector3(7.5, 0, -2.0), 0.0)
	_put("mach_silo_01", Vector3(11.3, 0, -2.0), 0.0)
	_put("res_ore_gold_01", Vector3(-6.0, 0, 5.2), 30.0)
	_put("prop_crate_wood_01", Vector3(4.0, 0, 6.0), 20.0)
	_put("prop_ore_sack_01", Vector3(-3.8, 0, 6.6), 0.0)
	_put("env_lamp_post_01", Vector3(3.2, 0, 3.4), 0.0)
	_put("veh_mine_cart_01", Vector3(-1.2, 0, 7.4), 90.0)
	for i in 5:
		_put("env_rail_straight_01", Vector3(-5.0 + 2.0 * i, 0.01, 7.4), 90.0)
	var rng := RandomNumberGenerator.new()
	rng.seed = 77
	for i in 26:
		var ang := rng.randf() * TAU
		var r := rng.randf_range(31.0, 58.0)
		var p := Vector3(cos(ang) * r, 0, sin(ang) * r - 6.0)
		_put(["env_tree_pine_01", "env_tree_pine_01", "env_bush_01", "env_rock_large_01", "env_boulder_01"][i % 5], p, rng.randf() * 360.0,
			rng.randf_range(0.8, 1.4))
	var miner := _put("chr_worker_miner_01", Vector3(-6.0, 0, 7.0), 180.0)
	_anim(miner, "Mine")
	var hauler := _put("chr_worker_hauler_02", Vector3(-2.6, 0, 5.8), 250.0)
	_anim(hauler, "Idle")
	camera.fov = 48.0
	camera.far = 400.0
	add_child(camera)
	camera.current = true


func _put(id: String, p: Vector3, yaw_deg: float, sc: float = 1.0) -> Node3D:
	var n := Assets.instantiate(id, "", true)
	n.position = p
	n.rotation_degrees.y = yaw_deg
	n.scale = Vector3.ONE * sc
	add_child(n)
	return n


func _anim(n: Node3D, clip: String) -> void:
	for ap in n.find_children("*", "AnimationPlayer", true, false):
		if (ap as AnimationPlayer).has_animation(clip):
			(ap as AnimationPlayer).play(clip)


func _process(delta: float) -> void:
	_t += delta * 0.07
	var p := Vector3(sin(_t) * 26.0, 9.0 + sin(_t * 0.7) * 1.5, cos(_t) * 26.0 + 4.0)
	camera.global_transform = Transform3D(Basis(), p).looking_at(Vector3(0, 5.0, 2.0), Vector3.UP)
