class_name MineWorld
extends Node3D
## The 3D mine site. Built from data (layout, facilities, depths, region) and
## the generated asset library, then kept in sync with the simulation:
## facilities appear and change with their level tiers, depths are dug out
## when unlocked, veins deplete and respawn, the cage winds, trucks drive.
## Rendering never changes the economy - it only reads SimState / rt.

signal rebuilt
signal facilities_changed

const PICK_LAYER := 1 << 1        # physics layer for tap targets

var sim: Simulation
var content: ContentDB
var layout: WorldLayout
var rock: RockBuilder
var atmosphere: Atmosphere
var surface_root := Node3D.new()
var mine_root := Node3D.new()
var decor_root := Node3D.new()
var facility_views: Dictionary = {}     # fid -> FacilityView
var depth_views: Dictionary = {}        # depth -> DepthView
var lift_view: LiftView
var sales_view: SalesView
var modules: ModuleLibrary
var placements: Array = []               # validated placement records (see ModuleLibrary)
var agents: AgentManager
var decor_obstacles: Array = []          # [centre xz, half xz] of decor inside the camp (agents avoid them)
var surface_seats: Array = []            # Transform3D of bench seats at the surface rest area
var _face_mesh: MeshInstance3D
var _shaft_mesh: MeshInstance3D
var _unlocked_sig := ""
var _rng := RandomNumberGenerator.new()


var timings: Dictionary = {}              # build step -> ms (performance budget checks)


## Builds the whole world at once (tools, tests). The game uses begin() and
## steps() so the loading screen can show progress between the steps.
func setup(s: Simulation) -> void:
	begin(s)
	for st in steps():
		run_step(st)


func begin(s: Simulation) -> void:
	sim = s
	content = s.content
	layout = s.layout
	rock = RockBuilder.new(layout)
	modules = ModuleLibrary.new(content)
	modules.rock = rock
	name = "World"
	surface_root.name = "Surface"
	mine_root.name = "Mine"
	decor_root.name = "Decor"
	add_child(surface_root)
	add_child(mine_root)
	add_child(decor_root)
	atmosphere = Atmosphere.new()
	add_child(atmosphere)
	atmosphere.setup(content.region_by_id.get(sim.state.region, content.regions[0]))


## [label, Callable] build steps in order.
func steps() -> Array:
	return [
		["Shaping the valley", _build_terrain],
		["Raising the plant", _build_surface],
		["Cutting the galleries", _build_rock],
		["Rigging the headframe", _build_lift],
		["Fuelling the trucks", _build_sales],
		["Setting up camp", _build_surface_dressing],
		["Planting the hills", _build_decor],
		["Calling the crews", _build_agents],
		["Lighting the lamps", func() -> void: sync(0.0)],
	]


func run_step(st: Array) -> void:
	var t0 := Time.get_ticks_usec()
	(st[1] as Callable).call()
	timings[String(st[0])] = float(Time.get_ticks_usec() - t0) / 1000.0


func _build_lift() -> void:
	lift_view = LiftView.new()
	surface_root.add_child(lift_view)
	lift_view.setup(self)


func _build_sales() -> void:
	sales_view = SalesView.new()
	surface_root.add_child(sales_view)
	sales_view.setup(self)


func _build_agents() -> void:
	agents = AgentManager.new()
	add_child(agents)
	agents.setup(self)


# ------------------------------------------------------------------ terrain

func _build_terrain() -> void:
	var tb := TerrainBuilder.new(layout)
	for fid in content.facility_by_id:
		var fac: Dictionary = content.facility(fid)
		var pl := layout.plot(String(fac.get("plot", "")))
		if pl.is_empty():
			continue
		var fp := footprint(String(fac["asset"]), float(pl.get("yaw", 0.0)))
		var pos: Array = pl["pos"]
		tb.add_pad(Vector2(float(pos[0]), float(pos[1])) + fp.get_center(), fp.size + Vector2(3.0, 3.0))
	var road: Array = layout.data.get("surface", {}).get("road", [])
	var pts := PackedVector2Array()
	for p in road:
		pts.append(Vector2(float(p[0]), float(p[1])))
	tb.add_road(pts, SiteLayout.ROAD_WIDTH)
	for path in layout.data.get("surface", {}).get("paths", []):
		var pp := PackedVector2Array()
		for q in path.get("points", []):
			pp.append(Vector2(float(q[0]), float(q[1])))
		tb.add_road(pp, float(path.get("width", 2.4)))
	var region: Dictionary = content.region_by_id.get(sim.state.region, content.regions[0])
	var mat := WorldMaterials.terrain(region)
	var terrain := MeshInstance3D.new()
	terrain.name = "Terrain"
	terrain.mesh = tb.build()
	terrain.material_override = mat
	terrain.layers = Atmosphere.LAYER_SURFACE
	surface_root.add_child(terrain)
	var mountains := MeshInstance3D.new()
	mountains.name = "Mountains"
	mountains.mesh = tb.build_mountains()
	mountains.material_override = mat
	mountains.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	surface_root.add_child(mountains)
	_terrain_builder = tb


var _terrain_builder: TerrainBuilder


func ground_height(x: float, z: float) -> float:
	return _terrain_builder.height(x, z) if _terrain_builder else 0.0


## Axis-aligned footprint (x, z) of an asset rotated by yaw, relative to its origin.
func footprint(asset_id: String, yaw_deg: float) -> Rect2:
	return SiteLayout.footprint(asset_id, yaw_deg)


# ------------------------------------------------------------------ surface

func _build_surface() -> void:
	for fac in content.facilities:
		var fid := String(fac["id"])
		# Reserve every facility's largest footprint so surface dressing
		# never lands on a plot, whatever tier it reaches later.
		var plot := layout.plot(String(fac.get("plot", fid)))
		var tier := 1 if fid == "headframe" else SiteLayout.max_tier(fid)
		for r in SiteLayout.unit_rects(fid, plot, String(fac.get("asset", "")), tier):
			var rr: Rect2 = r
			modules.records.append({"module": "facility:" + fid, "zone": "surface", "depth": 0, "solid": true, "clear": 0.6,
				"rect": rr, "y0": -1.0, "y1": 12.0, "nav_ignore": true})
		if fid == "headframe":
			continue                     # the lift view owns the headframe
		var fv := FacilityView.new()
		surface_root.add_child(fv)
		fv.setup(self, fid)
		facility_views[fid] = fv


## Props around the camp from data (surface.dressing in the layout): a rest
## area, lamps, containers, the old mine entrance. Every piece goes through
## the module library's placement validation.
func _build_surface_dressing() -> void:
	# Roads, footpaths and the walk stops stay clear.
	for rr in SiteLayout.road_rects(layout) + SiteLayout.path_rects(layout):
		modules.records.append({"module": "path", "zone": "surface", "depth": 0, "solid": true, "clear": 0.2,
			"rect": rr, "y0": -1.0, "y1": 4.0, "nav_ignore": true})
	for loc in ["surface:landing", "surface:rest", "surface:gate", "plant"]:
		var sp := layout.position(loc)
		modules.records.append({"module": "stop:" + loc, "zone": "surface", "depth": 0, "solid": true, "clear": 0.2,
			"rect": Rect2(Vector2(sp.x - 0.8, sp.z - 0.8), Vector2(1.6, 1.6)), "y0": -1.0, "y1": 2.0, "nav_ignore": true})
	var by_module := {}
	for item in layout.data.get("surface", {}).get("dressing", []):
		var mid := String(item.get("module", ""))
		var pos: Array = item.get("pos", [0, 0])
		var x := float(pos[0])
		var z := float(pos[1])
		var t := Transform3D(Basis(Vector3.UP, deg_to_rad(float(item.get("yaw", 0.0)))), Vector3(x, ground_height(x, z), z))
		(by_module.get_or_add(mid, []) as Array).append(t)
		if mid == "mod_bench":
			var aid := String(modules.module(mid).get("asset", "prop_bench_01"))
			if Assets.has_socket(aid, "seat"):
				var seat := t * Assets.socket(aid, "seat")
				surface_seats.append(seat * Transform3D(Basis(), Vector3(-0.4, 0, 0)))
				surface_seats.append(seat * Transform3D(Basis(), Vector3(0.4, 0, 0)))
	for mid in by_module:
		modules.place_many(surface_root, String(mid), by_module[mid], "surface", 0)
	# Safety barrier chained along the cut edge (skipping the shaft collar).
	var eb: Dictionary = layout.data.get("surface", {}).get("edge_barrier", {})
	if not eb.is_empty():
		var ez := float(eb.get("z", -1.0))
		var ex: Array = eb.get("x", [-44.0, 48.0])
		var spans: Array = [[float(ex[0]), float(ex[1])]]
		for sk in eb.get("skip_x", []):
			var nxt: Array = []
			for span in spans:
				var a := float(span[0])
				var b := float(span[1])
				var s0 := float(sk[0])
				var s1 := float(sk[1])
				if s1 <= a or s0 >= b:
					nxt.append([a, b])
					continue
				if s0 > a:
					nxt.append([a, s0])
				if s1 < b:
					nxt.append([s1, b])
			spans = nxt
		for span in spans:
			modules.place_chain(surface_root, String(eb.get("module", "mod_barrier")), Vector3(float(span[0]), 0, ez),
				Vector3(float(span[1]), 0, ez), "surface", 0, ground_height)


## Bench seats (worker root transforms for the Sit clip) on a level.
func seats(level: int) -> Array:
	if level <= 0:
		return surface_seats
	var dv: DepthView = depth_views.get(level)
	return dv.bench_seats() if dv else []


# --------------------------------------------------------------------- rock

func unlocked_depths() -> Array:
	var out := []
	for dep in sim.state.depths:
		if dep["unlocked"]:
			out.append(int(dep["index"]))
	return out


func shaft_bottom() -> float:
	var deepest := maxi(1, sim.state.deepest_unlocked())
	return content.depth_floor_y(deepest) - 1.6


func _build_rock() -> void:
	var unlocked := unlocked_depths()
	_unlocked_sig = str(unlocked)
	if _face_mesh == null:
		_face_mesh = MeshInstance3D.new()
		_face_mesh.name = "CutFace"
		_face_mesh.material_override = WorldMaterials.face()
		_face_mesh.layers = Atmosphere.LAYER_SURFACE
		mine_root.add_child(_face_mesh)
		_shaft_mesh = MeshInstance3D.new()
		_shaft_mesh.name = "Shaft"
		_shaft_mesh.material_override = WorldMaterials.rock(content.depth(1))
		_shaft_mesh.layers = Atmosphere.LAYER_UNDERGROUND
		mine_root.add_child(_shaft_mesh)
	_face_mesh.mesh = rock.build_face(unlocked, shaft_bottom())
	_shaft_mesh.mesh = rock.build_shaft(shaft_bottom(), unlocked)
	_build_shaft_lights(unlocked)
	for d in unlocked:
		if not depth_views.has(d):
			var dv := DepthView.new()
			mine_root.add_child(dv)
			dv.setup(self, int(d))
			depth_views[d] = dv
	for d in range(1, content.depth_count() + 1):
		if not d in unlocked and not depth_views.has(-d):
			pass
	rebuilt.emit()


var _shaft_lights: Array = []


## Work lights at every landing in the shaft (warm, underground layer only).
func _build_shaft_lights(unlocked: Array) -> void:
	for l in _shaft_lights:
		(l as Node).queue_free()
	_shaft_lights.clear()
	for d in unlocked:
		var ol := OmniLight3D.new()
		ol.position = Vector3((rock.shaft_x0 + rock.shaft_x1) * 0.5, content.depth_floor_y(int(d)) + 4.5, -1.5)
		ol.light_color = Color("ffd29a")
		ol.light_energy = 1.4
		ol.omni_range = 9.0
		ol.light_cull_mask = Atmosphere.LAYER_UNDERGROUND
		mine_root.add_child(ol)
		_shaft_lights.append(ol)


# -------------------------------------------------------------------- decor

func _build_decor() -> void:
	_rng.seed = 424242
	var region: Dictionary = content.region_by_id.get(sim.state.region, content.regions[0])
	var veg: Array = region.get("look", {}).get("vegetation", ["env_tree_pine_01"])
	var trees := {}
	var bushes := []
	var grass := []
	var rocks := {}
	var tb := _terrain_builder
	var camp := Rect2(Vector2(-40.0, -44.0), Vector2(90.0, 44.0))
	for i in 420:
		var x := _rng.randf_range(tb.x_range.x + 2.0, tb.x_range.y - 2.0)
		var z := _rng.randf_range(-90.0, -3.0)
		var p := Vector2(x, z)
		var in_camp := camp.has_point(p)
		if in_camp and _rng.randf() < 0.93:
			continue
		if _blocked(p, 3.0) or modules.blocked("surface", 0, Rect2(p - Vector2(1.2, 1.2), Vector2(2.4, 2.4))):
			continue
		var h := tb.height(x, z)
		if h > 26.0:
			continue
		var basis := Basis(Vector3.UP, _rng.randf() * TAU).scaled(Vector3.ONE * _rng.randf_range(0.75, 1.35))
		var t := Transform3D(basis, Vector3(x, h - 0.05, z))
		var roll := _rng.randf()
		if in_camp and roll < 0.72:
			decor_obstacles.append([p, Vector2(0.6, 0.6)])
		if roll < 0.5 and not in_camp:
			var tid := String(veg[_rng.randi_range(0, veg.size() - 1)]) if veg.size() > 0 else "env_tree_pine_01"
			if tid.begins_with("env_tree"):
				(trees.get_or_add(tid, []) as Array).append(t)
			else:
				grass.append(t)
		elif roll < 0.72:
			bushes.append(t)
		elif roll < 0.9:
			grass.append(t)
		else:
			var rid: String = ["env_rock_small_01", "env_rock_medium_01", "env_rock_large_01", "env_boulder_01"][_rng.randi_range(0, 3)]
			(rocks.get_or_add(rid, []) as Array).append(t)
	for tid in trees:
		Scatter.place(decor_root, tid, trees[tid], Atmosphere.LAYER_SURFACE, true, 150.0)
	if "env_bush_01" in Assets.assets:
		Scatter.place(decor_root, "env_bush_01", bushes, Atmosphere.LAYER_SURFACE, false, 70.0)
	Scatter.place(decor_root, "env_grass_clump_01", grass, Atmosphere.LAYER_SURFACE, false, 45.0)
	for rid in rocks:
		Scatter.place(decor_root, rid, rocks[rid], Atmosphere.LAYER_SURFACE, true, 110.0)
	# Cliff line along the foot of the hills behind the camp.
	var cliffs := []
	var x2 := tb.x_range.x + 6.0
	while x2 < tb.x_range.y - 6.0:
		var z2 := -50.0 + 2.5 * sin(x2 * 0.13)
		cliffs.append(Transform3D(Basis(Vector3.UP, deg_to_rad(_rng.randf_range(-4.0, 4.0))), Vector3(x2, tb.height(x2, z2 + 1.5) - 0.3, z2)))
		x2 += 5.8
	Scatter.place(decor_root, "env_cliff_01", cliffs, Atmosphere.LAYER_SURFACE, true, 160.0)


func _blocked(p: Vector2, margin: float) -> bool:
	for fid in content.facility_by_id:
		var fac: Dictionary = content.facility(fid)
		var pl := layout.plot(String(fac.get("plot", "")))
		if pl.is_empty():
			continue
		var fp := footprint(String(fac["asset"]), float(pl.get("yaw", 0.0)))
		var pos: Array = pl["pos"]
		var r := Rect2(Vector2(float(pos[0]), float(pos[1])) + fp.position, fp.size).grow(margin)
		if r.has_point(p):
			return true
	return _terrain_builder._road_weight(p) > 0.2


# --------------------------------------------------------------------- sync

func sync(delta: float) -> void:
	if str(unlocked_depths()) != _unlocked_sig:
		_build_rock()
	for fid in facility_views:
		(facility_views[fid] as FacilityView).sync(delta)
	for d in depth_views:
		(depth_views[d] as DepthView).sync(delta)
	if agents:
		agents.sync(delta)
	lift_view.sync(delta)
	sales_view.sync(delta)


func _process(delta: float) -> void:
	if sim != null:
		sync(delta)


## The agents follow the world's own sync (not a separate _process) so the
## order is fixed: facilities, depths, agents, lift, trucks.
func notify_facility_rebuilt() -> void:
	facilities_changed.emit()


# ------------------------------------------------------------------ queries

## World position for simulation events (sounds, VFX, popups).
func event_position(ev: Dictionary) -> Variant:
	if ev.has("depth") and ev.has("slot"):
		var dv: DepthView = depth_views.get(int(ev["depth"]))
		if dv:
			return dv.node_position(int(ev["slot"]))
	if ev.has("depth"):
		return Vector3(5.0, content.depth_floor_y(int(ev["depth"])) + 2.0, -3.0)
	if ev.has("facility"):
		var fid := String(ev["facility"])
		if fid == "headframe":
			return lift_view.global_position
		var fv: FacilityView = facility_views.get(fid)
		if fv:
			return fv.global_position + Vector3(0, 2, 0)
	return null
