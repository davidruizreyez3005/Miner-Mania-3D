class_name Atmosphere
extends Node3D
## Sky, sun, fog and exposure for the current region, blended toward a darker
## cave mood as the camera goes underground. Underground geometry lives on
## render layer 2 (LAYER_UNDERGROUND), which the sun does not light: galleries
## are lit by their own lamps and a per-depth fill light.

const LAYER_SURFACE := 1
const LAYER_UNDERGROUND := 2

var env := Environment.new()
var world_env := WorldEnvironment.new()
var sun := DirectionalLight3D.new()
var sky_mat := ProceduralSkyMaterial.new()
var look: Dictionary = {}
var _under := 0.0


func setup(region: Dictionary) -> void:
	look = region.get("look", {})
	name = "Atmosphere"
	var sky := Sky.new()
	sky.sky_material = sky_mat
	sky.radiance_size = Sky.RADIANCE_SIZE_64
	sky_mat.sky_top_color = Color(String(look.get("sky_top", "#3c79c4")))
	sky_mat.sky_horizon_color = Color(String(look.get("sky_horizon", "#bfd6e8")))
	sky_mat.ground_horizon_color = Color(String(look.get("sky_horizon", "#bfd6e8"))).darkened(0.25)
	sky_mat.ground_bottom_color = Color(String(look.get("terrain", "#6e6a55"))).darkened(0.5)
	sky_mat.sun_angle_max = 20.0
	sky_mat.sky_curve = 0.12
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color("8a8f98")
	env.ambient_light_energy = float(look.get("ambient_energy", 0.55))
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.tonemap_exposure = 1.0
	env.tonemap_white = 6.0
	env.fog_enabled = true
	env.fog_mode = Environment.FOG_MODE_EXPONENTIAL
	env.fog_light_color = Color(String(look.get("fog", "#afc3d0")))
	env.fog_density = 0.0016
	env.fog_sky_affect = 0.25
	env.fog_aerial_perspective = 0.35
	env.glow_enabled = true
	env.glow_intensity = 0.55
	env.glow_strength = 0.9
	env.glow_bloom = 0.04
	env.glow_hdr_threshold = 1.1
	env.adjustment_enabled = true
	env.adjustment_saturation = 1.12
	env.adjustment_contrast = 1.06
	world_env.environment = env
	add_child(world_env)
	sun.name = "Sun"
	sun.light_color = Color(String(look.get("sun", "#fff1dc")))
	sun.light_energy = float(look.get("sun_energy", 1.35))
	sun.rotation_degrees = Vector3(float(look.get("sun_pitch", -48.0)), float(look.get("sun_yaw", -30.0)), 0.0)
	sun.shadow_enabled = true
	sun.shadow_bias = 0.04
	sun.shadow_normal_bias = 1.2
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_ORTHOGONAL
	sun.directional_shadow_max_distance = 90.0
	sun.light_cull_mask = LAYER_SURFACE
	# Only surface geometry lies in the sun's light: the galleries under the
	# camp stay out of its shadow map too.
	sun.shadow_caster_mask = LAYER_SURFACE
	sun.sky_mode = DirectionalLight3D.SKY_MODE_LIGHT_AND_SKY
	add_child(sun)
	apply_quality(GraphicsQuality.current())


## Graphics preset: sun shadows (and their reach) and glow; the cheap
## shading of Low also drops the fog's aerial perspective and sky
## reflections (each a cube-map read for every pixel).
func apply_quality(q: int) -> void:
	var p := GraphicsQuality.preset(q)
	var lite := bool(p.get("lite_shaders", false))
	sun.shadow_enabled = bool(p.get("shadows", true))
	sun.directional_shadow_max_distance = float(p.get("shadow_distance", 90.0))
	env.glow_enabled = bool(p.get("glow", true))
	env.fog_aerial_perspective = 0.0 if lite else 0.35
	env.reflected_light_source = Environment.REFLECTION_SOURCE_DISABLED if lite else Environment.REFLECTION_SOURCE_SKY
	env.sdfgi_enabled = false
	env.ssao_enabled = false


## underground: 0 at the surface, 1 inside the mine (camera below the cut edge).
func set_underground(u: float, depth_def: Dictionary) -> void:
	_under = clampf(u, 0.0, 1.0)
	var e: Dictionary = depth_def.get("environment", {})
	var cave_fog := Color(String(e.get("fog", "#1e1c1c")))
	var surf_fog := Color(String(look.get("fog", "#afc3d0")))
	env.fog_light_color = surf_fog.lerp(cave_fog, _under * 0.85)
	env.fog_density = lerpf(0.0016, float(e.get("fog_density", 0.015)) * 0.35, _under)
	env.ambient_light_color = Color("8a8f98").lerp(Color(String(e.get("ambient", "#5a5048"))), _under)
	env.ambient_light_energy = lerpf(float(look.get("ambient_energy", 0.55)), float(e.get("ambient_energy", 0.5)), _under)
	env.tonemap_exposure = lerpf(1.0, 1.25, _under)
