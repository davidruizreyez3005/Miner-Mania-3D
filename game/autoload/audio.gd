extends Node
## The audio system. Sounds are data (data/audio.json -> generated WAVs, all
## replaceable by id). One-shots come from pooled players (2D for UI, 3D
## positional in the world), with per-sound polyphony limits and pitch
## variation. Machines attach looping 3D emitters whose volume follows their
## utilisation. Music and ambience crossfade between the surface and the mine
## as the camera moves underground. Simulation events map to sounds (and
## optional haptics) through the same data file.

const DATA := "res://data/audio.json"
const MANIFEST := "res://assets/generated/audio/audio_manifest.json"
const POOL_2D := 8
const POOL_3D := 16

var sounds: Dictionary = {}
var events: Dictionary = {}
var music_ids: Dictionary = {}
var ambience_ids: Dictionary = {}
var files: Dictionary = {}                 # sound file id -> res path
var position_resolver: Callable = Callable()   # func(ev: Dictionary) -> Variant (Vector3 or null)
var _streams: Dictionary = {}
var _pool2d: Array[AudioStreamPlayer] = []
var _pool3d: Array[AudioStreamPlayer3D] = []
var _playing: Dictionary = {}              # sound id -> Array of players currently used
var _music: Array[AudioStreamPlayer] = []
var _amb: Array[AudioStreamPlayer] = []
var _music_track := ""
var _amb_track := ""
var _music_active := 0
var _amb_active := 0
var _rng := RandomNumberGenerator.new()
var _underground := 0.0


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_rng.seed = 12345
	var data = JsonUtil.load_file(DATA)
	if data is Dictionary:
		sounds = data.get("sounds", {})
		events = data.get("events", {})
		music_ids = data.get("music", {})
		ambience_ids = data.get("ambience", {})
	var man = JsonUtil.load_file(MANIFEST)
	if man is Dictionary:
		for id in man:
			files[id] = String(man[id]["file"])
	for i in POOL_2D:
		var p := AudioStreamPlayer.new()
		add_child(p)
		_pool2d.append(p)
	for i in POOL_3D:
		var p3 := AudioStreamPlayer3D.new()
		p3.attenuation_model = AudioStreamPlayer3D.ATTENUATION_INVERSE_DISTANCE
		add_child(p3)
		_pool3d.append(p3)
	for i in 2:
		var m := AudioStreamPlayer.new()
		m.bus = &"Music"
		m.volume_db = -80.0
		add_child(m)
		_music.append(m)
		var a := AudioStreamPlayer.new()
		a.bus = &"Ambience"
		a.volume_db = -80.0
		add_child(a)
		_amb.append(a)
	EventBus.sim_event.connect(_on_sim_event)


func stream(file_id: String) -> AudioStream:
	if _streams.has(file_id):
		return _streams[file_id]
	var path := String(files.get(file_id, "res://assets/generated/audio/%s.wav" % file_id))
	var s: AudioStream = null
	if ResourceLoader.exists(path):
		s = load(path) as AudioStream
	_streams[file_id] = s
	return s


func _pick(sound_id: String) -> Array:
	## -> [stream, spec] for a sound (random variant), or [] when unavailable.
	var spec: Dictionary = sounds.get(sound_id, {})
	if spec.is_empty():
		return []
	var list: Array = spec.get("files", [])
	if list.is_empty():
		return []
	var st := stream(String(list[_rng.randi_range(0, list.size() - 1)]))
	if st == null:
		return []
	if spec.get("loop", false) and st is AudioStreamWAV:
		var w := st as AudioStreamWAV
		if w.loop_mode == AudioStreamWAV.LOOP_DISABLED:
			w.loop_mode = AudioStreamWAV.LOOP_FORWARD
			w.loop_begin = 0
			w.loop_end = int(w.get_length() * w.mix_rate)
	return [st, spec]


func _budget_ok(sound_id: String, spec: Dictionary) -> bool:
	var list: Array = _playing.get(sound_id, [])
	list = list.filter(func(p): return is_instance_valid(p) and p.playing)
	_playing[sound_id] = list
	return list.size() < int(spec.get("max", 4))


## Plays a one-shot. With a position (Vector3) positional sounds play in 3D.
func play(sound_id: String, at: Variant = null, volume_offset_db: float = 0.0) -> void:
	var picked := _pick(sound_id)
	if picked.is_empty():
		return
	var spec: Dictionary = picked[1]
	if not _budget_ok(sound_id, spec):
		return
	var pr: Array = spec.get("pitch", [1.0, 1.0])
	var pitch := _rng.randf_range(float(pr[0]), float(pr[1]))
	var vol := float(spec.get("volume_db", 0.0)) + volume_offset_db
	var p: Node = null
	if spec.get("positional", false) and at is Vector3:
		var p3 := _free3d()
		p3.stream = picked[0]
		p3.bus = StringName(spec.get("bus", "SFX"))
		p3.global_position = at
		p3.unit_size = float(spec.get("unit_size", 8.0))
		p3.max_distance = float(spec.get("max_distance", 60.0))
		p3.volume_db = vol
		p3.pitch_scale = pitch
		p3.play()
		p = p3
	else:
		var p2 := _free2d()
		p2.stream = picked[0]
		p2.bus = StringName(spec.get("bus", "SFX"))
		p2.volume_db = vol
		p2.pitch_scale = pitch
		p2.play()
		p = p2
	(_playing.get_or_add(sound_id, []) as Array).append(p)


func ui(sound_id: String) -> void:
	play(sound_id)


func _free2d() -> AudioStreamPlayer:
	for p in _pool2d:
		if not p.playing:
			return p
	return _pool2d[_rng.randi_range(0, _pool2d.size() - 1)]


func _free3d() -> AudioStreamPlayer3D:
	for p in _pool3d:
		if not p.playing:
			return p
	return _pool3d[_rng.randi_range(0, _pool3d.size() - 1)]


## A looping positional emitter owned by a world object (machine, cart...).
## Returns null when the sound is unavailable. Control it with set_loop_level.
func attach_loop(sound_id: String, parent: Node3D, offset: Vector3 = Vector3.ZERO) -> AudioStreamPlayer3D:
	var picked := _pick(sound_id)
	if picked.is_empty():
		return null
	var spec: Dictionary = picked[1]
	var p := AudioStreamPlayer3D.new()
	p.name = "Loop_" + sound_id
	p.stream = picked[0]
	p.bus = StringName(spec.get("bus", "SFX"))
	p.unit_size = float(spec.get("unit_size", 6.0))
	p.max_distance = float(spec.get("max_distance", 45.0))
	p.attenuation_model = AudioStreamPlayer3D.ATTENUATION_INVERSE_DISTANCE
	p.position = offset
	p.set_meta("base_db", float(spec.get("volume_db", -12.0)))
	p.volume_db = -80.0
	p.pitch_scale = _rng.randf_range(0.96, 1.04)
	parent.add_child(p)
	return p


## level 0..1: 0 stops the loop, otherwise plays at a volume following level.
func set_loop_level(p: AudioStreamPlayer3D, level: float) -> void:
	if p == null or not is_instance_valid(p):
		return
	if level <= 0.01:
		if p.playing:
			p.stop()
		return
	p.volume_db = float(p.get_meta("base_db", -12.0)) + linear_to_db(clampf(level, 0.05, 1.0))
	if not p.playing and p.is_inside_tree():
		p.play(_rng.randf_range(0.0, 0.5))


# ------------------------------------------------------------ music/ambience

func set_music(zone: String) -> void:
	var id := String(music_ids.get(zone, ""))
	if id == _music_track or id == "":
		return
	_music_track = id
	_music_active = _crossfade(_music, _music_active, id, -8.0, 2.5)


func set_ambience(zone: String) -> void:
	var id := String(ambience_ids.get(zone, ""))
	if id == _amb_track or id == "":
		return
	_amb_track = id
	_amb_active = _crossfade(_amb, _amb_active, id, -6.0, 2.0)


## Called by the camera: 0 = surface, 1 = underground, depth index for the deep ambience.
func set_listener_zone(underground: float, depth_index: int) -> void:
	_underground = underground
	set_music("mine" if underground > 0.5 else "surface")
	if underground <= 0.5:
		set_ambience("surface")
	else:
		set_ambience("deep" if depth_index >= 5 else "mine")
	var sfx := AudioServer.get_bus_index("SFX")
	if sfx >= 0 and AudioServer.get_bus_effect_count(sfx) > 0:
		AudioServer.set_bus_effect_enabled(sfx, 0, underground > 0.5)


func _crossfade(players: Array, active: int, file_id: String, target_db: float, seconds: float) -> int:
	var st := stream(file_id)
	if st == null:
		return active
	if st is AudioStreamWAV:
		var w := st as AudioStreamWAV
		if w.loop_mode == AudioStreamWAV.LOOP_DISABLED:
			w.loop_mode = AudioStreamWAV.LOOP_FORWARD
			w.loop_begin = 0
			w.loop_end = int(w.get_length() * w.mix_rate)
	var nxt := 1 - active
	var incoming: AudioStreamPlayer = players[nxt]
	var outgoing: AudioStreamPlayer = players[active]
	incoming.stream = st
	incoming.volume_db = -60.0
	incoming.play()
	var tw := create_tween().set_parallel(true)
	tw.tween_property(incoming, "volume_db", target_db, seconds)
	tw.tween_property(outgoing, "volume_db", -60.0, seconds)
	tw.chain().tween_callback(outgoing.stop)
	return nxt


# --------------------------------------------------------------- sim events

func _on_sim_event(ev: Dictionary) -> void:
	var map: Dictionary = events.get(String(ev.get("type", "")), {})
	if map.is_empty():
		return
	var pos: Variant = null
	if position_resolver.is_valid():
		pos = position_resolver.call(ev)
	play(String(map.get("sound", "")), pos)
	var ms := int(map.get("haptic", 0))
	if ms > 0 and Settings.get_value("haptics", true) and OS.has_feature("mobile"):
		Input.vibrate_handheld(ms)
