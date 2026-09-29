extends GamePanel
## Paused: the mine stops until you resume.

func frame_kind() -> String:
	return "popup"


func game_state() -> int:
	return State.PAUSED


func panel_id() -> String:
	return "pause"


func title() -> String:
	return "Paused"


func icon_kind() -> String:
	return "pause"


func build() -> void:
	content.add_child(UiKit.button("Resume", close, "Primary"))
	content.add_child(UiKit.button("Settings", func() -> void:
		close()
		open("settings"), "Button"))
	content.add_child(UiKit.button("Save and exit to title", func() -> void:
		close()
		if ui.main:
			ui.main.quit_to_menu(), "Chip"))
