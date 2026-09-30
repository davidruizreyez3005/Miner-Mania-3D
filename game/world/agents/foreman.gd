class_name Foreman
extends Agent
## The player's character. Tap a vein and the foreman runs over (riding the
## cage if it is on another level) and swings the pick: every swing's impact
## frame mines through the simulation's manual_swing command, so what you see
## is what you earn. Rapid taps queue swings and quicken the rhythm. Tap open
## floor to walk there. The outfit is the equipped cosmetic.

signal swung(result: Dictionary)

const MAX_QUEUE := 5
const PICK := "tool_pickaxe_01"

var mgr: AgentManager
var node_depth := 0
var node_slot := -1
var swings := 0
var mining := false
var outfit := ""
var _swing_speed := 1.5
var _stop_at := -1.0
var _pending_mine := false


func setup_foreman(m: AgentManager, asset_id: String) -> void:
	mgr = m
	outfit = asset_id
	name = "Foreman"
	setup_agent(m.nav, asset_id)
	rig.always_animate = true
	rig.set_detail(CharacterRig.DETAIL_FULL)
	rider_slot = 5
	arrived.connect(_on_arrived)
	rig.clip_event.connect(_on_clip_event)
	var ring := MeshInstance3D.new()
	var tm := TorusMesh.new()
	tm.inner_radius = 0.42
	tm.outer_radius = 0.52
	tm.rings = 24
	tm.ring_segments = 6
	ring.mesh = tm
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = Color(1.0, 0.82, 0.25, 0.85)
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	ring.material_override = mat
	ring.scale = Vector3(1, 0.25, 1)
	ring.position = Vector3(0, 0.03, 0)
	ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	ring.layers = Atmosphere.LAYER_SURFACE | Atmosphere.LAYER_UNDERGROUND
	add_child(ring)


## Taps on a vein: walk there if needed, otherwise add a swing. Taps while
## already on the way to that vein queue swings for the arrival.
func mine(d: int, slot: int) -> void:
	if d == node_depth and slot == node_slot and _pending_mine and moving:
		swings = mini(swings + 1, MAX_QUEUE)
		_swing_speed = minf(2.6, 1.5 + 0.25 * float(swings))
		return
	if d == node_depth and slot == node_slot and not moving and _at_node():
		swings = mini(swings + 1, MAX_QUEUE)
		_swing_speed = minf(2.6, 1.5 + 0.25 * float(swings))
		if not mining:
			_start_swing()
		else:
			rig.set_speed(_swing_speed)
		_stop_at = -1.0
		return
	node_depth = d
	node_slot = slot
	swings = 1
	mining = false
	_pending_mine = true
	var s := mgr.foreman_spot(d, slot)
	go_to(s["pos"], d, -1.0, 3.3)
	speed = 3.3


func walk_to(lvl: int, p: Vector3) -> void:
	node_slot = -1
	node_depth = 0
	swings = 0
	mining = false
	_pending_mine = false
	rig.set_carry("")
	var far := p.distance_to(position) > 12.0 or lvl != level
	go_to(p, lvl, -1.0, 3.3 if far else 1.8)
	speed = 3.3 if far else 1.8


func _at_node() -> bool:
	if node_slot < 0:
		return false
	var s := mgr.foreman_spot(node_depth, node_slot)
	return level == node_depth and Vector2(position.x - s["pos"].x, position.z - s["pos"].z).length() < 0.6


func _on_arrived() -> void:
	if _pending_mine and _at_node():
		_pending_mine = false
		var s := mgr.foreman_spot(node_depth, node_slot)
		face_point(s["look"])
		if swings > 0:
			_start_swing()
		else:
			rig.play("Idle", 1.0, 0.3)
	else:
		rig.play("Idle", 1.0, 0.3)


func _start_swing() -> void:
	mining = true
	_stop_at = -1.0
	rig.set_hand_tool(PICK)
	rig.play("Mine", _swing_speed, 0.12, true)


func _on_clip_event(ev: String) -> void:
	if ev != "impact" or not mining or node_slot < 0:
		return
	if swings <= 0:
		# A wrapped loop after the last swing: never mine unasked.
		mining = false
		rig.play("Idle", 1.0, 0.3)
		return
	var r := mgr.command({"type": "manual_swing", "depth": node_depth, "slot": node_slot})
	swung.emit(r)
	mgr.on_foreman_swing(self, r, mgr.foreman_spot(node_depth, node_slot)["look"])
	swings -= 1
	if not r.get("ok", false):
		swings = 0
	if swings <= 0:
		# Finish the follow-through, then rest the pick.
		_stop_at = rig.clip_length("Mine") * 0.9


func tick(delta: float) -> void:
	advance(delta)
	if moving:
		return
	if mining and _stop_at > 0.0 and rig.clip_position() >= _stop_at:
		mining = false
		_stop_at = -1.0
		rig.play("Idle", 1.0, 0.35)
