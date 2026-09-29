extends GamePanel
## A yes/no question before something that cannot be undone.

func frame_kind() -> String:
	return "popup"


## A confirmation belongs to whatever asked the question; it is not a
## game state of its own.
func game_state() -> int:
	return -1


func panel_id() -> String:
	return "confirm"


func title() -> String:
	return "Are you sure?"


func icon_kind() -> String:
	return "warning"


func build() -> void:
	content.add_child(UiKit.wrap(String(args.get("text", "")), "Small"))
	var h := UiKit.hbox(12)
	var no := UiKit.button(String(args.get("no", "Cancel")), close, "Chip")
	no.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(no)
	var yes := UiKit.button(String(args.get("yes", "Yes")), func() -> void:
		var a: Callable = args.get("action", Callable())
		close()
		if a.is_valid():
			a.call(), "Danger")
	yes.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(yes)
	content.add_child(h)
