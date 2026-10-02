extends GamePanel
## "WHILE YOU WERE AWAY": what the mine did while the app was closed -
## time away (and how much of it counted), resources mined, units processed
## and sold, money earned and any rare discoveries.

func frame_kind() -> String:
	return "popup"


func game_state() -> int:
	return State.OFFLINE_REWARD


func panel_id() -> String:
	return "offline"


func title() -> String:
	return "WHILE YOU WERE AWAY"


func icon_kind() -> String:
	return "clock"


func build() -> void:
	var s := sim()
	var r: Dictionary = args.get("report", Session.offline_report)
	var away := float(r.get("away_s", 0.0))
	var credited := float(r.get("credited_s", 0.0))
	content.add_child(UiKit.label("Away for %s" % Num.duration(away), "Heading"))
	if bool(r.get("capped", false)) or credited < away - 1.0:
		content.add_child(UiKit.wrap("Your crews worked %s of it at %d%% pace. Research remote operations to keep them going longer." % [Num.duration(credited), roundi(float(r.get("efficiency", 1.0)) * 100.0)]))
	var money := UiKit.label("+" + Num.money(float(r.get("earned", 0.0))), "Big")
	money.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	content.add_child(UiKit.card(money, "CardHi"))
	var v := UiKit.vbox(UiTheme.GAP_IN)
	v.add_child(UiKit.label("Resources mined", "Accent"))
	var mined: Dictionary = r.get("mined", {})
	if mined.is_empty():
		v.add_child(UiKit.label("Nothing - hire miners to keep digging while you're away", "Caption"))
	var keys := mined.keys()
	keys.sort_custom(func(a: String, b: String) -> bool: return float(mined[a]) > float(mined[b]))
	for k in keys:
		var res: Dictionary = s.content.resource_by_id.get(String(k), {})
		var h := UiKit.hbox(UiTheme.GAP_ROW)
		h.add_child(Icon.make("gem", 32, UiTheme.TEXT, Color(String(res.get("color", "#cccccc")))))
		var n := UiKit.label(String(res.get("name", k)), "Small")
		n.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		h.add_child(n)
		h.add_child(UiKit.label(Num.short(float(mined[k])), "Small"))
		v.add_child(h)
	v.add_child(UiKit.separator())
	v.add_child(UiKit.kv("Resources processed", Num.short(float(r.get("processed_units", 0.0)))))
	v.add_child(UiKit.kv("Goods sold", Num.short(float(r.get("sold_units", 0.0)))))
	v.add_child(UiKit.kv("Money earned", Num.money(float(r.get("earned", 0.0))), "Accent"))
	content.add_child(UiKit.card(v))
	var disc: Array = r.get("discoveries", [])
	if not disc.is_empty():
		var dv := UiKit.vbox(UiTheme.GAP_IN)
		dv.add_child(UiKit.label("Rare discoveries", "Accent"))
		for rid in disc:
			var res2: Dictionary = s.content.resource_by_id.get(String(rid), {})
			var l := UiKit.label(String(res2.get("name", rid)), "Small")
			l.add_theme_color_override("font_color", UiTheme.RARITY.get(String(res2.get("rarity", "common")), UiTheme.TEXT))
			dv.add_child(l)
		content.add_child(UiKit.card(dv, "CardHi"))
	content.add_child(UiKit.button("Collect", func() -> void:
		Audio.ui("ui_coin")
		close(), "Primary"))
