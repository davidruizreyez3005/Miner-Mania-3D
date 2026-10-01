extends Node
## Player settings (user://settings.cfg), separate from the save game so a
## corrupted save never loses them. Applies audio bus volumes, frame rate and
## graphics quality immediately. The graphics quality starts as an automatic
## choice for the device (GraphicsQuality.detect) - picked again whenever the
## presets change (GRAPHICS_REV) - until the player picks one; while it is
## automatic the frame-rate watchdog may lower it.

const PATH := "user://settings.cfg"
const GRAPHICS_REV := 2
const DEFAULTS := {
	"master_volume": 0.9, "music_volume": 0.6, "sfx_volume": 0.85, "ambience_volume": 0.7, "ui_volume": 0.8,
	"haptics": true, "quality": 1, "quality_auto": true, "graphics_rev": 0, "fps_limit": 60, "show_fps": false,
	"camera_sensitivity": 1.0, "notifications": true, "telemetry_log": false, "tutorial_enabled": true, "reduce_motion": false,
}
enum Quality { LOW, MEDIUM, HIGH }

var values: Dictionary = DEFAULTS.duplicate()
var detected: Dictionary = {}          # {"quality", "reason"} of the last automatic choice


func _ready() -> void:
	load_settings()
	if int(values["graphics_rev"]) < GRAPHICS_REV:
		choose_graphics_for_device()
	apply_all()


func get_value(key: String, default: Variant = null) -> Variant:
	return values.get(key, DEFAULTS.get(key, default))


func set_value(key: String, value: Variant, persist: bool = true) -> void:
	if not DEFAULTS.has(key):
		push_warning("Settings: unknown key " + key)
		return
	values[key] = value
	_apply(key)
	EventBus.settings_changed.emit(key, value)
	if persist:
		save_settings()


## The player picks a quality: it sticks (no automatic changes) and brings
## the preset's frame cap.
func choose_quality(q: int) -> void:
	values["quality_auto"] = false
	values["fps_limit"] = int(GraphicsQuality.value(q, "fps", 60))
	_apply("fps_limit")
	EventBus.settings_changed.emit("fps_limit", values["fps_limit"])
	set_value("quality", q)


## Automatic choice for this device (first launch, new presets).
func choose_graphics_for_device() -> void:
	detected = GraphicsQuality.detect_here()
	var q := int(detected["quality"])
	values["quality"] = q
	values["quality_auto"] = true
	values["graphics_rev"] = GRAPHICS_REV
	values["fps_limit"] = int(GraphicsQuality.value(q, "fps", 60))
	print("[graphics] %s for this device (%s)" % [String(GraphicsQuality.value(q, "name", "?")), String(detected["reason"])])
	save_settings()


## The watchdog found the frame rate too low: one level down.
func lower_quality() -> bool:
	var q := int(values["quality"])
	if q <= GraphicsQuality.LOW:
		return false
	values["fps_limit"] = mini(int(values["fps_limit"]), int(GraphicsQuality.value(q - 1, "fps", 60)))
	_apply("fps_limit")
	set_value("quality", q - 1)
	print("[graphics] lowered to %s (frame rate)" % String(GraphicsQuality.value(q - 1, "name", "?")))
	return true


func load_settings() -> void:
	var cf := ConfigFile.new()
	if cf.load(PATH) != OK:
		return
	for key in DEFAULTS:
		var v = cf.get_value("settings", key, DEFAULTS[key])
		if typeof(v) == typeof(DEFAULTS[key]) or (DEFAULTS[key] is float and v is int):
			values[key] = v


func save_settings() -> void:
	var cf := ConfigFile.new()
	for key in values:
		cf.set_value("settings", key, values[key])
	cf.save(PATH)


func apply_all() -> void:
	for key in values:
		_apply(key)


func _apply(key: String) -> void:
	match key:
		"master_volume", "music_volume", "sfx_volume", "ambience_volume", "ui_volume":
			var buses := {"master_volume": "Master", "music_volume": "Music", "sfx_volume": "SFX",
				"ambience_volume": "Ambience", "ui_volume": "UI"}
			var bus: String = buses[key]
			var idx := AudioServer.get_bus_index(bus)
			if idx >= 0:
				var v := clampf(float(values[key]), 0.0, 1.0)
				AudioServer.set_bus_volume_db(idx, linear_to_db(maxf(v, 0.0001)))
				AudioServer.set_bus_mute(idx, v <= 0.001)
		"fps_limit":
			Engine.max_fps = int(values[key])
		"quality":
			var q := int(values[key])
			WorldMaterials.set_lite(bool(GraphicsQuality.value(q, "lite_shaders", false)))
			MaterialLite.set_lite(bool(GraphicsQuality.value(q, "lite_materials", false)))
			VfxLibrary.set_amount_scale(float(GraphicsQuality.value(q, "vfx", 1.0)))
			if is_inside_tree():
				GraphicsQuality.apply_viewport(get_tree().root, q)
			EventBus.quality_changed.emit(q)
