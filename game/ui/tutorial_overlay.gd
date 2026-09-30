class_name TutorialOverlay
extends Control
## First-session coaching (data/tutorial.json): one tip at a time, a card
## with the instruction and a Next button, and a pulsing marker on what to
## touch - a HUD button, a control in an open panel, a vein or a gallery in
## the 3D world. A tip completes when its game event fires the required
## number of times, as soon as its done_when objectives hold in the
## simulation (so an action done early, or from a screen that hides the
## card, still counts), or when the player taps Next. Progress is saved in
## the simulation state. While a tip shows, the game is in the TUTORIAL state.

const OFF := Vector2(-10000, -10000)       # anchor not on screen (the tip's fallback may be)
const HIDDEN := Vector2(-20000, -20000)    # anchor exists but is scrolled away (no marker, no fallback)
const CHECK_S := 0.2

var ui: UiRoot
var card: PanelContainer
var text: Label
var next_button: Button
var skip_button: Button
var marker: Control
var _count := 0
var _step := -1
var _active := false
var _point_anchor := ""
var _point_left := 0.0
var _check_t := 0.0
var _card_key := ""
var _settle := 0
var _scrolled_to := 0


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
	skip_button = UiKit.button("Skip tips", _skip, "Flat", 60)
	row.add_child(skip_button)
	row.add_child(UiKit.spacer())
	next_button = UiKit.button("Next", _next, "Primary", 70)
	next_button.custom_minimum_size.x = 180
	row.add_child(next_button)
	v.add_child(row)
	card.add_child(v)
	card.visible = false
	add_child(card)
	EventBus.tutorial_event.connect(_on_event)


func steps() -> Array:
	return Session.content.tutorial if Session.content else []


## Index of the tip that should show, or -1 when the tutorial is over, off
## or not in play.
func current_step() -> int:
	var s := Session.sim
	if s == null or not visible:
		return -1
	if not bool(Settings.get_value("tutorial_enabled", true)) or bool(s.state.meta.get("tutorial_done", false)):
		return -1
	if GameState.fsm.base != GameStateMachine.State.PLAYING:
		return -1
	var idx := int(s.state.meta.get("tutorial_step", 0))
	return idx if idx >= 0 and idx < steps().size() else -1


func _process(delta: float) -> void:
	var idx := current_step()
	# Tips finish from the game state too, whatever is on screen.
	_check_t -= delta
	if idx >= 0 and _check_t <= 0.0:
		_check_t = CHECK_S
		if _objectives_met(steps()[idx]):
			_advance(idx)
			idx = current_step()
	var want := idx >= 0
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
			next_button.text = "Got it" if idx == steps().size() - 1 else "Next"
			_card_key = ""
			UiKit.pop_in(card)
		_layout_card(idx)
	# Marker: the current tip's anchor, or a temporary "show me" pointer.
	var p := OFF
	if _point_left > 0.0:
		_point_left -= delta
		p = _anchor_pos(_point_anchor)
	elif card.visible:
		p = step_anchor_pos(idx)
	marker.visible = p.x > -9000.0
	if marker.visible:
		marker.position = p - marker.size * 0.5


## Screen position the tip points at: its anchor, else its fallback.
func step_anchor_pos(idx: int) -> Vector2:
	if idx < 0 or idx >= steps().size():
		return OFF
	var st: Dictionary = steps()[idx]
	var p := _anchor_pos(String(st.get("anchor", "")))
	if p == OFF and st.has("anchor_else"):
		p = _anchor_pos(String(st["anchor_else"]))
	return p


func _layout_card(idx: int) -> void:
	var vp := get_viewport().get_visible_rect().size
	var w := minf(vp.x - 32.0, 680.0)
	var ap := step_anchor_pos(idx)
	# Keep the card away from what it points at (and above an open sheet).
	var y := vp.y * 0.60 if ap.y < vp.y * 0.55 or ap.x < -9000.0 else vp.y * 0.16
	if not ui.stack.is_empty():
		y = vp.y * 0.16
	# Lay out again only when something changed (a relayout every frame is
	# wasted work on a small phone); wrapped text settles over a few frames.
	var key := "%d|%s|%d" % [idx, str(vp), int(y)]
	if key != _card_key:
		_card_key = key
		_settle = 3
	if _settle <= 0:
		return
	_settle -= 1
	card.custom_minimum_size = Vector2(w, 0)
	card.size = Vector2(w, 0)
	card.position = Vector2((vp.x - w) * 0.5, y)


## Screen position of an anchor ("button:lift", "hud:quests",
## "panel:depth_upgrade", "world:node:1:0", "world:depth:1"), or far
## off-screen when it is not visible.
func _anchor_pos(anchor: String) -> Vector2:
	if anchor == "":
		return OFF
	var parts := anchor.split(":", true, 1)
	match parts[0]:
		"button", "hud":
			var r := ui.hud.anchor_rect(parts[1])
			return r.get_center() if r.size != Vector2.ZERO else OFF
		"panel":
			var c := ui.panel_anchor(parts[1])
			return _in_panel_view(c) if c != null else OFF
		"world":
			var w: MineWorld = ui.main.world_ref() if ui.main else null
			var cam := get_viewport().get_camera_3d()
			if w == null or cam == null:
				return OFF
			var q := parts[1].split(":")
			var wp := Vector3.INF
			if q[0] == "node" and w.depth_views.has(int(q[1])):
				wp = (w.depth_views[int(q[1])] as DepthView).node_position(int(q[2]))
			elif q[0] == "depth":
				wp = Vector3(4.0, w.content.depth_floor_y(int(q[1])) + 2.5, -3.5)
			if wp == Vector3.INF or cam.is_position_behind(wp):
				return OFF
			var sp := cam.unproject_position(wp)
			return sp if get_viewport().get_visible_rect().has_point(sp) else OFF
	return OFF


## A control in a panel's scrolling list: scrolled into view once, then its
## centre while it shows inside the list.
func _in_panel_view(c: Control) -> Vector2:
	var r := c.get_global_rect()
	if r.size.y < 1.0:
		return HIDDEN                          # not laid out yet
	var sc: ScrollContainer = null
	var n := c.get_parent()
	while n != null and sc == null:
		sc = n as ScrollContainer
		n = n.get_parent()
	if sc == null:
		return r.get_center()
	var view := sc.get_global_rect()
	if c.get_instance_id() != _scrolled_to:
		_scrolled_to = c.get_instance_id()
		if not view.encloses(r):
			sc.ensure_control_visible(c)
			return HIDDEN                      # in view from the next frame
	return r.get_center() if view.has_point(r.get_center()) else HIDDEN


## Pulses the marker on an anchor for a few seconds (quest "Show me").
func point_at(anchor: String, seconds: float) -> void:
	_point_anchor = anchor
	_point_left = seconds


func _objectives_met(st: Dictionary) -> bool:
	var s := Session.sim
	if s == null:
		return false
	for o in st.get("done_when", []):
		if ProgressionSystem.objective_done(s, o):
			return true
	return false


## Counts the current tip's event wherever it happened (a full-screen panel
## may be hiding the card).
func _on_event(name: String) -> void:
	var idx := current_step()
	if idx < 0:
		return
	var st: Dictionary = steps()[idx]
	if name != String(st.get("complete_on", "")):
		return
	if idx != _step:
		_step = idx
		_count = 0
	_count += 1
	if _count >= int(st.get("count", 1)):
		_advance(idx)


func _next() -> void:
	var idx := current_step()
	if idx >= 0:
		_advance(idx)


## Moves on from tip `idx` (once, even if several signals arrive together).
func _advance(idx: int) -> void:
	var s := Session.sim
	if s == null or int(s.state.meta.get("tutorial_step", 0)) != idx:
		return
	var nxt := idx + 1
	Session.command({"type": "set_tutorial", "step": nxt, "done": nxt >= steps().size()})
	_count = 0
	Audio.ui("ui_quest")


func _skip() -> void:
	Session.command({"type": "set_tutorial", "step": steps().size(), "done": true})


class _Marker extends Control:
	var _t := 0.0

	func _init() -> void:
		size = Vector2(150, 150)

	func _notification(what: int) -> void:
		if what == NOTIFICATION_VISIBILITY_CHANGED:
			set_process(is_visible_in_tree())

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
