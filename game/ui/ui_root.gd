class_name UiRoot
extends CanvasLayer
## Owns every screen and panel. Panels open and close through the game
## state machine (each panel stands for an overlay state); the Android back
## button closes the top-most panel or opens the pause menu; simulation
## events become toasts, popups (discoveries) and floating texts; command
## refusals become friendly messages.

const PANELS := {
	"facility": "res://game/ui/panels/facility_panel.gd",
	"depth": "res://game/ui/panels/depth_panel.gd",
	"worker": "res://game/ui/panels/worker_panel.gd",
	"crew": "res://game/ui/panels/crew_panel.gd",
	"research": "res://game/ui/panels/research_panel.gd",
	"quests": "res://game/ui/panels/quests_panel.gd",
	"codex": "res://game/ui/panels/codex_panel.gd",
	"stats": "res://game/ui/panels/stats_panel.gd",
	"prestige": "res://game/ui/panels/prestige_panel.gd",
	"settings": "res://game/ui/panels/settings_panel.gd",
	"more": "res://game/ui/panels/more_panel.gd",
	"cosmetics": "res://game/ui/panels/cosmetics_panel.gd",
	"pause": "res://game/ui/panels/pause_panel.gd",
	"offline": "res://game/ui/panels/offline_popup.gd",
	"discovery": "res://game/ui/panels/discovery_popup.gd",
	"confirm": "res://game/ui/panels/confirm_popup.gd",
}

const ERRORS := {
	"no_money": "Not enough money",
	"no_research_points": "Not enough research points",
	"post_full": "No free slots here - upgrade to add more",
	"housing_full": "The camp is full - upgrade the Site Office",
	"role_locked": "That role is not available yet",
	"locked": "Research needed first",
	"max_level": "Already at the maximum level",
	"station_full": "The shaft station is full - call the lift!",
	"node_depleted": "This vein is exhausted - it will regrow",
	"lift_busy": "The cage is already running",
	"trucks_busy": "The trucks are already on the road",
	"warehouse_empty": "Nothing to sell yet - process some ore first",
	"depth_locked": "Dig down to this depth first",
	"previous_locked": "Dig the depth above first",
	"requires_prestige": "Reachable after selling your first claim",
	"requires_charter": "Needs the Deep Charter legacy upgrade",
	"cooldown": "Not ready yet",
	"not_worn": "Already in perfect shape",
	"prerequisites": "Research its prerequisites first",
}

var main: Node
var root := Control.new()
var hud: Hud
var sheet_host := Control.new()
var full_host := Control.new()
var popup_host := Control.new()
var toast_box := VBoxContainer.new()
var fx_host := Control.new()
var tutorial: TutorialOverlay
var stack: Array = []                # open panels, bottom to top
var _toast_queue: Array = []
var _toast_busy := false
var _dim: ColorRect


func _ready() -> void:
	layer = 10
	root.name = "UiRoot"
	root.theme = UiTheme.get_theme()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)
	for n in [fx_host, sheet_host, full_host, popup_host]:
		(n as Control).set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		(n as Control).mouse_filter = Control.MOUSE_FILTER_IGNORE
	fx_host.name = "Fx"
	sheet_host.name = "Sheets"
	full_host.name = "Full"
	popup_host.name = "Popups"
	root.add_child(fx_host)
	hud = Hud.new()
	hud.ui = self
	hud.name = "Hud"
	root.add_child(hud)
	root.add_child(sheet_host)
	root.add_child(full_host)
	_dim = ColorRect.new()
	_dim.color = Color(0, 0, 0, 0.55)
	_dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_dim.visible = false
	_dim.mouse_filter = Control.MOUSE_FILTER_STOP
	root.add_child(_dim)
	root.add_child(popup_host)
	toast_box.name = "Toasts"
	toast_box.set_anchors_and_offsets_preset(Control.PRESET_CENTER_TOP)
	toast_box.position.y = 190
	toast_box.alignment = BoxContainer.ALIGNMENT_BEGIN
	toast_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	toast_box.add_theme_constant_override("separation", 8)
	root.add_child(toast_box)
	tutorial = TutorialOverlay.new()
	tutorial.ui = self
	root.add_child(tutorial)
	EventBus.panel_requested.connect(open_panel)
	EventBus.toast.connect(toast)
	EventBus.sim_event.connect(_on_sim_event)
	EventBus.state_changed.connect(_on_state_changed)
	get_viewport().size_changed.connect(_layout)
	hud.visible = false
	_layout()


func _layout() -> void:
	var vp := get_viewport().get_visible_rect().size
	toast_box.position = Vector2((vp.x - 640.0) * 0.5, 176.0)
	toast_box.size = Vector2(640, 0)


func show_game(on: bool) -> void:
	hud.visible = on
	tutorial.visible = on
	if not on:
		close_all()


# ------------------------------------------------------------------ panels

func top_panel() -> GamePanel:
	return stack[stack.size() - 1] if not stack.is_empty() else null


func find_panel(id: String) -> GamePanel:
	for p in stack:
		if (p as GamePanel).panel_id() == id:
			return p
	return null


## Opens a panel (replacing a panel of the same frame kind). Returns it.
func open_panel(id: String, args: Dictionary = {}) -> GamePanel:
	if not PANELS.has(id):
		push_warning("UiRoot: unknown panel " + id)
		return null
	var existing := find_panel(id)
	if existing and existing.args == args:
		return existing
	var script: GDScript = load(PANELS[id])
	var p: GamePanel = script.new()
	p.ui = self
	p.args = args.duplicate()
	var kind := p.frame_kind()
	# One sheet and one full panel at a time; a full panel hides sheets.
	for q in stack.duplicate():
		var qk := (q as GamePanel).frame_kind()
		if qk == kind and kind != "popup" or (kind == "full" and qk == "sheet"):
			_close_now(q)
	var gs := p.game_state()
	var pushed := gs >= 0 and not GameState.has(gs)
	if gs >= 0 and not GameState.open_overlay(gs, args):
		p.free()
		return null
	p.set_meta("pushed", pushed)
	stack.append(p)
	_frame(p)
	EventBus.tutorial("panel_opened:" + id)
	Audio.ui("ui_open")
	return p


func close_panel(p: GamePanel) -> void:
	if p == null or not p in stack:
		return
	_close_now(p)
	Audio.ui("ui_close")


func close_all() -> void:
	for p in stack.duplicate():
		_close_now(p)


func _close_now(p: GamePanel) -> void:
	stack.erase(p)
	if p.game_state() >= 0 and bool(p.get_meta("pushed", false)):
		GameState.close(p.game_state())
	var f := p.frame
	if f == null or not is_instance_valid(f):
		p.queue_free()
		return
	var tw := f.create_tween()
	match p.frame_kind():
		"sheet":
			tw.tween_property(f, "position:y", get_viewport().get_visible_rect().size.y, 0.18).set_ease(Tween.EASE_IN)
		_:
			tw.tween_property(f, "modulate:a", 0.0, 0.14)
	tw.tween_callback(f.queue_free)
	_update_dim()


func _update_dim() -> void:
	var any_popup := false
	for p in stack:
		if (p as GamePanel).frame_kind() == "popup":
			any_popup = true
	_dim.visible = any_popup


## Wraps a panel in its frame: bottom sheet, full screen or popup card.
func _frame(p: GamePanel) -> void:
	var vp := get_viewport().get_visible_rect().size
	var outer := PanelContainer.new()
	var box := UiKit.vbox(14)
	var header := UiKit.hbox(12)
	if p.icon_kind() != "":
		header.add_child(Icon.make(p.icon_kind(), 46, UiTheme.TEXT))
	var t := UiKit.label(p.title(), "Heading")
	t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	t.clip_text = true
	header.add_child(t)
	header.add_child(UiKit.icon_button("close", func() -> void: close_panel(p), 76, "Flat"))
	box.add_child(header)
	p.content = UiKit.vbox(14)
	p.content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.add_child(p.content)
	box.add_child(scroll)
	outer.add_child(box)
	outer.add_child(p)                   # the panel node itself rides along (processing)
	p.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	p.size = Vector2.ZERO
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	p.frame = outer
	match p.frame_kind():
		"sheet":
			outer.theme_type_variation = "Sheet"
			var h := vp.y * 0.56
			outer.custom_minimum_size = Vector2(vp.x, h)
			outer.size = Vector2(vp.x, h)
			outer.position = Vector2(0, vp.y)
			full_host.add_child(outer)
			outer.create_tween().tween_property(outer, "position:y", vp.y - h, 0.24).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
		"full":
			outer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
			outer.offset_top = 8
			var sb := UiTheme.box(Color(UiTheme.BG, 0.985), 0, 22)
			outer.add_theme_stylebox_override("panel", sb)
			full_host.add_child(outer)
			outer.modulate.a = 0.0
			outer.create_tween().tween_property(outer, "modulate:a", 1.0, 0.16)
		"popup":
			var w := minf(vp.x - 48.0, 660.0)
			outer.custom_minimum_size = Vector2(w, 0)
			outer.size = Vector2(w, 0)
			popup_host.add_child(outer)
	p.rebuild()
	p._sig = p.signature()
	if p.frame_kind() == "popup":
		scroll.custom_minimum_size = Vector2(0, minf(p.content.get_combined_minimum_size().y + 8.0, vp.y * 0.7))
		_place_popup(outer, scroll, p.content)
		_place_popup.call_deferred(outer, scroll, p.content)
		UiKit.pop_in(outer)
	_update_dim()


## Popups fit their content (scrolling only when taller than the screen);
## run again after layout, when wrapped text knows its real height.
func _place_popup(outer: Control, scroll: Control, content: Control) -> void:
	if not is_instance_valid(outer):
		return
	var vp := get_viewport().get_visible_rect().size
	var ch := content.size.y if content.size.y > 1.0 else content.get_combined_minimum_size().y
	scroll.custom_minimum_size = Vector2(0, minf(ch + 8.0, vp.y * 0.7))
	outer.size = Vector2(outer.custom_minimum_size.x, 0)
	outer.reset_size()
	outer.position = Vector2((vp.x - outer.size.x) * 0.5, maxf(40.0, (vp.y - outer.size.y) * 0.42))


func _on_state_changed(_from: int, _to: int) -> void:
	# A state closed from elsewhere (e.g. GameState.back) closes its panel.
	for p in stack.duplicate():
		var gs := (p as GamePanel).game_state()
		if gs >= 0 and not GameState.has(gs):
			stack.erase(p)
			if p.frame:
				p.frame.queue_free()
	_update_dim()


## Back button / Escape: close the top panel, or pause.
func back() -> bool:
	var p := top_panel()
	if p:
		close_panel(p)
		return true
	if hud.visible and GameState.is_state(GameStateMachine.State.PLAYING):
		open_panel("pause")
		return true
	return false


func _unhandled_key_input(event: InputEvent) -> void:
	var k := event as InputEventKey
	if k and k.pressed and not k.echo and k.keycode == KEY_ESCAPE:
		back()
		get_viewport().set_input_as_handled()


# ------------------------------------------------------------------ toasts

func toast(text: String, kind: String = "info") -> void:
	_toast_queue.append([text, kind])
	if _toast_queue.size() > 4:
		_toast_queue.pop_front()
	_next_toast()


func _next_toast() -> void:
	if _toast_busy or _toast_queue.is_empty():
		return
	_toast_busy = true
	var item: Array = _toast_queue.pop_front()
	var kind := String(item[1])
	var col: Color = {"info": UiTheme.CARD, "good": Color("24452a"), "bad": Color("4d2320"), "gold": Color("4a3a12"), "rare": Color("3a2a52")}.get(kind, UiTheme.CARD)
	var p := PanelContainer.new()
	p.add_theme_stylebox_override("panel", UiTheme.box(Color(col, 0.95), 20, 14))
	var h := UiKit.hbox(12)
	var icon: String = {"info": "star", "good": "check", "bad": "warning", "gold": "trophy", "rare": "gem"}.get(kind, "star")
	h.add_child(Icon.make(icon, 38, UiTheme.TEXT, UiTheme.GOLD))
	var l := UiKit.wrap(String(item[0]), "Small")
	h.add_child(l)
	p.add_child(h)
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	toast_box.add_child(p)
	UiKit.pop_in(p)
	var tw := p.create_tween()
	tw.tween_interval(2.2 if kind != "gold" else 3.0)
	tw.tween_property(p, "modulate:a", 0.0, 0.3)
	tw.tween_callback(func() -> void:
		p.queue_free()
		_toast_busy = false
		_next_toast())


func report_error(r: Dictionary) -> void:
	var e := String(r.get("error", ""))
	var msg := String(ERRORS.get(e, e.capitalize()))
	if e == "no_money" and r.has("cost"):
		msg = "Need %s" % Num.money(float(r["cost"]))
	elif e == "locked" and String(r.get("tech", "")) != "":
		var t: Dictionary = Session.content.tech_by_id.get(String(r["tech"]), {})
		msg = "Research %s first" % String(t.get("name", r["tech"]))
	toast(msg, "bad")
	Audio.ui("ui_error")


## Rising text at a world position ("+3 Copper Ore").
func float_text(world_pos: Vector3, text: String, c: Color = UiTheme.MONEY) -> void:
	var cam := get_viewport().get_camera_3d()
	if cam == null or cam.is_position_behind(world_pos):
		return
	var sp := cam.unproject_position(world_pos)
	var l := UiKit.label(text, "Accent")
	l.add_theme_color_override("font_color", c)
	l.add_theme_constant_override("outline_size", 8)
	l.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.7))
	l.position = sp - Vector2(60, 20)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	fx_host.add_child(l)
	var tw := l.create_tween()
	tw.set_parallel(true)
	tw.tween_property(l, "position:y", l.position.y - 90.0, 1.0).set_ease(Tween.EASE_OUT)
	tw.tween_property(l, "modulate:a", 0.0, 1.0).set_delay(0.4)
	tw.chain().tween_callback(l.queue_free)


# -------------------------------------------------------------- sim events

func _on_sim_event(ev: Dictionary) -> void:
	var c := Session.content
	match String(ev.get("type", "")):
		"achievement":
			var a: Dictionary = c.achievement_by_id.get(String(ev.get("achievement", "")), {})
			toast("Achievement: %s" % String(a.get("name", "")), "gold")
		"quest_done":
			var q: Dictionary = c.quest_by_id.get(String(ev.get("quest", "")), {})
			toast("Goal complete: %s - claim your reward!" % String(q.get("title", "")), "good")
		"discovery":
			var rd: Dictionary = c.resource_by_id.get(String(ev.get("resource", "")), {})
			if String(rd.get("rarity", "common")) == "common":
				toast("New resource: %s" % String(rd.get("name", "")), "rare")
			else:
				open_panel("discovery", {"resource": String(ev.get("resource", "")), "depth": int(ev.get("depth", 0))})
		"rare_vein":
			var r: Dictionary = c.resource_by_id.get(String(ev.get("resource", "")), {})
			toast("A %s vein appeared!" % String(r.get("name", "rare")), "rare")
		"depth_unlocked":
			toast("%s is open!" % String(c.depth(int(ev.get("depth", 1))).get("name", "New depth")), "good")
		"facility_built":
			toast("%s built" % String(c.facility(String(ev.get("facility", ""))).get("name", "")), "good")
		"tech_researched":
			toast("Researched: %s" % String(c.tech_by_id.get(String(ev.get("tech", "")), {}).get("name", "")), "good")
		"contract_new":
			toast("New delivery contract available", "info")
		"contract_done":
			toast("Contract delivered! Bonus paid", "gold")
		"contract_failed":
			toast("The delivery contract expired", "bad")
		"tool_upgraded":
			var tt := c.tool_tier(int(ev.get("tier", 1)))
			toast("New tools at %s: %s" % [String(c.depth(int(ev.get("depth", 1))).get("name", "")), String(tt.get("name", ""))], "good")
		"worker_level":
			if Session.sim:
				var w := Session.sim.worker_by_id(int(ev.get("worker", -1)))
				if not w.is_empty():
					toast("%s reached level %d" % [String(w.get("name", "")), int(ev.get("level", 1))], "info")
		"machine_worn":
			toast("%s is worn and slowing down" % String(c.facility(String(ev.get("facility", ""))).get("name", "A machine")), "bad")
		"manual_mined":
			if main and main.has_method("world_ref") and main.world_ref():
				var w: MineWorld = main.world_ref()
				var p: Variant = w.event_position(ev)
				if p is Vector3:
					var res: Dictionary = c.resource_by_id.get(String(ev.get("resource", "")), {})
					float_text(p + Vector3(0, 1.4, 0.6), "+%s %s" % [Num.short(float(ev.get("units", 0.0))), String(res.get("name", ""))],
						Color(String(res.get("color", "#ffd45c"))).lightened(0.25))
