class_name Hud
extends Control
## The in-game heads-up display. Top: money (counting up smoothly), income
## per minute, research and legacy points, automation stage and the menu.
## Right: the level strip to jump between the camp and each depth (and dig
## the next one). Bottom: manual actions - wind the lift, send the trucks,
## rally the crews - which step aside once automated, and the navigation
## bar (crew, research, goals, flow, more). Features appear as the game
## introduces them (progressive disclosure).

var ui: UiRoot
var top: PanelContainer
var money_label: Label
var income_label: Label
var rp_chip: Control
var rp_label: Label
var lp_chip: Control
var lp_label: Label
var stage_label: Label
var strip: VBoxContainer
var action_row: HBoxContainer
var nav_row: HBoxContainer
var buttons: Dictionary = {}          # name -> Control (tutorial anchors)
var badges: Dictionary = {}           # name -> Label
var contract_card: PanelContainer
var contract_label: Label
var contract_bar: ProgressBar
var _money_shown := 0.0
var _t := 0.0
var _strip_sig := ""
var _level_in_view := -1
var _lift_bar: ProgressBar
var _sell_bar: ProgressBar
var _rally_label: Label


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_build_top()
	_build_strip()
	_build_bottom()
	_build_contract()
	get_viewport().size_changed.connect(_layout)
	_layout()


func safe_top() -> float:
	var sa := DisplayServer.get_display_safe_area()
	var ss := DisplayServer.screen_get_size()
	if ss.y <= 0 or OS.has_feature("pc"):
		return 0.0
	var vp := get_viewport().get_visible_rect().size
	return float(sa.position.y) * vp.y / float(ss.y)


func _layout() -> void:
	var vp := get_viewport().get_visible_rect().size
	var st := safe_top()
	top.position = Vector2(12, 10 + st)
	top.size = Vector2(vp.x - 24, 0)
	contract_card.position = Vector2(12, top.position.y + 116)
	contract_card.size = Vector2(vp.x - 130, 0)
	strip.position = Vector2(vp.x - 104, top.position.y + 130)
	var bottom_h := 118.0
	nav_row.position = Vector2(12, vp.y - bottom_h - 10)
	nav_row.size = Vector2(vp.x - 24, bottom_h)
	action_row.position = Vector2(12, vp.y - bottom_h - 142)
	action_row.size = Vector2(vp.x - 130, 124)


# ------------------------------------------------------------------- build

func _chip(icon: String, tint: Color) -> Array:
	var h := UiKit.hbox(6)
	h.add_child(Icon.make(icon, 34, tint, tint))
	var l := UiKit.label("0", "Small")
	l.add_theme_color_override("font_color", tint)
	h.add_child(l)
	return [h, l]


func _build_top() -> void:
	top = PanelContainer.new()
	top.theme_type_variation = "Bar"
	var row := UiKit.hbox(14)
	var coin := Icon.make("coin", 62)
	row.add_child(coin)
	var mv := UiKit.vbox(0)
	money_label = UiKit.label("$0", "Money")
	income_label = UiKit.label("", "Caption")
	mv.add_child(money_label)
	mv.add_child(income_label)
	row.add_child(mv)
	row.add_child(UiKit.spacer())
	var chips := UiKit.vbox(2)
	var rp := _chip("flask", UiTheme.RP)
	rp_chip = rp[0]
	rp_label = rp[1]
	var lp := _chip("crown", UiTheme.LP)
	lp_chip = lp[0]
	lp_label = lp[1]
	chips.add_child(rp_chip)
	chips.add_child(lp_chip)
	row.add_child(chips)
	stage_label = UiKit.label("Manual", "Caption")
	stage_label.custom_minimum_size.x = 120
	stage_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	row.add_child(stage_label)
	var menu := UiKit.icon_button("pause", func() -> void: ui.open_panel("pause"), 84, "Flat")
	row.add_child(menu)
	buttons["menu"] = menu
	top.add_child(row)
	add_child(top)


func _build_strip() -> void:
	strip = UiKit.vbox(8)
	add_child(strip)


func _rebuild_strip() -> void:
	UiKit.clear(strip)
	var s := Session.sim
	var surf := UiKit.icon_button("surface", func() -> void: _goto_level(0), 88, "Chip")
	strip.add_child(surf)
	buttons["level:0"] = surf
	for dep in s.state.depths:
		var d := int(dep["index"])
		if not dep["unlocked"]:
			continue
		var b := UiKit.button(str(d), func() -> void: _goto_level(d), "Chip", 88)
		b.custom_minimum_size = Vector2(88, 88)
		b.add_theme_font_override("font", UiTheme.bold_font())
		b.add_theme_font_size_override("font_size", 32)
		strip.add_child(b)
		buttons["level:%d" % d] = b
		buttons["depth:%d" % d] = b
	var nxt := s.state.deepest_unlocked() + 1
	if nxt <= s.content.depth_count():
		var dig := UiKit.icon_button("down_level", func() -> void: ui.open_panel("depth", {"depth": nxt}), 88, "Teal", Color("06221f"))
		strip.add_child(dig)
		buttons["dig"] = dig
	_level_in_view = -1


func _goto_level(lvl: int) -> void:
	var rig: CameraRig = ui.main.camera_rig() if ui.main else null
	if rig == null:
		return
	if rig.level_in_view() == lvl and lvl > 0:
		ui.open_panel("depth", {"depth": lvl})
		return
	rig.focus_target("surface" if lvl == 0 else "depth:%d" % lvl)


func _action(name: String, icon: String, text: String, cb: Callable, variation: String) -> Button:
	var b := UiKit.button("", cb, variation, 118)
	b.custom_minimum_size = Vector2(186, 118)
	var v := UiKit.vbox(2)
	v.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	v.offset_left = 10
	v.offset_right = -10
	v.offset_top = 8
	v.offset_bottom = -8
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var h := UiKit.hbox(8)
	h.alignment = BoxContainer.ALIGNMENT_CENTER
	h.mouse_filter = Control.MOUSE_FILTER_IGNORE
	h.add_child(Icon.make(icon, 46, Color("241a06") if variation == "Primary" else UiTheme.TEXT, UiTheme.GOLD if variation != "Primary" else Color("7a4c0a")))
	var l := UiKit.label(text, "Heading")
	l.add_theme_font_size_override("font_size", 28)
	l.add_theme_color_override("font_color", Color("241a06") if variation == "Primary" else UiTheme.TEXT)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	h.add_child(l)
	v.add_child(h)
	var bar := UiKit.progress(0, 1, "TealBar", 10)
	bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(bar)
	b.add_child(v)
	b.set_meta("bar", bar)
	b.set_meta("label", l)
	buttons[name] = b
	return b


func _build_bottom() -> void:
	action_row = UiKit.hbox(12)
	action_row.alignment = BoxContainer.ALIGNMENT_BEGIN
	add_child(action_row)
	var lift := _action("lift", "lift", "LIFT", _call_lift, "Primary")
	_lift_bar = lift.get_meta("bar")
	action_row.add_child(lift)
	var sell := _action("sell", "truck", "SELL", _dispatch, "Primary")
	_sell_bar = sell.get_meta("bar")
	action_row.add_child(sell)
	var rally := _action("rally", "bolt", "RALLY", _rally, "Teal")
	_rally_label = rally.get_meta("label")
	action_row.add_child(rally)
	nav_row = UiKit.hbox(10)
	nav_row.alignment = BoxContainer.ALIGNMENT_CENTER
	add_child(nav_row)
	for n in [["crew", "people", "Crew"], ["research", "flask", "Research"], ["quests", "quest", "Goals"], ["stats", "chart", "Flow"],
			["more", "menu", "More"]]:
		var b := UiKit.button("", func() -> void: ui.open_panel(String(n[0])), "Button", 112)
		b.custom_minimum_size = Vector2(126, 112)
		var v := UiKit.vbox(0)
		v.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		v.alignment = BoxContainer.ALIGNMENT_CENTER
		v.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var ic := Icon.make(String(n[1]), 50, UiTheme.TEXT, UiTheme.GOLD)
		ic.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		v.add_child(ic)
		var l := UiKit.label(String(n[2]), "Caption", HORIZONTAL_ALIGNMENT_CENTER)
		l.add_theme_color_override("font_color", UiTheme.TEXT)
		l.mouse_filter = Control.MOUSE_FILTER_IGNORE
		v.add_child(l)
		b.add_child(v)
		var badge := UiKit.label("", "Small", HORIZONTAL_ALIGNMENT_CENTER)
		badge.add_theme_stylebox_override("normal", UiTheme.box(UiTheme.RED, 14, 4))
		badge.position = Vector2(84, -6)
		badge.custom_minimum_size = Vector2(34, 34)
		badge.visible = false
		b.add_child(badge)
		badges[String(n[0])] = badge
		nav_row.add_child(b)
		buttons[String(n[0])] = b


func _build_contract() -> void:
	contract_card = PanelContainer.new()
	contract_card.theme_type_variation = "Bar"
	var h := UiKit.hbox(10)
	h.add_child(Icon.make("truck", 36, UiTheme.TEXT, UiTheme.GOLD))
	var v := UiKit.vbox(4)
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	contract_label = UiKit.label("", "Small")
	contract_label.clip_text = true
	contract_bar = UiKit.progress(0, 1, "GreenBar", 12)
	v.add_child(contract_label)
	v.add_child(contract_bar)
	h.add_child(v)
	contract_card.add_child(h)
	contract_card.visible = false
	contract_card.gui_input.connect(func(e: InputEvent) -> void:
		if e is InputEventScreenTouch and (e as InputEventScreenTouch).pressed:
			ui.open_panel("quests", {"tab": "contract"}))
	add_child(contract_card)


# ------------------------------------------------------------------ actions

func _call_lift() -> void:
	var r := Session.command({"type": "call_lift"})
	if not r.get("ok", false):
		ui.report_error(r)


func _dispatch() -> void:
	var r := Session.command({"type": "dispatch"})
	if not r.get("ok", false):
		ui.report_error(r)


func _rally() -> void:
	var r := Session.command({"type": "rally"})
	if not r.get("ok", false):
		var e := String(r.get("error", ""))
		if e == "cooldown":
			ui.toast("Crews are catching their breath (%s)" % Num.duration(float(r.get("ready_in", 0.0))), "info")
		else:
			ui.report_error(r)
	else:
		ui.toast("Rally! Every crew works faster for a while", "gold")


# ------------------------------------------------------------------- update

func _process(delta: float) -> void:
	var s := Session.sim
	if s == null or not visible:
		return
	# Money counts toward the balance smoothly.
	var m := s.state.money
	_money_shown = m if absf(m - _money_shown) < 0.5 or absf(m - _money_shown) > absf(m) * 0.5 + 1e6 else lerpf(_money_shown, m, clampf(delta * 8.0, 0.0, 1.0))
	money_label.text = Num.money(_money_shown)
	_t -= delta
	if _t > 0.0:
		return
	_t = 0.2
	_refresh(s)


func _refresh(s: Simulation) -> void:
	var st := s.state
	income_label.text = "+%s /min" % Num.money(float(s.rt.get("income_per_min", 0.0)))
	var research_on := not st.techs.is_empty() or st.research_points > 0.0 or st.quests.has("q_first_research")
	rp_chip.visible = research_on
	rp_label.text = Num.short(st.research_points)
	lp_chip.visible = int(st.prestige.get("count", 0)) > 0 or int(st.prestige.get("lp", 0)) > 0
	lp_label.text = str(int(st.prestige.get("lp", 0)))
	var stages: Array = s.content.balance.get("automation_stages", [])
	var stage := s.automation_stage()
	stage_label.text = String(stages[clampi(stage, 0, stages.size() - 1)]) if not stages.is_empty() else ""
	# Level strip (rebuilt when depths change).
	var sig := str(st.deepest_unlocked())
	if sig != _strip_sig:
		_strip_sig = sig
		_rebuild_strip()
	var rig: CameraRig = ui.main.camera_rig() if ui.main else null
	var lv := rig.level_in_view() if rig else -1
	if lv != _level_in_view:
		_level_in_view = lv
		for k in buttons:
			if String(k).begins_with("level:"):
				var b := buttons[k] as Button
				b.theme_type_variation = "Primary" if int(String(k).split(":")[1]) == lv else "Chip"
	# Manual actions step aside once automated.
	var lift_auto := TransportSystem.lift_automatic(s)
	var ls := TransportSystem.lift_stats(s)
	var lb: Button = buttons["lift"]
	lb.visible = not lift_auto
	var max_s := float(ls["cycle_s"]) * float(s.content.bal("lift", "manual_trips_max", 3))
	_lift_bar.max_value = maxf(max_s, 0.01)
	_lift_bar.value = float(st.lift.get("manual_s", 0.0))
	var sales_auto := SalesSystem.automatic(s)
	var sb: Button = buttons["sell"]
	sb.visible = not sales_auto
	var ts := SalesSystem.truck_stats(s)
	var smax := float(ts["trip_s"]) * float(s.content.bal("sales", "manual_trips_max", 3))
	_sell_bar.max_value = maxf(smax, 0.01)
	_sell_bar.value = float(st.sales.get("manual_s", 0.0))
	var rb: Button = buttons["rally"]
	rb.visible = SimCommands.rally_unlocked(s)
	if rb.visible:
		var ready_at := float(st.boosts.get("rally_ready_at", 0.0))
		var until := float(st.boosts.get("rally_until", 0.0))
		if st.run_time < until:
			_rally_label.text = Num.duration(until - st.run_time)
		elif st.run_time < ready_at:
			_rally_label.text = Num.duration(ready_at - st.run_time)
		else:
			_rally_label.text = "RALLY"
		rb.disabled = st.run_time < ready_at
	action_row.visible = lb.visible or sb.visible or rb.visible
	# Navigation: features appear as they are introduced.
	(buttons["research"] as Control).visible = research_on
	(buttons["crew"] as Control).visible = not st.workers.is_empty() or int(st.meta.get("tutorial_step", 0)) >= 4 \
		or bool(st.meta.get("tutorial_done", false)) or st.money >= Economy.hire_cost(s, "miner")
	(buttons["stats"] as Control).visible = s.facility_built("crusher") or stage >= 1 or int(st.prestige.get("count", 0)) > 0
	var claimable := 0
	for q in st.quests:
		if st.quests[q] == "done":
			claimable += 1
	var qb: Label = badges["quests"]
	qb.visible = claimable > 0
	qb.text = str(claimable)
	var tech_ready := 0
	for t in s.content.techs:
		if SimCommands.tech_available(s, String(t["id"])) and st.research_points >= float(t.get("rp", 0.0)) and st.money >= float(t.get("cost", 0.0)):
			tech_ready += 1
	var rbd: Label = badges["research"]
	rbd.visible = tech_ready > 0
	rbd.text = str(tech_ready)
	# Contract banner.
	var c := st.contract
	contract_card.visible = c.has("item")
	if contract_card.visible:
		var it := s.content.item(String(c["item"]))
		var done := float(c.get("progress", 0.0))
		var need := float(c.get("target", 1.0))
		var left := float(c.get("deadline", 0.0)) - st.run_time
		contract_label.text = "Deliver %s %s  -  %s left" % [Num.short(need), String(it.get("name", c["item"])), Num.duration(left)]
		contract_bar.max_value = maxf(need, 1e-6)
		contract_bar.value = done


## Global rect of a named HUD control (tutorial arrows), or an empty rect.
func anchor_rect(name: String) -> Rect2:
	var c: Control = buttons.get(name)
	if c and c.is_visible_in_tree():
		return c.get_global_rect()
	return Rect2()
