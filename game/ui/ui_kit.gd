class_name UiKit
extends RefCounted
## Small constructors for consistent UI pieces (labels, buttons, cards,
## rows, progress bars, cost buttons) so panels read as one system.


static func label(text: String, variation: String = "", align: HorizontalAlignment = HORIZONTAL_ALIGNMENT_LEFT) -> Label:
	var l := Label.new()
	l.text = text
	if variation != "":
		l.theme_type_variation = variation
	l.horizontal_alignment = align
	l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	return l


static func wrap(text: String, variation: String = "Caption") -> Label:
	var l := label(text, variation)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	l.custom_minimum_size.x = 120
	return l


static func button(text: String, cb: Callable, variation: String = "", min_h: float = 84.0) -> Button:
	var b := Button.new()
	b.text = text
	if variation != "":
		b.theme_type_variation = variation
	b.custom_minimum_size = Vector2(0, min_h)
	b.focus_mode = Control.FOCUS_NONE
	if cb.is_valid():
		b.pressed.connect(func() -> void:
			Audio.ui("ui_tap")
			cb.call())
	return b


## A square button showing one vector icon (and an optional badge label).
static func icon_button(kind: String, cb: Callable, size: float = 92.0, variation: String = "Button", tint: Color = UiTheme.TEXT) -> Button:
	var b := button("", cb, variation, size)
	b.custom_minimum_size = Vector2(size, size)
	var ic := Icon.make(kind, size * 0.56, tint)
	ic.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	b.add_child(ic)
	return b


static func hbox(sep: int = 12) -> HBoxContainer:
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", sep)
	return h


static func vbox(sep: int = 12) -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", sep)
	return v


static func card(content: Control, variation: String = "Card") -> PanelContainer:
	var p := PanelContainer.new()
	p.theme_type_variation = variation
	p.add_child(content)
	return p


static func spacer(expand: bool = true, w: float = 0.0) -> Control:
	var c := Control.new()
	c.custom_minimum_size = Vector2(w, 0)
	if expand:
		c.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return c


static func progress(value: float, max_value: float, variation: String = "", h: float = 22.0) -> ProgressBar:
	var p := ProgressBar.new()
	p.max_value = maxf(max_value, 1e-9)
	p.value = clampf(value, 0.0, p.max_value)
	p.show_percentage = false
	p.custom_minimum_size = Vector2(0, h)
	p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if variation != "":
		p.theme_type_variation = variation
	return p


static func separator() -> HSeparator:
	var s := HSeparator.new()
	s.add_theme_constant_override("separation", 8)
	var sb := StyleBoxLine.new()
	sb.color = UiTheme.LINE
	sb.thickness = 2
	s.add_theme_stylebox_override("separator", sb)
	return s


## Icon + value row, e.g. the money readout.
static func stat_row(icon: String, text: String, variation: String = "", icon_tint: Color = UiTheme.TEXT) -> HBoxContainer:
	var h := hbox(8)
	h.add_child(Icon.make(icon, 34, icon_tint))
	h.add_child(label(text, variation))
	return h


## A key/value line for stat tables.
static func kv(key: String, value: String, value_variation: String = "") -> HBoxContainer:
	var h := hbox(8)
	var k := label(key, "Caption")
	k.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(k)
	h.add_child(label(value, value_variation))
	return h


## Buy button with a price line; greyed out and red-priced when unaffordable.
static func cost_button(title: String, cost: float, affordable: bool, cb: Callable, variation: String = "Primary", unit: String = "$") -> Button:
	var b := button("", cb, variation, 92.0)
	b.disabled = not affordable
	var v := vbox(0)
	v.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var t := label(title, "", HORIZONTAL_ALIGNMENT_CENTER)
	t.add_theme_color_override("font_color", Color("241a06") if variation == "Primary" and affordable else UiTheme.TEXT)
	t.add_theme_font_override("font", UiTheme.bold_font())
	t.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var price := (unit + Num.short(cost)) if unit == "$" else (Num.short(cost) + " " + unit)
	var c := label(price, "Small", HORIZONTAL_ALIGNMENT_CENTER)
	c.add_theme_color_override("font_color", Color("3a2a08") if affordable and variation == "Primary" else (UiTheme.RED if not affordable else UiTheme.TEXT))
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(t)
	v.add_child(c)
	b.add_child(v)
	return b


static func clear(n: Node) -> void:
	for c in n.get_children():
		n.remove_child(c)
		c.queue_free()


## A short pop animation for newly shown controls.
static func pop_in(c: Control, delay: float = 0.0) -> void:
	if bool(Settings.get_value("reduce_motion", false)):
		return
	c.pivot_offset = c.size * 0.5
	c.scale = Vector2(0.92, 0.92)
	c.modulate.a = 0.0
	var tw := c.create_tween()
	tw.set_parallel(true)
	tw.tween_property(c, "scale", Vector2.ONE, 0.22).set_delay(delay).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	tw.tween_property(c, "modulate:a", 1.0, 0.18).set_delay(delay)
