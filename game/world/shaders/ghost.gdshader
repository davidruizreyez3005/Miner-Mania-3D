// Translucent "planned building" preview: fresnel rim + soft scanlines.
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_back;

uniform vec4 tint : source_color = vec4(0.35, 0.8, 1.0, 0.3);

void fragment() {
	float rim = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 2.0);
	vec3 wp = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float scan = 0.6 + 0.4 * sin(wp.y * 9.0 - TIME * 2.5);
	ALBEDO = tint.rgb * (0.35 + 1.4 * rim) * scan;
	ALPHA = tint.a;
}
