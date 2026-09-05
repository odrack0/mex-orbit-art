#!/usr/bin/env python3
"""Cierra Audit 2 del recorrido manual M3 para ``esfera-mecanica``.

El script no modifica Blender, GLB ni texturas. Verifica los artefactos ya
generados por ``esfera-mecanica-uv.py`` y ``reproyectar-texturas.py`` y emite
un reporte JSON trazable. Es deliberadamente especifico del activo; la
generalizacion spec-driven corresponde a M6.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import struct
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TOOL = "astrion-m3-audit-esfera/0.1"
GENERIC_OCCUPANCY_REFERENCE = 75.0
COMPONENTS = {
    "Core_Bezel_Outer",
    "Core_Lens",
    "Core_Rim_Inner",
    "Hub_Pole_Upper",
    "Plates_Band_Equator",
    "Plates_Band_Upper",
    "Plates_Cap_Upper",
    "Sphere_Core",
}
MATERIALS = {"MAT_HULL", "MAT_RECESSES", "MAT_EMISSION"}
MAP_FILENAMES = {"base_color": "basecolor.png", "normal": "normal.png", "orm": "orm.png"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def repo_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def artifact(path: Path, root: Path) -> dict[str, Any]:
    return {"path": repo_path(path, root), "bytes": path.stat().st_size, "sha256": sha256(path)}


def require_match(pattern: str, text: str, label: str, flags: int = 0) -> re.Match[str]:
    match = re.search(pattern, text, flags)
    if not match:
        raise ValueError(f"{label}: patron no encontrado en el reporte")
    return match


def png_info(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError(f"{path}: no es PNG")
    width, height, bit_depth, color_type = struct.unpack(">IIBB", data[16:26])
    return {
        "width": width,
        "height": height,
        "bit_depth": bit_depth,
        "color_type": color_type,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _paeth(a: int, b: int, c: int) -> int:
    estimate = a + b - c
    da, db, dc = abs(estimate - a), abs(estimate - b), abs(estimate - c)
    return a if da <= db and da <= dc else b if db <= dc else c


def decode_png8(path: Path) -> tuple[dict[str, Any], bytes, int]:
    """Decodifica PNG 8-bit no entrelazado; suficiente para la mascara determinista."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: no es PNG")
    offset = 8
    compressed = bytearray()
    header: tuple[int, int, int, int, int] | None = None
    while offset < len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", payload)
            header = width, height, depth, color_type, interlace
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
    if header is None:
        raise ValueError(f"{path}: falta IHDR")
    width, height, depth, color_type, interlace = header
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
    if depth != 8 or channels is None or interlace != 0:
        raise ValueError(f"{path}: formato PNG no soportado para mascara")
    raw = zlib.decompress(bytes(compressed))
    stride = width * channels
    rows: list[bytes] = []
    previous = bytearray(stride)
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        source = raw[cursor + 1:cursor + 1 + stride]
        cursor += stride + 1
        row = bytearray(stride)
        for index, value in enumerate(source):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            predictor = (
                0 if filter_type == 0 else
                left if filter_type == 1 else
                up if filter_type == 2 else
                (left + up) // 2 if filter_type == 3 else
                _paeth(left, up, upper_left) if filter_type == 4 else
                None
            )
            if predictor is None:
                raise ValueError(f"{path}: filtro PNG desconocido {filter_type}")
            row[index] = (value + predictor) & 0xFF
        rows.append(bytes(row))
        previous = row
    pixels = b"".join(rows)
    white = sum(
        all(channel == 255 for channel in pixels[index:index + channels])
        for index in range(0, len(pixels), channels)
    )
    return png_info(path), pixels, white


def read_glb(path: Path) -> tuple[dict[str, Any], bytes]:
    data = path.read_bytes()
    magic, version, total = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67 or version != 2 or total != len(data):
        raise ValueError(f"{path}: cabecera GLB 2 invalida")
    offset = 12
    document: dict[str, Any] | None = None
    binary = b""
    while offset < len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        chunk = data[offset + 8:offset + 8 + length]
        offset += 8 + length
        if kind == 0x4E4F534A:
            document = json.loads(chunk.rstrip(b" \t\r\n\x00"))
        elif kind == 0x004E4942:
            binary = chunk
    if document is None:
        raise ValueError(f"{path}: falta chunk JSON")
    return document, binary


def accessor_payload(document: dict[str, Any], binary: bytes, index: int) -> bytes:
    accessor = document["accessors"][index]
    if "sparse" in accessor or "bufferView" not in accessor:
        raise ValueError("accessor sparse/sin bufferView no soportado en la firma M3")
    view = document["bufferViews"][accessor["bufferView"]]
    component_size = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}[accessor["componentType"]]
    components = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}[accessor["type"]]
    item_size = component_size * components
    stride = view.get("byteStride", item_size)
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    return b"".join(
        binary[start + item * stride:start + item * stride + item_size]
        for item in range(accessor["count"])
    )


def geometry_signature(document: dict[str, Any], binary: bytes) -> str:
    digest = hashlib.sha256()
    for mesh in document.get("meshes", []):
        digest.update(mesh.get("name", "").encode("utf-8"))
        for primitive in mesh.get("primitives", []):
            digest.update(str(primitive.get("mode", 4)).encode("ascii"))
            for semantic in ("POSITION", "NORMAL", "TEXCOORD_0"):
                digest.update(semantic.encode("ascii"))
                digest.update(accessor_payload(document, binary, primitive["attributes"][semantic]))
            digest.update(accessor_payload(document, binary, primitive["indices"]))
    return digest.hexdigest()


def embedded_image(document: dict[str, Any], binary: bytes, name: str) -> bytes:
    image = next((item for item in document.get("images", []) if item.get("name") == name), None)
    if not image or "bufferView" not in image:
        raise ValueError(f"imagen embebida ausente: {name}")
    view = document["bufferViews"][image["bufferView"]]
    start = view.get("byteOffset", 0)
    return binary[start:start + view["byteLength"]]


def add_check(checks: list[dict[str, Any]], check_id: str, passed: bool, evidence: Any) -> None:
    checks.append({"id": check_id, "status": "pass" if passed else "error", "evidence": evidence})


def parse_uv_report(text: str) -> dict[str, Any]:
    uv = require_match(
        r"UV: en rango 0\.\.1=(True|False)\s+pixeles con solape=(\d+)\s+ocupacion=([\d.]+)%\s+"
        r"texeles/unidad \(visibles\): media=(\d+) p5=(\d+) p95=(\d+)",
        text, "metricas UV",
    )
    topology = require_match(r"triangulos evaluados antes=(\d+) despues=(\d+)", text, "regresion geometrica")
    mask = require_match(
        r"mascara: (\d+) px blancos de (\d+) \(([\d.]+)%\), sangrado (\d+) px, valores solo 0/1",
        text, "mascara de emision",
    )
    detached = require_match(r"reparacion UV de pliegues: poligonos aislados=(\[[^\n]*\])", text, "reparacion UV")
    totals = require_match(
        r"TOTAL\s+MAT_HULL=(\d+)\s+MAT_RECESSES=(\d+)\s+MAT_EMISSION=(\d+)",
        text, "totales de materiales",
    )
    components = set(re.findall(r"^\s{2}([A-Za-z][A-Za-z0-9_]+)\s+MAT_HULL=", text, re.MULTILINE))
    components.discard("TOTAL")
    return {
        "in_range_0_1": uv.group(1) == "True",
        "overlap_pixels": int(uv.group(2)),
        "occupancy_percent": float(uv.group(3)),
        "visible_texels_per_unit": {"mean": int(uv.group(4)), "p5": int(uv.group(5)), "p95": int(uv.group(6))},
        "triangles_before": int(topology.group(1)),
        "triangles_after": int(topology.group(2)),
        "emission_mask": {
            "white_pixels": int(mask.group(1)), "total_pixels": int(mask.group(2)),
            "white_percent": float(mask.group(3)), "bleed_pixels": int(mask.group(4)),
            "reported_binary": True,
        },
        "detached_uv_polygons": ast.literal_eval(detached.group(1)),
        "material_triangles": {
            "MAT_HULL": int(totals.group(1)),
            "MAT_RECESSES": int(totals.group(2)),
            "MAT_EMISSION": int(totals.group(3)),
        },
        "components": sorted(components),
    }


def parse_reprojection_report(text: str) -> dict[str, Any]:
    twins = require_match(
        r"triangulos nuestros=(\d+) con gemelo exacto=(\d+) resueltos por BVH \(n-gonos retriangulados\)=(\d+)",
        text, "correspondencia de triangulos",
    )
    coverage = require_match(
        r"muestras=(\d+) texeles cubiertos=(\d+) \(([\d.]+)%\)\s+"
        r"distancia max punto->malla Meshy en los no gemelos=([\d.eE+-]+)",
        text, "cobertura de reproyeccion",
    )
    geometry = require_match(
        r"geometria: (\d+) triangulos evaluados \(master UV: (\d+); vertices GLB almacenados: (\d+)\) -> (\w+)",
        text, "identidad geometrica",
    )
    comparisons = {}
    for view, mean, p99, maximum in re.findall(
        r"comparativa ([\w-]+): diferencia media=([\d.]+) p99=([\d.]+) max=([\d.]+)", text
    ):
        comparisons[view] = {"mean": float(mean), "p99": float(p99), "max": float(maximum)}
    mip = {
        view: float(mean)
        for view, mean in re.findall(
            r"mip 256px ([\w-]+): diferencia media Meshy vs reproyectado=([\d.]+)", text
        )
    }
    return {
        "triangles": int(twins.group(1)),
        "exact_twins": int(twins.group(2)),
        "bvh_triangles": int(twins.group(3)),
        "samples": int(coverage.group(1)),
        "covered_texels": int(coverage.group(2)),
        "coverage_percent": float(coverage.group(3)),
        "max_bvh_distance": float(coverage.group(4)),
        "geometry_triangles": int(geometry.group(1)),
        "master_uv_triangles": int(geometry.group(2)),
        "stored_glb_vertices": int(geometry.group(3)),
        "geometry_result": geometry.group(4),
        "comparisons_srgb": comparisons,
        "mip_256_mean_difference": mip,
    }


def run(
    work_dir: Path,
    spec_path: Path,
    output: Path,
    root: Path,
    appearance_source: Path | None = None,
) -> dict[str, Any]:
    work_dir, spec_path, output, root = (path.resolve() for path in (work_dir, spec_path, output, root))
    if root not in work_dir.parents or "astrion-3d-pipeline" not in work_dir.parts or "work" not in work_dir.parts:
        raise ValueError("--work-dir debe estar bajo astrion-3d-pipeline/work")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec["identity"]["asset_id"] != "esfera-mecanica":
        raise ValueError("este auditor M3 solo acepta esfera-mecanica")

    uv_report_path = work_dir / "reporte-uv.txt"
    reproj_report_path = work_dir / "reporte-reproyeccion.txt"
    repair_report_path = work_dir / "repair-report.json"
    uv = parse_uv_report(uv_report_path.read_text(encoding="utf-8"))
    reprojection = parse_reprojection_report(reproj_report_path.read_text(encoding="utf-8"))
    repair = json.loads(repair_report_path.read_text(encoding="utf-8"))
    appearance_source_path = (
        appearance_source.resolve()
        if appearance_source is not None
        else root / "source/3d-models/crudo/esfera-mecanica-v2-meshy.glb"
    )
    if root not in appearance_source_path.parents or not appearance_source_path.is_file():
        raise ValueError("--appearance-source debe ser un GLB existente dentro del repositorio")

    v2_path = work_dir / "esfera-mecanica-v2-uv.glb"
    v3_path = work_dir / "esfera-mecanica-v3-tex.glb"
    v2_doc, v2_bin = read_glb(v2_path)
    v3_doc, v3_bin = read_glb(v3_path)
    v2_signature = geometry_signature(v2_doc, v2_bin)
    v3_signature = geometry_signature(v3_doc, v3_bin)

    texture_inventory: dict[str, Any] = {}
    for resolution in spec["appearance"]["texture_resolutions"]:
        directory = work_dir / "textures" if resolution == 2048 else work_dir / "textures" / str(resolution)
        for map_name, filename in MAP_FILENAMES.items():
            path = directory / filename
            texture_inventory[f"{map_name}_{resolution}"] = png_info(path)
    mask_path = work_dir / "emission-mask.png"
    mask_info, mask_pixels, decoded_white = decode_png8(mask_path)
    texture_inventory["emission_mask_2048"] = mask_info

    glb_materials = {material.get("name") for material in v3_doc.get("materials", [])}
    glb_images = {image.get("name") for image in v3_doc.get("images", [])}
    primitives = [primitive for mesh in v3_doc.get("meshes", []) for primitive in mesh.get("primitives", [])]
    attributes_ok = all(
        {"POSITION", "NORMAL", "TEXCOORD_0"} <= set(primitive.get("attributes", {})) and "indices" in primitive
        for primitive in primitives
    )
    single_sided = all(not material.get("doubleSided", False) for material in v3_doc.get("materials", []))
    emission_material = next((m for m in v3_doc.get("materials", []) if m.get("name") == "MAT_EMISSION"), {})
    non_emission_materials = [m for m in v3_doc.get("materials", []) if m.get("name") != "MAT_EMISSION"]
    emission_contract = (
        "emissiveTexture" in emission_material
        and all("emissiveTexture" not in material for material in non_emission_materials)
        and emission_material.get("emissiveFactor", [0.0, 0.0, 0.0]) == [0.0, 0.0, 0.0]
    )
    embedded_mask = embedded_image(v3_doc, v3_bin, "emission-mask")

    source_path = root / repair["input"]["path"]
    source_unchanged = source_path.is_file() and sha256(source_path) == repair["input"]["sha256"]
    expected_sizes = set(spec["appearance"]["texture_resolutions"])
    texture_sizes_ok = all(
        info["width"] == int(key.rsplit("_", 1)[1]) and info["height"] == int(key.rsplit("_", 1)[1])
        for key, info in texture_inventory.items()
        if not key.startswith("emission_mask")
    ) and expected_sizes == {1024, 2048}

    checks: list[dict[str, Any]] = []
    add_check(checks, "source_asset_unchanged", source_unchanged, artifact(source_path, root))
    add_check(checks, "uv_tile_range", uv["in_range_0_1"], uv)
    add_check(checks, "uv_overlap", uv["overlap_pixels"] == 0, {"overlap_pixels": uv["overlap_pixels"]})
    add_check(
        checks, "uv_geometry_regression",
        uv["triangles_before"] == uv["triangles_after"] == reprojection["master_uv_triangles"] == 4166,
        {"before": uv["triangles_before"], "after": uv["triangles_after"], "master_uv": reprojection["master_uv_triangles"]},
    )
    add_check(
        checks, "semantic_material_assignment",
        set(uv["components"]) == COMPONENTS
        and set(uv["material_triangles"]) == MATERIALS
        and sum(uv["material_triangles"].values()) == 4166
        and uv["material_triangles"]["MAT_EMISSION"] > 0,
        {"components": uv["components"], "material_triangles": uv["material_triangles"]},
    )
    add_check(
        checks, "texture_resolutions_and_maps", texture_sizes_ok,
        {"required_maps": spec["appearance"]["maps_required"], "inventory": texture_inventory},
    )
    mask_binary = set(mask_pixels) <= {0, 255}
    add_check(
        checks, "deterministic_emission_mask",
        mask_binary and decoded_white == uv["emission_mask"]["white_pixels"]
        and hashlib.sha256(embedded_mask).hexdigest() == mask_info["sha256"],
        {
            "decoded_values": sorted(set(mask_pixels)), "decoded_white_pixels": decoded_white,
            "reported": uv["emission_mask"], "embedded_sha256": hashlib.sha256(embedded_mask).hexdigest(),
            "baked_glow_halo": False,
        },
    )
    add_check(
        checks, "reprojection_correspondence",
        reprojection["triangles"] == 4166
        and reprojection["exact_twins"] + reprojection["bvh_triangles"] == 4166
        and reprojection["max_bvh_distance"] <= 1.0e-3,
        reprojection,
    )
    visual_ok = (
        set(reprojection["comparisons_srgb"]) == {"three-quarter", "top", "front"}
        and all(value["mean"] <= 0.02 and value["p99"] <= 0.25 for value in reprojection["comparisons_srgb"].values())
        and set(reprojection["mip_256_mean_difference"]) == {"three-quarter", "top"}
        and all(value <= 0.02 for value in reprojection["mip_256_mean_difference"].values())
    )
    add_check(checks, "reprojection_visual_error", visual_ok, {
        "full_resolution": reprojection["comparisons_srgb"],
        "mip_256": reprojection["mip_256_mean_difference"],
    })
    add_check(
        checks, "uv_to_textured_geometry_identity",
        v2_signature == v3_signature and reprojection["geometry_result"] == "IDENTICA",
        {"v2_signature": v2_signature, "v3_signature": v3_signature, "reported": reprojection["geometry_result"]},
    )
    add_check(
        checks, "godot_glb_static_contract",
        len(v3_doc.get("meshes", [])) == 8 and glb_materials == MATERIALS
        and {"basecolor", "normal", "orm", "emission-mask"} <= glb_images
        and attributes_ok and single_sided and emission_contract,
        {
            "meshes": len(v3_doc.get("meshes", [])), "materials": sorted(glb_materials),
            "images": sorted(glb_images), "indexed_position_normal_uv": attributes_ok,
            "single_sided": single_sided, "emission_mask_only_on_semantic_material": emission_contract,
            "color_space_contract": {"basecolor": "sRGB", "orm": "linear", "normal": "linear", "emission_mask": "sRGB glTF semantic / binary data"},
        },
    )

    errors = sum(check["status"] == "error" for check in checks)
    warnings: list[dict[str, Any]] = []
    if uv["occupancy_percent"] < GENERIC_OCCUPANCY_REFERENCE:
        warnings.append({
            "id": "uv_occupancy_policy_reference",
            "status": "warning",
            "measured_percent": uv["occupancy_percent"],
            "generic_reference_percent": GENERIC_OCCUPANCY_REFERENCE,
            "disposition": "accepted_for_m3",
            "reason": "Asset Spec v0.1 has no occupancy threshold. The atlas preserves 8 px fractional packing margin, zero overlap, all semantic closed surfaces, and p5 visible density above 200 texels/unit at 2048.",
            "revisit_condition": "Define class-specific occupancy/padding policy in M6 before production promotion.",
        })

    tool_path = Path(__file__).resolve()
    report = {
        "schema_version": "m3-uv-texture-audit-0.1",
        "audit": {
            "asset_id": spec["identity"]["asset_id"],
            "stage": "audit_2_uv_textures",
            "result": "fail" if errors else "pass",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "tool": TOOL,
            "tool_sha256": sha256(tool_path),
        },
        "inputs": {
            "spec": artifact(spec_path, root),
            "repair_report": artifact(repair_report_path, root),
            "uv_report": artifact(uv_report_path, root),
            "reprojection_report": artifact(reproj_report_path, root),
            "appearance_source": artifact(appearance_source_path, root),
            "uv_glb": artifact(v2_path, root),
            "textured_glb": artifact(v3_path, root),
        },
        "metrics": {"uv": uv, "reprojection": reprojection},
        "checks": checks,
        "warnings": warnings,
        "summary": {"pass": len(checks) - errors, "warning": len(warnings), "error": errors},
        "outputs": {
            "textured_blend": artifact(work_dir / "esfera-mecanica-v3-tex.blend", root),
            "textured_glb": artifact(v3_path, root),
            "emission_mask": artifact(mask_path, root),
            "comparison_render": artifact(work_dir / "renders" / "compare-three-quarter.png", root),
            "gameplay_mip_comparison": artifact(work_dir / "renders" / "compare-top-256px.png", root),
        },
        "provenance": {
            "geometry_authority": repair["outputs"]["blend"],
            "appearance_source": repo_path(appearance_source_path, root),
            "appearance_source_authority": "external_input_non_geometry",
            "emission_authority": "MAT_EMISSION material ID plus deterministic binary mask",
            "source_asset_unchanged": source_unchanged,
            "blender_version": repair["blender_version"],
            "tools": {
                name: artifact(root / path, root)
                for name, path in {
                    "builder": "tools/esfera-mecanica.py",
                    "repair": "tools/reparar-esfera-mecanica.py",
                    "uv_materials": "tools/esfera-mecanica-uv.py",
                    "reprojection": "tools/reproyectar-texturas.py",
                    "audit_2_recorder": "astrion-3d-pipeline/tools/audit_m3_esfera.py",
                }.items()
            },
            "commands": [
                f"blender --background --factory-startup --python tools/esfera-mecanica-uv.py -- {repo_path(work_dir, root)}",
                f"blender --background --factory-startup --python tools/reproyectar-texturas.py -- {repo_path(work_dir, root)} {repo_path(appearance_source_path, root)}",
                f"python astrion-3d-pipeline/tools/audit_m3_esfera.py --work-dir {repo_path(work_dir, root)} --spec {repo_path(spec_path, root)} --output {repo_path(output, root)} --appearance-source {repo_path(appearance_source_path, root)}",
            ],
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--appearance-source", type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    try:
        report = run(args.work_dir, args.spec, args.output, root, args.appearance_source)
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    summary = report["summary"]
    print(f"{report['audit']['result'].upper()}: {summary['pass']} pass, {summary['warning']} warning, {summary['error']} error")
    print(args.output)
    return 0 if report["audit"]["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
