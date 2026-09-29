class_name Agent
extends Node3D
## A walking character: follows MineNav routes (walk legs along the floor,
## waits at the cage, rides in the shaft), turns smoothly toward where it is
## going and picks walk/run/carry clips to match its ground speed so the feet
## do not slide. Subclasses decide where to go and what to do on arrival.

signal arrived

const WALK_CLIP_MPS := 1.1
const RUN_CLIP_MPS := 3.0
const CARRY_CLIP_MPS := 1.1
const TURN_RATE := 9.0

var nav: MineNav
var rig: CharacterRig
var level := 0
var legs: Array = []
var leg_i := 0
var leg_s := 0.0                  # distance (walk) or time (wait/ride) into the current leg
var seg_i := 0
var speed := 2.0                  # ground speed on walk legs (m/s)
var moving := false
var carrying := false
var yaw := 0.0
var _target_yaw := 0.0
var rider_slot := 0


func setup_agent(n: MineNav, asset_id: String, lod: int = 0) -> void:
	nav = n
	rig = CharacterRig.new()
	add_child(rig)
	rig.setup(asset_id, lod)


func place(pos: Vector3, lvl: int, face_yaw: float = 0.0) -> void:
	level = lvl
	position = pos
	yaw = face_yaw
	_target_yaw = face_yaw
	rotation.y = yaw
	moving = false
	legs.clear()
	rig.set_underground(level > 0)


func face_point(p: Vector3) -> void:
	var d := p - position
	if Vector2(d.x, d.z).length() > 0.05:
		_target_yaw = atan2(d.x, d.z)


func face_yaw(y: float) -> void:
	_target_yaw = y


## Starts walking to `target` on `target_level`. `eta_s` > 0 asks to arrive in
## about that many seconds (the simulation's travel time); the speed is kept
## within believable walking/running limits.
func go_to(target: Vector3, target_level: int, eta_s: float = -1.0, max_mps: float = 3.4) -> void:
	legs = nav.route(position, level, target, target_level, rider_slot)
	leg_i = 0
	leg_s = 0.0
	seg_i = 0
	var walk := MineNav.route_walk_len(legs)
	var fixed := MineNav.route_time(legs, 1e9)
	var base := 2.2
	if eta_s > 0.0:
		base = walk / maxf(eta_s - fixed, 0.5)
	speed = clampf(base, 1.0, max_mps)
	moving = walk > 0.05 or legs.size() > 1
	if not moving:
		legs.clear()
		arrived.emit()


func stop() -> void:
	moving = false
	legs.clear()


func destination() -> Vector3:
	if legs.is_empty():
		return position
	var last: Dictionary = legs[legs.size() - 1]
	if String(last["kind"]) == "walk":
		var pts: PackedVector3Array = last["pts"]
		return pts[pts.size() - 1]
	return position


func advance(delta: float) -> void:
	if moving:
		_step(delta)
	var diff := wrapf(_target_yaw - yaw, -PI, PI)
	yaw += diff * clampf(delta * TURN_RATE, 0.0, 1.0)
	rotation.y = yaw


func _step(delta: float) -> void:
	var left := delta
	while moving and left > 0.0:
		var leg: Dictionary = legs[leg_i]
		match String(leg["kind"]):
			"walk":
				left = _walk(leg, left)
			"wait":
				_locomotion_clip(0.0)
				leg_s += left
				if leg_s >= float(leg["time"]):
					left = leg_s - float(leg["time"])
					_next_leg()
				else:
					left = 0.0
			"ride":
				_locomotion_clip(0.0)
				leg_s += left
				var t := clampf(leg_s / maxf(float(leg["time"]), 0.01), 0.0, 1.0)
				var a: Vector3 = leg["from"]
				var b: Vector3 = leg["to"]
				position = a.lerp(b, smoothstep(0.0, 1.0, t))
				# Lighting follows the cage through the collar of the shaft.
				rig.set_underground(position.y < -1.5)
				if t >= 1.0:
					left = leg_s - float(leg["time"])
					level = int(leg["to_level"])
					_next_leg()
				else:
					left = 0.0


func _walk(leg: Dictionary, dt: float) -> float:
	var pts: PackedVector3Array = leg["pts"]
	level = int(leg["level"])
	var budget := speed * dt
	while budget > 0.0:
		if seg_i >= pts.size() - 1:
			_next_leg()
			return budget / maxf(speed, 0.01)
		var a := pts[seg_i]
		var b := pts[seg_i + 1]
		var seg := Vector2(b.x - a.x, b.z - a.z).length()
		var remain := seg - leg_s
		if remain <= budget:
			budget -= maxf(remain, 0.0)
			seg_i += 1
			leg_s = 0.0
			position = b
			continue
		leg_s += budget
		budget = 0.0
		var f := leg_s / maxf(seg, 1e-4)
		position = a.lerp(b, f)
		if seg > 0.05:
			_target_yaw = atan2(b.x - a.x, b.z - a.z)
	_locomotion_clip(speed)
	return 0.0


func _next_leg() -> void:
	leg_i += 1
	leg_s = 0.0
	seg_i = 0
	if leg_i >= legs.size():
		moving = false
		legs.clear()
		rig.set_underground(level > 0)
		arrived.emit()


## Walk / run / carry clip for the current ground speed.
func _locomotion_clip(mps: float) -> void:
	if mps <= 0.05:
		rig.play("Idle", 1.0, 0.3)
		return
	if carrying:
		rig.play("Carry_Walk", clampf(mps / CARRY_CLIP_MPS, 0.7, 1.8), 0.2)
	elif mps > 1.9:
		rig.play("Run", clampf(mps / RUN_CLIP_MPS, 0.65, 1.3), 0.2)
	else:
		rig.play("Walk", clampf(mps / WALK_CLIP_MPS, 0.7, 1.75), 0.2)
