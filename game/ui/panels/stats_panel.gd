extends GamePanel
## The production flow, stage by stage - mining at each depth, haulage,
## the lift, the silos, the plant (with machine loads), the warehouse and
## the trucks - with the current bottleneck called out, plus power and
## pumping. This is where a tycoon finds what to upgrade next.

var _rows: VBoxContainer
var _hint: Label


func frame_kind() -> String:
	return "full"


func game_state() -> int:
	return State.PROCESSING


func panel_id() -> String:
	return "stats"


func title() -> String:
	return "Production flow"


func icon_kind() -> String:
	return "chart"


func build() -> void:
	_hint = UiKit.wrap("", "Small")
	_hint.add_theme_color_override("font_color", UiTheme.GOLD)
	content.add_child(UiKit.card(_hint, "CardHi"))
	_rows = UiKit.vbox(10)
	content.add_child(_rows)


func _stage(icon: String, name: String, rate: float, cap: float, note: String = "") -> void:
	var v := UiKit.vbox(4)
	var h := UiKit.hbox(10)
	h.add_child(Icon.make(icon, 40, UiTheme.TEXT, UiTheme.GOLD))
	var n := UiKit.label(name, "Small")
	n.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(n)
	h.add_child(UiKit.label("%s / %s" % [Num.rate(rate), Num.rate(cap)], "Caption"))
	v.add_child(h)
	v.add_child(UiKit.progress(rate, maxf(cap, 1e-9), "TealBar", 12))
	if note != "":
		v.add_child(UiKit.label(note, "Caption"))
	_rows.add_child(UiKit.card(v))


func refresh() -> void:
	var s := sim()
	UiKit.clear(_rows)
	var mined := 0.0
	var mine_cap := 0.0
	for dep in s.state.depths:
		if not dep["unlocked"]:
			continue
		var d := int(dep["index"])
		var rt: Dictionary = s.rt.get("depth", {}).get(d, {})
		mined += float(rt.get("units_rate", 0.0))
		mine_cap += float(rt.get("work_rate", 0.0))
	var haul := 0.0
	var haul_cap := 0.0
	for d in s.rt.get("haul", {}):
		haul += float(s.rt["haul"][d].get("moved_rate", 0.0))
		haul_cap += float(s.rt["haul"][d].get("rate", 0.0))
	var ls: Dictionary = s.rt.get("lift", {})
	var pl: Dictionary = s.rt.get("plant", {})
	var ts: Dictionary = s.rt.get("sales", {})
	_stage("pick", "Mining (all depths)", mined, maxf(mine_cap, mined))
	if haul_cap > 0.0:
		_stage("cart", "Haulage carts", haul, haul_cap)
	_stage("lift", "Lift", float(ls.get("moved_rate", 0.0)), float(ls.get("rate", 0.0)), "" if TransportSystem.lift_automatic(s) else "Manual - tap LIFT or hire an operator")
	var bin := Simulation.inv_total(s.state.surface_bin)
	_stage("factory", "Silos  %s / %s" % [Num.short(bin), Num.short(Economy.bin_capacity(s))], bin, Economy.bin_capacity(s))
	var utils: Dictionary = pl.get("util", {})
	var note := ""
	for fid in utils:
		note += "%s %d%%   " % [String(s.content.facility(String(fid)).get("name", fid)), roundi(float(utils[fid]) * 100.0)]
	_stage("factory", "Plant & conveyor", float(pl.get("rate", 0.0)), float(pl.get("capacity", 0.0)), note.strip_edges())
	var wh := Simulation.inv_total(s.state.warehouse)
	_stage("factory", "Warehouse  %s / %s" % [Num.short(wh), Num.short(Economy.warehouse_capacity(s))], wh, Economy.warehouse_capacity(s))
	_stage("truck", "Trucks", float(ts.get("sold_rate", 0.0)), float(ts.get("rate", 0.0)), "Earning %s/s" % Num.money(float(ts.get("earn_rate", 0.0))))
	var pw: Dictionary = s.rt.get("power", {})
	if float(pw.get("demand", 0.0)) > 0.0:
		_rows.add_child(UiKit.kv("Power", "%s / %s kW  (%d%%)" % [Num.short(float(pw.get("supply", 0.0))), Num.short(float(pw.get("demand", 0.0))),
			roundi(float(s.rt.get("power_factor", 1.0)) * 100.0)]))
	_hint.text = _bottleneck(s, mined, ls, pl, ts)


func _bottleneck(s: Simulation, mined: float, ls: Dictionary, pl: Dictionary, ts: Dictionary) -> String:
	if s.state.workers.is_empty():
		return "Tip: hire miners so the mine works while you do other things."
	for dep in s.state.depths:
		if dep["unlocked"] and Simulation.inv_total(dep["station"]) >= Economy.station_capacity(s, int(dep["index"])) - 0.01:
			return "Bottleneck: the %s station is full - the lift can't keep up. Upgrade the Headframe or hire a lift operator." % String(s.content.depth(int(dep["index"])).get("name", ""))
	if Simulation.inv_total(s.state.warehouse) >= Economy.warehouse_capacity(s) - 0.01:
		return "Bottleneck: the warehouse is full - upgrade the Truck Depot or send the trucks."
	if String(pl.get("bottleneck", "")) == "conveyor":
		return "Bottleneck: the conveyor is at capacity - upgrade the Surface Conveyor."
	if String(pl.get("short", "")) != "" and float(pl.get("processed_share", 1.0)) < 0.95:
		return "Some ore skips the %s (it is at capacity) and sells for less. Upgrade it or add an operator." % String(s.content.facility(String(pl["short"])).get("name", ""))
	if float(ls.get("moved_rate", 0.0)) < mined * 0.8 and TransportSystem.lift_automatic(s):
		return "The lift is the slowest stage: upgrade the Headframe."
	return "Everything flows. Upgrade Mining Operations to push more ore through."
