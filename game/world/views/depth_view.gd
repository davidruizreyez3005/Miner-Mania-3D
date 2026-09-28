class_name DepthView
extends Node3D
## One unlocked depth: its gallery in the mountain and everything in it.
## Veins are the generated resource nodes in their full / damaged / depleted
## states; the station ore pile grows with the bin; mine carts run on the rails
## once haulage is upgraded; drill rigs and excavators appear with tooling
## tiers; lamps, timber or steel sets, pipes, signs and hazard effects dress
## the gallery per depth. Everything is placed through the ModuleLibrary,
## which validates bounds, grounding and overlaps.

const NODE_STATES := ["full", "damaged", "depleted"]

var world: MineWorld
var d: int
var ddef: Dictionary
var env: Dictionary
var floor_y := 0.0
var gallery: MeshInstance3D
var nodes: Array = []             # per slot: {"root": Node3D, "resource", "state", "respawns", "pos"}
var lights: Array = []
var pile: Node3D
var cart: Node3D
var cart_anim: AnimationPlayer
var tier_machine: Node3D
var tier_shown := 0
var props_root := Node3D.new()
var hazard_fx: Array = []
var _cart_t := 0.0
var _cart_dir := 1.0
var _flicker_t := 0.0


func setup(w: MineWorld, depth_index: int) -> void:
	world = w
	d = depth_index
	ddef = w.content.depth(d)
	env = ddef.get("environment", {})
	floor_y = w.content.depth_floor_y(d)
	name = "Depth_%d" % d
	props_root.name = "Props"
	add_child(props_root)
	gallery = MeshInstance3D.new()
	gallery.name = "Gallery"
	gallery.mesh = w.rock.build_gallery(d)
	gallery.material_override = WorldMaterials.rock(ddef)
	gallery.layers = Atmosphere.LAYER_UNDERGROUND
	gallery.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(gallery)
	_add_pick("depth:%d" % d, Vector3(5.0, floor_y + 3.0, -3.5), Vector3(34.0, 5.5, 7.0))
	_reserve_space()
	_build_lights()
	_build_structure()
	_build_dressing()
	_build_nodes()
	_build_hazards()
	_set_layer(self, Atmosphere.LAYER_UNDERGROUND)


func _set_layer(n: Node, layer: int) -> void:
	if n is VisualInstance3D:
		(n as VisualInstance3D).layers = layer
	for c in n.get_children():
		_set_layer(c, layer)


func _add_pick(target: String, center: Vector3, size: Vector3) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.collision_layer = MineWorld.PICK_LAYER
	body.collision_mask = 0
	body.set_meta("target", target)
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	cs.shape = box
	body.position = center
	body.add_child(cs)
	add_child(body)
	return body


func gal() -> Dictionary:
	return world.layout.data.get("gallery", {})


func floor_at(x: float) -> float:
	return world.rock.floor_at(d, x)


## Marks veins, the station pile, the machine bay and the landing as solid so
## set dressing never lands on them.
func _reserve_space() -> void:
	var g := gal()
	for i in int(ddef.get("node_slots", 3)):
		var xz := slot_xz(i)
		world.modules.reserve("res_ore_iron_01", Transform3D(Basis(), Vector3(xz.x, floor_at(xz.x), xz.y)), "gallery", d, 0.3)
	var st: Array = g.get("station", [-9.5, -5.5])
	world.modules.reserve("env_pile_gravel_01", Transform3D(Basis(), Vector3(float(st[0]), floor_at(float(st[0])), float(st[1]))), "gallery", d, 0.2)
	var bay: Array = g.get("machine_bay", [-2.6, -6.2])
	world.modules.reserve("mach_drill_01", Transform3D(Basis(Vector3.UP, PI * 0.5), Vector3(float(bay[0]), floor_at(float(bay[0])), float(bay[1]))), "gallery", d, 0.2)


# ------------------------------------------------------------------ lights

func lamp_color() -> Color:
	var theme := String(world.sim.state.cosmetics.get("equipped", {}).get("lamp_theme", ""))
	var c: Dictionary = world.content.cosmetic_by_id.get(theme, {})
	if String(c.get("color", "")) != "":
		return Color(String(c["color"]))
	return Color(String(env.get("lamp", "#ffc47a")))


func _build_lights() -> void:
	var xs := [-8.0, 0.0, 8.0, 16.0]
	var energy := float(env.get("lamp_energy", 2.2)) * 1.5
	for x in xs:
		var z := -3.4
		var cy := world.rock.ceiling_at(d, x, z)
		var lamp := Assets.instantiate("env_lamp_hanging_01", "", false)
		lamp.position = Vector3(x, cy - 0.05, z)
		props_root.add_child(lamp)
		var ol := OmniLight3D.new()
		ol.name = "Lamp"
		ol.position = Vector3(x, cy - 0.9, z + 0.4)
		ol.light_color = lamp_color()
		ol.light_energy = energy
		ol.omni_range = 12.5
		ol.omni_attenuation = 1.2
		ol.light_cull_mask = Atmosphere.LAYER_UNDERGROUND
		ol.shadow_enabled = false
		add_child(ol)
		lights.append(ol)
	var fill := OmniLight3D.new()
	fill.name = "Fill"
	fill.position = Vector3(5.0, floor_y + 3.2, 2.5)
	fill.light_color = Color(String(env.get("ambient", "#6b5a48"))).lightened(0.3)
	fill.light_energy = 1.8
	fill.omni_range = 32.0
	fill.omni_attenuation = 0.6
	fill.light_cull_mask = Atmosphere.LAYER_UNDERGROUND
	add_child(fill)
	var glow := String(env.get("crystal_glow", ""))
	if glow != "":
		for x in [2.0, 14.0]:
			var gl := OmniLight3D.new()
			gl.position = Vector3(x, floor_y + 1.2, -7.0)
			gl.light_color = Color(glow)
			gl.light_energy = 1.6
			gl.omni_range = 7.0
			gl.light_cull_mask = Atmosphere.LAYER_UNDERGROUND
			add_child(gl)


# ------------------------------------------------------------- structure

func _build_structure() -> void:
	var g := gal()
	# Rails along the gallery front with a buffer stop at the face end.
	var rail_z := float(g.get("rail_z", -1.8))
	var rx: Array = g.get("rail_x", [-11.0, 21.5])
	var rails := []
	var x := float(rx[0]) + 1.0
	while x < float(rx[1]) - 1.0:
		rails.append(Transform3D(Basis(Vector3.UP, PI * 0.5), Vector3(x, floor_at(x) + 0.01, rail_z)))
		x += 2.0
	world.modules.place_many(self, "mod_rail_straight", rails, "gallery", d)
	var bx := minf(x + 0.3, float(rx[1]) - 1.2)
	var buf := Transform3D(Basis(Vector3.UP, -PI * 0.5), Vector3(bx, floor_at(bx), rail_z))
	world.modules.place_many(self, "mod_rail_buffer", [buf], "gallery", d)
	# Timber (shallow) or steel (deep) sets against the back wall.
	var set_id := "mod_support_wood" if d <= 2 else "mod_support_steel"
	var sets := []
	for sx in [-10.9, -4.8]:
		var bz := -world.rock.back_depth(sx) + 1.1
		sets.append(Transform3D(Basis(), Vector3(sx, floor_at(sx), bz)))
	world.modules.place_many(self, set_id, sets, "gallery", d)
	# Shaft landing: steel deck bridging into the shaft, with a safety post.
	var deck := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = Vector3(2.2, 0.18, 5.5)
	deck.mesh = bm
	deck.material_override = WorldMaterials.structure("steel")
	deck.position = Vector3(-13.9, floor_y - 0.09, -3.6)
	props_root.add_child(deck)
	# Station ore pile (scaled with the bin fill in sync()).
	pile = Assets.instantiate("env_pile_coal_01" if d == 2 else "env_pile_gravel_01", "", false)
	var st: Array = g.get("station", [-9.5, -5.5])
	pile.position = Vector3(float(st[0]), floor_at(float(st[0])) - 0.02, float(st[1]))
	props_root.add_child(pile)
	# Rest corner: a bench where tired workers sit.
	var rest: Array = g.get("rest", [-5.5, -7.2])
	var rx2 := float(rest[0])
	world.modules.place_many(self, "mod_bench", [Transform3D(Basis(), Vector3(rx2, floor_at(rx2), float(rest[1])))], "gallery", d)
	# Mine cart (hidden until haulage >= 2).
	cart = Assets.instantiate("veh_mine_cart_01", "", false)
	cart.rotation_degrees.y = 90.0
	cart.visible = false
	props_root.add_child(cart)
	var aps := cart.find_children("*", "AnimationPlayer", true, false)
	cart_anim = aps[0] if not aps.is_empty() else null


# ---------------------------------------------------------------- dressing

func _build_dressing() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 5000 + d
	var bz := -world.rock.back_depth(0.0)
	for item in ddef.get("set_dressing", []):
		match String(item):
			"barrels":
				world.modules.place_many(self, "mod_barrel_oil", [Transform3D(Basis(Vector3.UP, 0.4), Vector3(0.4, floor_at(0.4), -8.0)),
					Transform3D(Basis(Vector3.UP, 1.3), Vector3(1.3, floor_at(1.3), -8.2))], "gallery", d)
			"old_tools":
				world.modules.place_many(self, "mod_crate", [Transform3D(Basis(Vector3.UP, 0.2), Vector3(18.5, floor_at(18.5), -4.2))], "gallery", d)
				world.modules.place_many(self, "mod_ore_sack", [Transform3D(Basis(Vector3.UP, 0.9), Vector3(-7.9, floor_at(-7.9), -8.3))], "gallery", d)
			"rubble":
				var ts := []
				for i in 5:
					var rx := rng.randf_range(-4.0, 20.0)
					ts.append(Transform3D(Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3.ONE * rng.randf_range(0.6, 1.1)), Vector3(rx, floor_at(rx), rng.randf_range(-8.3, -7.6))))
				world.modules.place_many(self, "mod_rock_small", ts, "gallery", d)
			"coal_pile":
				world.modules.place_many(self, "mod_pile_coal", [Transform3D(Basis(), Vector3(19.5, floor_at(19.5), -6.9))], "gallery", d)
			"signs":
				world.modules.place_many(self, "mod_sign_warning", [Transform3D(Basis(Vector3.UP, 0.2), Vector3(-2.2, floor_at(-2.2), -7.8))], "gallery", d)
			"cable_tray":
				var trays := []
				for tx in [-10.0, -7.0, -4.0]:
					trays.append(Transform3D(Basis(Vector3.UP, PI * 0.5), Vector3(tx, floor_y + 3.4, bz + 0.35)))
				world.modules.place_many(self, "mod_cable_tray", trays, "gallery_wall", d)
			"pipes", "vent_ducts":
				var pipes := []
				for px in [-9.0, -6.0, -3.0, 0.0]:
					pipes.append(Transform3D(Basis(Vector3.UP, PI * 0.5), Vector3(px, floor_y, bz + 0.9)))
				world.modules.place_many(self, "mod_pipe_straight", pipes, "gallery", d)
			"pump_station":
				world.modules.place_many(self, "mod_pump_small", [Transform3D(Basis(Vector3.UP, PI * 0.5), Vector3(-6.4, floor_at(-6.4), -4.6))], "gallery", d)
			"containers":
				world.modules.place_many(self, "mod_container", [Transform3D(Basis(Vector3.UP, PI * 0.5), Vector3(20.2, floor_at(20.2), -5.9))], "gallery", d)
			"scaffold":
				world.modules.place_many(self, "mod_scaffold", [Transform3D(Basis(), Vector3(17.0, floor_at(17.0), -7.6))], "gallery", d)
			"catwalk":
				world.modules.place_many(self, "mod_catwalk", [Transform3D(Basis(Vector3.UP, PI * 0.5), Vector3(7.0, floor_at(7.0), -8.0))], "gallery", d)
			"lamp_post":
				world.modules.place_many(self, "mod_lamp_post", [Transform3D(Basis(), Vector3(-1.0, floor_at(-1.0), -7.9))], "gallery", d)
			"barriers":
				world.modules.place_many(self, "mod_barrier", [Transform3D(Basis(Vector3.UP, PI * 0.5), Vector3(21.2, floor_at(21.2), -3.2))], "gallery", d)
			"crystal_clusters":
				_crystals(rng)
			"stalactites":
				_stalactites(rng)
			"puddles":
				_puddles(rng)


func _crystals(rng: RandomNumberGenerator) -> void:
	var glow := Color(String(env.get("crystal_glow", "#b070ff")))
	var mat := StandardMaterial3D.new()
	mat.albedo_color = glow.darkened(0.3)
	mat.emission_enabled = true
	mat.emission = glow
	mat.emission_energy_multiplier = 2.4
	mat.roughness = 0.15
	mat.metallic = 0.2
	for i in 9:
		var x := rng.randf_range(-6.0, 21.0)
		var cluster := Node3D.new()
		var on_ceiling := rng.randf() < 0.4
		var z := rng.randf_range(-8.2, -6.8)
		var y := world.rock.ceiling_at(d, x, z) if on_ceiling else floor_at(x)
		cluster.position = Vector3(x, y, z)
		for k in rng.randi_range(3, 6):
			var c := MeshInstance3D.new()
			var cm := CylinderMesh.new()
			cm.top_radius = 0.0
			var h := rng.randf_range(0.35, 1.1)
			cm.bottom_radius = h * rng.randf_range(0.12, 0.2)
			cm.height = h
			cm.radial_segments = 6
			cm.rings = 1
			c.mesh = cm
			c.material_override = mat
			var tilt := Vector3(rng.randf_range(-0.6, 0.6), 0, rng.randf_range(-0.6, 0.6))
			c.rotation = tilt + (Vector3(PI, 0, 0) if on_ceiling else Vector3.ZERO)
			c.position = Vector3(rng.randf_range(-0.3, 0.3), (-h if on_ceiling else h) * 0.45, rng.randf_range(-0.3, 0.3))
			cluster.add_child(c)
		props_root.add_child(cluster)


func _stalactites(rng: RandomNumberGenerator) -> void:
	var mat := WorldMaterials.rock(ddef)
	for i in 14:
		var x := rng.randf_range(-6.0, 21.0)
		var z := rng.randf_range(-8.0, -3.5)
		var s := MeshInstance3D.new()
		var cm := CylinderMesh.new()
		cm.top_radius = rng.randf_range(0.18, 0.35)
		cm.bottom_radius = 0.02
		cm.height = rng.randf_range(0.6, 1.6)
		cm.radial_segments = 7
		cm.rings = 2
		s.mesh = cm
		s.material_override = mat
		s.position = Vector3(x, world.rock.ceiling_at(d, x, z) - cm.height * 0.45, z)
		props_root.add_child(s)


func _puddles(rng: RandomNumberGenerator) -> void:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.12, 0.16, 0.18, 0.55)
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.roughness = 0.02
	mat.metallic = 0.6
	for i in 5:
		var x := rng.randf_range(-6.0, 20.0)
		var p := MeshInstance3D.new()
		var pm := PlaneMesh.new()
		pm.size = Vector2(rng.randf_range(1.2, 2.6), rng.randf_range(0.7, 1.4))
		p.mesh = pm
		p.material_override = mat
		p.position = Vector3(x, floor_at(x) + 0.03, rng.randf_range(-7.5, -2.5))
		p.rotation.y = rng.randf() * TAU
		props_root.add_child(p)


func _build_hazards() -> void:
	for h in ddef.get("hazards", []):
		match String(h):
			"water":
				for x in [-4.0, 9.0, 17.0]:
					var fx := VfxLibrary.attach(self, "drips", Vector3(x, world.rock.ceiling_at(d, x, -5.0) - 0.2, -5.0))
					hazard_fx.append(fx)
			"gas":
				hazard_fx.append(VfxLibrary.attach(self, "steam", Vector3(10.0, floor_y + 0.4, -7.5), Color("9acd6a")))
			"heat":
				hazard_fx.append(VfxLibrary.attach(self, "steam", Vector3(4.0, floor_y + 0.3, -7.0), Color("ff9a5a")))
			"radiation":
				hazard_fx.append(VfxLibrary.attach(self, "motes", Vector3(8.0, floor_y + 2.5, -4.0), Color("86ff3c")))
	var glow := String(env.get("crystal_glow", ""))
	if glow != "":
		hazard_fx.append(VfxLibrary.attach(self, "motes", Vector3(8.0, floor_y + 2.5, -4.5), Color(glow)))


# -------------------------------------------------------------------- veins

func slot_xz(slot: int) -> Vector2:
	return world.layout.node_slot_xz(slot)


func node_position(slot: int) -> Vector3:
	var xz := slot_xz(slot)
	return Vector3(xz.x, floor_at(xz.x) + 0.8, xz.y)


func _node_state(n: Dictionary) -> String:
	if float(n["respawn_at"]) >= 0.0:
		return "depleted"
	var f := float(n["hp"]) / maxf(float(n["max_hp"]), 1e-6)
	return "full" if f > 0.55 else "damaged"


func _build_nodes() -> void:
	var dep := world.sim.state.depth(d)
	for n in dep["nodes"]:
		nodes.append({"root": null, "resource": "", "state": "", "respawns": -1, "slot": int(n["slot"])})
	_sync_nodes(true)


func _sync_nodes(initial: bool) -> void:
	var dep := world.sim.state.depth(d)
	for i in dep["nodes"].size():
		var n: Dictionary = dep["nodes"][i]
		if i >= nodes.size():
			nodes.append({"root": null, "resource": "", "state": "", "respawns": -1, "slot": int(n["slot"])})
		var v: Dictionary = nodes[i]
		var state := _node_state(n)
		var res := String(n["resource"])
		if state == String(v["state"]) and res == String(v["resource"]) and int(n["respawns"]) == int(v["respawns"]):
			continue
		var respawned := int(v["respawns"]) >= 0 and int(n["respawns"]) != int(v["respawns"])
		if v["root"] != null:
			(v["root"] as Node3D).queue_free()
		var aid := String(world.content.resource_by_id.get(res, {}).get("node_asset", ""))
		var root := Assets.instantiate(aid, state if state != "full" else "", true)
		var xz := slot_xz(int(n["slot"]))
		root.position = Vector3(xz.x, floor_at(xz.x), xz.y)
		root.rotation_degrees.y = float((int(n["slot"]) * 53 + d * 17) % 40) - 20.0
		_set_layer(root, Atmosphere.LAYER_UNDERGROUND)
		add_child(root)
		var pick := StaticBody3D.new()
		pick.collision_layer = MineWorld.PICK_LAYER
		pick.collision_mask = 0
		pick.set_meta("target", "node:%d:%d" % [d, int(n["slot"])])
		var cs := CollisionShape3D.new()
		var box := BoxShape3D.new()
		box.size = Vector3(2.4, 1.8, 2.2)
		cs.shape = box
		cs.position = Vector3(0, 0.8, 0)
		pick.add_child(cs)
		root.add_child(pick)
		if not initial:
			if state == "depleted" and String(v["state"]) != "depleted":
				VfxLibrary.spawn(world, "dust", root.global_position + Vector3(0, 0.6, 0.6))
				VfxLibrary.spawn(world, "rock_chips", root.global_position + Vector3(0, 0.8, 0.6))
			elif respawned:
				root.scale = Vector3.ONE * 0.4
				create_tween().tween_property(root, "scale", Vector3.ONE, 0.8).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
				var rar := String(world.content.resource_by_id.get(res, {}).get("rarity", "common"))
				if rar in ["rare", "very_rare", "exotic"]:
					VfxLibrary.spawn(world, "discovery", root.global_position + Vector3(0, 1.0, 0.4), Color(String(world.content.resource_by_id[res]["color"])))
		v["root"] = root
		v["state"] = state
		v["resource"] = res
		v["respawns"] = int(n["respawns"])


## The asset's mining socket i (worker root transform) for a slot, in world space.
func mine_socket(slot: int, i: int) -> Transform3D:
	for v in nodes:
		if int(v["slot"]) == slot and v["root"] != null:
			var root: Node3D = v["root"]
			var aid := String(root.get_meta("asset_id", ""))
			var sock := "mine_%d" % (i + 1)
			if Assets.has_socket(aid, sock):
				return root.global_transform * Assets.socket(aid, sock)
			return root.global_transform * Transform3D(Basis(Vector3.UP, PI), Vector3(0, 0, 1.6))
	var p := node_position(slot)
	return Transform3D(Basis(Vector3.UP, PI), p + Vector3(0, -0.8, 1.6))


# --------------------------------------------------------------------- sync

func sync(delta: float) -> void:
	_sync_nodes(false)
	var dep := world.sim.state.depth(d)
	# Station pile follows the bin fill.
	var cap := Economy.station_capacity(world.sim, d)
	var fill := clampf(Simulation.inv_total(dep["station"]) / maxf(cap, 1e-6), 0.0, 1.0)
	var target := Vector3.ONE * lerpf(0.15, 1.25, sqrt(fill))
	pile.scale = pile.scale.lerp(target, clampf(delta * 2.0, 0.0, 1.0))
	pile.visible = fill > 0.005
	# Mine cart shuttles between face and station while haulage runs.
	var hl := int(dep["levels"]["haulage"])
	var haul: Dictionary = world.sim.rt.get("haul", {}).get(d, {})
	var moving := hl >= 2 and float(haul.get("moved_rate", 0.0)) > 0.0
	cart.visible = hl >= 2
	if cart.visible:
		var g := gal()
		var rx: Array = g.get("rail_x", [-11.0, 21.5])
		var x0 := float(rx[0]) + 1.5
		var x1 := float(rx[1]) - 3.0
		if moving:
			_cart_t += _cart_dir * delta * 2.4 / (x1 - x0)
			if _cart_t >= 1.0:
				_cart_t = 1.0
				_cart_dir = -1.0
			elif _cart_t <= 0.0:
				_cart_t = 0.0
				_cart_dir = 1.0
		var cx := lerpf(x0, x1, smoothstep(0.0, 1.0, _cart_t))
		cart.position = Vector3(cx, floor_at(cx) + 0.02, float(g.get("rail_z", -1.8)))
		if cart_anim and cart_anim.has_animation("Roll"):
			if moving and cart_anim.current_animation != "Roll":
				cart_anim.play("Roll")
			elif not moving and cart_anim.current_animation == "Roll":
				cart_anim.play("Idle")
	# Tooling tier machines at the face.
	var tier := int(dep["tool_tier"])
	if tier != tier_shown:
		tier_shown = tier
		if tier_machine:
			tier_machine.queue_free()
			tier_machine = null
		var t := world.content.tool_tier(tier)
		var mid := String(t.get("machine_asset", ""))
		if mid != "":
			tier_machine = Assets.instantiate(mid, "", false)
			var bay: Array = gal().get("machine_bay", [-2.6, -6.2])
			var mx := float(bay[0])
			tier_machine.position = Vector3(mx, floor_at(mx), float(bay[1]))
			tier_machine.rotation_degrees.y = 90.0
			_set_layer(tier_machine, Atmosphere.LAYER_UNDERGROUND)
			add_child(tier_machine)
	if tier_machine:
		var working := world.sim.crew("depth:%d" % d, "miner") > 0.0
		for ap in tier_machine.find_children("*", "AnimationPlayer", true, false):
			var a := ap as AnimationPlayer
			var want := "Dig" if a.has_animation("Dig") else "Work"
			want = want if working else "Idle"
			if a.current_animation != want and a.has_animation(want):
				a.play(want, 0.5)
	# Subtle lamp flicker.
	_flicker_t += delta
	for i in lights.size():
		var l := lights[i] as OmniLight3D
		l.light_energy = float(env.get("lamp_energy", 2.2)) * 1.5 * (0.93 + 0.07 * sin(_flicker_t * (3.1 + i) + i * 1.7))
