class_name CameraRig
extends Node3D
## The 3/4 view camera. It looks at a focus point from a fixed heading (north,
## into the hills) at a pitch and distance, eased toward targets. Pitch
## follows the focus height - a high 3/4 view over the camp, a near-level
## view into the cutaway galleries - so one rig serves the whole mine. Drags
## move the content with the finger everywhere: up the screen means toward
## the cut edge on the surface and deeper underground, so dragging past the
## camp's front edge flows smoothly down the cut face (and back up). Supports
## pan with inertia, zoom, focus flights to targets, following an agent,
## bounds, and obstruction handling: surface buildings between the camera
## and what it looks at fade.

signal moved

const FRONT_Z := -2.0                # the camp's front edge (focus z on the surface)
const GALLERY_Z := -3.8              # focus z underground (mid-gallery)
const SURFACE_PITCH := Vector2(-34.0, -52.0)      # pitch at min / max distance (deg)
const UNDER_PITCH := Vector2(-9.0, -16.0)
const EASE := 7.0

var world: MineWorld
var camera := Camera3D.new()
var focus := Vector3(2.0, -8.0, GALLERY_Z)
var target_focus := focus
var dist := 24.0
var target_dist := 24.0
var min_dist := 7.0
var max_dist := 72.0
var pan_velocity := Vector3.ZERO
var follow: Node3D
var dragging := false
var bounds_x := Vector2(-40.0, 44.0)
var bounds_z := Vector2(-42.0, FRONT_Z)
var _faded: Array = []
var _obstruct_t := 0.0
var _u := 1.0                         # 0 surface .. 1 underground (smoothed)
var _pitch := deg_to_rad(UNDER_PITCH.x)
var _last_zone := Vector2(-1, -1)


func setup(w: MineWorld) -> void:
	world = w
	name = "CameraRig"
	camera.name = "Camera"
	camera.fov = 52.0
	camera.near = 0.3
	camera.far = float(GraphicsQuality.current_value("camera_far", 700.0))
	add_child(camera)
	camera.current = true
	EventBus.quality_changed.connect(_on_quality_changed)
	_apply(1.0)


func _on_quality_changed(q: int) -> void:
	camera.far = float(GraphicsQuality.value(q, "camera_far", 700.0))


# ---------------------------------------------------------------- controls

func deepest_y() -> float:
	var d := maxi(1, world.sim.state.deepest_unlocked())
	return world.content.depth_floor_y(d) + 1.6


## Pans by a screen-space drag (pixels). Content follows the finger; the
## camp's front edge turns into the descent down the cut face.
func pan_pixels(delta_px: Vector2) -> void:
	_pan_world(_px_to_world(delta_px) * float(Settings.get_value("camera_sensitivity", 1.0)))
	follow = null


## Focus move (view space, see _pan_world) that keeps the content under a
## finger moving by `px` screen pixels. Over the camp the view is slanted, so
## a vertical pixel covers more ground (1 / sin pitch).
func _px_to_world(px: Vector2) -> Vector2:
	var vp := get_viewport().get_visible_rect().size
	var k := 2.0 * dist * tan(deg_to_rad(camera.fov) * 0.5) / maxf(vp.y, 1.0)
	var d := -px * k
	if target_focus.y > -0.5:
		d.y /= maxf(sin(-_pitch), 0.35)
	return d


## `d` is the focus move in view space: +x to the right, +y down the screen
## (on the surface: toward the camera and the cut edge; underground: deeper).
func _pan_world(d: Vector2) -> void:
	if target_focus.y > -0.5:
		target_focus += Vector3(d.x, 0.0, d.y)
		if target_focus.z > FRONT_Z:
			var excess := target_focus.z - FRONT_Z
			target_focus.z = FRONT_Z
			target_focus.y -= excess * 1.4
	else:
		target_focus.x += d.x
		target_focus.y -= d.y
		target_focus.z = GALLERY_Z
		if target_focus.y > 0.0:
			var excess2 := target_focus.y
			target_focus.y = 0.0
			target_focus.z = FRONT_Z - excess2 / 1.4
	_clamp_target()


## A finger lands on the view: a flight in progress stops where it is and
## the view follows the finger 1:1 until it lifts (easing toward the finger
## would make the content trail behind it, worst at a low frame rate).
func grab() -> void:
	dragging = true
	pan_velocity = Vector3.ZERO
	target_focus = focus
	target_dist = dist


func zoom_by(factor: float) -> void:
	target_dist = clampf(target_dist * factor, min_dist, _max_dist_here())


func release_pan(velocity_px: Vector2) -> void:
	if bool(Settings.get_value("reduce_motion", false)):
		pan_velocity = Vector3.ZERO
		return
	var v := _px_to_world(velocity_px)
	pan_velocity = Vector3(v.x, v.y, 0.0).limit_length(60.0)


## Flies to a world point (and optionally a zoom distance).
func focus_on(p: Vector3, zoom: float = -1.0) -> void:
	follow = null
	pan_velocity = Vector3.ZERO
	target_focus = p
	if p.y < -0.5:
		target_focus.z = GALLERY_Z
	if zoom > 0.0:
		target_dist = zoom
	_clamp_target()


func follow_node(n: Node3D, zoom: float = -1.0) -> void:
	follow = n
	pan_velocity = Vector3.ZERO
	if zoom > 0.0:
		target_dist = zoom


## Named targets: "surface", "depth:<d>", "facility:<id>", "worker:<id>", "foreman".
func focus_target(t: String) -> void:
	var parts := t.split(":")
	match parts[0]:
		"surface":
			focus_on(Vector3(4.0, 0.0, -14.0), 34.0)
		"depth":
			var d := int(parts[1])
			focus_on(Vector3(4.0, world.content.depth_floor_y(d) + 1.9, GALLERY_Z), 29.0)
		"facility":
			if parts[1] == "headframe":
				focus_on(world.lift_view.global_position + Vector3(0, 2, -4), 22.0)
			elif world.facility_views.has(parts[1]):
				focus_on((world.facility_views[parts[1]] as Node3D).global_position + Vector3(0, 1.5, 0), 20.0)
		"worker":
			var a: Node3D = world.agents.agents.get(int(parts[1]))
			if a:
				follow_node(a, 13.0)
		"foreman":
			follow_node(world.agents.foreman, 13.0)
		"node":
			var dv: DepthView = world.depth_views.get(int(parts[1]))
			if dv:
				focus_on(dv.node_position(int(parts[2])), 14.0)


# ------------------------------------------------------------------ update

func _max_dist_here() -> float:
	return lerpf(max_dist, 44.0, clampf(-target_focus.y / 8.0, 0.0, 1.0))


func _clamp_target() -> void:
	target_focus.x = clampf(target_focus.x, bounds_x.x, bounds_x.y)
	target_focus.y = clampf(target_focus.y, deepest_y(), 0.0)
	if target_focus.y > -0.5:
		target_focus.z = clampf(target_focus.z, bounds_z.x, bounds_z.y)
		target_focus.y = 0.0 if target_focus.y > -0.5 else target_focus.y
	else:
		# Underground the view stays on the galleries' span.
		target_focus.x = clampf(target_focus.x, -14.0, 22.0)
		target_focus.z = GALLERY_Z


func _process(delta: float) -> void:
	if world == null:
		return
	if follow and is_instance_valid(follow) and follow.is_inside_tree():
		var fp := follow.global_position + Vector3(0, 1.2, 0)
		target_focus = Vector3(fp.x, fp.y if fp.y < -0.5 else 0.0, GALLERY_Z if fp.y < -0.5 else fp.z)
		_clamp_target()
	elif not dragging and pan_velocity.length_squared() > 0.01:
		_pan_world(Vector2(pan_velocity.x, pan_velocity.y) * delta)
		pan_velocity = pan_velocity.lerp(Vector3.ZERO, clampf(delta * 4.0, 0.0, 1.0))
	target_dist = clampf(target_dist, min_dist, _max_dist_here())
	_apply(delta)
	_obstruct_t -= delta
	if _obstruct_t <= 0.0:
		_obstruct_t = 0.2
		_update_obstruction()


func _apply(delta: float) -> void:
	# Reduced motion: shorter, snappier camera moves.
	var ease := EASE * (2.5 if bool(Settings.get_value("reduce_motion", false)) else 1.0)
	var a := 1.0 if dragging else clampf(delta * ease, 0.0, 1.0)
	focus = focus.lerp(target_focus, a)
	dist = lerpf(dist, target_dist, a)
	_u = clampf(-(focus.y + 0.5) / 5.5, 0.0, 1.0)
	var zt := clampf((dist - min_dist) / (max_dist - min_dist), 0.0, 1.0)
	var pitch_s := lerpf(SURFACE_PITCH.x, SURFACE_PITCH.y, zt)
	var pitch_u := lerpf(UNDER_PITCH.x, UNDER_PITCH.y, zt)
	_pitch = deg_to_rad(lerpf(pitch_s, pitch_u, smoothstep(0.0, 1.0, _u)))
	var eye := focus + Vector3(0.0, -sin(_pitch) * dist, cos(_pitch) * dist)
	# Never dip the eye into the ground over the camp.
	if _u < 0.5:
		eye.y = maxf(eye.y, world.ground_height(eye.x, minf(eye.z, -0.5)) + 2.0)
	camera.global_transform = Transform3D(Basis(), eye).looking_at(focus, Vector3.UP)
	# Surroundings follow the view: atmosphere, sound zone.
	var dnear := clampi(roundi(-(focus.y - world.content.depth_floor_y(1)) / world.content.level_spacing) + 1, 1, world.content.depth_count())
	var zone := Vector2(snappedf(_u, 0.02), dnear)
	if zone != _last_zone:
		_last_zone = zone
		world.atmosphere.set_underground(_u, world.content.depth(dnear))
		Audio.set_listener_zone(_u, dnear)
	moved.emit()


func underground_amount() -> float:
	return _u


## World depth index the camera is looking at (0 on the surface).
func level_in_view() -> int:
	if _u < 0.5:
		return 0
	var d := roundi(-(focus.y - world.content.depth_floor_y(1)) / world.content.level_spacing) + 1
	return clampi(d, 1, world.content.depth_count())


# -------------------------------------------------------------- obstruction

## Surface buildings between the eye and the focus fade out so the thing you
## look at stays visible.
func _update_obstruction() -> void:
	var hits: Array = []
	if _u < 0.6 and is_inside_tree():
		var space := get_world_3d().direct_space_state
		var from := camera.global_position
		var to := focus + Vector3(0, 0.8, 0)
		var exclude: Array[RID] = []
		for i in 4:
			var q := PhysicsRayQueryParameters3D.create(from, to, MineWorld.PICK_LAYER, exclude)
			var r := space.intersect_ray(q)
			if r.is_empty():
				break
			var col: Object = r["collider"]
			exclude.append((col as CollisionObject3D).get_rid())
			var fv := _facility_of(col as Node)
			if fv and fv.global_position.distance_to(to) > 3.5:
				hits.append(fv)
	for f in _faded:
		if is_instance_valid(f) and not f in hits:
			(f as FacilityView).set_faded(false)
	for f in hits:
		(f as FacilityView).set_faded(true)
	_faded = hits


func _facility_of(n: Node) -> FacilityView:
	while n != null:
		if n is FacilityView:
			return n as FacilityView
		n = n.get_parent()
	return null
