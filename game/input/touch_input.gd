class_name TouchInput
extends Node
## Gestures on the 3D view. One finger drags to pan (with inertia), two
## fingers pinch to zoom and drag together to pan, a tap picks what is under
## the finger and a double tap zooms toward it. The camera never rotates.
## Mouse wheel and keys (WASD / arrows, +/-) do the same on desktop. UI
## controls receive events first; this only sees what the UI did not consume.
##
## Picking asks the physics world for every tap target along the ray and
## prefers veins over workers over buildings over whole galleries, so the
## core tap-to-mine loop works even with a crew standing at the rock.

signal tapped(target: String, world_pos: Vector3, floor_level: int, floor_pos: Vector3)

const TAP_MOVE_PX := 16.0
const TAP_TIME := 0.4
const DOUBLE_TAP_S := 0.3
const PRIORITY := {"node": 0, "worker": 1, "facility": 2, "lift": 2, "depth": 3}

var rig: CameraRig
var world: MineWorld
var enabled := true
var _touches := {}                 # index -> Vector2
var _start := {}                   # index -> [Vector2, msec]
var _dragging := false
var _pinch_d := 0.0
var _pinch_mid := Vector2.ZERO
var _last_tap_ms := -10000
var _last_tap_p := Vector2.ZERO
var _vel := Vector2.ZERO


func setup(r: CameraRig, w: MineWorld) -> void:
	rig = r
	world = w
	name = "TouchInput"


func _unhandled_input(event: InputEvent) -> void:
	if not enabled or rig == null:
		return
	if event is InputEventScreenTouch:
		_touch(event as InputEventScreenTouch)
	elif event is InputEventScreenDrag:
		_drag(event as InputEventScreenDrag)
	elif event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.pressed and mb.button_index == MOUSE_BUTTON_WHEEL_UP:
			rig.zoom_by(0.88)
		elif mb.pressed and mb.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			rig.zoom_by(1.13)
	elif event is InputEventMagnifyGesture:
		rig.zoom_by(1.0 / maxf((event as InputEventMagnifyGesture).factor, 0.01))
	elif event is InputEventPanGesture:
		rig.pan_pixels(-(event as InputEventPanGesture).delta * 20.0)


func _touch(e: InputEventScreenTouch) -> void:
	if e.pressed:
		_touches[e.index] = e.position
		_start[e.index] = [e.position, Time.get_ticks_msec()]
		if _touches.size() == 1:
			_dragging = false
			rig.dragging = true
			rig.pan_velocity = Vector3.ZERO
			_vel = Vector2.ZERO
		elif _touches.size() == 2:
			_begin_pinch()
		return
	var st: Array = _start.get(e.index, [e.position, Time.get_ticks_msec()])
	var was_single := _touches.size() == 1
	_touches.erase(e.index)
	_start.erase(e.index)
	if _touches.size() == 1:
		# Back to one finger: continue panning from where it is.
		_dragging = true
	if not _touches.is_empty():
		return
	rig.dragging = false
	if was_single and not _dragging and Time.get_ticks_msec() - int(st[1]) <= int(TAP_TIME * 1000.0) \
			and (e.position - (st[0] as Vector2)).length() < TAP_MOVE_PX:
		_tap(e.position)
	elif _dragging:
		rig.release_pan(_vel)
	_dragging = false


func _drag(e: InputEventScreenDrag) -> void:
	if not _touches.has(e.index):
		_touches[e.index] = e.position
		_start[e.index] = [e.position, Time.get_ticks_msec()]
	var prev: Vector2 = _touches[e.index]
	_touches[e.index] = e.position
	if _touches.size() == 1:
		var st: Array = _start[e.index]
		if not _dragging and (e.position - (st[0] as Vector2)).length() >= TAP_MOVE_PX:
			_dragging = true
		if _dragging:
			rig.pan_pixels(e.position - prev)
			_vel = e.velocity if e.velocity.length() > 0.0 else _vel
	elif _touches.size() >= 2:
		_dragging = true
		var pts: Array = _touches.values()
		var a: Vector2 = pts[0]
		var b: Vector2 = pts[1]
		var d := a.distance_to(b)
		var mid := (a + b) * 0.5
		if _pinch_d > 1.0 and d > 1.0:
			rig.zoom_by(_pinch_d / d)
		rig.pan_pixels(mid - _pinch_mid)
		_pinch_d = d
		_pinch_mid = mid


func _begin_pinch() -> void:
	var pts: Array = _touches.values()
	var a: Vector2 = pts[0]
	var b: Vector2 = pts[1]
	_pinch_d = a.distance_to(b)
	_pinch_mid = (a + b) * 0.5
	_dragging = true


func _process(delta: float) -> void:
	if not enabled or rig == null or not OS.has_feature("pc"):
		return
	# Desktop keys (development and testing).
	var k := Vector2.ZERO
	if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT):
		k.x += 1.0
	if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT):
		k.x -= 1.0
	if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP):
		k.y += 1.0
	if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN):
		k.y -= 1.0
	if k != Vector2.ZERO:
		rig.pan_pixels(k * 900.0 * delta)
	if Input.is_key_pressed(KEY_EQUAL) or Input.is_key_pressed(KEY_KP_ADD):
		rig.zoom_by(1.0 - 1.2 * delta)
	if Input.is_key_pressed(KEY_MINUS) or Input.is_key_pressed(KEY_KP_SUBTRACT):
		rig.zoom_by(1.0 + 1.2 * delta)


# -------------------------------------------------------------------- tap

func _tap(p: Vector2) -> void:
	var now := Time.get_ticks_msec()
	var double := now - _last_tap_ms < int(DOUBLE_TAP_S * 1000.0) and p.distance_to(_last_tap_p) < 60.0
	_last_tap_ms = now
	_last_tap_p = p
	var pick := pick_at(p)
	if double and String(pick["target"]) == "" or double and String(pick["target"]).begins_with("depth"):
		var at: Vector3 = pick["floor_pos"] if int(pick["floor_level"]) >= 0 else pick["pos"]
		rig.focus_on(at, maxf(rig.target_dist * 0.6, rig.min_dist))
		return
	tapped.emit(String(pick["target"]), pick["pos"], int(pick["floor_level"]), pick["floor_pos"])


## What is under a screen point: {target, pos, floor_level, floor_pos}.
## floor_level is the level whose walkable floor the ray meets (-1: none).
func pick_at(p: Vector2) -> Dictionary:
	var cam := rig.camera
	var from := cam.project_ray_origin(p)
	var dir := cam.project_ray_normal(p)
	var best := ""
	var best_pos := Vector3.ZERO
	var best_rank := 99
	var space := world.get_world_3d().direct_space_state
	var exclude: Array[RID] = []
	for i in 6:
		var q := PhysicsRayQueryParameters3D.create(from, from + dir * 500.0, MineWorld.PICK_LAYER | MineWorld.PICK_AREA_LAYER, exclude)
		var r := space.intersect_ray(q)
		if r.is_empty():
			break
		var col := r["collider"] as CollisionObject3D
		exclude.append(col.get_rid())
		var t := String(col.get_meta("target", ""))
		var kind := t.split(":")[0]
		var rank := int(PRIORITY.get(kind, 9))
		if rank < best_rank:
			best_rank = rank
			best = t
			best_pos = r["position"]
	var fl := _floor_hit(from, dir)
	return {"target": best, "pos": best_pos, "floor_level": fl[0], "floor_pos": fl[1]}


## First walkable floor (surface camp or a dug gallery) the ray meets.
func _floor_hit(from: Vector3, dir: Vector3) -> Array:
	var nav := world.agents.nav
	var levels := [0]
	levels.append_array(world.unlocked_depths())
	var best_t := INF
	var best: Array = [-1, Vector3.ZERO]
	for lvl in levels:
		var y := 0.0 if int(lvl) == 0 else world.content.depth_floor_y(int(lvl))
		if absf(dir.y) < 1e-4:
			continue
		var t := (y - from.y) / dir.y
		if t <= 0.0 or t >= best_t:
			continue
		var hp := from + dir * t
		var g := nav.grid(int(lvl))
		if g.is_free(Vector2(hp.x, hp.z)):
			best_t = t
			best = [int(lvl), Vector3(hp.x, nav.floor_y(int(lvl), hp.x, hp.z), hp.z)]
	return best
