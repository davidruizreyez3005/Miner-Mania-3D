class_name CharacterRig
extends Node3D
## One animated worker model (every variant shares the humanoid_worker_v1
## skeleton and clip library): clip playback with cross-fades and speed,
## hand-tool swaps on the hand_tool.R socket, carried props on the
## carry_attachment bone, and clip events (e.g. the pick's impact frame) from
## the humanoid clip metadata. Rigs that are off screen stop animating and
## distant ones animate at a reduced rate (see set_detail).

signal clip_event(event_name: String)

const DETAIL_FULL := 0
const DETAIL_REDUCED := 1
const DETAIL_FROZEN := 2

var asset_id := ""
var model: Node3D
var anim: AnimationPlayer
var skeleton: Skeleton3D
var hand_r: BoneAttachment3D
var baked_right_id := ""
var baked_right: Array = []          # MeshInstance3D nodes of the modelled right-hand tool
var shown_tool := ""                 # tool asset currently in the right hand
var attached_tool: Node3D
var carry_attach: BoneAttachment3D
var carry_prop: Node3D
var carry_id := ""
var clip := ""
var detail := DETAIL_FULL
var on_screen := true
var underground := false            # lit by the gallery lamps instead of the sun
var always_animate := false         # the player's foreman: gameplay rides on its clip events
var lod_level := 0                   # 0 = full model; crews use the pipeline's lighter LOD
static var _shared_library: AnimationLibrary
var _events: Array = []              # [[time, name]] of the current clip
var _prev_pos := 0.0
var _manual_acc := 0.0
var _frame_skip := 0


## `lod`: 0 for the full model (the foreman), 1-2 for the pipeline's lighter
## LOD models (crews at game distance). LOD models carry no clips of their
## own; every variant shares the humanoid_worker_v1 skeleton, so they play
## the shared clip library.
func setup(aid: String, lod: int = 0) -> void:
	asset_id = aid
	name = "Rig_" + aid
	model = _lod_model(aid, lod)
	if model == null:
		model = Assets.instantiate(aid, "", false)
	else:
		MaterialLite.track(model)
	add_child(model)
	var aps := model.find_children("*", "AnimationPlayer", true, false)
	if not aps.is_empty():
		anim = aps[0] as AnimationPlayer
	var sks := model.find_children("*", "Skeleton3D", true, false)
	if not sks.is_empty():
		skeleton = sks[0] as Skeleton3D
	for ba in model.find_children("*", "BoneAttachment3D", true, false):
		if (ba as BoneAttachment3D).bone_name == "hand_tool.R":
			hand_r = ba
	var tools: Dictionary = Assets.info(aid).get("metadata", {}).get("character", {}).get("tools", {})
	baked_right_id = String(tools.get("right", ""))
	shown_tool = baked_right_id
	if hand_r:
		for mi in hand_r.find_children("*", "MeshInstance3D", true, false):
			if String(mi.name).contains("_tool_r"):
				baked_right.append(mi)
	_apply_layers(model)
	var notifier := VisibleOnScreenNotifier3D.new()
	notifier.aabb = AABB(Vector3(-0.7, 0.0, -0.7), Vector3(1.4, 2.0, 1.4))
	notifier.screen_entered.connect(_on_screen_changed.bind(true))
	notifier.screen_exited.connect(_on_screen_changed.bind(false))
	add_child(notifier)


func _lod_model(aid: String, lod: int) -> Node3D:
	if lod <= 0:
		return null
	var path := ""
	for l in Assets.info(aid).get("lods", []):
		if int(l.get("level", 0)) == lod:
			path = String(l.get("model", ""))
	var lib := shared_library()
	if path == "" or lib == null or not ResourceLoader.exists(path):
		return null
	var ps := Assets.scene(path)
	if ps == null:
		return null
	var root := Node3D.new()
	root.name = aid
	root.set_meta("asset_id", aid)
	var inst := ps.instantiate() as Node3D
	inst.name = "LOD%d" % lod
	root.add_child(inst)
	var ap := AnimationPlayer.new()
	ap.name = "AnimationPlayer"
	inst.add_child(ap)
	ap.root_node = NodePath("..")
	ap.add_animation_library("", lib)
	lod_level = lod
	return root


## The clip library every worker variant shares (from the animation
## library model), loaded once.
static func shared_library() -> AnimationLibrary:
	if _shared_library == null:
		var path := String(Assets.humanoid.get("library_model", ""))
		var ps := Assets.scene(path) if path != "" and ResourceLoader.exists(path) else null
		if ps == null:
			return null
		var inst := ps.instantiate()
		for ap in inst.find_children("*", "AnimationPlayer", true, false):
			var a := ap as AnimationPlayer
			if a.has_animation_library(""):
				_shared_library = a.get_animation_library("")
		inst.free()
	return _shared_library


func has_clip(c: String) -> bool:
	return anim != null and anim.has_animation(c)


## Plays a clip (cross-faded). `restart` replays it from the start even when
## it is already playing (e.g. every tapped swing).
func play(c: String, speed: float = 1.0, blend: float = 0.25, restart: bool = false, from_s: float = 0.0) -> void:
	if anim == null or not anim.has_animation(c):
		return
	anim.speed_scale = speed
	if c == clip and not restart and anim.is_playing():
		return
	clip = c
	anim.play(c, blend)
	if from_s > 0.0:
		anim.seek(from_s, true)
	_prev_pos = anim.current_animation_position
	_events.clear()
	var info: Dictionary = Assets.humanoid.get("clips", {}).get(c, {})
	var ev: Dictionary = info.get("events", {})
	for k in ev:
		_events.append([float(ev[k]), String(k)])


func set_speed(speed: float) -> void:
	if anim:
		anim.speed_scale = speed


func clip_length(c: String) -> float:
	if anim and anim.has_animation(c):
		return anim.get_animation(c).length
	return 1.0


func clip_position() -> float:
	return anim.current_animation_position if anim and anim.is_playing() else 0.0


## Shows `tool_id` in the right hand ("" = empty hand). The modelled tool is
## reused when it matches; other tools attach to the hand socket (tools are
## authored in grip space, so the identity transform lines them up).
func set_hand_tool(tool_id: String) -> void:
	if tool_id == shown_tool:
		return
	shown_tool = tool_id
	if attached_tool:
		attached_tool.queue_free()
		attached_tool = null
	var use_baked := tool_id != "" and tool_id == baked_right_id
	for mi in baked_right:
		(mi as Node3D).visible = use_baked
	if tool_id != "" and not use_baked and hand_r and Assets.has(tool_id):
		attached_tool = Assets.instantiate(tool_id, "", false)
		_apply_layers(attached_tool)
		hand_r.add_child(attached_tool)


## Carries a prop on the chest (carry_attachment bone); "" drops it.
func set_carry(prop_id: String) -> void:
	if prop_id == carry_id:
		return
	carry_id = prop_id
	if carry_prop:
		carry_prop.queue_free()
		carry_prop = null
	if prop_id == "" or skeleton == null:
		return
	if carry_attach == null:
		carry_attach = BoneAttachment3D.new()
		carry_attach.bone_name = "carry_attachment"
		skeleton.add_child(carry_attach)
	carry_prop = Assets.instantiate(prop_id, "", false)
	var b := Assets.bounds(prop_id)
	carry_prop.position = -Vector3(b.get_center().x, b.position.y + b.size.y * 0.35, b.get_center().z)
	_apply_layers(carry_prop)
	carry_attach.add_child(carry_prop)


## Surface characters are lit by the sun, underground ones by the lamps
## (render layers match the lights' cull masks).
func set_underground(u: bool) -> void:
	if u == underground:
		return
	underground = u
	_apply_layers(self)


func _apply_layers(root: Node) -> void:
	var mask := Atmosphere.LAYER_UNDERGROUND if underground else Atmosphere.LAYER_SURFACE
	for gi in root.find_children("*", "GeometryInstance3D", true, false):
		(gi as GeometryInstance3D).layers = mask


func _on_screen_changed(visible_now: bool) -> void:
	on_screen = visible_now
	_apply_detail()


## 0 full rate, 1 reduced rate (~15 Hz), 2 frozen (off screen / far away).
func set_detail(level: int) -> void:
	if level == detail:
		return
	detail = level
	_apply_detail()


func _apply_detail() -> void:
	if anim == null:
		return
	var lv := detail if on_screen or always_animate else DETAIL_FROZEN
	anim.active = lv != DETAIL_FROZEN
	anim.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL if lv == DETAIL_REDUCED \
		else AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_IDLE


func _process(delta: float) -> void:
	if anim == null or not anim.is_playing():
		return
	if anim.callback_mode_process == AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL and anim.active:
		_manual_acc += delta
		_frame_skip += 1
		if _frame_skip >= 4:
			anim.advance(_manual_acc)
			_manual_acc = 0.0
			_frame_skip = 0
	_check_events()


func _check_events() -> void:
	if _events.is_empty():
		return
	var pos := anim.current_animation_position
	for e in _events:
		var t := float(e[0])
		var crossed := (pos >= t and _prev_pos < t) if pos >= _prev_pos else (t > _prev_pos or t <= pos)
		if crossed:
			clip_event.emit(String(e[1]))
	_prev_pos = pos
