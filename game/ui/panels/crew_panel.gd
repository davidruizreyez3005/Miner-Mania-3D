extends GamePanel
## The whole workforce: camp capacity, hiring for every unlocked role (pick
## where they go), and everyone on the payroll grouped by post.

var _cap_label: Label
var _hire: Dictionary = {}           # role -> CostButton
var _post_pick: Dictionary = {}      # role -> OptionButton


func frame_kind() -> String:
	return "full"


func panel_id() -> String:
	return "crew"


func title() -> String:
	return "Crew"


func icon_kind() -> String:
	return "people"


func signature() -> String:
	var s := sim()
	return "%d|%d|%d|%d" % [s.state.workers.size(), s.state.deepest_unlocked(), s.state.techs.size(), s.state.quests.size()]


func build() -> void:
	var s := sim()
	_hire.clear()
	_post_pick.clear()
	_cap_label = UiKit.label("", "Accent")
	content.add_child(_cap_label)
	content.add_child(UiKit.wrap("Workers need beds at the Site Office. Each hire of a role costs more than the last."))
	section("Hire")
	for r in s.content.roles:
		var role := String(r["id"])
		var v := UiKit.vbox(6)
		var h := UiKit.hbox(10)
		h.add_child(Icon.make(String(UiText.ROLE_ICONS.get(role, "worker")), 44, UiTheme.TEXT, UiTheme.GOLD))
		var nv := UiKit.vbox(0)
		nv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var nl := UiKit.label(String(r.get("name", role)), "Small")
		nl.add_theme_font_override("font", UiTheme.bold_font())
		nv.add_child(nl)
		nv.add_child(UiKit.wrap(String(r.get("description", "")), "Caption"))
		h.add_child(nv)
		v.add_child(h)
		if not SimCommands.role_unlocked(s, role):
			v.add_child(UiKit.label(_unlock_hint(s, r), "Caption"))
			content.add_child(UiKit.card(v))
			continue
		var posts := preload("res://game/ui/panels/worker_panel.gd")._posts(s, role)
		if posts.is_empty():
			v.add_child(UiKit.label("No place to post one yet.", "Caption"))
			content.add_child(UiKit.card(v))
			continue
		var row := UiKit.hbox(10)
		var ob := OptionButton.new()
		ob.custom_minimum_size = Vector2(0, 84)
		ob.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		ob.focus_mode = Control.FOCUS_NONE
		for p in posts:
			ob.add_item(UiText.post(s, p))
			ob.set_item_metadata(ob.item_count - 1, p)
		row.add_child(ob)
		var b := CostButton.make("Hire", func() -> void:
			var sel := ob.get_selected_id()
			var post := String(ob.get_item_metadata(ob.get_item_index(sel))) if sel >= 0 else String(posts[0])
			cmd({"type": "hire", "role": role, "post": post}))
		row.add_child(b)
		v.add_child(row)
		content.add_child(UiKit.card(v))
		_hire[role] = b
		_post_pick[role] = ob
	section("On the payroll")
	var by_post := {}
	for w in s.state.workers:
		(by_post.get_or_add(String(w["post"]), []) as Array).append(w)
	var keys := by_post.keys()
	keys.sort()
	if keys.is_empty():
		content.add_child(UiKit.label("Nobody yet - hire your first miner!", "Caption"))
	for p in keys:
		content.add_child(UiKit.label(UiText.post(s, String(p)), "Accent"))
		for w in by_post[p]:
			var wid := int(w["id"])
			var role_name := String(s.content.role_by_id.get(String(w["role"]), {}).get("name", w["role"]))
			content.add_child(UiKit.button("%s  -  %s  Lv %d" % [String(w["name"]), role_name, int(w["level"])],
				func() -> void: open("worker", {"worker": wid}), "Chip", 66))


func _unlock_hint(s: Simulation, r: Dictionary) -> String:
	var un: Dictionary = r.get("unlock", {})
	if un.has("quest"):
		return "Unlocks with the goal \"%s\"" % String(s.content.quest_by_id.get(String(un["quest"]), {}).get("title", un["quest"]))
	if un.has("tech"):
		return "Unlocks with research: %s" % String(s.content.tech_by_id.get(String(un["tech"]), {}).get("name", un["tech"]))
	if un.has("facility"):
		return "Build the %s first" % String(s.content.facility(String(un["facility"])).get("name", un["facility"]))
	return "Locked"


func refresh() -> void:
	var s := sim()
	_cap_label.text = "Workers %d / %d" % [s.state.workers.size(), Economy.worker_capacity(s)]
	for role in _hire:
		var b: CostButton = _hire[role]
		var ob: OptionButton = _post_pick[role]
		var post := String(ob.get_item_metadata(maxi(0, ob.selected))) if ob.item_count > 0 else ""
		if s.state.workers.size() >= Economy.worker_capacity(s):
			b.set_text_only("Camp full", "Upgrade office")
		elif post != "" and SimCommands.post_free(s, String(role), post) <= 0:
			b.set_text_only("No slot", "Upgrade post")
		else:
			var c := Economy.hire_cost(s, String(role))
			b.set_cost("Hire", c, s.state.money >= c)
