extends GamePanel
## A surface facility: what it does, its level and stats (now -> next),
## upgrades (x1 / x10 / max), building it, condition and repairs, its
## operators, and a live readout (lift, trucks, stores, power, pumps).

var fid := ""
var fac: Dictionary
var _live: VBoxContainer
var _up_box: HBoxContainer
var _up_buttons: Array = []
var _stat_labels: Dictionary = {}
var _cond_bar: ProgressBar
var _repair_button: Button
var _cond_label: Label
var _stats_box: VBoxContainer


func frame_kind() -> String:
	return "sheet"


func panel_id() -> String:
	return "facility"


func title() -> String:
	fid = String(args.get("facility", ""))
	fac = Session.content.facility(fid)
	var s := sim()
	if s and s.facility_built(fid):
		return "%s  -  Lv %d" % [String(fac.get("name", fid)), s.facility_level(fid)]
	return String(fac.get("name", fid))


func icon_kind() -> String:
	var f := Session.content.facility(String(args.get("facility", "")))
	return String(UiText.CATEGORY_ICONS.get(String(f.get("category", "")), "factory"))


func signature() -> String:
	var s := sim()
	return "%s|%s|%d|%d" % [fid, s.facility_built(fid), s.state.workers.size(), s.facility_level(fid) / 10]


func build() -> void:
	var s := sim()
	fid = String(args.get("facility", ""))
	fac = s.content.facility(fid)
	content.add_child(UiKit.wrap(String(fac.get("description", ""))))
	if not s.facility_built(fid):
		_build_unbuilt(s)
		return
	_stats_box = UiKit.vbox(6)
	content.add_child(UiKit.card(_stats_box))
	_stat_labels.clear()
	var lv_row := UiKit.kv("Level", "", "Accent")
	_stats_box.add_child(lv_row)
	_stat_labels["_level"] = lv_row.get_child(1)
	for st in fac.get("stats", {}):
		var row := UiKit.kv(UiText.stat_name(String(st)), "")
		_stats_box.add_child(row)
		_stat_labels[String(st)] = row.get_child(1)
	_up_box = UiKit.hbox(10)
	content.add_child(_up_box)
	_up_buttons = [
		CostButton.make("+1", func() -> void: cmd({"type": "upgrade", "facility": fid, "count": 1})),
		CostButton.make("+10", func() -> void: cmd({"type": "upgrade", "facility": fid, "count": 10})),
		CostButton.make("MAX", func() -> void: cmd({"type": "upgrade", "facility": fid, "count": maxi(1, Economy.facility_affordable(sim(), fid))}), "Teal"),
	]
	for b in _up_buttons:
		_up_box.add_child(b)
	if bool(fac.get("repairable", false)):
		var cv := UiKit.vbox(6)
		var ch := UiKit.hbox(8)
		ch.add_child(Icon.make("hammer", 34))
		_cond_label = UiKit.label("", "Small")
		_cond_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		ch.add_child(_cond_label)
		_repair_button = UiKit.button("Repair", func() -> void: cmd({"type": "manual_repair", "facility": fid}), "Teal", 70)
		ch.add_child(_repair_button)
		cv.add_child(ch)
		_cond_bar = UiKit.progress(1, 1, "GreenBar", 16)
		cv.add_child(_cond_bar)
		content.add_child(UiKit.card(cv))
	if int(fac.get("operator_slots", 0)) > 0:
		_build_operators(s)
	_live = UiKit.vbox(6)
	content.add_child(UiKit.card(_live))
	_build_actions(s)
	var tiers: Array = fac.get("visual_tiers", [])
	for t in tiers:
		if int(t.get("level", 1)) > s.facility_level(fid):
			content.add_child(UiKit.wrap("Level %d: %s" % [int(t["level"]), String(t.get("label", ""))], "Caption"))
			break


func _build_unbuilt(s: Simulation) -> void:
	var ok := SimCommands.facility_requirement_met(s, fid)
	var req: Dictionary = fac.get("requires", {})
	if not ok:
		var t: Dictionary = s.content.tech_by_id.get(String(req.get("tech", "")), {})
		content.add_child(UiKit.wrap("Needs the %s research." % String(t.get("name", "required")), "Small"))
		content.add_child(UiKit.button("Open research", func() -> void: open("research"), "Teal"))
		return
	var cost := float(fac.get("build_cost", 0.0))
	content.add_child(UiKit.cost_button("Build %s" % String(fac.get("name", "")), cost, s.state.money >= cost,
		func() -> void:
			var r := cmd({"type": "build", "facility": fid})
			if r.get("ok", false):
				close()))


func _build_operators(s: Simulation) -> void:
	var v := UiKit.vbox(6)
	var ops := s.workers_at(fid, "operator")
	var slots := int(fac.get("operator_slots", 1))
	var req := String(fac.get("operator_required", "speed"))
	var note := "Runs the lift automatically" if req == "automation" else "Runs the machine at full speed (%d%% unattended)" % roundi(float(fac.get("unoperated_speed", 0.35)) * 100.0)
	if s.mods.has_flag("machines_self_run") and req != "automation":
		note = "Machines run at full speed unattended (research)"
	var h := UiKit.hbox(8)
	h.add_child(Icon.make("gear", 34))
	var l := UiKit.label("Operators %d/%d" % [ops.size(), slots], "Small")
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(l)
	v.add_child(h)
	v.add_child(UiKit.wrap(note))
	for w in ops:
		var wb := UiKit.button("%s  (Lv %d)" % [String(w["name"]), int(w["level"])], func() -> void: open("worker", {"worker": int(w["id"])}), "Chip", 64)
		v.add_child(wb)
	if ops.size() < slots:
		if SimCommands.role_unlocked(s, "operator"):
			var cost := Economy.hire_cost(s, "operator")
			v.add_child(UiKit.cost_button("Hire operator", cost, s.state.money >= cost,
				func() -> void: cmd({"type": "hire", "role": "operator", "post": fid})))
		else:
			v.add_child(UiKit.wrap("Operators are not available yet."))
	content.add_child(UiKit.card(v))


func _build_actions(s: Simulation) -> void:
	match fid:
		"headframe":
			if not TransportSystem.lift_automatic(s):
				content.add_child(UiKit.button("Wind the lift", func() -> void: cmd({"type": "call_lift"}), "Primary"))
		"depot":
			if not SalesSystem.automatic(s):
				content.add_child(UiKit.button("Send the trucks", func() -> void: cmd({"type": "dispatch"}), "Primary"))
	if fid in ["office"]:
		content.add_child(UiKit.button("Open crew", func() -> void: open("crew"), "Chip", 70))
		content.add_child(UiKit.button("Open research", func() -> void: open("research"), "Chip", 70))


func refresh() -> void:
	var s := sim()
	if not s.facility_built(fid) or _stats_box == null:
		return
	var lvl := s.facility_level(fid)
	var max_lvl := int(fac.get("max_level", 1))
	(_stat_labels["_level"] as Label).text = "%d / %d" % [lvl, max_lvl]
	for st in fac.get("stats", {}):
		var now := s.content.facility_stat(fid, String(st), lvl)
		var nxt := s.content.facility_stat(fid, String(st), mini(lvl + 1, max_lvl))
		var txt := UiText.stat_value(String(st), now)
		if nxt != now and lvl < max_lvl:
			txt += "  >  " + UiText.stat_value(String(st), nxt)
		(_stat_labels[String(st)] as Label).text = txt
	if lvl >= max_lvl:
		for b in _up_buttons:
			(b as CostButton).set_text_only("Max level")
	else:
		var afford := Economy.facility_affordable(s, fid)
		for i in 2:
			var n: int = [1, 10][i]
			var c := Economy.facility_upgrade_cost(s, fid, mini(n, max_lvl - lvl))
			(_up_buttons[i] as CostButton).set_cost("+%d" % mini(n, max_lvl - lvl), c, s.state.money >= c)
		var mx := maxi(1, afford)
		(_up_buttons[2] as CostButton).set_cost("MAX +%d" % mx, Economy.facility_upgrade_cost(s, fid, mx), afford >= 1)
	var fs: Dictionary = s.state.facilities.get(fid, {})
	if _cond_bar:
		var cond := float(fs.get("condition", 1.0))
		_cond_bar.value = cond
		_repair_button.visible = cond < 0.999
		_cond_label.text = "Condition %d%%%s" % [roundi(cond * 100.0), "  -  worn, running slower" if bool(fs.get("repairing", false)) else ""]
	_refresh_live(s, fs)


func _refresh_live(s: Simulation, fs: Dictionary) -> void:
	UiKit.clear(_live)
	var util := float(fs.get("util", 0.0))
	match fid:
		"headframe":
			var ls: Dictionary = s.rt.get("lift", TransportSystem.lift_stats(s))
			_live.add_child(UiKit.kv("Lifting", Num.rate(float(ls.get("moved_rate", 0.0)))))
			_live.add_child(UiKit.kv("Capacity", Num.rate(float(ls.get("rate", 0.0)))))
			_live.add_child(UiKit.kv("Mode", "Automatic" if TransportSystem.lift_automatic(s) else "Manual - tap LIFT"))
		"silo":
			var cap := Economy.bin_capacity(s)
			var have := Simulation.inv_total(s.state.surface_bin)
			_live.add_child(UiKit.kv("Stored ore", "%s / %s" % [Num.short(have), Num.short(cap)]))
			_live.add_child(UiKit.progress(have, cap, "", 16))
		"warehouse":
			var cap2 := Economy.warehouse_capacity(s)
			var have2 := Simulation.inv_total(s.state.warehouse)
			_live.add_child(UiKit.kv("Stored goods", "%s / %s" % [Num.short(have2), Num.short(cap2)]))
			_live.add_child(UiKit.progress(have2, cap2, "", 16))
		"depot":
			var ts: Dictionary = s.rt.get("sales", SalesSystem.truck_stats(s))
			_live.add_child(UiKit.kv("Selling", Num.rate(float(ts.get("sold_rate", 0.0)))))
			_live.add_child(UiKit.kv("Earning", Num.money(float(ts.get("earn_rate", 0.0))) + "/s"))
			_live.add_child(UiKit.kv("Mode", "Automatic" if SalesSystem.automatic(s) else "Manual - tap SELL"))
		"generator":
			var pw: Dictionary = s.rt.get("power", {})
			_live.add_child(UiKit.kv("Supply / demand", "%s / %s kW" % [Num.short(float(pw.get("supply", 0.0))), Num.short(float(pw.get("demand", 0.0)))]))
		"pump":
			var pm: Dictionary = s.rt.get("pump", {})
			_live.add_child(UiKit.kv("Pumping / inflow", "%s / %s" % [Num.short(float(pm.get("capacity", 0.0))), Num.short(float(pm.get("inflow", 0.0)))]))
		"office":
			_live.add_child(UiKit.kv("Workers", "%d / %d" % [s.state.workers.size(), Economy.worker_capacity(s)]))
			_live.add_child(UiKit.kv("Research", Num.rate(float(s.rt.get("research_rate", 0.0)), " RP/s")))
		"conveyor":
			var pl: Dictionary = s.rt.get("plant", {})
			_live.add_child(UiKit.kv("Belt", "%s of %s" % [Num.rate(float(pl.get("rate", 0.0))), Num.rate(float(pl.get("capacity", 0.0)))]))
		_:
			if fac.get("category", "") == "processing":
				_live.add_child(UiKit.kv("Load", Num.percent(util)))
				_live.add_child(UiKit.progress(util, 1.0, "TealBar", 14))
	if _live.get_child_count() == 0:
		_live.add_child(UiKit.label("Running", "Caption"))
