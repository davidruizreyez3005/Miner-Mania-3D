class_name Scatter
extends RefCounted
## Batched placement of many copies of a static asset (trees, grass, rocks,
## rails, supports) as MultiMeshInstance3D per mesh, so hundreds of props
## cost a handful of draw calls. Meshes are taken from the imported asset
## scene (LOD0 geometry; the importer's automatic mesh LODs still apply).

static var _meshes: Dictionary = {}


## [[Mesh, Transform3D (node transform inside the asset)], ...] for an asset.
static func meshes_of(asset_id: String) -> Array:
	if _meshes.has(asset_id):
		return _meshes[asset_id]
	var out: Array = []
	var ps := Assets.scene(Assets.model_path(asset_id))
	if ps != null:
		var inst := ps.instantiate() as Node3D
		for mi in inst.find_children("*", "MeshInstance3D", true, false):
			var m := mi as MeshInstance3D
			if m.mesh == null or m.skeleton != NodePath("") and String(m.skeleton) != "":
				continue
			var t := Transform3D.IDENTITY
			var n: Node = m
			while n != null and n != inst:
				if n is Node3D:
					t = (n as Node3D).transform * t
				n = n.get_parent()
			out.append([m.mesh, t])
		inst.free()
	_meshes[asset_id] = out
	return out


## Creates MultiMeshInstance3D children under `parent` for `transforms`.
static func place(parent: Node3D, asset_id: String, transforms: Array, layer: int = 1, shadows: bool = true,
		visibility_end: float = 0.0) -> Array:
	var made: Array = []
	if transforms.is_empty():
		return made
	for pair in meshes_of(asset_id):
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = pair[0]
		mm.instance_count = transforms.size()
		for i in transforms.size():
			mm.set_instance_transform(i, (transforms[i] as Transform3D) * (pair[1] as Transform3D))
		var mmi := MultiMeshInstance3D.new()
		mmi.name = "%s_x%d" % [asset_id, transforms.size()]
		mmi.multimesh = mm
		mmi.layers = layer
		mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if shadows else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		if visibility_end > 0.0:
			mmi.visibility_range_end = visibility_end
			mmi.visibility_range_end_margin = 4.0
		parent.add_child(mmi)
		made.append(mmi)
	return made
