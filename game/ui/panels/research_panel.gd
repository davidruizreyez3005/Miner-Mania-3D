extends GamePanel
## The research tree by tier: every technology with its effects, costs
## (research points + money) and state - researched, available, or waiting
## on prerequisites.

var _rp_label: Label
var _buttons: Dictionary = {}          # tech id -> CostButton


func frame_kind() -> String:
	return "full"


func panel_id() -> String:
	return "research"


func title() -> String:
	return "Research"


func icon_kind() -> String:
	return "flask"


func signature() -> String:
	return str(sim().state.techs.size())


func build() -> void:
	var s := sim()
	_buttons.clear()
	_rp_label = UiKit.label("", "Accent")
	content.add_child(_rp_label)
	content.add_child(UiKit.wrap("Engineers at the Site Office produce research points. Researching also costs money."))
	var by_tier := {}
	for t in s.content.techs:
		(by_tier.get_or_add(int(t.get("tier", 1)), []) as Array).append(t)
	var tiers := by_tier.keys()
	tiers.sort()
	for tier in tiers:
		section("Tier %d" % int(tier))
		var list: Array = by_tier[tier]
		list.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return int(a.get("column", 0)) < int(b.get("column", 0)))
		for t in list:
			content.add_child(_tech_card(s, t))


func _tech_card(s: Simulation, t: Dictionary) -> Control:
	var tid := String(t["id"])
	var done := s.state.techs.has(tid)
	var v := UiKit.vbox(UiTheme.GAP_IN)
	var h := UiKit.hbox(UiTheme.GAP_ROW)
	h.add_child(Icon.make("check" if done else ("flask" if SimCommands.tech_available(s, tid) else "lock"), 40, UiTheme.TEXT, UiTheme.GREEN))
	var n := UiKit.label(String(t.get("name", tid)), "Small")
	n.add_theme_font_override("font", UiTheme.bold_font())
	n.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(n)
	v.add_child(h)
	v.add_child(UiKit.wrap(String(t.get("description", ""))))
	var eff := []
	for e in t.get("effects", []):
		var txt := UiText.effect(s, e)
		if txt != "":
			eff.append(txt)
	if not eff.is_empty():
		var el := UiKit.wrap("  -  ".join(PackedStringArray(eff)), "Small")
		el.add_theme_color_override("font_color", UiTheme.TEAL)
		v.add_child(el)
	if not done:
		var req := []
		for r in t.get("requires", []):
			if not s.state.techs.has(r):
				req.append(String(s.content.tech_by_id.get(String(r), {}).get("name", r)))
		if not req.is_empty():
			v.add_child(UiKit.label("Needs: " + ", ".join(PackedStringArray(req)), "Caption"))
		else:
			var b := CostButton.make("Research", func() -> void: cmd({"type": "research", "tech": tid}), "Teal")
			v.add_child(b)
			_buttons[tid] = b
	return UiKit.card(v, "Card" if not done else "Card")


func refresh() -> void:
	var s := sim()
	_rp_label.text = "%s RP  (+%s/s)" % [Num.short(s.state.research_points), Num.short(float(s.rt.get("research_rate", 0.0)))]
	for tid in _buttons:
		var t: Dictionary = s.content.tech_by_id[tid]
		var rp := float(t.get("rp", 0.0))
		var cost := float(t.get("cost", 0.0))
		var b: CostButton = _buttons[tid]
		var ok := s.state.research_points >= rp and s.state.money >= cost
		b.set_cost("Research  (%s RP)" % Num.short(rp), cost, ok)
		if s.state.research_points < rp:
			b.price_label.text = "%s RP needed  -  %s" % [Num.short(rp - s.state.research_points), Num.money(cost)]
