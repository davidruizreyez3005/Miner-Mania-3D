class_name UiTheme
extends RefCounted
## The game's look for all UI, built in code: a warm "mine office" palette
## (dark slate panels, brass accents), rounded touch-sized controls, and
## type variations (Title, Heading, Caption, Money...). Sizes assume the
## 720 px wide base viewport (canvas_items stretch scales for the device).

const BG := Color("161a20")
const PANEL := Color("1f252d")
const CARD := Color("2a313b")
const CARD_HI := Color("343d49")
const LINE := Color("3d4653")
const TEXT := Color("f4efe4")
const DIM := Color("a8a293")
const GOLD := Color("f5b93a")
const GOLD_DARK := Color("b9821d")
const TEAL := Color("3cc6b5")
const RED := Color("e5534b")
const GREEN := Color("62c35f")
const MONEY := Color("ffd45c")
const RP := Color("8fd3ff")
const LP := Color("d7a6ff")
const RARITY := {"common": Color("c8c2b4"), "uncommon": Color("7fd46a"), "rare": Color("5aa8ff"), "very_rare": Color("c178ff"),
	"exotic": Color("ff8a3c")}

const FONT_SIZE := 26

## One spacing scale for every panel (px at the 720 px base width): between
## the blocks of a panel, inside a card, between the buttons of a row. A
## card's padding equals GAP, so space reads the same inside and between.
const GAP := 16
const GAP_IN := 10
const GAP_ROW := 10
## The scroll bar's lane on the right of a scrolling panel (bar + gap). The
## frames take it out of their right margin, so content keeps equal margins
## left and right whether or not the bar shows.
const SCROLL_BAR := 8
const GUTTER := 16

static var _theme: Theme
static var _bold: FontVariation


static func bold_font() -> Font:
	if _bold == null:
		_bold = FontVariation.new()
		_bold.base_font = ThemeDB.fallback_font
		_bold.variation_embolden = 0.75
	return _bold


static func box(c: Color, radius: int = 18, margin: int = 16, border: Color = Color(0, 0, 0, 0), bw: int = 0) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = c
	s.set_corner_radius_all(radius)
	s.set_content_margin_all(margin)
	if bw > 0:
		s.border_color = border
		s.set_border_width_all(bw)
	s.anti_aliasing = true
	return s


static func get_theme() -> Theme:
	if _theme != null:
		return _theme
	var t := Theme.new()
	t.default_font_size = FONT_SIZE
	# Labels.
	t.set_color("font_color", "Label", TEXT)
	t.set_color("font_outline_color", "Label", Color(0, 0, 0, 0.6))
	for v in [["Title", 44, true, TEXT], ["Heading", 32, true, TEXT], ["Caption", 21, false, DIM], ["Small", 22, false, TEXT],
			["Money", 34, true, MONEY], ["Big", 56, true, GOLD], ["Accent", 26, true, GOLD]]:
		t.add_type(v[0])
		t.set_type_variation(v[0], "Label")
		t.set_font_size("font_size", v[0], v[1])
		t.set_color("font_color", v[0], v[3])
		if v[2]:
			t.set_font("font", v[0], bold_font())
	# Panels.
	t.set_stylebox("panel", "Panel", box(PANEL, 26, 18))
	t.set_stylebox("panel", "PanelContainer", box(PANEL, 26, 18))
	t.add_type("Card")
	t.set_type_variation("Card", "PanelContainer")
	t.set_stylebox("panel", "Card", box(CARD, 20, GAP))
	t.add_type("CardHi")
	t.set_type_variation("CardHi", "PanelContainer")
	t.set_stylebox("panel", "CardHi", box(CARD_HI, 20, GAP, GOLD, 3))
	t.add_type("Bar")
	t.set_type_variation("Bar", "PanelContainer")
	t.set_stylebox("panel", "Bar", box(Color(0.07, 0.08, 0.1, 0.82), 22, 10))
	t.add_type("Sheet")
	t.set_type_variation("Sheet", "PanelContainer")
	var sheet := box(Color(PANEL, 0.97), 30, 20)
	sheet.content_margin_right = 20 - GUTTER
	sheet.corner_radius_bottom_left = 0
	sheet.corner_radius_bottom_right = 0
	sheet.shadow_color = Color(0, 0, 0, 0.45)
	sheet.shadow_size = 18
	t.set_stylebox("panel", "Sheet", sheet)
	# Buttons.
	_button(t, "Button", Color("3a4350"), TEXT)
	_button(t, "Primary", GOLD, Color("241a06"))
	_button(t, "Teal", TEAL, Color("06221f"))
	_button(t, "Danger", RED, Color("2a0806"))
	_button(t, "Flat", Color(0, 0, 0, 0), TEXT)
	_button(t, "Chip", Color("2b323c"), TEXT, 30, 10)
	t.set_stylebox("pressed", "Chip", box(CARD_HI, 30, 10, GOLD, 3))
	t.set_stylebox("hover_pressed", "Chip", box(CARD_HI, 30, 10, GOLD, 3))
	t.set_font("font", "Primary", bold_font())
	t.set_font("font", "Teal", bold_font())
	t.set_font("font", "Danger", bold_font())
	# Progress bars.
	t.set_stylebox("background", "ProgressBar", box(Color("10141a"), 10, 0))
	t.set_stylebox("fill", "ProgressBar", box(GOLD, 10, 0))
	t.set_font_size("font_size", "ProgressBar", 18)
	t.set_color("font_color", "ProgressBar", TEXT)
	t.add_type("TealBar")
	t.set_type_variation("TealBar", "ProgressBar")
	t.set_stylebox("fill", "TealBar", box(TEAL, 10, 0))
	t.add_type("GreenBar")
	t.set_type_variation("GreenBar", "ProgressBar")
	t.set_stylebox("fill", "GreenBar", box(GREEN, 10, 0))
	# Sliders / checks.
	t.set_stylebox("slider", "HSlider", box(Color("10141a"), 8, 6))
	t.set_stylebox("grabber_area", "HSlider", box(GOLD, 8, 6))
	t.set_stylebox("grabber_area_highlight", "HSlider", box(GOLD, 8, 6))
	t.set_icon("grabber", "HSlider", _dot(34, GOLD))
	t.set_icon("grabber_highlight", "HSlider", _dot(38, Color("ffd26a")))
	t.set_color("font_color", "CheckButton", TEXT)
	# Scroll bars: slim, in their own lane (GUTTER) beside the content.
	var lane := box(Color(0, 0, 0, 0.0), 4, 2)
	lane.content_margin_left = SCROLL_BAR * 0.5
	lane.content_margin_right = SCROLL_BAR * 0.5
	t.set_stylebox("scroll", "VScrollBar", lane)
	# (h = the horizontal space between the content and the vertical bar)
	t.set_constant("scrollbar_h_separation", "ScrollContainer", GUTTER - SCROLL_BAR)
	t.set_stylebox("grabber", "VScrollBar", box(Color(1, 1, 1, 0.18), 4, 2))
	t.set_stylebox("grabber_highlight", "VScrollBar", box(Color(1, 1, 1, 0.3), 4, 2))
	t.set_stylebox("grabber_pressed", "VScrollBar", box(Color(1, 1, 1, 0.3), 4, 2))
	# Tabs.
	t.set_stylebox("tab_selected", "TabBar", box(GOLD, 16, 14))
	t.set_stylebox("tab_unselected", "TabBar", box(CARD, 16, 14))
	t.set_stylebox("tab_hovered", "TabBar", box(CARD_HI, 16, 14))
	t.set_color("font_selected_color", "TabBar", Color("241a06"))
	t.set_color("font_unselected_color", "TabBar", TEXT)
	t.set_font_size("font_size", "TabBar", 24)
	t.set_constant("h_separation", "TabBar", 8)
	# Tooltips.
	t.set_stylebox("panel", "TooltipPanel", box(Color("0f1216"), 12, 12))
	_theme = t
	return t


static func _button(t: Theme, type_name: String, c: Color, fc: Color, radius: int = 18, margin: int = 14) -> void:
	if type_name != "Button":
		t.add_type(type_name)
		t.set_type_variation(type_name, "Button")
	var normal := box(c, radius, margin)
	var hover := box(c.lightened(0.08) if c.a > 0.0 else Color(1, 1, 1, 0.06), radius, margin)
	var pressed := box(c.darkened(0.18) if c.a > 0.0 else Color(1, 1, 1, 0.12), radius, margin)
	var disabled := box(Color(c.darkened(0.45), 0.7) if c.a > 0.0 else Color(0, 0, 0, 0), radius, margin)
	t.set_stylebox("normal", type_name, normal)
	t.set_stylebox("hover", type_name, hover)
	t.set_stylebox("pressed", type_name, pressed)
	t.set_stylebox("disabled", type_name, disabled)
	t.set_stylebox("focus", type_name, StyleBoxEmpty.new())
	t.set_color("font_color", type_name, fc)
	t.set_color("font_hover_color", type_name, fc)
	t.set_color("font_pressed_color", type_name, fc)
	t.set_color("font_focus_color", type_name, fc)
	t.set_color("font_disabled_color", type_name, Color(fc, 0.45) if c.a > 0.0 else Color(TEXT, 0.35))
	t.set_color("icon_normal_color", type_name, fc)


static func _dot(size: int, c: Color) -> ImageTexture:
	var img := Image.create(size, size, false, Image.FORMAT_RGBA8)
	var r := float(size) * 0.5
	for y in size:
		for x in size:
			var d := Vector2(x + 0.5 - r, y + 0.5 - r).length()
			img.set_pixel(x, y, Color(c, clampf(r - d, 0.0, 1.0)))
	return ImageTexture.create_from_image(img)
