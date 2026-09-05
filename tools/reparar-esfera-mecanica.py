"""Repara de forma no destructiva el Master Mesh de esfera-mecanica.

Uso (Blender 5.x):
    blender --background --factory-startup \
      --python tools/reparar-esfera-mecanica.py -- \
      --input source/3d-models/procedural/esfera-mecanica/esfera-mecanica.blend \
      --output-dir astrion-3d-pipeline/work/esfera-mecanica-repair-v1

El script abre la fuente, evalua/aplica sus modificadores, triangula de forma
determinista y elimina pares de caras coincidentes con normales opuestas. Esos
pares son el defecto que convierte dos aristas de Plates_Band_Upper en
non-manifold al exportar. La fuente nunca se sobrescribe: se generan un BLEND,
un GLB y un reporte JSON nuevos en una carpeta fuera de ``source/``.

La geometria enterrada intencional no se elimina aqui: hacerlo requeriria
fusionar piezas semanticas con Sphere_Core y cambiaria el diseno/contrato.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import sys
from pathlib import Path
from typing import Any

try:
    import bpy
    import bmesh
    from mathutils import Matrix
except ModuleNotFoundError:  # permite probar la seguridad del CLI fuera de Blender
    bpy = None
    bmesh = None
    Matrix = None


SCRIPT_VERSION = "astrion-repair-esfera-mecanica/0.1"
REPAIRED_BASENAME = "esfera-mecanica-repaired"
REQUIRED_COMPONENTS = (
    "Sphere_Core",
    "Plates_Band_Equator",
    "Plates_Band_Upper",
    "Plates_Cap_Upper",
    "Hub_Pole_Upper",
    "Core_Bezel_Outer",
    "Core_Rim_Inner",
    "Core_Lens",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def validate_paths(input_path: Path, output_dir: Path, repo_root: Path) -> tuple[Path, Path, Path]:
    input_path = input_path.resolve()
    output_dir = output_dir.resolve()
    repo_root = repo_root.resolve()
    if input_path.suffix.lower() != ".blend" or not input_path.is_file():
        raise ValueError(f"--input debe ser un .blend existente: {input_path}")
    if not is_within(input_path, repo_root):
        raise ValueError(f"la entrada debe estar dentro del repositorio: {repo_root}")
    if not is_within(output_dir, repo_root):
        raise ValueError(f"la salida debe permanecer dentro del repositorio: {repo_root}")
    source_root = repo_root / "source"
    if is_within(output_dir, source_root):
        raise ValueError("la salida no puede estar dentro de source/; use una carpeta de trabajo aislada")
    if output_dir == input_path.parent or is_within(input_path, output_dir):
        raise ValueError("la salida no puede contener ni reemplazar la entrada")
    targets = (
        output_dir / f"{REPAIRED_BASENAME}.blend",
        output_dir / f"{REPAIRED_BASENAME}.glb",
        output_dir / "repair-report.json",
    )
    existing = [path for path in targets if path.exists()]
    if existing:
        raise ValueError("la salida ya contiene artefactos; elija otra carpeta: " + ", ".join(map(str, existing)))
    return input_path, output_dir, repo_root


def blender_arguments(argv: list[str]) -> argparse.Namespace:
    raw = argv[argv.index("--") + 1:] if "--" in argv else argv
    parser = argparse.ArgumentParser(description="Reparacion no destructiva de esfera-mecanica")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--epsilon", type=float, default=1e-5)
    args = parser.parse_args(raw)
    if not math.isfinite(args.epsilon) or not 0 < args.epsilon <= 1e-3:
        parser.error("--epsilon debe estar en el rango (0, 0.001]")
    return args


def evaluated_mesh(object_3d):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = object_3d.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(
        evaluated,
        preserve_all_data_layers=True,
        depsgraph=depsgraph,
    )
    mesh.name = object_3d.name
    mesh.transform(object_3d.matrix_world)
    object_3d.matrix_world = Matrix.Identity(4)
    old_mesh = object_3d.data
    object_3d.modifiers.clear()
    object_3d.data = mesh
    if old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)
    return mesh


def mesh_counts(mesh) -> dict[str, int]:
    return {
        "vertices": len(mesh.vertices),
        "polygons": len(mesh.polygons),
        "triangles": sum(max(len(polygon.vertices) - 2, 0) for polygon in mesh.polygons),
        "ngons": sum(len(polygon.vertices) > 3 for polygon in mesh.polygons),
    }


def _coincident_face_groups(bm) -> list[list[Any]]:
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.verts.index_update()
    bm.faces.index_update()
    groups: dict[tuple[int, ...], list[Any]] = {}
    for face in bm.faces:
        signature = tuple(sorted(vertex.index for vertex in face.verts))
        groups.setdefault(signature, []).append(face)
    return [faces for faces in groups.values() if len(faces) > 1]


def _duplicate_cleanup_plan(groups: list[list[Any]]) -> tuple[list[Any], list[dict[str, Any]]]:
    delete_faces = []
    decisions = []
    for faces in groups:
        opposed = any(
            first.normal.dot(second.normal) <= -0.999
            for index, first in enumerate(faces)
            for second in faces[index + 1:]
        )
        chosen = faces if opposed else faces[1:]
        delete_faces.extend(chosen)
        decisions.append({
            "coincident_faces": len(faces),
            "opposed_normals": opposed,
            "faces_removed": len(chosen),
            "policy": "remove_both_sides" if opposed else "keep_first",
        })
    return delete_faces, decisions


def bmesh_topology(bm) -> dict[str, int]:
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    return {
        "vertices": len(bm.verts),
        "edges": len(bm.edges),
        "triangles": len(bm.faces),
        "ngons": sum(len(face.verts) > 3 for face in bm.faces),
        "boundary_edges": sum(len(edge.link_faces) == 1 for edge in bm.edges),
        "nonmanifold_edges": sum(len(edge.link_faces) > 2 for edge in bm.edges),
        "loose_edges": sum(not edge.link_faces for edge in bm.edges),
        "loose_vertices": sum(not vertex.link_edges for vertex in bm.verts),
        "flipped_manifold_edges": sum(len(edge.link_faces) == 2 and not edge.is_contiguous for edge in bm.edges),
        "degenerate_triangles": sum(face.calc_area() <= 1e-12 for face in bm.faces),
    }


def repair_component(object_3d, epsilon: float) -> dict[str, Any]:
    before = mesh_counts(object_3d.data)
    mesh = evaluated_mesh(object_3d)
    evaluated = mesh_counts(mesh)
    bm = bmesh.new()
    bm.from_mesh(mesh)

    if bm.faces:
        bmesh.ops.triangulate(
            bm,
            faces=list(bm.faces),
            quad_method="FIXED",
            ngon_method="EAR_CLIP",
        )
    bmesh.ops.dissolve_degenerate(bm, dist=epsilon, edges=list(bm.edges))
    merge_result = bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=epsilon)
    bm.normal_update()

    duplicate_groups = _coincident_face_groups(bm)
    delete_faces, decisions = _duplicate_cleanup_plan(duplicate_groups)
    if delete_faces:
        bmesh.ops.delete(bm, geom=delete_faces, context="FACES")
    loose_edges = [edge for edge in bm.edges if not edge.link_faces]
    if loose_edges:
        bmesh.ops.delete(bm, geom=loose_edges, context="EDGES")
    loose_vertices = [vertex for vertex in bm.verts if not vertex.link_edges]
    if loose_vertices:
        bmesh.ops.delete(bm, geom=loose_vertices, context="VERTS")
    # Eliminar las dos caras de una pared coincidente puede reconstruir caras
    # coplanares alrededor del borde. Triangular de nuevo garantiza el contrato
    # final aun cuando Blender cierre esa zona como quad/ngon.
    if bm.faces:
        bmesh.ops.triangulate(
            bm,
            faces=list(bm.faces),
            quad_method="FIXED",
            ngon_method="EAR_CLIP",
        )
    if bm.faces:
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.normal_update()
    after = bmesh_topology(bm)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update(calc_edges=True)
    for polygon in mesh.polygons:
        polygon.use_smooth = True

    return {
        "component": object_3d.name,
        "before_modifiers": before,
        "after_modifiers": evaluated,
        "after_repair": after,
        # Blender 5.2 can return None here when no target map is produced.
        "merged_vertices": len((merge_result or {}).get("targetmap") or {}),
        "coincident_groups": decisions,
    }


def global_topology(objects: list[Any], epsilon: float) -> dict[str, Any]:
    key_to_vertex: dict[tuple[int, int, int], int] = {}
    next_vertex = 0
    faces = []
    for object_3d in objects:
        local_to_welded = {}
        for vertex in object_3d.data.vertices:
            coordinate = object_3d.matrix_world @ vertex.co
            key = tuple(int(round(value / epsilon)) for value in coordinate)
            if key not in key_to_vertex:
                key_to_vertex[key] = next_vertex
                next_vertex += 1
            local_to_welded[vertex.index] = key_to_vertex[key]
        for polygon in object_3d.data.polygons:
            welded = tuple(local_to_welded[index] for index in polygon.vertices)
            faces.append((object_3d.name, polygon.index, welded))

    face_groups: dict[tuple[int, ...], list[tuple[str, int]]] = {}
    edge_faces: dict[tuple[int, int], list[tuple[str, int]]] = {}
    for component, face_index, face in faces:
        face_groups.setdefault(tuple(sorted(face)), []).append((component, face_index))
        for index in range(len(face)):
            edge = tuple(sorted((face[index], face[(index + 1) % len(face)])))
            edge_faces.setdefault(edge, []).append((component, face_index))
    duplicates = [owners for owners in face_groups.values() if len(owners) > 1]
    nonmanifold = [owners for owners in edge_faces.values() if len(owners) > 2]
    boundary = [owners for owners in edge_faces.values() if len(owners) == 1]
    return {
        "stored_vertices": sum(len(object_3d.data.vertices) for object_3d in objects),
        "welded_vertices": next_vertex,
        "triangles": len(faces),
        "duplicate_faces": sum(len(group) - 1 for group in duplicates),
        "duplicate_face_groups": duplicates,
        "nonmanifold_edges": len(nonmanifold),
        "nonmanifold_edge_faces": nonmanifold,
        "boundary_edges": len(boundary),
    }


def glb_counts(path: Path) -> dict[str, int]:
    data = path.read_bytes()
    if data[:4] != b"glTF":
        raise ValueError("la exportacion no produjo un GLB valido")
    json_document = None
    offset = 12
    while offset < len(data):
        length, chunk_type = struct.unpack_from("<II", data, offset)
        chunk = data[offset + 8:offset + 8 + length]
        offset += 8 + length
        if chunk_type == 0x4E4F534A:
            json_document = json.loads(chunk.decode("utf-8").rstrip(" \t\r\n\x00"))
    if not json_document:
        raise ValueError("el GLB exportado no contiene JSON")
    accessors = json_document["accessors"]
    triangles = vertices = 0
    for mesh in json_document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            if primitive.get("mode", 4) != 4:
                raise ValueError("la exportacion contiene primitivas que no son triangulos")
            indices = accessors[primitive["indices"]]["count"]
            triangles += indices // 3
            vertices += accessors[primitive["attributes"]["POSITION"]]["count"]
    return {"meshes": len(json_document.get("meshes", [])), "vertices": vertices, "triangles": triangles, "bytes": len(data)}


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    if bpy is None or bmesh is None:
        print("ERROR: este script debe ejecutarse con Blender, no con Python normal", file=sys.stderr)
        return 2
    args = blender_arguments(sys.argv if argv is None else argv)
    try:
        input_path, output_dir, repo_root = validate_paths(args.input, args.output_dir, args.repo_root)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    output_dir.mkdir(parents=True, exist_ok=True)
    blend_output = output_dir / f"{REPAIRED_BASENAME}.blend"
    glb_output = output_dir / f"{REPAIRED_BASENAME}.glb"
    report_output = output_dir / "repair-report.json"

    report: dict[str, Any] = {
        "schema_version": "0.1",
        "tool": SCRIPT_VERSION,
        "status": "fail",
        "input": {
            "path": input_path.relative_to(repo_root).as_posix(),
            "sha256": sha256_file(input_path),
        },
        "output_dir": output_dir.relative_to(repo_root).as_posix(),
        "epsilon": args.epsilon,
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "blender_version": bpy.app.version_string,
        "components": [],
        "limitations": [
            "Intentional buried closure geometry is preserved.",
            "Gameplay visibility must be reviewed by Geometry Audit v0.1 after repair.",
        ],
    }

    try:
        bpy.ops.wm.open_mainfile(filepath=str(input_path))
        missing = [name for name in REQUIRED_COMPONENTS if bpy.data.objects.get(name) is None]
        non_mesh = [name for name in REQUIRED_COMPONENTS if bpy.data.objects.get(name) and bpy.data.objects[name].type != "MESH"]
        if missing or non_mesh:
            raise RuntimeError(f"contrato de componentes invalido; faltan={missing}, no_mesh={non_mesh}")
        parts = [bpy.data.objects[name] for name in REQUIRED_COMPONENTS]

        for object_3d in parts:
            report["components"].append(repair_component(object_3d, args.epsilon))
        topology = global_topology(parts, args.epsilon)
        report["global_topology"] = topology
        component_errors = [
            item["component"] for item in report["components"]
            if any(item["after_repair"][key] for key in (
                "ngons", "boundary_edges", "nonmanifold_edges", "loose_edges",
                "loose_vertices", "flipped_manifold_edges", "degenerate_triangles",
            ))
        ]
        if component_errors:
            raise RuntimeError(f"la reparacion dejo topologia invalida en {component_errors}")
        if topology["duplicate_faces"] or topology["nonmanifold_edges"] or topology["boundary_edges"]:
            raise RuntimeError(f"la comprobacion global fallo: {topology}")

        bpy.ops.wm.save_as_mainfile(filepath=str(blend_output), relative_remap=False)
        for object_3d in bpy.context.view_layer.objects:
            object_3d.select_set(object_3d in parts)
        bpy.context.view_layer.objects.active = parts[0]
        bpy.ops.export_scene.gltf(
            filepath=str(glb_output),
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_yup=True,
            export_materials="EXPORT",
            export_animations=False,
            export_skins=False,
        )
        exported = glb_counts(glb_output)
        if exported["meshes"] != len(REQUIRED_COMPONENTS):
            raise RuntimeError(f"se esperaban {len(REQUIRED_COMPONENTS)} mallas GLB, se exportaron {exported['meshes']}")
        report["outputs"] = {
            "blend": {
                "path": blend_output.relative_to(repo_root).as_posix(),
                "sha256": sha256_file(blend_output),
                "bytes": blend_output.stat().st_size,
            },
            "glb": {
                "path": glb_output.relative_to(repo_root).as_posix(),
                "sha256": sha256_file(glb_output),
                **exported,
            },
        }
        report["status"] = "pass"
        write_report(report_output, report)
        print(f"PASS {report_output}")
        return 0
    except Exception as exc:
        report["error"] = str(exc)
        write_report(report_output, report)
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"REPORTE: {report_output}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
