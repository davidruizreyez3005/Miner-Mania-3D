extends Node
## Player settings (user://settings.cfg), separate from the save game so a
## corrupted save never loses them. Applies audio bus volumes, frame rate and
## graphics quality immediately.

const PATH := "user://settings.cfg"
const DEFAULTS := {
	"master_volume": 0.9, "music_volume": 0.6, "sfx_volume": 0.85, "ambience_volume": 0.7, "ui_volume": 0.8,
	"haptics": true, "quality": 1, "fps_limit": 60, "show_fps": false, "camera_sensitivity": 1.0,
	"notifications": true, "telemetry_log": false, "tutorial_enabled": true, "reduce_motion": false,
}
enum Quality { LOW, MEDIUM, HIGH }

var values: Dictionary = DEFAULTS.duplicate()


func _ready() -> void:
	load_settings()
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
			EventBus.quality_changed.emit(int(values[key]))
