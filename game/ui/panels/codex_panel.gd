extends GamePanel
## The codex: every resource of the mine - discovered ones with rarity,
## where they were found, how many and what they sell for; undiscovered
## ones as silhouettes - plus each resource's processing chain.

func frame_kind() -> String:
	return "full"


func game_state() -> int:
	return State.QUEST


func panel_id() -> String:
	return "codex"


func title() -> String:
	return "Codex"


func icon_kind() -> String:
	return "book"


func signature() -> String:
	return str(sim().state.discoveries.size())


func build() -> void:
	var s := sim()
	content.add_child(UiKit.label("%d / %d discovered" % [s.state.discoveries.size(), s.content.resources.size()], "Accent"))
	for r in s.content.resources:
		var rid := String(r["id"])
		var known := s.state.discoveries.has(rid)
		var rar := String(r.get("rarity", "common"))
		var h := UiKit.hbox(12)
		h.add_child(Icon.make("gem", 56, UiTheme.TEXT, Color(String(r.get("color", "#888888"))) if known else Color("3a3f47")))
		var v := UiKit.vbox(2)
		v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var n := UiKit.label(String(r.get("name", rid)) if known else "???", "Small")
		n.add_theme_font_override("font", UiTheme.bold_font())
		n.add_theme_color_override("font_color", UiTheme.RARITY.get(rar, UiTheme.TEXT) if known else UiTheme.DIM)
		v.add_child(n)
		v.add_child(UiKit.label(String(UiText.RARITY_NAMES.get(rar, rar)), "Caption"))
		if known:
			var dsc: Dictionary = s.state.discoveries[rid]
			v.add_child(UiKit.label("First found at %s  -  %s mined" % [String(s.content.depth(int(dsc.get("depth", 1))).get("name", "")),
				Num.short(float(s.state.life_stats.get("mined." + rid, 0.0)))], "Caption"))
			var chain: Array = s.content.chains.get(rid, [])
			var steps := [String(r.get("name", rid))]
			for st in chain:
				steps.append(String(st.get("name", st.get("item", ""))))
			var cl := UiKit.wrap(" > ".join(PackedStringArray(steps)), "Caption")
			cl.add_theme_color_override("font_color", UiTheme.TEAL)
			v.add_child(cl)
		h.add_child(v)
		if known:
			h.add_child(UiKit.label(Num.money(Economy.item_price(s, rid)), "Caption"))
		content.add_child(UiKit.card(h))
