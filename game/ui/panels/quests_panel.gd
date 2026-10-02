extends GamePanel
## Goals: the current quests with progress and rewards (claim when done,
## "Show me" jumps to where it happens), the delivery contract, and the
## achievements with their permanent bonuses.

var _tabs: TabBar
var _body: VBoxContainer
var _tab := 0
var _bars: Array = []                 # [ProgressBar, Label, objective]


func frame_kind() -> String:
	return "full"


func game_state() -> int:
	return State.QUEST


func panel_id() -> String:
	return "quests"


func title() -> String:
	return "Goals"


func icon_kind() -> String:
	return "quest"


func signature() -> String:
	var s := sim()
	var n := 0
	for q in s.state.quests:
		n += {"active": 1, "done": 100, "claimed": 10000}.get(s.state.quests[q], 0)
	return "%d|%d|%d|%s" % [_tab, n, s.state.achievements.size(), s.state.contract.get("item", "")]


func build() -> void:
	var want := String(args.get("tab", ""))
	if want != "":
		_tab = {"goals": 0, "contract": 1, "achievements": 2}.get(want, 0)
		args.erase("tab")
	_tabs = TabBar.new()
	for t in ["Goals", "Contract", "Achievements"]:
		_tabs.add_tab(t)
	_tabs.current_tab = _tab
	_tabs.tab_changed.connect(func(i: int) -> void:
		_tab = i
		_sig = ""
		rebuild())
	_tabs.focus_mode = Control.FOCUS_NONE
	content.add_child(_tabs)
	_body = UiKit.vbox(UiTheme.GAP)
	content.add_child(_body)
	_bars.clear()
	match _tab:
		0:
			_build_quests()
		1:
			_build_contract()
		2:
			_build_achievements()


func _build_quests() -> void:
	var s := sim()
	var shown := 0
	for q in s.content.quests:
		var qid := String(q["id"])
		var st := String(s.state.quests.get(qid, ""))
		if st != "active" and st != "done":
			continue
		shown += 1
		var v := UiKit.vbox(UiTheme.GAP_IN)
		var t := UiKit.label(String(q.get("title", qid)), "Small")
		t.add_theme_font_override("font", UiTheme.bold_font())
		v.add_child(t)
		v.add_child(UiKit.wrap(String(q.get("description", ""))))
		var o: Dictionary = q.get("objective", {})
		var bar := UiKit.progress(0, 1, "GreenBar", 16)
		var pl := UiKit.label("", "Caption")
		v.add_child(bar)
		v.add_child(pl)
		_bars.append([bar, pl, o])
		var row := UiKit.hbox(UiTheme.GAP_ROW)
		var rl := UiKit.label("Reward: " + UiText.reward(s, q.get("reward", {})), "Caption")
		rl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		rl.add_theme_color_override("font_color", UiTheme.MONEY)
		row.add_child(rl)
		if st == "done":
			row.add_child(UiKit.button("Claim", func() -> void: cmd({"type": "claim_quest", "quest": qid}), "Primary", 80))
		elif String(q.get("hint", "")) != "":
			var hint := String(q["hint"])
			row.add_child(UiKit.button("Show me", func() -> void: _show(hint), "Chip", 72))
		v.add_child(row)
		_body.add_child(UiKit.card(v, "CardHi" if st == "done" else "Card"))
	if shown == 0:
		_body.add_child(UiKit.wrap("All caught up! New goals appear as the mine grows.", "Small"))


func _show(hint: String) -> void:
	close()
	var rig: CameraRig = ui.main.camera_rig() if ui.main else null
	if hint.begins_with("depth:") or hint.begins_with("facility:"):
		if rig:
			rig.focus_target(hint)
	elif hint.begins_with("button:"):
		ui.tutorial.point_at("hud:" + hint.substr(7), 3.0)
	elif hint.begins_with("panel:"):
		open(hint.substr(6))


func _build_contract() -> void:
	var s := sim()
	var c := s.state.contract
	if not ProgressionSystem.contracts_unlocked(s):
		_body.add_child(UiKit.wrap("Delivery contracts open up once you hire a sales manager.", "Small"))
		return
	if not c.has("item"):
		var nxt := float(c.get("next_at", 0.0)) - s.state.run_time
		_body.add_child(UiKit.wrap("No contract right now. The next offer arrives in %s." % Num.duration(maxf(nxt, 0.0)), "Small"))
		return
	var it := s.content.item(String(c["item"]))
	var v := UiKit.vbox(UiTheme.GAP_IN)
	v.add_child(UiKit.label("Deliver %s" % String(it.get("name", c["item"])), "Heading"))
	var bar := UiKit.progress(float(c.get("progress", 0.0)), float(c.get("target", 1.0)), "GreenBar", 20)
	v.add_child(bar)
	v.add_child(UiKit.kv("Delivered", "%s / %s" % [Num.short(float(c.get("progress", 0.0))), Num.short(float(c.get("target", 1.0)))]))
	v.add_child(UiKit.kv("Time left", Num.duration(float(c.get("deadline", 0.0)) - s.state.run_time)))
	v.add_child(UiKit.kv("Bonus", Num.money(float(c.get("reward", 0.0))), "Money"))
	_body.add_child(UiKit.card(v))


func _build_achievements() -> void:
	var s := sim()
	var got := 0
	for a in s.content.achievements:
		if s.state.achievements.has(String(a["id"])):
			got += 1
	_body.add_child(UiKit.label("%d / %d unlocked" % [got, s.content.achievements.size()], "Accent"))
	for a in s.content.achievements:
		var aid := String(a["id"])
		var have := s.state.achievements.has(aid)
		var h := UiKit.hbox(UiTheme.GAP_ROW)
		h.add_child(Icon.make("trophy" if have else "lock", 44, UiTheme.DIM, UiTheme.GOLD if have else UiTheme.DIM))
		var v := UiKit.vbox(2)
		v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var n := UiKit.label(String(a.get("name", aid)), "Small")
		n.add_theme_font_override("font", UiTheme.bold_font())
		v.add_child(n)
		v.add_child(UiKit.wrap(String(a.get("description", ""))))
		var rw := UiText.reward(s, a.get("reward", {}))
		if rw != "":
			var rl := UiKit.label(rw, "Caption")
			rl.add_theme_color_override("font_color", UiTheme.TEAL)
			v.add_child(rl)
		if not have:
			var o: Dictionary = a.get("objective", {})
			var bar := UiKit.progress(0, 1, "", 10)
			var pl := UiKit.label("", "Caption")
			v.add_child(bar)
			v.add_child(pl)
			_bars.append([bar, pl, o])
		h.add_child(v)
		_body.add_child(UiKit.card(h, "CardHi" if have else "Card"))


func refresh() -> void:
	var s := sim()
	for b in _bars:
		var p := ProgressionSystem.objective_progress(s, b[2])
		var bar: ProgressBar = b[0]
		bar.max_value = maxf(float(p[1]), 1e-9)
		bar.value = minf(float(p[0]), float(p[1]))
		(b[1] as Label).text = "%s / %s" % [Num.short(minf(float(p[0]), float(p[1]))), Num.short(float(p[1]))]
