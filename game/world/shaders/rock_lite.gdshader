// Low-quality rock (entry-level phones): the rock_albedo tiling texture on
// the surface's dominant world axis, strata on the cutaway face (+Z) - one or
// two texture reads, no normal/ORM maps, no specular. Vertex colour carries
// baked ambient occlusion (rgb) and wetness (a); crystal veins keep glowing.
// Same uniforms as rock.gdshader so a material can switch between the two.
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_lambert, specular_disabled, vertex_lighting;

uniform sampler2D rock_albedo : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D strata_albedo : source_color, filter_linear_mipmap, repeat_enable;
uniform vec3 rock_tint : source_color = vec3(1.0);
uniform vec3 strata_tint : source_color = vec3(1.0);
uniform float tex_scale = 0.22;
uniform float strata_scale = 0.075;
uniform float strata_amount = 0.85;
uniform vec3 glow_color : source_color = vec3(0.0);
uniform float glow_strength = 0.0;
uniform float wet_darken = 0.35;

varying vec3 w_pos;
varying vec3 w_nrm;

void vertex() {
	w_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	w_nrm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

void fragment() {
	vec3 an = abs(w_nrm);
	vec2 uv = an.x > an.y && an.x > an.z ? w_pos.zy : (an.y > an.z ? w_pos.xz : w_pos.xy);
	vec3 rock_raw = texture(rock_albedo, uv * tex_scale).rgb;
	vec3 albedo = rock_raw * rock_tint;
	float sa = smoothstep(0.2, 0.6, w_nrm.z) * strata_amount;
	if (sa > 0.01) {
		vec3 strata = texture(strata_albedo, w_pos.xy * strata_scale).rgb * strata_tint;
		albedo = mix(albedo, strata, sa);
	}
	float wet = COLOR.a;
	ALBEDO = albedo * COLOR.rgb * (1.0 - wet * wet_darken);
	ROUGHNESS = 0.9;
	if (glow_strength > 0.0) {
		float lum = dot(rock_raw, vec3(0.333));
		float vein = smoothstep(0.048, 0.036, lum) * (0.6 + 0.4 * sin(TIME * 1.7 + w_pos.x * 0.9 + w_pos.y * 1.3));
		EMISSION = glow_color * vein * glow_strength;
	}
}
