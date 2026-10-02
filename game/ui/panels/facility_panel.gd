extends GamePanel
## A surface facility as a column of evenly spaced cards (one spacing scale,
## UiTheme.GAP / GAP_IN / GAP_ROW): what it does; upgrade (level, stats now
## > next, +1 / +10 / MAX, the next look); condition and repairs (and what
## the mechanics are doing); power (the grid plus the generator, what this
## machine draws and whether the supply reaches it); its crew (operators,
## or the workshop's mechanics); and a live readout with its actions. Rows
## are built once and their numbers updated in place.

var fid := ""
var fac: Dictionary
var _up_buttons: Array = []
var _stat_labels: Dictionary = {}
var _cond_bar: ProgressBar
var _repair_button: Button
var _cond_label: Label
var _cond_note: Label
var _power_rows: Dictionary = {}       # key -> value Label
var _power_bar: ProgressBar
var _power_note: Label
var _crew_rows: Array = []              # [worker id, Button]
var _crew_hire: CostButton
var _crew_role := ""
var _live_box: VBoxContainer
var _live_values: Array = []            # value Labels, in row order
var _live_bar: ProgressBar
var _live_sig := ""


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
	_stat_labels.clear()
	_power_rows.clear()
	_crew_rows.clear()
	_up_buttons.clear()
	_cond_bar = null
	_power_bar = null
	_crew_hire = null
	_live_box = null
	_live_sig = ""
	content.add_child(UiKit.wrap(String(fac.get("description", ""))))
	if not s.facility_built(fid):
		_build_unbuilt(s)
		return
	_build_upgrade(s)
	if bool(fac.get("repairable", false)):
		_build_condition()
	if fid == "generator" or float(fac.get("power_kw", 0.0)) > 0.0:
		_build_power()
	if int(fac.get("operator_slots", 0)) > 0:
		_build_crew(s, "operator")
	elif fid == "workshop":
		_build_crew(s, "mechanic")
	_build_live(s)


## Level, stats (now > next), the upgrade buttons and the next look, in one card.
func _build_upgrade(s: Simulation) -> void:
	var v := UiKit.vbox(UiTheme.GAP_IN)
	var lv_row := UiKit.kv("Level", "", "Accent")
	v.add_child(lv_row)
	_stat_labels["_level"] = lv_row.get_child(1)
	for st in fac.get("stats", {}):
		var title := "Generator output" if fid == "generator" and String(st) == "power_kw" else UiText.stat_name(String(st))
		var row := UiKit.kv(title, "")
		v.add_child(row)
		_stat_labels[String(st)] = row.get_child(1)
	if fid == "generator":
		var tot := UiKit.kv("Plant supply (grid + generator)", "")
		v.add_child(tot)
		_stat_labels["_supply"] = tot.get_child(1)
	var row2 := UiKit.hbox(UiTheme.GAP_ROW)
	_up_buttons = [
		CostButton.make("+1", func() -> void: cmd({"type": "upgrade", "facility": fid, "count": 1})),
		CostButton.make("+10", func() -> void: cmd({"type": "upgrade", "facility": fid, "count": 10})),
		CostButton.make("MAX", func() -> void: cmd({"type": "upgrade", "facility": fid, "count": maxi(1, Economy.facility_affordable(sim(), fid))}), "Teal"),
	]
	for b in _up_buttons:
		row2.add_child(b)
	v.add_child(row2)
	for t in fac.get("visual_tiers", []):
		if int(t.get("level", 1)) > s.facility_level(fid):
			v.add_child(UiKit.wrap("Next look at level %d: %s" % [int(t["level"]), String(t.get("label", ""))], "Caption"))
			break
	content.add_child(UiKit.card(v))


func _build_condition() -> void:
	var v := UiKit.vbox(UiTheme.GAP_IN)
	var h := UiKit.hbox(UiTheme.GAP_ROW)
	h.add_child(Icon.make("hammer", 34))
	_cond_label = UiKit.label("", "Small")
	_cond_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(_cond_label)
	_repair_button = UiKit.button("Repair", func() -> void: cmd({"type": "manual_repair", "facility": fid}), "Teal", 64)
	_repair_button.custom_minimum_size.x = 150
	h.add_child(_repair_button)
	v.add_child(h)
	_cond_bar = UiKit.progress(1, 1, "GreenBar", 16)
	v.add_child(_cond_bar)
	_cond_note = UiKit.wrap("", "Caption")
	v.add_child(_cond_note)
	content.add_child(UiKit.card(v))


## The generator: grid + generator = supply against the plant's demand. A
## machine: its rating, what it gets and whether the supply reaches it.
func _build_power() -> void:
	var v := UiKit.vbox(UiTheme.GAP_IN)
	var h := UiKit.hbox(UiTheme.GAP_ROW)
	h.add_child(Icon.make("bolt", 34, UiTheme.TEXT, UiTheme.GOLD))
	var t := UiKit.label("Power", "Small")
	t.add_theme_font_override("font", UiTheme.bold_font())
	t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(t)
	v.add_child(h)
	var keys := ["grid", "generator", "demand"] if fid == "generator" else ["rating", "getting", "plant"]
	var names := {"grid": "From the grid", "generator": "From the generator", "demand": "Plant demand",
		"rating": "Needs at full load", "getting": "Drawing now", "plant": "Plant supply / demand"}
	for k in keys:
		var row := UiKit.kv(String(names[k]), "")
		v.add_child(row)
		_power_rows[k] = row.get_child(1)
	_power_bar = UiKit.progress(0, 1, "TealBar", 14)
	v.add_child(_power_bar)
	_power_note = UiKit.wrap("", "Caption")
	v.add_child(_power_note)
	content.add_child(UiKit.card(v))


## Operators at a machine, or the workshop's mechanics: who is there and
## what they do, and a hire button while there is room.
func _build_crew(s: Simulation, role: String) -> void:
	_crew_role = role
	var v := UiKit.vbox(UiTheme.GAP_IN)
	var post := fid
	var people := s.workers_at(post, role)
	var slots := Economy.post_capacity(s, post, role)
	var h := UiKit.hbox(UiTheme.GAP_ROW)
	h.add_child(Icon.make(String(UiText.ROLE_ICONS.get(role, "worker")), 34))
	var r: Dictionary = s.content.role_by_id.get(role, {})
	var l := UiKit.label("%s %d/%d" % [String(r.get("plural", role)), people.size(), slots], "Small")
	l.add_theme_font_override("font", UiTheme.bold_font())
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(l)
	v.add_child(h)
	v.add_child(UiKit.wrap(_crew_note(s, role)))
	for w in people:
		var wid := int(w["id"])
		var wb := UiKit.two_line_button("", "", func() -> void: open("worker", {"worker": wid}), "Chip", 80)
		v.add_child(wb)
		_crew_rows.append([wid, wb])
	if people.size() < slots:
		if SimCommands.role_unlocked(s, role):
			_crew_hire = CostButton.make("Hire %s" % String(r.get("name", role)).to_lower(), func() -> void: cmd({"type": "hire", "role": role, "post": post}))
			v.add_child(_crew_hire)
		else:
			v.add_child(UiKit.wrap("%s are not available yet." % String(r.get("plural", role))))
	content.add_child(UiKit.card(v))


func _crew_note(s: Simulation, role: String) -> String:
	if role == "mechanic":
		return "Mechanics walk a round of every machine, keep each one in full condition and rush to any that wears down."
	if String(fac.get("operator_required", "speed")) == "automation":
		return "Runs the lift automatically"
	if s.mods.has_flag("machines_self_run"):
		return "Machines run at full speed unattended (research)"
	return "Runs the machine at full speed (%d%% unattended)" % roundi(float(fac.get("unoperated_speed", 0.35)) * 100.0)


## Live numbers (rows updated in place) and the facility's own actions.
func _build_live(s: Simulation) -> void:
	var v := UiKit.vbox(UiTheme.GAP_IN)
	_live_box = UiKit.vbox(UiTheme.GAP_IN)
	v.add_child(_live_box)
	var actions := UiKit.hbox(UiTheme.GAP_ROW)
	match fid:
		"headframe":
			if not TransportSystem.lift_automatic(s):
				actions.add_child(_action("Wind the lift", func() -> void: cmd({"type": "call_lift"})))
		"depot":
			if not SalesSystem.automatic(s):
				actions.add_child(_action("Send the trucks", func() -> void: cmd({"type": "dispatch"})))
		"office":
			actions.add_child(_action("Open crew", func() -> void: open("crew"), "Chip"))
			actions.add_child(_action("Open research", func() -> void: open("research"), "Chip"))
	if actions.get_child_count() > 0:
		v.add_child(actions)
	content.add_child(UiKit.card(v))


func _action(text: String, cb: Callable, variation: String = "Primary") -> Button:
	var b := UiKit.button(text, cb, variation, 76)
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return b


func _build_unbuilt(s: Simulation) -> void:
	var ok := SimCommands.facility_requirement_met(s, fid)
	var req: Dictionary = fac.get("requires", {})
	var v := UiKit.vbox(UiTheme.GAP_IN)
	var power := _unbuilt_power_text(s)
	if power != "":
		var h := UiKit.hbox(UiTheme.GAP_ROW)
		h.add_child(Icon.make("bolt", 34, UiTheme.TEXT, UiTheme.GOLD))
		var pl := UiKit.wrap(power, "Small")
		h.add_child(pl)
		v.add_child(h)
	if not ok:
		var t: Dictionary = s.content.tech_by_id.get(String(req.get("tech", "")), {})
		v.add_child(UiKit.wrap("Needs the %s research." % String(t.get("name", "required")), "Small"))
		v.add_child(UiKit.button("Open research", func() -> void: open("research"), "Teal", 84))
		content.add_child(UiKit.card(v))
		return
	var cost := float(fac.get("build_cost", 0.0))
	v.add_child(UiKit.cost_button("Build %s" % String(fac.get("name", "")), cost, s.state.money >= cost,
		func() -> void:
			var r := cmd({"type": "build", "facility": fid})
			if r.get("ok", false):
				close()))
	content.add_child(UiKit.card(v))


## Before building: what the facility does to the power balance.
func _unbuilt_power_text(s: Simulation) -> String:
	var pw: Dictionary = s.rt.get("power", {})
	var supply := float(pw.get("supply", UtilitySystem.grid_kw(s)))
	var demand := float(pw.get("demand", 0.0))
	if fid == "generator":
		return "Adds %s to the grid's %s (plant demand now %s)." % [_kw(UtilitySystem.generator_kw(s, 1)), _kw(UtilitySystem.grid_kw(s)), _kw(demand)]
	var kw := float(fac.get("power_kw", 0.0))
	if kw <= 0.0:
		return ""
	var spare := maxf(supply - demand, 0.0)
	var txt := "Needs %s at full load; %s spare now." % [_kw(kw), _kw(spare)]
	if spare < kw:
		txt += " %s for more." % UiText.power_fix(s)
	return txt


static func _kw(v: float) -> String:
	return "%s kW" % Num.short(v)


func refresh() -> void:
	var s := sim()
	if not s.facility_built(fid) or _up_buttons.is_empty():
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
	var fs: Dictionary = s.state.facilities.get(fid, {})
	if _stat_labels.has("_supply"):
		var cond := float(fs.get("condition", 1.0))
		var now_kw := UtilitySystem.grid_kw(s) + UtilitySystem.generator_kw(s, lvl, cond)
		var txt2 := _kw(now_kw)
		if lvl < max_lvl:
			txt2 += "  >  " + _kw(UtilitySystem.grid_kw(s) + UtilitySystem.generator_kw(s, lvl + 1, cond))
		(_stat_labels["_supply"] as Label).text = txt2
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
	if _cond_bar:
		_refresh_condition(s, fs)
	if _power_bar:
		_refresh_power(s)
	_refresh_crew(s)
	_refresh_live(s, fs)


func _refresh_condition(s: Simulation, fs: Dictionary) -> void:
	var cond := float(fs.get("condition", 1.0))
	_cond_bar.value = cond
	_repair_button.disabled = cond >= 0.999
	var speed := Economy.condition_factor(s, cond)
	_cond_label.text = "Condition %d%%" % roundi(cond * 100.0)
	if speed < 0.995:
		_cond_label.text += "  -  %d%% speed" % roundi(speed * 100.0)
	var mechanics := s.workers_at("workshop", "mechanic")
	var on_it: Dictionary = {}
	for w in mechanics:
		if String(w["target"]) == fid and String(w["job"]) in ["repair", "service"]:
			on_it = w
	if not on_it.is_empty():
		_cond_note.text = "%s is %s." % [String(on_it["name"]), "on the way" if float(on_it["arrive_at"]) > s.state.run_time else "servicing it now"]
	elif not mechanics.is_empty():
		_cond_note.text = "Mechanics keep it in shape on their rounds."
	elif s.facility_built("workshop"):
		_cond_note.text = "Hire a mechanic at the Workshop to keep machines in shape. Repair patches it by hand."
	else:
		_cond_note.text = "Worn machines run slower. Repair patches it by hand; a Workshop's mechanics keep every machine in shape."


func _refresh_power(s: Simulation) -> void:
	var pw: Dictionary = s.rt.get("power", {})
	var supply := float(pw.get("supply", 0.0))
	var demand := float(pw.get("demand", 0.0))
	if fid == "generator":
		(_power_rows["grid"] as Label).text = _kw(float(pw.get("grid", 0.0)))
		(_power_rows["generator"] as Label).text = _kw(float(pw.get("generator", 0.0)))
		(_power_rows["demand"] as Label).text = "%s of %s" % [_kw(demand), _kw(supply)]
		_power_bar.max_value = maxf(supply, 1e-6)
		_power_bar.value = minf(demand, supply)
		var short := String(pw.get("short", ""))
		if demand > supply + 0.01 and short != "":
			_power_note.text = "Short by %s: the %s runs at %d%%. Upgrade the generator." % [_kw(demand - supply),
				String(s.content.facility(short).get("name", short)), roundi(UtilitySystem.power_factor(s, short) * 100.0)]
		else:
			_power_note.text = "Every machine has full power (%s spare). The grid's share never runs out." % _kw(supply - demand)
		return
	var kw := float(fac.get("power_kw", 0.0))
	var got := float(pw.get("draw", {}).get(fid, 0.0))
	var f := UtilitySystem.power_factor(s, fid)
	(_power_rows["rating"] as Label).text = _kw(kw)
	(_power_rows["getting"] as Label).text = _kw(got)
	(_power_rows["plant"] as Label).text = "%s / %s" % [_kw(supply), _kw(demand)]
	_power_bar.max_value = maxf(kw, 1e-6)
	_power_bar.value = got
	if f < 0.995:
		_power_note.text = "Not enough power: running at %d%%. Machines further up the line get power first. %s." % [roundi(f * 100.0), UiText.power_fix(s)]
	else:
		_power_note.text = "Fully powered."


func _refresh_crew(s: Simulation) -> void:
	for pair in _crew_rows:
		var w := s.worker_by_id(int(pair[0]))
		if not w.is_empty():
			var ls := UiKit.line_labels(pair[1] as Button)
			(ls[0] as Label).text = "%s  (Lv %d)" % [String(w["name"]), int(w["level"])]
			(ls[1] as Label).text = UiText.worker_status(s, w)
	if _crew_hire:
		if s.state.workers.size() >= Economy.worker_capacity(s):
			_crew_hire.set_text_only("Camp is full", "Upgrade the Site Office")
		else:
			var c := Economy.hire_cost(s, _crew_role)
			_crew_hire.set_cost(_crew_hire.title_label.text, c, s.state.money >= c)


## Rows (label, value) and an optional bar [value, max, variation] per facility.
func _live_data(s: Simulation, fs: Dictionary) -> Dictionary:
	var rows: Array = []
	var bar: Array = []
	match fid:
		"headframe":
			var ls: Dictionary = s.rt.get("lift", TransportSystem.lift_stats(s))
			rows = [["Lifting", Num.rate(float(ls.get("moved_rate", 0.0)))], ["Capacity", Num.rate(float(ls.get("rate", 0.0)))],
				["Mode", "Automatic" if TransportSystem.lift_automatic(s) else "Manual - tap LIFT"]]
		"silo":
			var cap := Economy.bin_capacity(s)
			var have := Simulation.inv_total(s.state.surface_bin)
			rows = [["Stored ore", "%s / %s" % [Num.short(have), Num.short(cap)]]]
			bar = [have, cap, ""]
		"warehouse":
			var cap2 := Economy.warehouse_capacity(s)
			var have2 := Simulation.inv_total(s.state.warehouse)
			rows = [["Stored goods", "%s / %s" % [Num.short(have2), Num.short(cap2)]]]
			bar = [have2, cap2, ""]
		"depot":
			var ts: Dictionary = s.rt.get("sales", SalesSystem.truck_stats(s))
			rows = [["Selling", Num.rate(float(ts.get("sold_rate", 0.0)))], ["Earning", Num.money(float(ts.get("earn_rate", 0.0))) + "/s"],
				["Mode", "Automatic" if SalesSystem.automatic(s) else "Manual - tap SELL"]]
		"pump":
			var pm: Dictionary = s.rt.get("pump", {})
			rows = [["Pumping / inflow", "%s / %s" % [Num.short(float(pm.get("capacity", 0.0))), Num.short(float(pm.get("inflow", 0.0)))]]]
		"office":
			rows = [["Workers", "%d / %d" % [s.state.workers.size(), Economy.worker_capacity(s)]],
				["Research", Num.rate(float(s.rt.get("research_rate", 0.0)), " RP/s")]]
		"conveyor":
			var pl: Dictionary = s.rt.get("plant", {})
			rows = [["Belt", "%s of %s" % [Num.rate(float(pl.get("rate", 0.0))), Num.rate(float(pl.get("capacity", 0.0)))]]]
		"generator":
			rows = [["Load", Num.percent(float(fs.get("util", 0.0)))]]
			bar = [float(fs.get("util", 0.0)), 1.0, "TealBar"]
		"workshop":
			var busy := 0
			var mech := s.workers_at("workshop", "mechanic")
			for w in mech:
				if String(w["job"]) in ["repair", "service"] and String(w["target"]) != "workshop":
					busy += 1
			rows = [["Mechanics at machines", "%d / %d" % [busy, mech.size()]], ["Machines needing work", str(WorkforceSystem.repair_queue(s).size())]]
		_:
			if fac.get("category", "") == "processing":
				var util := float(fs.get("util", 0.0))
				rows = [["Load", Num.percent(util)]]
				bar = [util, 1.0, "TealBar"]
	if rows.is_empty():
		rows = [["Status", "Running"]]
	return {"rows": rows, "bar": bar}


func _refresh_live(s: Simulation, fs: Dictionary) -> void:
	if _live_box == null:
		return
	var d := _live_data(s, fs)
	var rows: Array = d["rows"]
	var bar: Array = d["bar"]
	var sig := ""
	for r in rows:
		sig += String(r[0]) + "|"
	sig += String(bar[2]) if not bar.is_empty() else "-"
	if sig != _live_sig:
		_live_sig = sig
		UiKit.clear(_live_box)
		_live_values.clear()
		_live_bar = null
		for r in rows:
			var row := UiKit.kv(String(r[0]), "")
			_live_box.add_child(row)
			_live_values.append(row.get_child(1))
		if not bar.is_empty():
			_live_bar = UiKit.progress(0.0, 1.0, String(bar[2]), 14)
			_live_box.add_child(_live_bar)
	for i in rows.size():
		(_live_values[i] as Label).text = String(rows[i][1])
	if _live_bar and not bar.is_empty():
		_live_bar.max_value = maxf(float(bar[1]), 1e-6)
		_live_bar.value = float(bar[0])
