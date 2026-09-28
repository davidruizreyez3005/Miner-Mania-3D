class_name LiftView
extends Node3D
## The headframe over the main shaft and its cage. The generated headframe's
## rig (bones: cage, rope, sheave) is driven directly: the cage winds down the
## shaft to the deepest station, pauses to load, winds up with a visible ore
## load, pauses to tip, and repeats while the lift runs (operator or manual
## call). The rope stretches with the travel and the sheave turns with it.

const ASSET := "bld_headframe_01"
const CAGE_REST_Y := 0.6
const CAGE_TOP_ABOVE_ORIGIN := 2.877      # from the rig: rope ends at the cage top
const ROPE_REST_LEN := 9.923
const SHEAVE_Y := 13.4
const SHEAVE_RADIUS := 1.1

var world: MineWorld
var headframe: Node3D
var skeleton: Skeleton3D
var cage_bone := -1
var rope_bone := -1
var sheave_bone := -1
var sheave_rest := Quaternion.IDENTITY
var cage_y := CAGE_REST_Y
var load_mesh: Node3D
var loop_player: AudioStreamPlayer3D
var pick: StaticBody3D
var _phase := "idle"          # idle | down | load | up | unload
var _phase_t := 0.0
var _target_y := CAGE_REST_Y
var _sheave_angle := 0.0
var _speed := 3.0


func setup(w: MineWorld) -> void:
	world = w
	name = "Lift"
	var pl := w.layout.plot("headframe")
	var pos: Array = pl.get("pos", [-16, -4])
	position = Vector3(float(pos[0]), 0.0, float(pos[1]))
	rotation_degrees.y = float(pl.get("yaw", 0.0))
	headframe = Assets.instantiate(ASSET, "", false)
	add_child(headframe)
	var sks := headframe.find_children("*", "Skeleton3D", true, false)
	if not sks.is_empty():
		skeleton = sks[0]
		cage_bone = skeleton.find_bone("cage")
		rope_bone = skeleton.find_bone("rope")
		sheave_bone = skeleton.find_bone("sheave")
		if sheave_bone >= 0:
			sheave_rest = skeleton.get_bone_rest(sheave_bone).basis.get_rotation_quaternion()
	for ap in headframe.find_children("*", "AnimationPlayer", true, false):
		(ap as AnimationPlayer).stop()
	# Ore riding in the cage on the way up.
	var cage_attach := headframe.find_child("cage", true, false)
	load_mesh = Assets.instantiate("env_pile_gravel_01", "", false)
	load_mesh.scale = Vector3(0.42, 0.5, 0.42)
	load_mesh.position = Vector3(0, 0.15, 0)
	load_mesh.visible = false
	if cage_attach:
		cage_attach.add_child(load_mesh)
	loop_player = Audio.attach_loop("lift_loop", self, Vector3(0, 8, -8))
	pick = StaticBody3D.new()
	pick.collision_layer = MineWorld.PICK_LAYER
	pick.collision_mask = 0
	pick.set_meta("target", "facility:headframe")
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	var b := Assets.bounds(ASSET)
	box.size = b.size
	cs.shape = box
	cs.position = b.get_center()
	pick.add_child(cs)
	add_child(pick)
	_apply_pose()


func level_cage_y(d: int) -> float:
	return world.content.depth_floor_y(d) + CAGE_REST_Y - position.y


func _choose_target() -> int:
	## Deepest station with ore, else the deepest open level.
	var best := 0
	for dep in world.sim.state.depths:
		if dep["unlocked"] and Simulation.inv_total(dep["station"]) > 0.5:
			best = maxi(best, int(dep["index"]))
	return best if best > 0 else maxi(1, world.sim.state.deepest_unlocked())


func sync(delta: float) -> void:
	var lr: Dictionary = world.sim.rt.get("lift", {})
	var running := bool(lr.get("running", false))
	var cycle := maxf(4.0, float(lr.get("cycle_s", 12.0)))
	var travel := absf(level_cage_y(maxi(1, int(lr.get("deepest", 1)))) - CAGE_REST_Y)
	_speed = maxf(1.5, 2.0 * travel / maxf(1.0, cycle - 4.0))
	_phase_t += delta
	match _phase:
		"idle":
			if running:
				_target_y = level_cage_y(_choose_target())
				_phase = "down"
			else:
				_move_to(CAGE_REST_Y, delta)
		"down":
			if _move_to(_target_y, delta):
				_phase = "load"
				_phase_t = 0.0
		"load":
			if _phase_t >= 1.6:
				load_mesh.visible = true
				_phase = "up"
		"up":
			if _move_to(CAGE_REST_Y, delta):
				_phase = "unload"
				_phase_t = 0.0
		"unload":
			if _phase_t >= 1.4:
				load_mesh.visible = false
				_phase = "idle"
	var moving := _phase in ["down", "up"] or (_phase == "idle" and absf(cage_y - CAGE_REST_Y) > 0.05)
	Audio.set_loop_level(loop_player, 1.0 if moving else 0.0)
	_apply_pose()


## Moves the cage toward y; returns true on arrival.
func _move_to(y: float, delta: float) -> bool:
	var step := _speed * delta
	var dy := y - cage_y
	var moved := clampf(dy, -step, step)
	cage_y += moved
	_sheave_angle += moved / SHEAVE_RADIUS
	return absf(y - cage_y) < 0.01


func _apply_pose() -> void:
	if skeleton == null:
		return
	if cage_bone >= 0:
		skeleton.set_bone_pose_position(cage_bone, Vector3(0, cage_y, 0))
	if rope_bone >= 0:
		var length := SHEAVE_Y - (cage_y + CAGE_TOP_ABOVE_ORIGIN)
		skeleton.set_bone_pose_scale(rope_bone, Vector3(1, maxf(0.05, length / ROPE_REST_LEN), 1))
	if sheave_bone >= 0:
		skeleton.set_bone_pose_rotation(sheave_bone, sheave_rest * Quaternion(Vector3.UP, _sheave_angle))


## World position of the cage (for effects, the camera and riding workers).
func cage_position() -> Vector3:
	return global_transform * Vector3(0, cage_y, 0)
