extends GamePanel
## The rest of the game's screens, revealed as they become relevant.

func frame_kind() -> String:
	return "full"


func panel_id() -> String:
	return "more"


func title() -> String:
	return "More"


func icon_kind() -> String:
	return "menu"


func build() -> void:
	var s := sim()
	var items := [["codex", "book", "Codex", "Every resource you have found"], ["quests", "trophy", "Achievements", "Milestones and their bonuses"],
		["stats", "chart", "Production flow", "Find your bottleneck"], ["cosmetics", "shirt", "Outfits", "Change the foreman's look"]]
	var f: Dictionary = s.content.legacy_cfg.get("formula", {})
	if float(s.state.life_stats.get("earned", 0.0)) >= float(f.get("min_earned", 1e9)) * 0.05 or int(s.state.prestige.get("count", 0)) > 0:
		items.append(["prestige", "crown", "Sell the Claim", "Prestige for permanent bonuses"])
	items.append(["settings", "gear", "Settings", "Sound, graphics, controls"])
	for it in items:
		var id := String(it[0])
		var b := UiKit.button("", func() -> void: open(id, {"tab": "achievements"} if String(it[2]) == "Achievements" else {}), "Button", 110)
		var h := UiKit.hbox(16)
		h.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		h.offset_left = 20
		h.mouse_filter = Control.MOUSE_FILTER_IGNORE
		h.add_child(Icon.make(String(it[1]), 60, UiTheme.TEXT, UiTheme.GOLD))
		var v := UiKit.vbox(0)
		v.alignment = BoxContainer.ALIGNMENT_CENTER
		v.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var t := UiKit.label(String(it[2]), "Small")
		t.add_theme_font_override("font", UiTheme.bold_font())
		t.mouse_filter = Control.MOUSE_FILTER_IGNORE
		v.add_child(t)
		var c := UiKit.label(String(it[3]), "Caption")
		c.mouse_filter = Control.MOUSE_FILTER_IGNORE
		v.add_child(c)
		h.add_child(v)
		b.add_child(h)
		content.add_child(b)
	content.add_child(UiKit.spacer(false))
	content.add_child(UiKit.button("Save and exit to title", func() -> void:
		if ui.main:
			ui.main.quit_to_menu(), "Chip"))
