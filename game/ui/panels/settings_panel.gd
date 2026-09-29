extends GamePanel
## Sound levels, haptics, graphics quality and frame rate, gameplay helpers,
## and the (confirmed) progress reset. Settings live apart from the save.

func frame_kind() -> String:
	return "full"


func game_state() -> int:
	return State.SETTINGS


func panel_id() -> String:
	return "settings"


func title() -> String:
	return "Settings"


func icon_kind() -> String:
	return "gear"


func build() -> void:
	section("Sound")
	for k in [["master_volume", "Master"], ["music_volume", "Music"], ["sfx_volume", "Effects"], ["ambience_volume", "Ambience"], ["ui_volume", "Interface"]]:
		content.add_child(_slider(String(k[0]), String(k[1])))
	section("Feel")
	content.add_child(_toggle("haptics", "Vibration"))
	content.add_child(_toggle("reduce_motion", "Reduce motion"))
	content.add_child(_slider("camera_sensitivity", "Camera speed", 0.5, 2.0))
	content.add_child(_toggle("tutorial_enabled", "Show tips"))
	section("Graphics")
	var q := UiKit.hbox(8)
	for i in 3:
		var b := UiKit.button(["Low", "Medium", "High"][i], func() -> void:
			Settings.set_value("quality", i)
			rebuild(), "Primary" if int(Settings.get_value("quality", 1)) == i else "Chip", 80)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		q.add_child(b)
	content.add_child(q)
	var f := UiKit.hbox(8)
	for fps in [30, 60]:
		var b2 := UiKit.button("%d FPS" % fps, func() -> void:
			Settings.set_value("fps_limit", fps)
			rebuild(), "Primary" if int(Settings.get_value("fps_limit", 60)) == fps else "Chip", 80)
		b2.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		f.add_child(b2)
	content.add_child(f)
	content.add_child(_toggle("show_fps", "Show frame rate"))
	section("Game")
	content.add_child(UiKit.wrap("Progress saves automatically every 30 seconds and when you leave the app. Everything stays on this device."))
	content.add_child(UiKit.button("Reset all progress", func() -> void:
		ui.open_panel("confirm", {"text": "Erase your mine, legacy and achievements for good? This cannot be undone.", "yes": "Erase",
			"action": func() -> void:
				if ui.main:
					ui.main.reset_progress()}), "Danger"))
	section("About")
	content.add_child(UiKit.wrap("Miner Mania 3D  v%s\nMade with Godot Engine. Every model, texture and sound in this game is generated procedurally." % String(ProjectSettings.get_setting("application/config/version", "1.0.0"))))


func _slider(key: String, text: String, lo: float = 0.0, hi: float = 1.0) -> Control:
	var h := UiKit.hbox(12)
	var l := UiKit.label(text, "Small")
	l.custom_minimum_size.x = 170
	h.add_child(l)
	var sl := HSlider.new()
	sl.min_value = lo
	sl.max_value = hi
	sl.step = 0.05
	sl.value = float(Settings.get_value(key, 0.8))
	sl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	sl.custom_minimum_size = Vector2(0, 64)
	sl.focus_mode = Control.FOCUS_NONE
	sl.value_changed.connect(func(v: float) -> void: Settings.set_value(key, v, false))
	sl.drag_ended.connect(func(_c: bool) -> void:
		Settings.save_settings()
		Audio.ui("ui_tap"))
	h.add_child(sl)
	return h


func _toggle(key: String, text: String) -> Control:
	var c := CheckButton.new()
	c.text = text
	c.button_pressed = bool(Settings.get_value(key, true))
	c.custom_minimum_size = Vector2(0, 72)
	c.focus_mode = Control.FOCUS_NONE
	c.toggled.connect(func(on: bool) -> void: Settings.set_value(key, on))
	return c
