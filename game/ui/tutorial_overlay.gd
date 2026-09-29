class_name TutorialOverlay
extends Control
## First-session coaching (data/tutorial.json): one step at a time, a card
## with the instruction and a pulsing marker on what to touch - a HUD
## button, a vein or a gallery in the 3D world. A step completes when its
## game event fires the required number of times; progress is saved in the
## simulation state. While a step shows, the game is in the TUTORIAL state.

var ui: UiRoot
var card: PanelContainer
var text: Label
var next_button: Button
var marker: Control
var _count := 0
var _step := -1
var _active := false
var _point_anchor := ""
var _point_left := 0.0


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	marker = _Marker.new()
	marker.mouse_filter = Control.MOUSE_FILTER_IGNORE
	marker.visible = false
	add_child(marker)
	card = PanelContainer.new()
	card.add_theme_stylebox_override("panel", UiTheme.box(Color("20262e", 0.96), 24, 18, UiTheme.GOLD, 3))
	var v := UiKit.vbox(10)
	var h := UiKit.hbox(12)
	h.add_child(Icon.make("worker", 64, UiTheme.TEXT, UiTheme.GOLD))
	text = UiKit.wrap("", "Small")
	h.add_child(text)
	v.add_child(h)
	var row := UiKit.hbox(10)
	var skip := UiKit.button("Skip tips", _skip, "Flat", 60)
	row.add_child(skip)
	row.add_child(UiKit.spacer())
	next_button = UiKit.button("Next", func() -> void: EventBus.tutorial("tutorial_continue"), "Primary", 70)
	next_button.custom_minimum_size.x = 180
	row.add_child(next_button)
	v.add_child(row)
	card.add_child(v)
	card.visible = false
	add_child(card)
	EventBus.tutorial_event.connect(_on_event)


func steps() -> Array:
	return Session.content.tutorial if Session.content else []


func _process(delta: float) -> void:
	var s := Session.sim
	if s == null or not visible:
		card.visible = false
		marker.visible = false
		return
	var enabled := bool(Settings.get_value("tutorial_enabled", true))
	var done := bool(s.state.meta.get("tutorial_done", false))
	var idx := int(s.state.meta.get("tutorial_step", 0))
	var want := enabled and not done and idx < steps().size() and GameState.fsm.base == GameStateMachine.State.PLAYING
	if want and not _active:
		_active = GameState.open_overlay(GameStateMachine.State.TUTORIAL) if GameState.is_state(GameStateMachine.State.PLAYING) or GameState.has(GameStateMachine.State.TUTORIAL) else false
		if not _active:
			want = false
	elif not want and _active:
		GameState.close(GameStateMachine.State.TUTORIAL)
		_active = false
	if _active and not GameState.has(GameStateMachine.State.TUTORIAL):
		_active = false
	# Panels: over a bottom sheet the card moves to the top; full screens
	# and popups hide it until they close.
	var covering := ""
	for pn in ui.stack:
		var k := (pn as GamePanel).frame_kind()
		covering = k if k != "sheet" or covering == "" else covering
	card.visible = want and _active and covering in ["", "sheet"]
	if card.visible:
		if idx != _step:
			_step = idx
			_count = 0
			var st: Dictionary = steps()[idx]
			text.text = String(st.get("text", ""))
			next_button.visible = String(st.get("complete_on", "")) == "tutorial_continue"
			UiKit.pop_in(card)
		_layout_card(String(steps()[idx].get("anchor", "")))
	# Marker: the current step's anchor, or a temporary "show me" pointer.
	var anchor := ""
	if _point_left > 0.0:
		_point_left -= delta
		anchor = _point_anchor
	elif card.visible:
		anchor = String(steps()[idx].get("anchor", ""))
	var p := _anchor_pos(anchor)
	marker.visible = p.x > -9000.0
	if marker.visible:
		marker.position = p - marker.size * 0.5


func _layout_card(anchor: String) -> void:
	var vp := get_viewport().get_visible_rect().size
	var w := minf(vp.x - 32.0, 680.0)
	card.size = Vector2(w, 0)
	card.custom_minimum_size = Vector2(w, 0)
	var ap := _anchor_pos(anchor)
	# Keep the card away from what it points at (and above an open sheet).
	var y := vp.y * 0.60 if ap.y < vp.y * 0.55 or ap.x < -9000.0 else vp.y * 0.16
	if not ui.stack.is_empty():
		y = vp.y * 0.16
	card.position = Vector2((vp.x - w) * 0.5, y)


## Screen position of an anchor ("button:lift", "hud:quests", "world:node:1:0",
## "world:depth:1"), or far off-screen when it is not visible.
func _anchor_pos(anchor: String) -> Vector2:
	if anchor == "":
		return Vector2(-10000, -10000)
	var parts := anchor.split(":", true, 1)
	match parts[0]:
		"button", "hud":
			var r := ui.hud.anchor_rect(parts[1])
			return r.get_center() if r.size != Vector2.ZERO else Vector2(-10000, -10000)
		"world":
			var w: MineWorld = ui.main.world_ref() if ui.main else null
			var cam := get_viewport().get_camera_3d()
			if w == null or cam == null:
				return Vector2(-10000, -10000)
			var q := parts[1].split(":")
			var wp := Vector3.INF
			if q[0] == "node" and w.depth_views.has(int(q[1])):
				wp = (w.depth_views[int(q[1])] as DepthView).node_position(int(q[2]))
			elif q[0] == "depth":
				wp = Vector3(4.0, w.content.depth_floor_y(int(q[1])) + 2.5, -3.5)
			if wp == Vector3.INF or cam.is_position_behind(wp):
				return Vector2(-10000, -10000)
			return cam.unproject_position(wp)
	return Vector2(-10000, -10000)


## Pulses the marker on an anchor for a few seconds (quest "Show me").
func point_at(anchor: String, seconds: float) -> void:
	_point_anchor = anchor
	_point_left = seconds


func _on_event(name: String) -> void:
	var s := Session.sim
	if s == null or not card.visible:
		return
	var idx := int(s.state.meta.get("tutorial_step", 0))
	if idx >= steps().size():
		return
	var st: Dictionary = steps()[idx]
	if name != String(st.get("complete_on", "")):
		return
	_count += 1
	if _count >= int(st.get("count", 1)):
		var nxt := idx + 1
		Session.command({"type": "set_tutorial", "step": nxt, "done": nxt >= steps().size()})
		Audio.ui("ui_quest")


func _skip() -> void:
	Session.command({"type": "set_tutorial", "step": steps().size(), "done": true})


class _Marker extends Control:
	var _t := 0.0

	func _init() -> void:
		size = Vector2(150, 150)

	func _process(delta: float) -> void:
		_t += delta
		queue_redraw()

	func _draw() -> void:
		var c := size * 0.5
		var k := fmod(_t, 1.2) / 1.2
		draw_arc(c, 34.0 + 34.0 * k, 0.0, TAU, 48, Color(1.0, 0.8, 0.25, 1.0 - k), 6.0, true)
		draw_arc(c, 30.0, 0.0, TAU, 48, Color(1.0, 0.85, 0.3, 0.95), 5.0, true)
		var bob := sin(_t * 6.0) * 8.0
		var tip := c + Vector2(0, -40 + bob)
		draw_colored_polygon(PackedVector2Array([tip, tip + Vector2(-18, -30), tip + Vector2(18, -30)]), Color(1.0, 0.85, 0.3))
