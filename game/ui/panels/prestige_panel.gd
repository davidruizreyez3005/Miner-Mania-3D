extends GamePanel
## "Sell the Claim": what this claim is worth in Legacy Points, the
## permanent income bonus, the next region to open, and the legacy
## upgrades bought with LP.

var _gain_label: Label
var _mult_label: Label
var _sell: CostButton
var _region := ""
var _legacy: Dictionary = {}          # upgrade id -> CostButton


func frame_kind() -> String:
	return "full"


func game_state() -> int:
	return State.PRESTIGE


func panel_id() -> String:
	return "prestige"


func title() -> String:
	return "Sell the Claim"


func icon_kind() -> String:
	return "crown"


func signature() -> String:
	var s := sim()
	return "%d|%d|%s" % [int(s.state.prestige.get("count", 0)), int(s.state.prestige.get("lp", 0)), str(s.state.prestige.get("upgrades", {}))]


func build() -> void:
	var s := sim()
	_legacy.clear()
	content.add_child(UiKit.wrap("Sell this claim to a mining company for Legacy Points. You start a new claim with nothing but your legacy: every Legacy Point ever earned raises all income for good, and points buy lasting upgrades. Achievements, the codex and outfits stay with you."))
	var v := UiKit.vbox(UiTheme.GAP_IN)
	_gain_label = UiKit.label("", "Big")
	v.add_child(_gain_label)
	_mult_label = UiKit.label("", "Small")
	v.add_child(_mult_label)
	content.add_child(UiKit.card(v, "CardHi"))
	section("Next claim")
	var count_after := int(s.state.prestige.get("count", 0)) + 1
	var group := ButtonGroup.new()
	_region = s.state.region
	for r in s.content.regions:
		var rid := String(r["id"])
		var ok := PrestigeSystem.region_available(s, rid, count_after)
		var b := Button.new()
		b.toggle_mode = true
		b.button_group = group
		b.text = "%s%s" % [String(r.get("name", rid)), "" if ok else "  (after %d sales)" % int(r.get("requires_prestige", 0))]
		b.disabled = not ok
		b.custom_minimum_size = Vector2(0, 80)
		b.focus_mode = Control.FOCUS_NONE
		b.theme_type_variation = "Chip"
		b.button_pressed = rid == _region
		b.toggled.connect(func(on: bool) -> void:
			if on:
				_region = rid)
		content.add_child(b)
		content.add_child(UiKit.wrap(String(r.get("description", ""))))
	_sell = CostButton.make("Sell the claim", _confirm, "Danger", "LP")
	content.add_child(_sell)
	section("Legacy upgrades")
	for u in s.content.legacy_upgrades:
		var uid := String(u["id"])
		var uv := UiKit.vbox(4)
		var lvl := int(s.state.prestige.get("upgrades", {}).get(uid, 0))
		var n := UiKit.label("%s  Lv %d / %d" % [String(u.get("name", uid)), lvl, int(u.get("max_level", 1))], "Small")
		n.add_theme_font_override("font", UiTheme.bold_font())
		uv.add_child(n)
		uv.add_child(UiKit.wrap(String(u.get("description", ""))))
		var b2 := CostButton.make("Buy", func() -> void:
			var r2 := Session.command({"type": "buy_legacy", "upgrade": uid})
			if not r2.get("ok", false):
				ui.toast("Not enough Legacy Points" if r2.get("error", "") == "no_lp" else String(UiRoot.ERRORS.get(String(r2.get("error", "")), "Not available")), "bad")
			refresh(), "Primary", "LP")
		uv.add_child(b2)
		_legacy[uid] = b2
		content.add_child(UiKit.card(uv))


func _confirm() -> void:
	var s := sim()
	var pv := PrestigeSystem.preview(s)
	ui.open_panel("confirm", {"text": "Sell this claim for %d Legacy Points and start again in %s?" % [int(pv["gain"]),
		String(s.content.region_by_id.get(_region, {}).get("name", _region))], "yes": "Sell", "action": _do_prestige})


func _do_prestige() -> void:
	var r := Session.command({"type": "prestige", "region": _region})
	if not r.get("ok", false):
		ui.report_error(r)
		return
	close()


func refresh() -> void:
	var s := sim()
	var pv := PrestigeSystem.preview(s)
	_gain_label.text = "+%d LP" % int(pv["gain"])
	_mult_label.text = "Income bonus x%s  >  x%s" % [Num.short(float(pv["income_mult_now"])), Num.short(float(pv["income_mult_after"]))]
	if bool(pv["can"]):
		_sell.set_cost("Sell the claim", float(pv["gain"]), true)
	else:
		_sell.set_text_only("Not yet", "Earn %s this claim (%s so far)" % [Num.money(float(pv["min_earned"])), Num.money(float(pv["earned"]))])
	var lp := int(s.state.prestige.get("lp", 0))
	for uid in _legacy:
		var u: Dictionary = s.content.legacy_by_id[uid]
		var lvl := int(s.state.prestige.get("upgrades", {}).get(uid, 0))
		var b: CostButton = _legacy[uid]
		if lvl >= int(u.get("max_level", 1)):
			b.set_text_only("Maxed")
		else:
			var c := Economy.legacy_cost(s.content, uid, lvl)
			b.set_cost("Buy level %d" % (lvl + 1), float(c), lp >= c)
