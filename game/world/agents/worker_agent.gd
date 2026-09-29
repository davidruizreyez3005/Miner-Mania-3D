class_name WorkerAgent
extends Agent
## A hired worker made visible. It reads its simulation record (job, target,
## location, arrival time, resting) and acts it out: walks - riding the cage
## between levels - to where the simulation says it is heading, arriving
## about when the simulation says it arrives, then performs the job with the
## matching clip, tool and props. It only ever reads the simulation.
##
## Activities: mine, haul (face <-> station loop with a sack), operate,
## repair, research, survey (geologist wandering between veins), supervise,
## rest (bench or ground) and idle.

const HAUL_PROPS := ["prop_ore_sack_01", "prop_crate_carry_01"]
const CREW_LOD := 2                  # ~5k-triangle crew models (the foreman keeps the full one)

var mgr: AgentManager
var wid := 0
var role := ""
var record: Dictionary = {}
var sig := ""
var activity := "idle"
var spot: Dictionary = {}           # {"pos": Vector3, "yaw": float, "level": int, "look": Vector3?, "clip": String}
var _t := 0.0
var _phase := ""
var _hold := 0.0
var _variety := 1.0


func setup_worker(m: AgentManager, w: Dictionary) -> void:
	mgr = m
	wid = int(w["id"])
	role = String(w["role"])
	record = w
	name = "Worker_%d" % wid
	var aid := String(w.get("variant", ""))
	if not Assets.has(aid):
		aid = "chr_worker_%s_01" % role
	setup_agent(m.nav, aid, CREW_LOD)
	rider_slot = wid % 6
	_variety = 0.92 + 0.16 * float((wid * 37) % 11) / 10.0
	arrived.connect(_on_arrived)
	rig.clip_event.connect(_on_clip_event)
	var body := StaticBody3D.new()
	body.collision_layer = MineWorld.PICK_LAYER
	body.collision_mask = 0
	body.set_meta("target", "worker:%d" % wid)
	var cs := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.45
	cap.height = 1.9
	cs.shape = cap
	cs.position = Vector3(0, 0.95, 0)
	body.add_child(cs)
	add_child(body)


## Called every frame with the live record. `teleport` places the worker at
## its spot at once (loading a game, or far behind the simulation).
func sync(w: Dictionary, run_time: float, teleport: bool) -> void:
	record = w
	var s := "%s|%s|%s|%s" % [w["job"], w["target"], w["location"], w["resting"]]
	if s == sig:
		return
	sig = s
	spot = mgr.spot_for(self, w)
	var eta := float(w["arrive_at"]) - run_time
	if teleport:
		place(spot["pos"], int(spot["level"]), float(spot["yaw"]))
		_start_activity()
		return
	activity = "travel"
	_phase = ""
	carrying = false
	rig.set_carry("")
	rig.set_hand_tool(rig.baked_right_id)
	# Far behind (e.g. after a long pause): hurry, never teleport in view.
	go_to(spot["pos"], int(spot["level"]), eta if eta > 0.5 else 1.0)


func _on_arrived() -> void:
	if activity == "travel" or activity == "":
		_start_activity()
	elif activity == "haul":
		_haul_arrived()
	elif activity in ["survey", "supervise"]:
		_phase = "look"
		_hold = 4.0 + float((wid * 13 + int(_t * 10.0)) % 5)
		rig.play("Inspect", _variety, 0.3)


func _start_activity() -> void:
	var job := String(record.get("job", "idle"))
	_t = 0.0
	_phase = ""
	if bool(record.get("resting", false)):
		activity = "rest"
	else:
		activity = job
	if spot.has("look"):
		face_point(spot["look"])
	else:
		face_yaw(float(spot.get("yaw", yaw)))
	match activity:
		"mine":
			var tier := mgr.tool_tier(level)
			if tier >= 2:
				rig.set_hand_tool("tool_jackhammer_01")
				rig.play("Drill", _variety, 0.3)
			else:
				rig.set_hand_tool("tool_pickaxe_01")
				rig.play("Mine", _variety, 0.3)
		"haul":
			_haul_begin()
		"operate":
			rig.play("Operate", _variety, 0.35)
		"repair":
			rig.set_hand_tool("tool_wrench_01")
			rig.play("Repair", _variety, 0.35)
		"research":
			rig.play("Inspect", _variety, 0.35)
		"survey", "supervise", "manage":
			_phase = "look"
			_hold = 5.0
			rig.play("Inspect", _variety, 0.35)
		"rest":
			rig.set_hand_tool("")
			rig.play(String(spot.get("clip", "Rest")), 1.0, 0.4)
		_:
			activity = "idle"
			rig.play("Idle", _variety, 0.4)


func tick(delta: float) -> void:
	advance(delta)
	if moving:
		return
	_t += delta
	match activity:
		"mine":
			# The jackhammer has no impact frame: chips fly at its rhythm.
			if rig.clip == "Drill":
				_hold -= delta
				if _hold <= 0.0:
					_hold = 0.75
					mgr.on_impact(self, spot.get("look", position + Vector3(0, 0.8, -1.0)))
		"repair":
			# Alternate the wrench with the hammer now and then.
			var cyc := fmod(_t, 14.0)
			if cyc < 10.0:
				if rig.clip != "Repair":
					rig.set_hand_tool("tool_wrench_01")
					rig.play("Repair", _variety, 0.3)
			elif rig.clip != "Hammer":
				rig.set_hand_tool("tool_hammer_01")
				rig.play("Hammer", _variety, 0.3)
		"survey", "supervise", "manage":
			_hold -= delta
			if _phase == "look" and _hold <= 0.0:
				var p := mgr.wander_point(self, activity)
				_phase = "walk"
				speed = 1.3
				go_to(p, level, -1.0, 1.4)
		"idle":
			if rig.clip == "Idle" and fmod(_t + float(wid), 11.0) < delta:
				rig.play("Idle_Variant", 1.0, 0.3)
			elif rig.clip == "Idle_Variant" and _t > 0.0 and fmod(_t + float(wid), 11.0) > rig.clip_length("Idle_Variant"):
				rig.play("Idle", _variety, 0.3)
		"haul":
			_haul_tick(delta)


# ------------------------------------------------------------------ hauling

func _haul_begin() -> void:
	_phase = "pickup"
	_hold = rig.clip_length("Pick_Up") * 0.85
	face_point(mgr.haul_pick_point(level) + Vector3(0, 0, -1.0))
	rig.set_hand_tool("")
	rig.play("Pick_Up", 1.0, 0.25, true)


func _haul_tick(delta: float) -> void:
	if moving:
		return
	_hold -= delta
	if _hold > 0.0:
		return
	match _phase:
		"pickup":
			carrying = true
			rig.set_carry(HAUL_PROPS[wid % HAUL_PROPS.size()])
			_phase = "to_station"
			speed = 1.8
			go_to(mgr.haul_drop_point(level, wid), level, -1.0, 1.9)
		"drop":
			carrying = false
			rig.set_carry("")
			_phase = "to_face"
			go_to(mgr.haul_pick_point(level, wid), level, -1.0, 2.4)


func _haul_arrived() -> void:
	match _phase:
		"to_station":
			_phase = "drop"
			_hold = rig.clip_length("Put_Down") * 0.8
			face_point(mgr.station_point(level))
			rig.play("Put_Down", 1.0, 0.2, true)
		"to_face":
			_haul_begin()


func _on_clip_event(ev: String) -> void:
	if ev == "impact" and activity == "mine" and not moving:
		mgr.on_impact(self, spot.get("look", position + Vector3(0, 0.8, -1.0)))
