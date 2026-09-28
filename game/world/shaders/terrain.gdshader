// Valley terrain: four tiling layers (grass, dirt, gravel, rock) blended by
// vertex colour weights (r = grass, g = dirt/road, b = gravel pads, a =
// rock), rock forced on steep slopes, large-scale tint variation to hide
// tiling, and a region tint (red canyon, frost, basalt) plus optional snow.
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley;

uniform sampler2D grass_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D grass_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D dirt_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D dirt_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D gravel_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D gravel_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rock_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rock_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D snow_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec3 grass_tint : source_color = vec3(1.0);
uniform vec3 rock_tint : source_color = vec3(1.0);
uniform vec3 dirt_tint : source_color = vec3(1.0);
uniform float snow_amount = 0.0;
uniform float snow_height = 30.0;
uniform float tex_scale = 0.16;
uniform float macro_scale = 0.012;

varying vec3 w_pos;
varying vec3 w_nrm;

void vertex() {
	w_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	w_nrm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

vec3 unpack_n(vec3 c) {
	return c * 2.0 - 1.0;
}

void fragment() {
	vec2 uv = w_pos.xz * tex_scale;
	vec4 w = COLOR;
	float slope = 1.0 - clamp(w_nrm.y, 0.0, 1.0);
	float steep = smoothstep(0.35, 0.6, slope);
	w.a = max(w.a, steep);
	w.rgb *= (1.0 - steep);
	float sum = w.r + w.g + w.b + w.a + 1e-4;
	w /= sum;
	// Rock on slopes uses a side projection to avoid stretching.
	vec3 bl = pow(abs(w_nrm), vec3(4.0));
	bl /= (bl.x + bl.y + bl.z + 1e-5);
	vec3 rock_c = (texture(rock_albedo, w_pos.zy * tex_scale).rgb * bl.x + texture(rock_albedo, uv).rgb * bl.y
		+ texture(rock_albedo, w_pos.xy * tex_scale).rgb * bl.z) * rock_tint;
	vec3 col = texture(grass_albedo, uv).rgb * grass_tint * w.r
		+ texture(dirt_albedo, uv).rgb * dirt_tint * w.g
		+ texture(gravel_albedo, uv * 1.4).rgb * w.b
		+ rock_c * w.a;
	vec3 n = unpack_n(texture(grass_normal, uv).rgb) * w.r
		+ unpack_n(texture(dirt_normal, uv).rgb) * w.g
		+ unpack_n(texture(gravel_normal, uv * 1.4).rgb) * w.b
		+ unpack_n(texture(rock_normal, uv).rgb) * w.a;
	// Macro variation (breaks up tiling at a distance).
	float macro = texture(grass_albedo, w_pos.xz * macro_scale).g;
	col *= mix(0.82, 1.12, macro);
	if (snow_amount > 0.0) {
		float s = clamp(snow_amount * (0.55 + 0.45 * smoothstep(snow_height - 10.0, snow_height + 10.0, w_pos.y)) * (1.0 - steep * 0.7), 0.0, 1.0);
		col = mix(col, texture(snow_albedo, uv).rgb, s);
	}
	ALBEDO = col;
	ROUGHNESS = mix(0.95, 0.8, w.b);
	vec3 tn = normalize(vec3(n.xy, max(n.z, 0.2)));
	// Tangent frame for a y-up surface: x -> tangent, -z -> binormal.
	vec3 wn = normalize(vec3(tn.x, 0.0, -tn.y) + w_nrm * tn.z);
	NORMAL = normalize((VIEW_MATRIX * vec4(wn, 0.0)).xyz);
}
