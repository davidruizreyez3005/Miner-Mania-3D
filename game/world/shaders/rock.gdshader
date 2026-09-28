// Rock surfaces of the mine: cut face, gallery walls/floors/ceilings, shaft.
// World-space triplanar mapping of a tiling rock set; faces looking at the
// camera (+Z, the cutaway plane) show sedimentary strata instead, tinted per
// depth. Vertex colour carries baked ambient occlusion (rgb) and wetness (a).
// Optional emissive mineral veins for the crystal / abyss / anomaly depths.
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

uniform sampler2D rock_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rock_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rock_orm : filter_linear_mipmap, repeat_enable;
uniform sampler2D strata_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D strata_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec3 rock_tint : source_color = vec3(1.0);
uniform vec3 strata_tint : source_color = vec3(1.0);
uniform float tex_scale = 0.22;
uniform float strata_scale = 0.075;
uniform float strata_amount = 0.85;
uniform float normal_strength = 1.0;
uniform vec3 glow_color : source_color = vec3(0.0);
uniform float glow_strength = 0.0;
uniform float wet_darken = 0.35;

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
	vec3 bl = pow(abs(w_nrm), vec3(4.0));
	bl /= (bl.x + bl.y + bl.z + 1e-5);
	vec2 uv_x = w_pos.zy * tex_scale;
	vec2 uv_y = w_pos.xz * tex_scale;
	vec2 uv_z = w_pos.xy * tex_scale;
	vec3 ax = texture(rock_albedo, uv_x).rgb;
	vec3 ay = texture(rock_albedo, uv_y).rgb;
	vec3 az = texture(rock_albedo, uv_z).rgb;
	vec3 rock_raw = ax * bl.x + ay * bl.y + az * bl.z;
	vec3 rock = rock_raw * rock_tint;
	vec3 ox = texture(rock_orm, uv_x).rgb;
	vec3 oy = texture(rock_orm, uv_y).rgb;
	vec3 oz = texture(rock_orm, uv_z).rgb;
	vec3 orm = ox * bl.x + oy * bl.y + oz * bl.z;
	// Whiteout-blended triplanar normals in world space.
	vec3 nx = unpack_n(texture(rock_normal, uv_x).rgb);
	vec3 ny = unpack_n(texture(rock_normal, uv_y).rgb);
	vec3 nz = unpack_n(texture(rock_normal, uv_z).rgb);
	nx = vec3(nx.xy * normal_strength + w_nrm.zy, abs(nx.z) * w_nrm.x);
	ny = vec3(ny.xy * normal_strength + w_nrm.xz, abs(ny.z) * w_nrm.y);
	nz = vec3(nz.xy * normal_strength + w_nrm.xy, abs(nz.z) * w_nrm.z);
	vec3 wn = normalize(nx.zyx * bl.x + ny.xzy * bl.y + nz.xyz * bl.z);
	// Strata on the cutaway face (+Z facing surfaces).
	float face = bl.z * smoothstep(0.2, 0.6, w_nrm.z);
	vec2 suv = vec2(w_pos.x * strata_scale, w_pos.y * strata_scale);
	vec3 strata = texture(strata_albedo, suv).rgb * strata_tint;
	vec3 sn = unpack_n(texture(strata_normal, suv).rgb);
	vec3 face_n = normalize(vec3(sn.xy * normal_strength, 1.0));
	float sa = face * strata_amount;
	vec3 albedo = mix(rock, strata, sa);
	wn = normalize(mix(wn, face_n, sa));
	float wet = COLOR.a;
	albedo *= COLOR.rgb * (1.0 - wet * wet_darken);
	ALBEDO = albedo;
	ROUGHNESS = clamp(orm.g * (1.0 - wet * 0.6), 0.05, 1.0);
	METALLIC = 0.0;
	AO = orm.r;
	AO_LIGHT_AFFECT = 0.6;
	NORMAL = normalize((VIEW_MATRIX * vec4(wn, 0.0)).xyz);
	if (glow_strength > 0.0) {
		// Veins follow the darkest fractures of the untinted rock texture
		// (about the darkest 5% of texels), with a slow shimmer.
		float lum = dot(rock_raw, vec3(0.333));
		float vein = smoothstep(0.048, 0.036, lum) * (0.6 + 0.4 * sin(TIME * 1.7 + w_pos.x * 0.9 + w_pos.y * 1.3));
		EMISSION = glow_color * vein * glow_strength;
	}
}
