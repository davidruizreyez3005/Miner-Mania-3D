class_name WorldMaterials
extends RefCounted
## Materials for procedural world geometry (terrain, rock, structures), built
## from the generated tiling texture sets (tools/textures/texgen.py) and the
## per-region / per-depth colours in the data files. Cached per key.

const TEX := "res://assets/generated/textures/%s_%s.png"
const ROCK_SHADER := preload("res://game/world/shaders/rock.gdshader")
const TERRAIN_SHADER := preload("res://game/world/shaders/terrain.gdshader")

static var _cache: Dictionary = {}
static var _tex: Dictionary = {}


static func tex(set_name: String, kind: String) -> Texture2D:
	var key := set_name + "/" + kind
	if not _tex.has(key):
		var path := TEX % [set_name, kind]
		_tex[key] = load(path) as Texture2D if ResourceLoader.exists(path) else null
	return _tex[key]


static func rock(depth_def: Dictionary) -> ShaderMaterial:
	var key := "rock:%s" % depth_def.get("id", "surface")
	if _cache.has(key):
		return _cache[key]
	var env: Dictionary = depth_def.get("environment", {})
	var m := ShaderMaterial.new()
	m.shader = ROCK_SHADER
	var base := "concrete" if env.get("wall_material", "") == "concrete" else "rock"
	m.set_shader_parameter("rock_albedo", tex(base, "albedo"))
	m.set_shader_parameter("rock_normal", tex(base, "normal"))
	m.set_shader_parameter("rock_orm", tex(base, "orm"))
	m.set_shader_parameter("strata_albedo", tex("strata", "albedo"))
	m.set_shader_parameter("strata_normal", tex("strata", "normal"))
	m.set_shader_parameter("rock_tint", _tint(String(env.get("rock_tint", "#8a8078")), 2.1))
	m.set_shader_parameter("strata_tint", _tint(String(env.get("strata_tint", "#6e6052")), 2.3))
	var glow := String(env.get("crystal_glow", ""))
	if glow != "":
		m.set_shader_parameter("glow_color", Color(glow))
		m.set_shader_parameter("glow_strength", 2.2)
	_cache[key] = m
	return m


## Cut-face material for the solid mountain above/around the galleries: a
## neutral strata material (per-depth tints are applied on gallery interiors).
static func face() -> ShaderMaterial:
	if _cache.has("face"):
		return _cache["face"]
	var m := ShaderMaterial.new()
	m.shader = ROCK_SHADER
	m.set_shader_parameter("rock_albedo", tex("rock", "albedo"))
	m.set_shader_parameter("rock_normal", tex("rock", "normal"))
	m.set_shader_parameter("rock_orm", tex("rock", "orm"))
	m.set_shader_parameter("strata_albedo", tex("strata", "albedo"))
	m.set_shader_parameter("strata_normal", tex("strata", "normal"))
	m.set_shader_parameter("rock_tint", Color(1.05, 1.0, 0.95))
	m.set_shader_parameter("strata_tint", Color(1.08, 1.0, 0.92))
	m.set_shader_parameter("strata_amount", 1.0)
	_cache["face"] = m
	return m


static func terrain(region: Dictionary) -> ShaderMaterial:
	var key := "terrain:%s" % region.get("id", "")
	if _cache.has(key):
		return _cache[key]
	var look: Dictionary = region.get("look", {})
	var m := ShaderMaterial.new()
	m.shader = TERRAIN_SHADER
	for s in ["grass", "dirt", "gravel", "rock"]:
		m.set_shader_parameter(s + "_albedo", tex(s, "albedo"))
		m.set_shader_parameter(s + "_normal", tex(s, "normal"))
	m.set_shader_parameter("snow_albedo", tex("snow", "albedo"))
	m.set_shader_parameter("grass_tint", _tint(String(look.get("terrain_detail", "#6f7a4a")), 1.5))
	m.set_shader_parameter("rock_tint", _tint(String(look.get("cliff", "#8c7a64")), 1.6))
	m.set_shader_parameter("dirt_tint", _tint(String(look.get("terrain", "#7a6a55")), 1.5))
	m.set_shader_parameter("snow_amount", 0.85 if region.get("id", "") == "frostpeak_glacier" else 0.0)
	_cache[key] = m
	return m


static func structure(kind: String) -> StandardMaterial3D:
	var key := "struct:" + kind
	if _cache.has(key):
		return _cache[key]
	var m := StandardMaterial3D.new()
	m.albedo_texture = tex(kind, "albedo")
	m.normal_enabled = true
	m.normal_texture = tex(kind, "normal")
	m.roughness_texture = tex(kind, "orm")
	m.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GREEN
	m.uv1_triplanar = true
	m.uv1_world_triplanar = true
	m.uv1_scale = Vector3.ONE * 0.5
	m.metallic = 0.3 if kind == "steel" else 0.0
	_cache[key] = m
	return m


## Colours in the data are "average surface colour"; textures already carry
## tone, so tints are relative (scaled so a mid-grey texture reproduces them).
static func _tint(hex: String, gain: float) -> Color:
	var c := Color(hex)
	return Color(minf(c.r * gain, 2.0), minf(c.g * gain, 2.0), minf(c.b * gain, 2.0))
