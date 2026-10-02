class_name WorldLayout
extends RefCounted
## Named locations of the mine site (data/world/layout.json) and travel times
## between them. Shared by the simulation (job travel delays) and the world
## builder (where things are placed), so what workers do on screen matches
## what the economy assumes.
##
## Location ids:
##   surface:landing | surface:rest | plant | facility:<id> | facility:<id>:repair
##   depth:<d>:landing | depth:<d>:station | depth:<d>:rest | depth:<d>:face | depth:<d>:node:<slot>

var content: ContentDB
var data: Dictionary
var surface_y: float = 0.0
var shaft_x: float = -16.0
var shaft_z: float = -4.5
var _cache: Dictionary = {}


func _init(db: ContentDB) -> void:
	content = db
	data = db.layout
	surface_y = float(data.get("surface_y", 0.0))
	var sh: Dictionary = data.get("shaft", {})
	shaft_x = float(sh.get("x", -16.0))
	shaft_z = float(sh.get("z", -4.5))


func floor_y(depth_index: int) -> float:
	return surface_y if depth_index <= 0 else content.depth_floor_y(depth_index)


static func _v(a: Variant, y: float) -> Vector3:
	var arr: Array = a
	if arr.size() == 3:
		return Vector3(float(arr[0]), float(arr[1]) + y, float(arr[2]))
	return Vector3(float(arr[0]), y, float(arr[1]))


func plot(id: String) -> Dictionary:
	return data.get("surface", {}).get("plots", {}).get(id, {})


func node_slot_xz(slot: int) -> Vector2:
	var slots: Array = data.get("gallery", {}).get("node_slots", [])
	if slot < 0 or slot >= slots.size():
		return Vector2(0, -6)
	return Vector2(float(slots[slot][0]), float(slots[slot][1]))


func level_of(loc: String) -> int:
	if loc.begins_with("depth:"):
		return int(loc.split(":")[1])
	return 0


func position(loc: String) -> Vector3:
	if _cache.has(loc):
		return _cache[loc]
	var p := Vector3.ZERO
	var parts := loc.split(":")
	var surf: Dictionary = data.get("surface", {})
	var gal: Dictionary = data.get("gallery", {})
	match parts[0]:
		"surface":
			p = _v(surf.get(parts[1], [0, 0]), surface_y)
		"plant":
			p = _v(surf.get("plant", [0, -16]), surface_y)
		"facility":
			var pl := plot(parts[1])
			if pl.is_empty():
				p = _v(surf.get("plant", [0, -16]), surface_y)
			else:
				# facility:<id> is the operator's spot, facility:<id>:repair the mechanic's.
				var base := _v(pl.get("pos", [0, 0]), surface_y)
				var work: Array = pl.get("repair" if parts.size() > 2 and parts[2] == "repair" else "work", pl.get("work", [0, 0]))
				p = base + Vector3(float(work[0]), 0.0, float(work[1]))
		"depth":
			var d := int(parts[1])
			var y := floor_y(d)
			match parts[2]:
				"landing":
					p = _v(gal.get("landing", [-12, -4.5]), y)
				"station":
					p = _v(gal.get("station_work", [-9.5, -3.5]), y)
				"rest":
					p = _v(gal.get("rest", [-6, -7.5]), y)
				"face":
					p = _v(gal.get("face", [10, -3.5]), y)
				"node":
					var xz := node_slot_xz(int(parts[3]))
					p = Vector3(xz.x, y, xz.y + float(gal.get("node_work_offset_z", 1.6)))
				_:
					p = _v(gal.get("landing", [-12, -4.5]), y)
		_:
			p = Vector3.ZERO
	_cache[loc] = p
	return p


func landing(level: int) -> Vector3:
	return position("surface:landing") if level <= 0 else position("depth:%d:landing" % level)


static func _walk(a: Vector3, b: Vector3) -> float:
	return absf(a.x - b.x) + absf(a.z - b.z)


## Seconds to walk (and ride the cage) from one location to another.
func travel_time(from_loc: String, to_loc: String) -> float:
	if from_loc == to_loc or from_loc == "":
		return 0.0
	var tr: Dictionary = content.workers_cfg.get("travel", {})
	var walk := float(tr.get("walk_mps", 2.6))
	var wait := float(tr.get("lift_wait_s", 3.0))
	var ride := float(data.get("shaft", {}).get("ride_mps", 5.0))
	var la := level_of(from_loc)
	var lb := level_of(to_loc)
	var a := position(from_loc)
	var b := position(to_loc)
	if la == lb:
		return _walk(a, b) / walk
	var t := _walk(a, landing(la)) / walk
	t += wait + absf(floor_y(la) - floor_y(lb)) / ride
	t += _walk(landing(lb), b) / walk
	return t
