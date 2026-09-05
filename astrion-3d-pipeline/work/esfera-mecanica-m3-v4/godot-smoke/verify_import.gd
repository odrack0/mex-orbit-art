extends SceneTree

const EXPECTED_COMPONENTS := {
	"Core_Bezel_Outer": true,
	"Core_Lens": true,
	"Core_Rim_Inner": true,
	"Hub_Pole_Upper": true,
	"Plates_Band_Equator": true,
	"Plates_Band_Upper": true,
	"Plates_Cap_Upper": true,
	"Sphere_Core": true,
}
const EXPECTED_MATERIALS := {
	"MAT_HULL": true,
	"MAT_RECESSES": true,
	"MAT_EMISSION": true,
}


func _initialize() -> void:
	var checks: Array[Dictionary] = []
	var resource := load("res://esfera-mecanica-v3-tex.glb")
	_add_check(checks, "packed_scene_import", resource is PackedScene, {
		"resource_type": resource.get_class() if resource != null else "null",
	})
	if not resource is PackedScene:
		_finish(checks, {}, 1)
		return

	var root := (resource as PackedScene).instantiate()
	get_root().add_child(root)
	var instances: Array[MeshInstance3D] = []
	_collect_meshes(root, instances)
	var components := {}
	var materials := {}
	var triangle_count := 0
	var vertex_count := 0
	var all_have_normals := true
	var all_have_uv := true
	var all_pbr_textures_imported := true
	var bounds_initialized := false
	var minimum := Vector3.ZERO
	var maximum := Vector3.ZERO
	var material_details := {}

	for instance in instances:
		components[String(instance.name)] = true
		var mesh := instance.mesh
		for surface in range(mesh.get_surface_count()):
			var arrays := mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
			var uv: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			vertex_count += vertices.size()
			triangle_count += (indices.size() if indices.size() > 0 else vertices.size()) / 3
			all_have_normals = all_have_normals and normals.size() == vertices.size()
			all_have_uv = all_have_uv and uv.size() == vertices.size()
			for vertex in vertices:
				var point: Vector3 = instance.global_transform * vertex
				if not bounds_initialized:
					minimum = point
					maximum = point
					bounds_initialized = true
				else:
					minimum = minimum.min(point)
					maximum = maximum.max(point)
			var material := mesh.surface_get_material(surface)
			if material != null:
				var material_name := String(material.resource_name)
				materials[material_name] = true
				var base_texture := _resource_path(material.get("albedo_texture"))
				var normal_texture := _resource_path(material.get("normal_texture"))
				var metallic_texture := _resource_path(material.get("metallic_texture"))
				var roughness_texture := _resource_path(material.get("roughness_texture"))
				all_pbr_textures_imported = all_pbr_textures_imported \
					and not base_texture.is_empty() and not normal_texture.is_empty() \
					and not metallic_texture.is_empty() and not roughness_texture.is_empty()
				if not material_details.has(material_name):
					material_details[material_name] = {
						"class": material.get_class(),
						"base_color_texture": base_texture,
						"normal_texture": normal_texture,
						"metallic_texture": metallic_texture,
						"roughness_texture": roughness_texture,
						"emission_texture": _resource_path(material.get("emission_texture")),
						"emission_enabled": material.get("emission_enabled"),
					}

	_add_check(checks, "mesh_components", components == EXPECTED_COMPONENTS, {
		"count": instances.size(), "names": components.keys(),
	})
	_add_check(checks, "triangle_count", triangle_count == 4166, {
		"triangles": triangle_count, "stored_vertices": vertex_count,
	})
	_add_check(checks, "required_vertex_attributes", all_have_normals and all_have_uv, {
		"normals": all_have_normals, "uv0": all_have_uv,
	})
	_add_check(checks, "semantic_materials", materials == EXPECTED_MATERIALS, {
		"names": materials.keys(), "details": material_details,
	})
	var emission_details: Dictionary = material_details.get("MAT_EMISSION", {})
	_add_check(checks, "pbr_texture_import", all_pbr_textures_imported \
		and not String(emission_details.get("emission_texture", "")).is_empty() \
		and bool(emission_details.get("emission_enabled", false)), {
		"all_materials_have_base_normal_metallic_roughness": all_pbr_textures_imported,
		"emission_material": emission_details,
	})
	var runtime_emission_ok := false
	for instance in instances:
		for surface in range(instance.mesh.get_surface_count()):
			var material := instance.mesh.surface_get_material(surface)
			if material != null and material.resource_name == "MAT_EMISSION":
				material.set("emission", Color(0.0, 0.85, 1.0, 1.0))
				material.set("emission_energy_multiplier", 2.5)
				runtime_emission_ok = material.get("emission").is_equal_approx(Color(0.0, 0.85, 1.0, 1.0)) \
					and is_equal_approx(material.get("emission_energy_multiplier"), 2.5)
	_add_check(checks, "runtime_emission_control", runtime_emission_ok, {
		"color_srgb": [0.0, 0.85, 1.0, 1.0],
		"energy_multiplier": 2.5,
		"glow_halo_baked": false,
	})
	var size := maximum - minimum
	_add_check(checks, "finite_nonzero_bounds", bounds_initialized and size.length() > 0.0 and size.is_finite(), {
		"min": [minimum.x, minimum.y, minimum.z],
		"max": [maximum.x, maximum.y, maximum.z],
		"size": [size.x, size.y, size.z],
	})

	_finish(checks, {
		"godot_version": Engine.get_version_info(),
		"resource_path": "res://esfera-mecanica-v3-tex.glb",
	}, 0)


func _collect_meshes(node: Node, output: Array[MeshInstance3D]) -> void:
	if node is MeshInstance3D:
		output.append(node as MeshInstance3D)
	for child in node.get_children():
		_collect_meshes(child, output)


func _resource_path(value: Variant) -> String:
	return value.resource_path if value is Resource else ""


func _add_check(checks: Array[Dictionary], id: String, passed: bool, evidence: Dictionary) -> void:
	checks.append({"id": id, "status": "pass" if passed else "error", "evidence": evidence})


func _finish(checks: Array[Dictionary], provenance: Dictionary, forced_code: int) -> void:
	var errors := 0
	for check in checks:
		if check["status"] == "error":
			errors += 1
	var result := "pass" if errors == 0 and forced_code == 0 else "fail"
	var report := {
		"schema_version": "m3-godot-smoke-0.1",
		"asset_id": "esfera-mecanica",
		"result": result,
		"checks": checks,
		"summary": {"pass": checks.size() - errors, "error": errors},
		"provenance": provenance,
	}
	var file := FileAccess.open("res://godot-smoke-report.json", FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(report, "  ") + "\n")
		file.close()
	print(JSON.stringify(report))
	quit(0 if result == "pass" else 1)
