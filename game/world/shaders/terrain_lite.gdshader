// Low-quality valley terrain (entry-level phones): the same four layers
// blended by vertex colour weights, but a layer is only sampled where it
// shows, from one top-down projection, with no normal maps, macro variation
// or specular - usually one or two texture reads. Same uniforms as
// terrain.gdshader so a material can switch between the two.
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_lambert, specular_disabled, vertex_lighting;

uniform sampler2D grass_albedo : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D dirt_albedo : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D gravel_albedo : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D rock_albedo : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D snow_albedo : source_color, filter_linear_mipmap, repeat_enable;
uniform vec3 grass_tint : source_color = vec3(1.0);
uniform vec3 rock_tint : source_color = vec3(1.0);
uniform vec3 dirt_tint : source_color = vec3(1.0);
uniform float snow_amount = 0.0;
uniform float snow_height = 30.0;
uniform float tex_scale = 0.16;

varying vec3 w_pos;
varying vec3 w_nrm;

void vertex() {
	w_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	w_nrm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

void fragment() {
	vec2 uv = w_pos.xz * tex_scale;
	vec4 w = COLOR;
	float steep = smoothstep(0.35, 0.6, 1.0 - clamp(w_nrm.y, 0.0, 1.0));
	w.a = max(w.a, steep);
	w.rgb *= (1.0 - steep);
	w /= (w.r + w.g + w.b + w.a + 1e-4);
	vec3 col = vec3(0.0);
	if (w.r > 0.02) {
		col += texture(grass_albedo, uv).rgb * grass_tint * w.r;
	}
	if (w.g > 0.02) {
		col += texture(dirt_albedo, uv).rgb * dirt_tint * w.g;
	}
	if (w.b > 0.02) {
		col += texture(gravel_albedo, uv * 1.4).rgb * w.b;
	}
	if (w.a > 0.02) {
		// Steep slopes read the rock from the side they face.
		vec2 ruv = abs(w_nrm.x) > abs(w_nrm.z) ? w_pos.zy : w_pos.xy;
		col += texture(rock_albedo, (w.a > 0.5 ? ruv : w_pos.xz) * tex_scale).rgb * rock_tint * w.a;
	}
	if (snow_amount > 0.0) {
		float s = clamp(snow_amount * (0.55 + 0.45 * smoothstep(snow_height - 10.0, snow_height + 10.0, w_pos.y)) * (1.0 - steep * 0.7), 0.0, 1.0);
		col = mix(col, texture(snow_albedo, uv).rgb, s);
	}
	ALBEDO = col;
	ROUGHNESS = 0.95;
}
