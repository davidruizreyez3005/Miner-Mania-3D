class_name GraphicsQuality
extends RefCounted
## Graphics presets (data/performance.json "graphics"): Low for entry-level
## phones, Medium, High. Picks one for the device on first launch and applies
## the viewport side (3D resolution, MSAA, anisotropic filtering, mesh LOD
## detail, shadow atlas); the world reads the rest (lights, materials,
## scenery, crew animation detail, effects) through value().

const LOW := 0
const MEDIUM := 1
const HIGH := 2

static var _data: Dictionary = {}


static func data() -> Dictionary:
	if _data.is_empty():
		var d = JsonUtil.load_file("res://data/performance.json")
		_data = d.get("graphics", {}) if d is Dictionary else {}
	return _data


static func presets() -> Array:
	return data().get("presets", [])


static func preset(q: int) -> Dictionary:
	var p := presets()
	return p[clampi(q, 0, p.size() - 1)] if not p.is_empty() else {}


static func value(q: int, key: String, default: Variant = null) -> Variant:
	return preset(q).get(key, default)


## The preset of the current settings.
static func current() -> int:
	return clampi(int(Settings.get_value("quality", MEDIUM)), LOW, HIGH)


static func current_value(key: String, default: Variant = null) -> Variant:
	return value(current(), key, default)


## The preset for a device: {"quality", "reason"}. Phones on the OpenGL ES
## fallback, with little memory or an entry-level GPU get Low; a flagship
## GPU with plenty of memory gets High; other phones Medium; desktops High.
static func detect(gpu: String, ram_bytes: int, rendering_method: String, mobile: bool) -> Dictionary:
	var det: Dictionary = data().get("detect", {})
	if not mobile:
		return {"quality": HIGH, "reason": "desktop"}
	if rendering_method == "gl_compatibility":
		return {"quality": LOW, "reason": "OpenGL ES renderer"}
	var gb := float(ram_bytes) / 1073741824.0
	if ram_bytes > 0 and gb < float(det.get("low_ram_gb", 4.5)):
		return {"quality": LOW, "reason": "%.1f GB memory" % gb}
	for pat in det.get("low_gpu", []):
		if _matches(String(pat), gpu):
			return {"quality": LOW, "reason": gpu}
	if ram_bytes > 0 and gb >= float(det.get("high_ram_gb", 7.5)):
		for pat in det.get("high_gpu", []):
			if _matches(String(pat), gpu):
				return {"quality": HIGH, "reason": gpu}
	return {"quality": MEDIUM, "reason": gpu}


## detect() for the device the game runs on.
static func detect_here() -> Dictionary:
	var mem := OS.get_memory_info()
	return detect(RenderingServer.get_video_adapter_name(), int(mem.get("physical", 0)),
		RenderingServer.get_current_rendering_method(), OS.has_feature("mobile"))


static func _matches(pattern: String, text: String) -> bool:
	var re := RegEx.new()
	return re.compile(pattern) == OK and re.search(text) != null


## The viewport side of preset `q`: 3D resolution (the UI keeps full
## resolution), MSAA, anisotropic filtering, mesh LOD detail and the sun's
## shadow atlas.
static func apply_viewport(vp: Viewport, q: int) -> void:
	var p := preset(q)
	vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR
	vp.scaling_3d_scale = clampf(float(p.get("render_scale", 1.0)), 0.25, 1.0)
	vp.msaa_3d = [Viewport.MSAA_DISABLED, Viewport.MSAA_2X, Viewport.MSAA_4X][clampi(int(p.get("msaa", 0)), 0, 2)]
	vp.anisotropic_filtering_level = clampi(int(p.get("anisotropy", 2)), 0, 4) as Viewport.AnisotropicFiltering
	vp.mesh_lod_threshold = float(p.get("mesh_lod_threshold", 1.0))
	RenderingServer.directional_shadow_atlas_set_size(int(p.get("shadow_atlas", 2048)), true)
