class_name CostButton
extends Button
## A buy button with a title and a price line that panels update in place
## (never rebuilt while a finger may be on it). Greyed out with a red price
## when unaffordable.

var title_label: Label
var price_label: Label
var variation := "Primary"
var unit := "$"
var _cb: Callable


static func make(title: String, cb: Callable, v: String = "Primary", u: String = "$") -> CostButton:
	var b := CostButton.new()
	b.variation = v
	b.unit = u
	b._cb = cb
	b.theme_type_variation = v
	b.custom_minimum_size = Vector2(0, 92)
	b.focus_mode = Control.FOCUS_NONE
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 0)
	box.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	box.alignment = BoxContainer.ALIGNMENT_CENTER
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.title_label = UiKit.label(title, "", HORIZONTAL_ALIGNMENT_CENTER)
	b.title_label.add_theme_font_override("font", UiTheme.bold_font())
	b.title_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.price_label = UiKit.label("", "Small", HORIZONTAL_ALIGNMENT_CENTER)
	b.price_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_child(b.title_label)
	box.add_child(b.price_label)
	b.add_child(box)
	b.pressed.connect(func() -> void:
		Audio.ui("ui_tap")
		if b._cb.is_valid():
			b._cb.call())
	return b


func set_cost(title: String, cost: float, affordable: bool) -> void:
	title_label.text = title
	price_label.text = (unit + Num.short(cost)) if unit == "$" else (Num.short(cost) + " " + unit)
	disabled = not affordable
	var dark := variation in ["Primary", "Teal"]
	title_label.add_theme_color_override("font_color", Color("241a06") if dark and affordable else UiTheme.TEXT)
	price_label.add_theme_color_override("font_color",
		(Color("3a2a08") if dark else UiTheme.TEXT) if affordable else UiTheme.RED)


func set_text_only(title: String, note: String = "") -> void:
	title_label.text = title
	price_label.text = note
	disabled = true
	title_label.add_theme_color_override("font_color", UiTheme.TEXT)
	price_label.add_theme_color_override("font_color", UiTheme.DIM)
