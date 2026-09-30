class_name TouchScroll
extends ScrollContainer
## A vertical list that scrolls with the finger wherever the drag starts.
## Godot scrolls a ScrollContainer by touch only when the drag reaches it,
## and every button, card, bar and icon in a list would stop it first - so
## those let pointer events through (MOUSE_FILTER_PASS). Taps still press
## buttons: a drag past the dead zone cancels the press (the container sends
## NOTIFICATION_SCROLL_BEGIN) and scrolls instead, with a glide on release.
## Sliders and scroll bars keep their own drags. Rows added later (live
## lists) are handled as they enter the tree.

const DEADZONE := 16


func _init() -> void:
	horizontal_scroll_mode = SCROLL_MODE_DISABLED
	scroll_deadzone = DEADZONE


func _notification(what: int) -> void:
	match what:
		NOTIFICATION_ENTER_TREE:
			if not get_tree().node_added.is_connected(_on_node_added):
				get_tree().node_added.connect(_on_node_added)
			for c in find_children("*", "Control", true, false):
				let_through(c as Control)
		NOTIFICATION_EXIT_TREE:
			if get_tree().node_added.is_connected(_on_node_added):
				get_tree().node_added.disconnect(_on_node_added)


func _on_node_added(n: Node) -> void:
	if n is Control and is_ancestor_of(n):
		let_through(n as Control)


static func let_through(c: Control) -> void:
	if c.mouse_filter == Control.MOUSE_FILTER_STOP and not (c is Slider or c is ScrollBar or c is LineEdit or c is TextEdit):
		c.mouse_filter = Control.MOUSE_FILTER_PASS
