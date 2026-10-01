extends GamePanel
## One depth. Locked: what lies down there, its hazards, and the cost to dig
## it. Open: live output and station fill, equipment upgrades (mining,
## haulage, shaft station), tooling tiers, the crew posted here (hire
## miners, haulers, a geologist, a supervisor) and the veins with their
## regrowth timers.

const EQUIP := ["mining", "haulage", "station"]
const ROLES := ["miner", "hauler", "geologist", "supervisor"]

var d := 1
var _eq: Dictionary = {}          # kind -> {"level": Label, "stat": Label, "buttons": Array}
var _prod_label: Label
var _station_bar: ProgressBar
var _station_label: Label
var _hazard_label: Label
var _tool_button: CostButton
var _tool_label: Label
var _hire: Dictionary = {}        # role -> {"label": Label, "button": CostButton}
var _veins: VBoxContainer
var _veins_sig := ""
var _vein_rows: Array = []
var _unlock_button: CostButton


func panel_id() -> String:
	return "depth"


func title() -> String:
	d = int(args.get("depth", 1))
	return "%d  %s" % [d, String(Session.content.depth(d).get("name", "Depth"))]


func icon_kind() -> String:
	return "down_level"


func signature() -> String:
	var s := sim()
	var dep := s.state.depth(d)
	if dep.is_empty():
		return "none"
	var crew := 0
	for w in s.state.workers:
		if String(w["post"]) == "depth:%d" % d:
			crew += 1
	return "%s|%d|%d|%d" % [dep["unlocked"], crew, int(dep["tool_tier"]), s.state.techs.size()]


func build() -> void:
	var s := sim()
	d = int(args.get("depth", 1))
	var dd := s.content.depth(d)
	var dep := s.state.depth(d)
	_eq.clear()
	_hire.clear()
	content.add_child(UiKit.wrap(String(dd.get("story", ""))))
	if dep.is_empty() or not dep["unlocked"]:
		_build_locked(s, dd)
		return
	var pv := UiKit.vbox(6)
	_prod_label = UiKit.label("", "Accent")
	pv.add_child(_prod_label)
	_station_label = UiKit.label("", "Small")
	pv.add_child(_station_label)
	_station_bar = UiKit.progress(0, 1, "", 16)
	pv.add_child(_station_bar)
	_hazard_label = UiKit.wrap("", "Caption")
	pv.add_child(_hazard_label)
	content.add_child(UiKit.card(pv))
	section("Equipment")
	for kind in EQUIP:
		var eq: Dictionary = s.content.equipment.get(kind, {})
		var v := UiKit.vbox(6)
		var h := UiKit.hbox(8)
		var n := UiKit.label(String(eq.get("name", kind.capitalize())), "Small")
		n.add_theme_font_override("font", UiTheme.bold_font())
		n.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		h.add_child(n)
		var lv := UiKit.label("", "Accent")
		h.add_child(lv)
		v.add_child(h)
		var st := UiKit.wrap("", "Caption")
		v.add_child(st)
		var row := UiKit.hbox(8)
		var bs := [
			CostButton.make("+1", func() -> void: cmd({"type": "upgrade_equipment", "depth": d, "equipment": kind, "count": 1})),
			CostButton.make("+10", func() -> void: cmd({"type": "upgrade_equipment", "depth": d, "equipment": kind, "count": 10})),
			CostButton.make("MAX", func() -> void: cmd({"type": "upgrade_equipment", "depth": d, "equipment": kind, "count": maxi(1, Economy.equipment_affordable(sim(), d, kind))}), "Teal"),
		]
		for b in bs:
			row.add_child(b)
		v.add_child(row)
		content.add_child(UiKit.card(v))
		_eq[kind] = {"level": lv, "stat": st, "buttons": bs}
		if kind == "mining":
			anchor("depth_upgrade", bs[0])
	var tv := UiKit.vbox(6)
	_tool_label = UiKit.wrap("", "Small")
	tv.add_child(_tool_label)
	_tool_button = CostButton.make("Upgrade tools", func() -> void: cmd({"type": "buy_tool", "depth": d}))
	tv.add_child(_tool_button)
	content.add_child(UiKit.card(tv))
	section("Crew")
	for role in ROLES:
		if not SimCommands.role_unlocked(s, role):
			continue
		var r: Dictionary = s.content.role_by_id.get(role, {})
		var v2 := UiKit.vbox(6)
		var h2 := UiKit.hbox(8)
		h2.add_child(Icon.make(String(UiText.ROLE_ICONS.get(role, "worker")), 38, UiTheme.TEXT, UiTheme.GOLD))
		var l := UiKit.label("", "Small")
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		h2.add_child(l)
		v2.add_child(h2)
		v2.add_child(UiKit.wrap(String(r.get("description", "")), "Caption"))
		var hb := CostButton.make("Hire %s" % String(r.get("name", role)), func() -> void: cmd({"type": "hire", "role": role, "post": "depth:%d" % d}))
		v2.add_child(hb)
		for w in s.workers_at("depth:%d" % d, role):
			var wid := int(w["id"])
			v2.add_child(UiKit.button("%s  (Lv %d)" % [String(w["name"]), int(w["level"])], func() -> void: open("worker", {"worker": wid}), "Chip", 60))
		content.add_child(UiKit.card(v2))
		_hire[role] = {"label": l, "button": hb, "name": String(r.get("plural", role))}
		anchor("depth_hire_%s" % role, hb)
	section("Veins")
	_veins = UiKit.vbox(8)
	_veins_sig = ""
	content.add_child(_veins)


func _build_locked(s: Simulation, dd: Dictionary) -> void:
	var why := SimCommands.depth_unlockable(s, d)
	var v := UiKit.vbox(6)
	var res: Array = []
	for rid in dd.get("resources", {}):
		var r: Dictionary = s.content.resource_by_id.get(String(rid), {})
		var known := s.state.discoveries.has(String(rid)) or String(r.get("rarity", "common")) == "common"
		res.append(String(r.get("name", rid)) if known else "???")
	v.add_child(UiKit.kv("Deposits", ", ".join(PackedStringArray(res)) if not res.is_empty() else "-"))
	var hz: Array = dd.get("hazards", [])
	var hn := []
	for h in hz:
		hn.append(String(s.content.hazards.get(String(h), {}).get("name", String(h).capitalize())))
	v.add_child(UiKit.kv("Hazards", ", ".join(PackedStringArray(hn)) if not hn.is_empty() else "None"))
	for h in hz:
		v.add_child(UiKit.wrap(String(s.content.hazards.get(String(h), {}).get("description", ""))))
	content.add_child(UiKit.card(v))
	if why == "" :
		_unlock_button = CostButton.make("Dig to %s" % String(dd.get("name", "")), func() -> void:
			var r2 := cmd({"type": "unlock_depth", "depth": d})
			if r2.get("ok", false):
				close()
				if ui.main:
					ui.main.camera_rig().focus_target("depth:%d" % d))
		content.add_child(_unlock_button)
	else:
		content.add_child(UiKit.wrap(String(UiRoot.ERRORS.get(why, why.capitalize())), "Small"))


func refresh() -> void:
	var s := sim()
	var dep := s.state.depth(d)
	if dep.is_empty():
		return
	if not dep["unlocked"]:
		if _unlock_button:
			var c := Economy.depth_unlock_cost(s, d)
			_unlock_button.set_cost(_unlock_button.title_label.text, c, s.state.money >= c)
		return
	var rt: Dictionary = s.rt.get("depth", {}).get(d, {})
	_prod_label.text = "Mining %s" % Num.rate(float(rt.get("units_rate", 0.0)))
	var cap := Economy.station_capacity(s, d)
	var have := Simulation.inv_total(dep["station"])
	_station_label.text = "Shaft station %s / %s%s" % [Num.short(have), Num.short(cap), "  -  FULL, call the lift" if have >= cap - 0.01 else ""]
	_station_bar.max_value = maxf(cap, 1e-6)
	_station_bar.value = have
	var active: Array = s.rt.get("hazard_active", {}).get(d, [])
	var factor := float(s.rt.get("hazard", {}).get(d, 1.0))
	var hz_txt := []
	for k in active:
		var hd: Dictionary = s.content.hazards.get(String(k), {})
		var mit: Dictionary = hd.get("mitigation", {})
		var fix := "more pump capacity" if mit.has("facility_capacity") else "research %s" % String(s.content.tech_by_id.get(String(mit.get("tech", "")), {}).get("name", ""))
		hz_txt.append("%s (%s)" % [String(hd.get("name", k)), fix])
	_hazard_label.text = ("Work slowed to %d%% by %s" % [roundi(factor * 100.0), ", ".join(PackedStringArray(hz_txt))]) if not hz_txt.is_empty() else ""
	_hazard_label.visible = not hz_txt.is_empty()
	for kind in _eq:
		var e: Dictionary = _eq[kind]
		var eq: Dictionary = s.content.equipment.get(kind, {})
		var lvl := int(dep["levels"].get(kind, 1))
		var mx := int(eq.get("max_level", 1))
		(e["level"] as Label).text = "Lv %d" % lvl
		var parts := []
		for st in eq.get("stats", {}):
			var now := s.content.equipment_stat(kind, String(st), lvl)
			var nxt := s.content.equipment_stat(kind, String(st), mini(lvl + 1, mx))
			var t := "%s %s" % [UiText.stat_name(String(st)), UiText.stat_value(String(st), now)]
			if nxt != now:
				t += " > " + UiText.stat_value(String(st), nxt)
			parts.append(t)
		(e["stat"] as Label).text = "  |  ".join(PackedStringArray(parts))
		var bs: Array = e["buttons"]
		if lvl >= mx:
			for b in bs:
				(b as CostButton).set_text_only("Max level")
			continue
		var afford := Economy.equipment_affordable(s, d, kind)
		for i in 2:
			var n: int = [1, 10][i]
			var c2 := Economy.equipment_cost(s, d, kind, mini(n, mx - lvl))
			(bs[i] as CostButton).set_cost("+%d" % mini(n, mx - lvl), c2, s.state.money >= c2)
		var m := maxi(1, afford)
		(bs[2] as CostButton).set_cost("MAX +%d" % m, Economy.equipment_cost(s, d, kind, m), afford >= 1)
		var gates: Dictionary = eq.get("requires_tech_above_level", {})
		for gk in gates:
			if lvl >= int(gk) and not s.state.techs.has(gates[gk]):
				var tn := String(s.content.tech_by_id.get(String(gates[gk]), {}).get("name", gates[gk]))
				for b in bs:
					(b as CostButton).set_text_only("Locked", "Research %s" % tn)
	var tier := int(dep["tool_tier"])
	var cur := s.content.tool_tier(tier)
	var nxt_t := s.content.tool_tier(tier + 1)
	_tool_label.text = "Tools: %s (x%s)" % [String(cur.get("name", "")), Num.short(float(cur.get("mult", 1.0)))]
	if nxt_t.is_empty():
		_tool_button.set_text_only("Best tools", "")
	elif not s.mods.is_unlocked("tool:%d" % (tier + 1)):
		var tn2 := String(s.content.tech_by_id.get(String(nxt_t.get("requires_tech", "")), {}).get("name", "research"))
		_tool_button.set_text_only(String(nxt_t.get("name", "")), "Research %s" % tn2)
	else:
		var tc := Economy.tool_cost(s, d, tier + 1)
		_tool_button.set_cost("%s  x%s" % [String(nxt_t.get("name", "")), Num.short(float(nxt_t.get("mult", 1.0)))], tc, s.state.money >= tc)
	for role in _hire:
		var h: Dictionary = _hire[role]
		var have_n := s.workers_at("depth:%d" % d, String(role)).size()
		var slots := Economy.post_capacity(s, "depth:%d" % d, String(role))
		(h["label"] as Label).text = "%s  %d / %d" % [String(h["name"]), have_n, slots]
		var hb: CostButton = h["button"]
		if have_n >= slots:
			hb.set_text_only("All slots filled", "Upgrade to add slots")
		elif s.state.workers.size() >= Economy.worker_capacity(s):
			hb.set_text_only("Camp is full", "Upgrade the Site Office")
		else:
			var hc := Economy.hire_cost(s, String(role))
			hb.set_cost(hb.title_label.text if hb.title_label.text.begins_with("Hire") else "Hire", hc, s.state.money >= hc)
	_refresh_veins(s, dep)


## Vein rows are rebuilt only when the veins change (resource or state);
## otherwise their bars and timers update in place (a rebuild every refresh
## re-lays out text, which a small phone feels).
func _refresh_veins(s: Simulation, dep: Dictionary) -> void:
	var sig := ""
	for n in dep["nodes"]:
		sig += "%s:%s|" % [n["resource"], float(n["respawn_at"]) >= 0.0]
	if sig != _veins_sig:
		_veins_sig = sig
		_vein_rows.clear()
		UiKit.clear(_veins)
		for n in dep["nodes"]:
			var r: Dictionary = s.content.resource_by_id.get(String(n["resource"]), {})
			var h := UiKit.hbox(10)
			h.add_child(Icon.make("gem", 38, UiTheme.TEXT, Color(String(r.get("color", "#cccccc")))))
			var v := UiKit.vbox(2)
			v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			var rar := String(r.get("rarity", "common"))
			var nl := UiKit.label("%s  -  %s" % [String(r.get("name", n["resource"])), String(UiText.RARITY_NAMES.get(rar, rar))], "Small")
			nl.add_theme_color_override("font_color", UiTheme.RARITY.get(rar, UiTheme.TEXT))
			v.add_child(nl)
			var timer: Label = null
			var bar: ProgressBar = null
			if float(n["respawn_at"]) >= 0.0:
				timer = UiKit.label("", "Caption")
				v.add_child(timer)
			else:
				bar = UiKit.progress(0.0, float(n["max_hp"]), "GreenBar", 12)
				v.add_child(bar)
			h.add_child(v)
			var price := UiKit.label("", "Caption")
			h.add_child(price)
			_veins.add_child(h)
			_vein_rows.append({"timer": timer, "bar": bar, "price": price})
	for i in mini(_vein_rows.size(), dep["nodes"].size()):
		var n: Dictionary = dep["nodes"][i]
		var row: Dictionary = _vein_rows[i]
		if row["timer"] != null:
			(row["timer"] as Label).text = "Regrowing  %s" % Num.duration(float(n["respawn_at"]) - s.state.run_time)
		if row["bar"] != null:
			(row["bar"] as ProgressBar).max_value = maxf(float(n["max_hp"]), 1e-6)
			(row["bar"] as ProgressBar).value = float(n["hp"])
		(row["price"] as Label).text = Num.money(Economy.item_price(s, String(n["resource"])))
