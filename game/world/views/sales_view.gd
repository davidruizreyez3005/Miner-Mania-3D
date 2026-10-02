class_name SalesView
extends Node3D
## The truck fleet hauling goods from the depot to the railhead market. The
## fleet size and model follow the depot level (pickups first, haul trucks
## later). Every truck has its own bay in the depot's yard (layout
## surface.truck_yard, side by side, facing the road): it loads there, pulls
## out and turns onto the eastbound lane, drives off the map to the market,
## comes back on the other lane, drives past its bay and reverses in along a
## quarter turn. Trucks are sent one after another, never sooner than a trip /
## fleet-size apart; with manual sales (SELL) the fleet goes out in turn while
## the sale lasts and then parks. A truck drives its whole round at one speed,
## so where it will be is known the moment it leaves: a loaded truck pulls out
## only when its round keeps clear of every other truck's (it waits in its bay
## otherwise), so trucks never drive into each other - crossing the other
## lane, merging or reversing into their bays. Tapping a truck opens the depot.

const LOAD_SHARE := 0.14         # of a trip, loading in the bay
const PARK_SHARE := 0.06         # of a trip, settling into the bay
const MIN_HEADWAY_S := 1.5
const HIDE_X := 66.0             # beyond the edge of the map
const CLEARANCE := 0.3           # m kept between two trucks' footprints
const PLAN_STEP := 0.5           # m along a round between two looks ahead
const RECHECK_S := 0.25          # a loaded truck that must wait looks again
const ARC_STEP := PI / 72.0      # turns are drawn in 2.5 degree steps

var world: MineWorld
var trucks: Array = []           # {"node", "anim", "bay", "state", "s", "v", "timer"}
var model := ""
var bays: Array = []             # Vector3 bay centres (trucks face +z)
var _out: Array = []             # per bay: path bay -> end of the road
var _back: Array = []            # per bay: path end of the road -> past the bay -> reverse in
var _out_len: Array = []         # per bay: path lengths (m)
var _back_len: Array = []
var _longest := 1.0              # out + back length of the farthest bay (m)
var _half := Vector2.ONE         # footprint half size (width, length) with CLEARANCE
var _offset := Vector2.ZERO      # footprint centre in the model (x, z)
var _count := 0
var _since_departure := 1e9
var _next := 0


func setup(w: MineWorld) -> void:
	world = w
	name = "Sales"
	bays = SiteLayout.truck_bays(w.layout)
	if bays.is_empty():                       # layouts without a yard: one bay at the depot
		var pl := w.layout.plot("depot")
		var pos: Array = pl.get("pos", [30, -27])
		bays = [Vector3(float(pos[0]), 0, float(pos[1]) - 8.0)]
	var y: Dictionary = w.layout.data.get("surface", {}).get("truck_yard", {})
	var lane_out := float(y.get("lane_out_z", -23.1))
	var lane_back := float(y.get("lane_back_z", -26.9))
	var end_x := float(y.get("end_x", 72.0))
	_out.clear()
	_back.clear()
	_out_len.clear()
	_back_len.clear()
	_longest = 1.0
	for b in bays:
		var p: Vector3 = b
		# Out: straight ahead to the turn, a right turn onto the eastbound lane.
		var turn_z := clampf(float(y.get("exit_z", -27.7)), p.z + 0.5, lane_out - 1.0)
		var r_out := lane_out - turn_z
		var opts := [p, Vector3(p.x, 0, turn_z)] + _arc(Vector3(p.x + r_out, 0, turn_z), r_out, PI, PI * 0.5) \
			+ [Vector3(end_x, 0, lane_out)]
		# Back: past the bay on the westbound lane, then reverse along a quarter
		# turn until straight in front of the bay, and on into it.
		var r_in := clampf(float(y.get("reverse_radius", 5.0)), 1.0, lane_back - p.z - 0.5)
		var bpts := [Vector3(end_x, 0, lane_back), Vector3(p.x - r_in, 0, lane_back)] \
			+ _arc(Vector3(p.x - r_in, 0, lane_back - r_in), r_in, PI * 0.5, 0.0) + [p]
		var brev := [0]
		for k in bpts.size() - 2:
			brev.append(1)
		var out := _path(opts, [])
		var back := _path(bpts, brev)
		_out.append(out)
		_back.append(back)
		_out_len.append(_path_length(out))
		_back_len.append(_path_length(back))
		_longest = maxf(_longest, _path_length(out) + _path_length(back))


## Points on a circle around `c` (xz) from angle `a0` to `a1` (x = cos,
## z = sin), the start left out.
static func _arc(c: Vector3, r: float, a0: float, a1: float) -> Array:
	var out: Array = []
	var n := maxi(2, ceili(absf(a1 - a0) / ARC_STEP))
	for k in range(1, n + 1):
		var a := lerpf(a0, a1, float(k) / n)
		out.append(Vector3(c.x + r * cos(a), 0.0, c.z + r * sin(a)))
	return out


## A path through `pts`; `rev` flags the segments driven in reverse (1).
static func _path(pts: Array, rev: Array) -> Dictionary:
	var p := PackedVector3Array(pts)
	var cum := PackedFloat64Array([0.0])
	var r := PackedByteArray()
	for i in range(1, p.size()):
		cum.append(cum[i - 1] + p[i - 1].distance_to(p[i]))
		r.append(int(rev[i - 1]) if i - 1 < rev.size() else 0)
	return {"pts": p, "cum": cum, "rev": r}


static func _path_length(path: Dictionary) -> float:
	var cum: PackedFloat64Array = path["cum"]
	return cum[cum.size() - 1]


func _model_for_level() -> String:
	return "veh_utility_01" if world.sim.facility_level("depot") < 10 else "veh_mining_truck_01"


func _rebuild(n: int) -> void:
	for t in trucks:
		(t["node"] as Node3D).queue_free()
	trucks.clear()
	model = _model_for_level()
	var mb := Assets.bounds(model)
	_half = Vector2(mb.size.x, mb.size.z) * 0.5 + Vector2.ONE * CLEARANCE * 0.5
	_offset = Vector2(mb.get_center().x, mb.get_center().z)
	_count = n
	_next = 0
	for i in n:
		var node := Assets.instantiate(model, "", false)
		add_child(node)
		var aps := node.find_children("*", "AnimationPlayer", true, false)
		trucks.append({"node": node, "anim": aps[0] if not aps.is_empty() else null, "bay": i, "state": "parked",
			"s": 0.0, "v": 1.0, "timer": 0.0})
		var exhaust := VfxLibrary.attach(node, "exhaust", Vector3(0.7, 1.8 if model == "veh_utility_01" else 3.6, -1.2))
		exhaust.amount = 6
		_add_pick(node)
		var bay: Vector3 = bays[i]
		node.global_position = Vector3(bay.x, world.ground_height(bay.x, bay.z), bay.z)
		node.rotation.y = 0.0


## A tap on a truck opens the depot.
func _add_pick(node: Node3D) -> void:
	var body := StaticBody3D.new()
	body.collision_layer = MineWorld.PICK_LAYER
	body.collision_mask = 0
	body.set_meta("target", "facility:depot")
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	var b := Assets.bounds(model)
	box.size = b.size
	cs.shape = box
	cs.position = b.get_center()
	body.add_child(cs)
	node.add_child(body)


## Position and facing at distance `s` along a path: [position, facing] - a
## truck reversing faces against its way.
static func _along(path: Dictionary, s: float) -> Array:
	var pts: PackedVector3Array = path["pts"]
	var cum: PackedFloat64Array = path["cum"]
	var i := clampi(cum.bsearch(s) - 1, 0, pts.size() - 2)
	var a := pts[i]
	var b := pts[i + 1]
	var l := cum[i + 1] - cum[i]
	var d := (b - a) / l if l > 1e-4 else Vector3.BACK
	return [a.lerp(b, clampf((s - cum[i]) / maxf(l, 1e-4), 0.0, 1.0)), -d if (path["rev"] as PackedByteArray)[i] == 1 else d]


## Where bay `b`'s truck is `s` metres into its round: [position, facing].
func _round_pose(b: int, s: float) -> Array:
	if s < float(_out_len[b]):
		return _along(_out[b], s)
	if s < float(_out_len[b]) + float(_back_len[b]):
		return _along(_back[b], s - float(_out_len[b]))
	return [bays[b], Vector3.BACK]


## Where truck `t` will be `ahead` seconds from now: a truck on its round
## keeps its speed, any other stays in its bay.
func _pose(t: Dictionary, ahead: float) -> Array:
	var b := int(t["bay"])
	match String(t["state"]):
		"out":
			return _round_pose(b, float(t["s"]) + float(t["v"]) * ahead)
		"back":
			return _round_pose(b, float(_out_len[b]) + float(t["s"]) + float(t["v"]) * ahead)
	return [bays[b], Vector3.BACK]


## Whether two trucks' footprints (poses [position, facing]) come closer
## than CLEARANCE (separating axes of two rectangles).
func _overlap(a: Array, b: Array) -> bool:
	var fa := Vector2((a[1] as Vector3).x, (a[1] as Vector3).z)
	var fb := Vector2((b[1] as Vector3).x, (b[1] as Vector3).z)
	var ra := Vector2(fa.y, -fa.x)            # the model's +x side
	var rb := Vector2(fb.y, -fb.x)
	var ca := Vector2((a[0] as Vector3).x, (a[0] as Vector3).z) + ra * _offset.x + fa * _offset.y
	var cb := Vector2((b[0] as Vector3).x, (b[0] as Vector3).z) + rb * _offset.x + fb * _offset.y
	var d := cb - ca
	if d.length_squared() > 4.0 * _half.length_squared():
		return false
	for axis: Vector2 in [ra, fa, rb, fb]:
		var reach := _half.x * (absf(ra.dot(axis)) + absf(rb.dot(axis))) + _half.y * (absf(fa.dot(axis)) + absf(fb.dot(axis)))
		if absf(d.dot(axis)) > reach:
			return false
	return true


## Whether truck `i` can pull out now at `speed`: its whole round, out and
## back into its bay, keeps clear of where every other truck will be.
func _clear_to_go(i: int, speed: float) -> bool:
	var b := int(trucks[i]["bay"])
	var total := float(_out_len[b]) + float(_back_len[b])
	var steps := ceili(total / PLAN_STEP)
	var near := 2.0 * (_half.length() + _offset.length())
	near *= near
	var still: Array = []                     # poses of the trucks in their bays
	var rounds: Array = []                    # [bay, metres into the round now, speed]
	for j in trucks.size():
		if j == i:
			continue
		var t: Dictionary = trucks[j]
		var bj := int(t["bay"])
		match String(t["state"]):
			"out":
				rounds.append([bj, float(t["s"]), float(t["v"])])
			"back":
				rounds.append([bj, float(_out_len[bj]) + float(t["s"]), float(t["v"])])
			_:
				still.append([bays[bj], Vector3.BACK])
	for k in steps + 1:
		var s := minf(k * PLAN_STEP, total)
		var me := _round_pose(b, s)
		var at: Vector3 = me[0]
		for o: Array in still:
			if at.distance_squared_to(o[0]) < near and _overlap(me, o):
				return false
		for r: Array in rounds:
			var other := _round_pose(r[0], float(r[1]) + float(r[2]) * s / speed)
			if at.distance_squared_to(other[0]) < near and _overlap(me, other):
				return false
	return true


func sync(delta: float) -> void:
	var sr: Dictionary = world.sim.rt.get("sales", {})
	var n := clampi(int(sr.get("trucks", 1)), 1, mini(4, bays.size()))
	if n != _count or _model_for_level() != model:
		_rebuild(n)
	# A manual sale (SELL) sends the fleet out in turn while it lasts; with
	# automatic sales trucks run while there is something to sell.
	var goods := Simulation.inv_total(world.sim.state.warehouse) > 0.01 or float(sr.get("sold_rate", 0.0)) > 0.0
	var active := (goods if bool(sr.get("auto", false)) else true) and bool(sr.get("active", false))
	var trip := maxf(6.0, float(sr.get("trip_s", 16.0)))
	var speed := _longest / (trip * (1.0 - LOAD_SHARE - PARK_SHARE))
	var headway := maxf(trip / float(n), MIN_HEADWAY_S)
	_since_departure += delta
	# The next parked truck (in turn) starts loading once the one before has a head start.
	if active and _since_departure >= headway:
		for k in n:
			var j := (_next + k) % n
			if String(trucks[j]["state"]) == "parked":
				trucks[j]["state"] = "loading"
				trucks[j]["timer"] = trip * LOAD_SHARE
				_since_departure = 0.0
				_next = (j + 1) % n
				break
	for t in trucks:
		_advance(t, delta, trip)
	# Loaded trucks pull out once their way is clear (after everyone moved, so
	# the look ahead starts from where the others are now).
	for i in trucks.size():
		var t: Dictionary = trucks[i]
		if String(t["state"]) == "loading" and float(t["timer"]) <= 0.0:
			if _clear_to_go(i, speed):
				t["state"] = "out"
				t["s"] = 0.0
				t["v"] = speed
			else:
				t["timer"] = RECHECK_S


func _advance(t: Dictionary, delta: float, trip: float) -> void:
	var node: Node3D = t["node"]
	var b := int(t["bay"])
	var moving := false
	match String(t["state"]):
		"loading":
			t["timer"] = float(t["timer"]) - delta
		"out", "back":
			t["s"] = float(t["s"]) + float(t["v"]) * delta
			if String(t["state"]) == "out" and float(t["s"]) >= float(_out_len[b]):
				t["state"] = "back"
				t["s"] = float(t["s"]) - float(_out_len[b])
			if String(t["state"]) == "back" and float(t["s"]) >= float(_back_len[b]):
				t["state"] = "parking"
				t["timer"] = trip * PARK_SHARE
			else:
				moving = true
		"parking":
			t["timer"] = float(t["timer"]) - delta
			if float(t["timer"]) <= 0.0:
				t["state"] = "parked"
	# Trucks drive exactly where the plan has them, so the look ahead holds.
	var pose := _pose(t, 0.0)
	var pos: Vector3 = pose[0]
	var face: Vector3 = pose[1]
	node.global_position = Vector3(pos.x, world.ground_height(pos.x, pos.z), pos.z)
	node.rotation.y = atan2(face.x, face.z)
	node.visible = pos.x < HIDE_X
	var a: AnimationPlayer = t["anim"]
	if a:
		var want := "Drive" if moving else "Idle"
		if a.current_animation != want and a.has_animation(want):
			a.play(want, 0.3)


## Trucks on the road or in the yard (for tests and the camera).
func truck_positions() -> Array:
	var out: Array = []
	for t in trucks:
		out.append((t["node"] as Node3D).global_position)
	return out
