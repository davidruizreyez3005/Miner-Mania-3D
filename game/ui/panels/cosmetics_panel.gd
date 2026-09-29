extends GamePanel
## Looks only: the foreman's outfit (every worker model shares the rig) and
## lamp themes. Locked items say how to earn them.

func frame_kind() -> String:
	return "full"


func panel_id() -> String:
	return "cosmetics"


func title() -> String:
	return "Outfits"


func icon_kind() -> String:
	return "shirt"


func signature() -> String:
	var s := sim()
	return str(s.state.cosmetics.get("equipped", {})) + str(s.state.cosmetics.get("unlocked", {}).size())


func build() -> void:
	var s := sim()
	var eq: Dictionary = s.state.cosmetics.get("equipped", {})
	var unlocked: Dictionary = s.state.cosmetics.get("unlocked", {})
	for kind in ["foreman_outfit", "lamp_theme"]:
		section("Foreman outfits" if kind == "foreman_outfit" else "Lamp themes")
		for c in s.content.cosmetics:
			if String(c.get("kind", "")) != kind:
				continue
			var cid := String(c["id"])
			var have := unlocked.has(cid) or bool(c.get("default", false))
			var on := String(eq.get(kind, "")) == cid or (not eq.has(kind) and bool(c.get("default", false)))
			var h := UiKit.hbox(12)
			h.add_child(Icon.make("shirt" if kind == "foreman_outfit" else "bolt", 48, UiTheme.TEXT, UiTheme.GOLD if have else UiTheme.DIM))
			var v := UiKit.vbox(0)
			v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			v.add_child(UiKit.label(String(c.get("name", cid)), "Small"))
			if not have:
				v.add_child(UiKit.label(_how(s, cid), "Caption"))
			h.add_child(v)
			if on:
				h.add_child(UiKit.label("Worn", "Accent"))
			elif have:
				h.add_child(UiKit.button("Wear", func() -> void: cmd({"type": "equip_cosmetic", "cosmetic": cid}), "Teal", 72))
			content.add_child(UiKit.card(h, "CardHi" if on else "Card"))


func _how(s: Simulation, cid: String) -> String:
	for a in s.content.achievements:
		if String(a.get("reward", {}).get("cosmetic", "")) == cid:
			return "Achievement: %s" % String(a.get("name", ""))
	return "Keep playing to unlock"
