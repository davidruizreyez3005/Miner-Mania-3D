class_name SalesView
extends Node3D
## Trucks hauling goods from the depot to the railhead market along the road.
## The fleet size and model follow the depot level (pickup first, haul trucks
## later); trucks load at the depot, drive off along the road, and return
## empty, cycling at the simulation's trip time while sales are running.

var world: MineWorld
var trucks: Array = []           # {"node", "anim", "phase"}
var model := ""
var road: Array = []             # Vector3 polyline from the depot to beyond the map
var depot_pos := Vector3.ZERO
var _count := 0


func setup(w: MineWorld) -> void:
	world = w
	name = "Sales"
	var pl := w.layout.plot("depot")
	var pos: Array = pl.get("pos", [30, -24])
	depot_pos = Vector3(float(pos[0]), 0, float(pos[1]))
	road = [depot_pos + Vector3(-2.0, 0, 3.0)]
	for p in w.layout.data.get("surface", {}).get("road", []):
		road.append(Vector3(float(p[0]), 0, float(p[1]) + 1.6))


func _model_for_level() -> String:
	return "veh_utility_01" if world.sim.facility_level("depot") < 10 else "veh_mining_truck_01"


func _rebuild(n: int) -> void:
	for t in trucks:
		(t["node"] as Node3D).queue_free()
	trucks.clear()
	model = _model_for_level()
	_count = n
	for i in n:
		var node := Assets.instantiate(model, "", false)
		add_child(node)
		var aps := node.find_children("*", "AnimationPlayer", true, false)
		trucks.append({"node": node, "anim": aps[0] if not aps.is_empty() else null, "phase": float(i) / float(maxi(1, n))})
		var exhaust := VfxLibrary.attach(node, "exhaust", Vector3(0.7, 1.8 if model == "veh_utility_01" else 3.6, -1.2))
		exhaust.amount = 6


func _point_on_road(t: float) -> Array:
	## -> [position, direction] at fraction t of the road length.
	var lengths: Array = []
	var total := 0.0
	for i in road.size() - 1:
		var l := (road[i] as Vector3).distance_to(road[i + 1])
		lengths.append(l)
		total += l
	var s := clampf(t, 0.0, 1.0) * total
	for i in lengths.size():
		if s <= float(lengths[i]) or i == lengths.size() - 1:
			var a: Vector3 = road[i]
			var b: Vector3 = road[i + 1]
			var f := clampf(s / maxf(float(lengths[i]), 1e-4), 0.0, 1.0)
			return [a.lerp(b, f), (b - a).normalized()]
		s -= float(lengths[i])
	return [road[road.size() - 1], Vector3.RIGHT]


func sync(delta: float) -> void:
	var sr: Dictionary = world.sim.rt.get("sales", {})
	var n := clampi(int(sr.get("trucks", 1)), 1, 4)
	if n != _count or _model_for_level() != model:
		_rebuild(n)
	var active := bool(sr.get("active", false)) and Simulation.inv_total(world.sim.state.warehouse) > 0.01 or float(sr.get("sold_rate", 0.0)) > 0.0
	var trip := maxf(6.0, float(sr.get("trip_s", 16.0)))
	for i in trucks.size():
		var t: Dictionary = trucks[i]
		var node: Node3D = t["node"]
		var ph := float(t["phase"])
		if active or ph > 0.02:
			ph = fposmod(ph + delta / trip, 1.0)
			if not active and ph < 0.05:
				ph = 0.0
		t["phase"] = ph
		var pos: Vector3
		var dir: Vector3
		var moving := true
		if ph < 0.12 or ph > 0.94:
			var slot := depot_pos + Vector3(-1.5 - 3.4 * i, 0, 1.8)
			pos = slot
			dir = Vector3.RIGHT
			moving = false
		elif ph < 0.53:
			var r := _point_on_road((ph - 0.12) / 0.41)
			pos = r[0]
			dir = r[1]
		else:
			var r2 := _point_on_road(1.0 - (ph - 0.53) / 0.41)
			pos = (r2[0] as Vector3) + Vector3(0, 0, -3.2)
			dir = -(r2[1] as Vector3)
		pos.y = world.ground_height(pos.x, pos.z)
		node.global_position = node.global_position.lerp(pos, clampf(delta * 6.0, 0.0, 1.0)) if node.global_position.distance_to(pos) < 8.0 else pos
		if dir.length() > 0.1:
			var yaw := atan2(dir.x, dir.z)
			node.rotation.y = lerp_angle(node.rotation.y, yaw, clampf(delta * 5.0, 0.0, 1.0))
		node.visible = pos.x < 66.0
		var a: AnimationPlayer = t["anim"]
		if a:
			var want := "Drive" if moving else "Idle"
			if a.current_animation != want and a.has_animation(want):
				a.play(want, 0.3)
