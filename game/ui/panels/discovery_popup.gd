extends GamePanel
## A resource found for the first time.

func frame_kind() -> String:
	return "popup"


func game_state() -> int:
	return State.DISCOVERY


func panel_id() -> String:
	return "discovery"


func title() -> String:
	return "Discovery!"


func icon_kind() -> String:
	return "star"


func build() -> void:
	var s := sim()
	var rid := String(args.get("resource", ""))
	var r: Dictionary = s.content.resource_by_id.get(rid, {})
	var rar := String(r.get("rarity", "common"))
	var gem := Icon.make("gem", 150, UiTheme.TEXT, Color(String(r.get("color", "#ffffff"))))
	gem.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	content.add_child(gem)
	UiKit.pop_in(gem, 0.1)
	var n := UiKit.label(String(r.get("name", rid)), "Title", HORIZONTAL_ALIGNMENT_CENTER)
	n.add_theme_color_override("font_color", UiTheme.RARITY.get(rar, UiTheme.TEXT))
	content.add_child(n)
	content.add_child(UiKit.label(String(UiText.RARITY_NAMES.get(rar, rar)), "Accent", HORIZONTAL_ALIGNMENT_CENTER))
	content.add_child(UiKit.wrap(String(r.get("description", "")), "Small"))
	content.add_child(UiKit.kv("Found at", String(s.content.depth(int(args.get("depth", 1))).get("name", ""))))
	content.add_child(UiKit.kv("Sells for", Num.money(Economy.item_price(s, rid)) + " raw", "Accent"))
	content.add_child(UiKit.button("Into the codex!", close, "Primary"))
