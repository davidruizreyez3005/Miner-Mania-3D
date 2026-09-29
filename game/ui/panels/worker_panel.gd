extends GamePanel
## One worker: who they are, what they are doing right now, experience and
## energy, and where they are posted (reassign or dismiss).

var wid := -1
var _status: Label
var _xp: ProgressBar
var _xp_label: Label
var _energy: ProgressBar


func panel_id() -> String:
	return "worker"


func title() -> String:
	wid = int(args.get("worker", -1))
	var w := Session.sim.worker_by_id(wid) if Session.sim else {}
	return String(w.get("name", "Worker"))


func icon_kind() -> String:
	var w := Session.sim.worker_by_id(int(args.get("worker", -1))) if Session.sim else {}
	return String(UiText.ROLE_ICONS.get(String(w.get("role", "")), "worker"))


func signature() -> String:
	var w := sim().worker_by_id(wid)
	return "%s|%s" % [w.get("post", "gone"), w.get("level", 0)]


func build() -> void:
	var s := sim()
	wid = int(args.get("worker", -1))
	var w := s.worker_by_id(wid)
	if w.is_empty():
		content.add_child(UiKit.label("This worker has left the claim.", "Small"))
		return
	var role: Dictionary = s.content.role_by_id.get(String(w["role"]), {})
	EventBus.selection_changed.emit("worker:%d" % wid)
	var v := UiKit.vbox(6)
	v.add_child(UiKit.kv("Role", String(role.get("name", w["role"])), "Accent"))
	v.add_child(UiKit.kv("Posted at", UiText.post(s, String(w["post"]))))
	_status = UiKit.wrap("", "Small")
	v.add_child(_status)
	_xp_label = UiKit.label("", "Caption")
	v.add_child(_xp_label)
	_xp = UiKit.progress(0, 1, "", 12)
	v.add_child(_xp)
	v.add_child(UiKit.label("Energy", "Caption"))
	_energy = UiKit.progress(1, 1, "GreenBar", 12)
	v.add_child(_energy)
	content.add_child(UiKit.card(v))
	var row := UiKit.hbox(10)
	var follow := UiKit.button("Follow", func() -> void:
		if ui.main:
			ui.main.camera_rig().focus_target("worker:%d" % wid)
		close(), "Teal")
	follow.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(follow)
	var fire := UiKit.button("Dismiss", func() -> void:
		ui.open_panel("confirm", {"text": "Dismiss %s? Hiring again costs money." % String(w["name"]),
			"yes": "Dismiss", "action": func() -> void:
				Session.command({"type": "fire", "worker": wid})
				close()}), "Danger")
	fire.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(fire)
	content.add_child(row)
	section("Move to")
	var posts := _posts(s, String(w["role"]))
	for p in posts:
		if p == String(w["post"]):
			continue
		var free := SimCommands.post_free(s, String(w["role"]), p, wid)
		var b := UiKit.button("%s  (%d free)" % [UiText.post(s, p), maxi(free, 0)], func() -> void:
			cmd({"type": "reassign", "worker": wid, "post": p}), "Chip", 70)
		b.disabled = free <= 0
		content.add_child(b)


static func _posts(s: Simulation, role: String) -> Array:
	var out := []
	var r: Dictionary = s.content.role_by_id.get(role, {})
	for kind in r.get("posts", []):
		if kind == "depth":
			for dep in s.state.depths:
				if dep["unlocked"]:
					out.append("depth:%d" % int(dep["index"]))
		elif kind == "plant":
			out.append("plant")
		elif s.content.facility_by_id.has(kind) and s.facility_built(String(kind)):
			out.append(String(kind))
	return out


func refresh() -> void:
	var s := sim()
	var w := s.worker_by_id(wid)
	if w.is_empty() or _status == null:
		return
	_status.text = UiText.worker_status(s, w)
	var need := float(s.content.workers_cfg.get("xp_per_level_s", 600)) * float(w["level"])
	_xp_label.text = "Level %d  -  %d%% efficiency" % [int(w["level"]), roundi(WorkforceSystem.efficiency(s, w) * 100.0)]
	_xp.max_value = maxf(need, 1.0)
	_xp.value = float(w.get("xp", 0.0))
	_energy.value = float(w.get("energy", 1.0))


func _exit_tree() -> void:
	EventBus.selection_changed.emit("")
