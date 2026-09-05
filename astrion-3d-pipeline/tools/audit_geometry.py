#!/usr/bin/env python3
"""Astrion Geometry Audit v0.1: spec-driven, geometry-only evidence.

The command reads an Asset Spec and its candidate Master Mesh exchange GLB,
applies the active scene's node transforms, reuses the existing mesh metric
engine, and writes only an explicitly requested report/diagnostic destination.
It never reads UVs or textures and never modifies the asset.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from _mesh_engine import load_mesh_metrics
from glb_scene import SceneMesh, load_glb_scene
from validate_spec import load_spec, validate_spec


AUDIT_VERSION = "0.1"
TOOL_VERSION = "astrion-geometry-audit/0.1"
PX_PER_UNIT_1440 = 1440.0 / (2 * 1740 * math.tan(math.radians(15)))
DENSITY_WARN = 800.0
DENSITY_HARD = 2000.0
DENSITY_FLOOR_TRIS = 1000
LEGACY_TRIANGLE_GUIDELINES = {
    "prop": (200, 800),
    "prop_grande": (800, 2500),
    "dron": (400, 1200),
    "pet": (2000, 4000),
    "npc_normal": (2000, 4000),
    "npc_complejo": (4000, 7000),
    "elite": (6000, 10000),
    "boss": (9000, 16000),
    "uber": (14000, 25000),
    "player_ship": (10000, 20000),
    "estructura": (8000, 20000),
    "portal": (4000, 9000),
    "fx": (2, 24),
}
PROTECTED_OUTPUT_PARTS = (
    ("source",),
)


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json_value(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metric_subset(metrics: dict[str, Any]) -> dict[str, Any]:
    """Drop Audit 2 measurements and private implementation fields."""
    result = {}
    for key, value in metrics.items():
        lowered = key.lower()
        if key.startswith("_") or lowered == "has_uv" or lowered.startswith("uv_") or "texel" in lowered:
            continue
        result[key] = _json_value(value)
    return result


class Checks:
    def __init__(self):
        self.rows: list[dict[str, Any]] = []

    def add(self, check_id: str, status: str, actual: Any, expected: Any, evidence: str = "") -> None:
        row = {
            "id": check_id,
            "status": status,
            "actual": _json_value(actual),
            "expected": _json_value(expected),
        }
        if evidence:
            row["evidence"] = evidence
        self.rows.append(row)

    def test(self, check_id: str, condition: bool, actual: Any, expected: Any, evidence: str = "") -> None:
        self.add(check_id, "pass" if condition else "error", actual, expected, evidence)

    def warning(self, check_id: str, actual: Any, expected: Any, evidence: str) -> None:
        self.add(check_id, "warning", actual, expected, evidence)

    def info(self, check_id: str, actual: Any, expected: Any, evidence: str = "") -> None:
        self.add(check_id, "informational", actual, expected, evidence)


def _projected_screen_metrics(engine, vertices: np.ndarray, faces: np.ndarray) -> dict[str, Any]:
    direction = engine.camera_dir(engine.GAME_CAM_ELEVATION_DEG, engine.GAME_CAM_AZIMUTH_DEG)
    u, v, _w = engine._basis(direction)
    projected = np.stack([vertices @ u, vertices @ v], axis=1)
    dimensions = projected.max(axis=0) - projected.min(axis=0)
    span = float(max(dimensions))
    raster_size = max(32, min(2048, int(math.ceil(span * PX_PER_UNIT_1440)) + 4))
    _counts, id_buffer, _extent = engine.visible_triangle_area(vertices, faces, direction, res=raster_size)
    visible_pixels = int((id_buffer >= 0).sum())
    return {
        "projected_width_px": round(float(dimensions[0] * PX_PER_UNIT_1440), 2),
        "projected_height_px": round(float(dimensions[1] * PX_PER_UNIT_1440), 2),
        "projected_union_area_px2": visible_pixels,
        "raster_resolution_px": raster_size,
        "triangles_per_1000_projected_px2": round(
            float(len(faces) / max(visible_pixels / 1000.0, 1e-9)), 2
        ),
    }


def _boundary_pixels(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(mask, 1, mode="constant", constant_values=False)
    interior = mask.copy()
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        interior &= padded[1 + dy:1 + dy + mask.shape[0], 1 + dx:1 + dx + mask.shape[1]]
    return mask & ~interior


def _colour_id_buffer(vertices, faces, direction, id_buffer):
    face_normals = np.cross(
        vertices[faces[:, 1]] - vertices[faces[:, 0]],
        vertices[faces[:, 2]] - vertices[faces[:, 0]],
    )
    face_normals /= np.maximum(np.linalg.norm(face_normals, axis=1), 1e-20)[:, None]
    light = -np.asarray(direction, dtype=float)
    light /= np.linalg.norm(light)
    tone = 0.38 + 0.62 * np.clip(face_normals @ light, 0, 1)
    mask = id_buffer >= 0
    boundary = _boundary_pixels(mask)
    image = np.full(id_buffer.shape + (3,), (22, 23, 28), dtype=np.uint8)
    if mask.any():
        triangle_ids = id_buffer[mask]
        base = np.tile(np.array([68, 126, 218], dtype=float), (len(triangle_ids), 1))
        base[boundary[mask]] = np.array([235, 78, 61], dtype=float)
        image[mask] = np.clip(base * tone[triangle_ids, None], 0, 255).astype(np.uint8)
    return image, boundary


def write_gameplay_diagnostic(engine, vertices: np.ndarray, faces: np.ndarray, asset_id: str, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    direction = engine.camera_dir(engine.GAME_CAM_ELEVATION_DEG, engine.GAME_CAM_AZIMUTH_DEG)
    counts, large_ids, _span = engine.visible_triangle_area(vertices, faces, direction, res=560)
    large, boundary = _colour_id_buffer(vertices, faces, direction, large_ids)

    u, v, _w = engine._basis(direction)
    projection = np.stack([vertices @ u, vertices @ v], axis=1)
    dimensions = projection.max(axis=0) - projection.min(axis=0)
    gameplay_px = max(16, min(1024, int(round(float(max(dimensions)) * PX_PER_UNIT_1440)) + 4))
    _small_counts, small_ids, _small_span = engine.visible_triangle_area(
        vertices, faces, direction, res=gameplay_px
    )
    small, _small_boundary = _colour_id_buffer(vertices, faces, direction, small_ids)
    small_display = Image.fromarray(small).resize((560, 560), Image.Resampling.NEAREST)

    sheet = Image.new("RGB", (1140, 630), (16, 17, 21))
    sheet.paste(Image.fromarray(large), (10, 52))
    sheet.paste(small_display, (570, 52))
    draw = ImageDraw.Draw(sheet)
    draw.text((10, 12), f"{asset_id} | geometry diagnostic | {len(faces)} triangles", fill=(238, 238, 242))
    draw.text((10, 612), "560 px inspection view", fill=(165, 168, 176))
    draw.text((570, 612), f"gameplay projection: {gameplay_px - 4} px span (nearest-neighbor enlarged)", fill=(165, 168, 176))
    output_path = output_dir / f"silhouette-{asset_id}.png"
    sheet.save(output_path)

    visible = counts > 0
    silhouette_triangle_ids = np.unique(large_ids[boundary & (large_ids >= 0)])
    stats = {
        "path": str(output_path),
        "inspection_resolution_px": 560,
        "gameplay_projected_span_px": gameplay_px - 4,
        "visible_triangles": int(visible.sum()),
        "hidden_triangles_this_view": int((~visible).sum()),
        "silhouette_triangles": int(len(silhouette_triangle_ids)),
    }
    return output_path, stats


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def safe_output_path(raw: Path, art_root: Path) -> Path:
    path = raw if raw.is_absolute() else art_root / raw
    resolved = path.resolve()
    if not _is_within(resolved, art_root):
        raise ValueError(f"output must stay inside repository root: {art_root}")
    relative_parts = tuple(part.lower() for part in resolved.relative_to(art_root.resolve()).parts)
    for protected in PROTECTED_OUTPUT_PARTS:
        lowered = tuple(part.lower() for part in protected)
        if relative_parts[:len(lowered)] == lowered:
            raise ValueError(f"refusing to write audit output under {'/'.join(protected)}")
    return resolved


def _blend_topology_evidence(spec: dict[str, Any], art_root: Path, source_path: Path):
    """Accept a hash-bound Astrion repair report as Blender topology evidence."""
    reference = spec["pipeline"].get("provenance", {}).get("repair_report")
    if not isinstance(reference, str):
        return None, "no repair_report declared in pipeline.provenance"
    report_path = (art_root / reference).resolve()
    if not _is_within(report_path, art_root) or not report_path.is_file():
        return None, f"repair report does not exist inside the repository: {reference}"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"cannot read repair report: {exc}"
    blend_output = report.get("outputs", {}).get("blend", {})
    expected_path = _relative(source_path, art_root)
    if report.get("status") != "pass":
        return None, "repair report status is not pass"
    if blend_output.get("path") != expected_path:
        return None, "repair report does not describe the authoritative source path"
    if blend_output.get("sha256") != _sha256(source_path):
        return None, "authoritative source hash does not match the repair report"
    components = report.get("components")
    if not isinstance(components, list) or not components:
        return None, "repair report has no per-component topology evidence"
    residual_ngons = sum(int(item.get("after_repair", {}).get("ngons", 0)) for item in components)
    if residual_ngons:
        return None, f"repair report records {residual_ngons} residual n-gons"
    return {
        "path": reference,
        "sha256": _sha256(report_path),
        "tool": report.get("tool"),
        "blender_version": report.get("blender_version"),
        "residual_ngons": residual_ngons,
    }, "hash-bound Blender repair report"


def run_audit(
    spec_path: Path,
    *,
    art_root: Path | None = None,
    heavy: bool = True,
    diagnostics_dir: Path | None = None,
) -> dict[str, Any]:
    art_root = (art_root or Path(__file__).resolve().parents[2]).resolve()
    spec_path = spec_path.resolve()
    spec = load_spec(spec_path)
    spec_errors = validate_spec(spec)
    if spec_errors:
        raise ValueError("invalid Asset Spec:\n  - " + "\n  - ".join(spec_errors))
    master = spec["pipeline"].get("master_mesh")
    if not master:
        raise ValueError("Asset Spec has no pipeline.master_mesh to audit")
    model_path = (art_root / master["exchange_path"]).resolve()
    if not _is_within(model_path, art_root):
        raise ValueError("master_mesh.exchange_path resolves outside the repository")
    if model_path.suffix.lower() != ".glb":
        raise ValueError("Geometry Audit v0.1 requires a .glb exchange_path")
    if not model_path.is_file():
        raise ValueError(f"Master Mesh exchange does not exist: {model_path}")

    scene: SceneMesh = load_glb_scene(model_path)
    # The audited repository root may be overridden by tests or future callers;
    # the reused metric engine remains part of this tool installation.
    tool_art_root = Path(__file__).resolve().parents[2]
    metric_engine_path = tool_art_root / "tools" / "asset-audit" / "mesh_metrics.py"
    engine, spatial_backend = load_mesh_metrics(tool_art_root)
    vertices_source = scene.vertices
    faces = scene.faces
    source_dimensions = vertices_source.max(axis=0) - vertices_source.min(axis=0)
    source_footprint = float(max(source_dimensions[0], source_dimensions[2]))
    if source_footprint <= 1e-12:
        raise ValueError("Master Mesh has zero X/Z footprint")
    declared_screen_size = float(spec["visual"]["screen_size_world_units"])
    runtime_scale = declared_screen_size / source_footprint
    vertices = vertices_source * runtime_scale
    normals = scene.normals

    metrics_raw = engine.analyse(
        vertices,
        faces,
        UV=None,
        N=normals,
        name=spec["identity"]["asset_id"],
        heavy=heavy,
        res=384,
        px_per_unit=PX_PER_UNIT_1440 if heavy else None,
    )
    islands = engine.analyse_islands(vertices, faces, UV=None)
    metrics = _metric_subset(metrics_raw)
    screen = _projected_screen_metrics(engine, vertices, faces)
    checks = Checks()

    triangles = int(len(faces))
    soft_target = int(spec["geometry"]["soft_triangle_target"])
    ceiling = int(spec["geometry"]["triangle_ceiling"])
    checks.test("triangle_ceiling", triangles <= ceiling, triangles, f"<= {ceiling}")
    if triangles <= soft_target:
        checks.add("triangle_soft_target", "pass", triangles, f"planning target <= {soft_target}")
    else:
        checks.warning(
            "triangle_soft_target",
            triangles,
            f"planning target <= {soft_target}",
            "A soft target is not a minimum or a gate; review the overage at gameplay size.",
        )
    category = spec["identity"]["category"]
    legacy = LEGACY_TRIANGLE_GUIDELINES.get(category)
    if legacy and (soft_target > legacy[1] or ceiling > legacy[1]):
        checks.warning(
            "legacy_category_triangle_policy",
            {"spec_soft_target": soft_target, "spec_ceiling": ceiling},
            {"legacy_range": list(legacy)},
            "The explicit reviewed spec controls this audit; the older category range is reported as a policy conflict.",
        )
    else:
        checks.info("legacy_category_triangle_policy", list(legacy) if legacy else None, "informational")

    density = float(screen["triangles_per_1000_projected_px2"])
    if triangles < DENSITY_FLOOR_TRIS:
        checks.info(
            "gameplay_triangle_density",
            density,
            f"not gated below {DENSITY_FLOOR_TRIS} triangles",
            "Below the measurement floor, silhouette and identity review control.",
        )
    elif density > DENSITY_HARD:
        checks.add("gameplay_triangle_density", "error", density, f"<= {DENSITY_HARD}")
    elif density > DENSITY_WARN:
        checks.warning("gameplay_triangle_density", density, f"preferred <= {DENSITY_WARN}; hard <= {DENSITY_HARD}", "High density for projected screen area.")
    else:
        checks.add("gameplay_triangle_density", "pass", density, f"preferred <= {DENSITY_WARN}")

    for key, check_id in (
        ("degenerate_tris", "degenerate_triangles"),
        ("duplicate_faces", "duplicate_faces"),
        ("nonmanifold_edges", "nonmanifold_edges"),
    ):
        value = int(metrics.get(key, 0))
        checks.test(check_id, value == 0, value, 0)
    unused_vertices = int(len(vertices) - len(np.unique(faces)))
    checks.test("unused_vertices", unused_vertices == 0, unused_vertices, 0)
    is_fx = category == "fx"
    boundary_edges = int(metrics.get("boundary_edges", 0))
    if is_fx:
        checks.info("boundary_edges", boundary_edges, "allowed by FX class policy")
    else:
        checks.test("boundary_edges", boundary_edges == 0, boundary_edges, 0)
    planar_count = int(metrics.get("planar_islands", 0))
    if is_fx:
        checks.info("zero_thickness_islands", planar_count, "allowed by FX class policy")
    else:
        checks.test("zero_thickness_islands", planar_count == 0, planar_count, 0)
    checks.test("explicit_normals", scene.normals_complete, scene.normals_complete, True)

    source_path = (art_root / master["source_path"]).resolve()
    checks.test("authoritative_source_exists", source_path.is_file(), source_path.is_file(), True)
    source_topology_evidence = None
    if source_path.suffix.lower() == ".glb" and source_path == model_path:
        checks.add("authoritative_source_ngons", "pass", 0, 0, "The authoritative mesh is the triangulated GLB exchange.")
    elif source_path.suffix.lower() == ".blend":
        source_topology_evidence, evidence_note = _blend_topology_evidence(spec, art_root, source_path)
        if source_topology_evidence:
            checks.add(
                "authoritative_source_ngons",
                "pass",
                0,
                "0 in authoritative Blender source",
                f"Verified by {evidence_note}: {source_topology_evidence['path']}",
            )
        else:
            checks.add(
                "authoritative_source_ngons",
                "error",
                "not_evaluable_from_glb",
                "0 in authoritative Blender source",
                "GLB triangulation cannot prove that the .blend source has no n-gons; " + evidence_note,
            )
    else:
        checks.add(
            "authoritative_source_ngons",
            "error",
            "unsupported_source_format",
            "auditable authoritative source topology",
            f"Audit v0.1 cannot inspect source topology for {source_path.suffix or 'no extension'}.",
        )

    required_components = set(spec["geometry"]["components"]["required"])
    component_names = [component["name"] for component in scene.components]
    unique_component_names = set(component_names)
    missing_components = sorted(required_components - unique_component_names)
    duplicate_component_names = sorted({name for name in component_names if component_names.count(name) > 1})
    component_count = len(component_names)
    component_policy = spec["geometry"]["components"]
    checks.test("semantic_component_count", component_policy["min"] <= component_count <= component_policy["max"], component_count, f"{component_policy['min']}..{component_policy['max']}")
    checks.test("required_semantic_components", not missing_components, missing_components, [])
    checks.test("unique_semantic_component_names", not duplicate_component_names, duplicate_component_names, [])

    required_anchors = set(spec["geometry"]["anchors"]["required"])
    node_by_name: dict[str, list[dict[str, Any]]] = {}
    for node in scene.nodes:
        node_by_name.setdefault(node["name"], []).append(node)
    missing_anchors = sorted(name for name in required_anchors if name not in node_by_name)
    mesh_anchors = sorted(
        name for name in required_anchors
        if any(node["has_mesh"] for node in node_by_name.get(name, []))
    )
    duplicate_anchors = sorted(name for name in required_anchors if len(node_by_name.get(name, [])) > 1)
    checks.test("required_anchors", not missing_anchors, missing_anchors, [])
    checks.test("anchor_nodes_have_no_mesh", not mesh_anchors, mesh_anchors, [])
    checks.test("unique_anchor_names", not duplicate_anchors, duplicate_anchors, [])

    checks.add(
        "node_transforms_applied",
        "pass",
        scene.transformed_node_count,
        "all active-scene node transforms evaluated",
        "Metrics use world-space vertices after inherited GLB matrix/TRS transforms.",
    )
    world_dimensions = vertices.max(axis=0) - vertices.min(axis=0)
    runtime_footprint = float(max(world_dimensions[0], world_dimensions[2]))
    checks.test("runtime_screen_size", abs(runtime_footprint - declared_screen_size) <= 1e-6, round(runtime_footprint, 6), declared_screen_size)
    center = (vertices.max(axis=0) + vertices.min(axis=0)) / 2
    center_fraction = float(np.linalg.norm(center) / max(np.linalg.norm(world_dimensions), 1e-9))
    checks.test("centered_origin", center_fraction <= 0.05, round(center_fraction, 6), "<= 0.05 of bounding-box diagonal")

    flatness_range = spec["geometry"].get("flatness_range")
    flatness = float(world_dimensions[1] / max(world_dimensions[0], world_dimensions[2], 1e-9))
    if flatness_range:
        checks.test("class_flatness", flatness_range[0] <= flatness <= flatness_range[1], round(flatness, 4), flatness_range)
    else:
        checks.info("class_flatness", round(flatness, 4), "not declared by this spec")

    family = str(spec["identity"]["family"]).lower()
    mechanical = "mechan" in family or "primitive_rules" in spec["geometry"]
    construction_profile = "mechanical" if mechanical else "organic_or_general"
    symmetry = spec["visual"]["symmetry"]
    symmetry_type = symmetry["type"]
    if symmetry_type.startswith("bilateral_"):
        axis = symmetry_type[-1]
        fraction = float(metrics.get(f"mirror_{axis}c", 0.0))
        threshold = 0.95 if mechanical else 0.60
        checks.test("declared_bilateral_symmetry", fraction >= threshold, fraction, f">= {threshold}")
    elif symmetry_type == "radial":
        requested_order = int(symmetry["order"])
        measured_order = int(metrics.get("rot_sym_order", 0))
        if measured_order >= requested_order and measured_order % requested_order == 0:
            checks.add("declared_radial_symmetry", "pass", measured_order, f"multiple of {requested_order}")
        else:
            checks.warning(
                "declared_radial_symmetry",
                measured_order,
                f"multiple of {requested_order}",
                "The whole-mesh point-set probe is evidence only; confirm staggered/partial radial intent visually.",
            )
    else:
        checks.info("declared_symmetry", symmetry_type, "no automated symmetry threshold")

    primitive_rules = spec["geometry"].get("primitive_rules")
    if mechanical and primitive_rules and "max_rotational_segments" in primitive_rules:
        maximum = int(primitive_rules["max_rotational_segments"])
        over_segmented = [
            {"island": item["island"], "rot_order": item["rot_order"]}
            for item in islands
            if int(item.get("rot_order", 0)) > maximum
        ]
        if over_segmented:
            checks.warning(
                "mechanical_rotational_segments",
                over_segmented,
                f"<= {maximum}",
                "Automatic primitive classification is advisory; review the named components before changing geometry.",
            )
        else:
            checks.add("mechanical_rotational_segments", "pass", [], f"<= {maximum}")
    else:
        checks.info("mechanical_rotational_segments", None, "not applicable to organic/general profile")

    thin = [
        item["island"] for item in islands
        if not item["flat_card"]
        and item["diag"] > 0
        and min(item["size"]) < max(0.3, 0.008 * max(item["size"]))
    ]
    if thin:
        checks.warning("thin_geometry", thin, [], "Review subpixel thickness at the declared gameplay size.")
    else:
        checks.add("thin_geometry", "pass", [], [])

    if heavy:
        interior = float(metrics.get("interior_tri_ratio", 0.0))
        checks.test("never_visible_geometry", interior <= 0.05 or is_fx, interior, "<= 0.05 unless declared FX/exception")
        subpixel = float(metrics.get("subpixel_tri_ratio", 0.0))
        if subpixel > 0.10:
            checks.warning("subpixel_triangles", subpixel, "preferred <= 0.10", "Geometry below a projected pixel needs visual justification.")
        else:
            checks.add("subpixel_triangles", "pass", subpixel, "preferred <= 0.10")
    else:
        checks.info("never_visible_geometry", None, "requires heavy visibility pass")
        checks.info("subpixel_triangles", None, "requires heavy visibility pass")
    checks.warning(
        "gameplay_visual_review",
        "required",
        "human review of silhouette, major masses, and identity features",
        "Automated metrics and the diagnostic image are evidence, not visual approval.",
    )

    declared_source_inputs = []
    for item in spec["pipeline"]["source_inputs"]:
        input_path = (art_root / item["path"]).resolve()
        declared_source_inputs.append({
            **item,
            "exists": input_path.is_file(),
            "sha256": _sha256(input_path) if input_path.is_file() else None,
        })
    missing_sources = sorted(
        item["path"] for item in declared_source_inputs
        if item["authority"] == "astrion_source" and not item["exists"]
    )
    checks.test("declared_astrion_sources_exist", not missing_sources, missing_sources, [])
    checks.test(
        "geometry_origin_consistency",
        spec["pipeline"]["geometry_outcome"] != "undecided",
        spec["pipeline"]["geometry_outcome"],
        "decided geometry outcome",
    )

    waiver_records = spec["pipeline"]["audits"]["geometry"].get("waivers", [])
    check_rows = {row["id"]: row for row in checks.rows}
    for waiver in waiver_records:
        target = check_rows.get(waiver["check_id"])
        if target is None:
            checks.add(
                "waiver_target_exists",
                "error",
                waiver["check_id"],
                "an emitted geometry check id",
                "A waiver cannot suppress a missing or renamed check.",
            )
        elif target["status"] == "error":
            target["status"] = "waived"
            target["waiver"] = waiver
        else:
            checks.warning(
                "unused_waiver",
                waiver["check_id"],
                "a currently failing check",
                f"The target currently has status {target['status']!r}; remove or revisit the waiver.",
            )

    diagnostics: dict[str, Any] = {}
    if diagnostics_dir is not None:
        output_path, diagnostic_stats = write_gameplay_diagnostic(
            engine, vertices, faces, spec["identity"]["asset_id"], diagnostics_dir
        )
        diagnostic_stats["path"] = _relative(output_path, art_root)
        diagnostics["gameplay_silhouette"] = diagnostic_stats

    errors = sum(row["status"] == "error" for row in checks.rows)
    warnings = sum(row["status"] == "warning" for row in checks.rows)
    waived = sum(row["status"] == "waived" for row in checks.rows)
    report = {
        "schema_version": AUDIT_VERSION,
        "audit": {
            "name": "astrion_geometry",
            "version": AUDIT_VERSION,
            "tool_version": TOOL_VERSION,
            "scope": "geometry_only",
            "excluded": ["uv_layout", "textures", "materials", "appearance", "emission"],
            "result": "fail" if errors else ("waived" if waived else "pass"),
        },
        "asset": {
            "asset_id": spec["identity"]["asset_id"],
            "category": category,
            "family": spec["identity"]["family"],
            "construction_profile": construction_profile,
            "geometry_outcome": spec["pipeline"]["geometry_outcome"],
        },
        "inputs": {
            "spec_path": _relative(spec_path, art_root),
            "spec_sha256": _sha256(spec_path),
            "model_path": _relative(model_path, art_root),
            "model_sha256": _sha256(model_path),
            "authoritative_source_path": _relative(source_path, art_root),
            "authoritative_source_sha256": _sha256(source_path) if source_path.is_file() else None,
            "authoritative_source_topology_evidence": source_topology_evidence,
            "declared_source_inputs": declared_source_inputs,
            "declared_provenance": spec["pipeline"].get("provenance", {}),
        },
        "runtime": {
            "python": ".".join(str(value) for value in sys.version_info[:3]),
            "numpy": np.__version__,
            "pillow": Image.__version__,
            "spatial_query_backend": spatial_backend,
            "audit_tool_sha256": _sha256(Path(__file__).resolve()),
            "glb_loader_sha256": _sha256(Path(__file__).resolve().with_name("glb_scene.py")),
            "mesh_engine_wrapper_sha256": _sha256(Path(__file__).resolve().with_name("_mesh_engine.py")),
            "metric_engine_sha256": _sha256(metric_engine_path),
            "requirements_sha256": _sha256(Path(__file__).resolve().parents[1] / "requirements-audit-v0.1.txt"),
        },
        "camera": {
            "profile": spec["visual"]["camera_profile"],
            "elevation_degrees": engine.GAME_CAM_ELEVATION_DEG,
            "azimuth_degrees": engine.GAME_CAM_AZIMUTH_DEG,
            "pixels_per_world_unit_1440p_zoom1": round(PX_PER_UNIT_1440, 6),
            "declared_screen_size_world_units": declared_screen_size,
            "runtime_scale_from_glb_footprint": round(runtime_scale, 9),
            **screen,
        },
        "scene": {
            "active_scene": scene.active_scene,
            "source_bbox_dimensions": [round(float(value), 9) for value in source_dimensions],
            "source_xz_footprint": round(source_footprint, 9),
            "world_bbox_dimensions": [round(float(value), 9) for value in world_dimensions],
            "transformed_node_count": scene.transformed_node_count,
            "components": scene.components,
            "nodes": scene.nodes,
        },
        "checks": checks.rows,
        "metrics": metrics,
        "islands": _json_value(islands),
        "diagnostics": diagnostics,
        "summary": {
            "errors": errors,
            "warnings": warnings,
            "waived": waived,
            "informational": sum(row["status"] == "informational" for row in checks.rows),
            "passes": sum(row["status"] == "pass" for row in checks.rows),
        },
    }
    return _json_value(report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Astrion Geometry Audit v0.1 from an Asset Spec.")
    parser.add_argument("spec", type=Path, help="Asset Spec v0.1 JSON")
    parser.add_argument("--output", type=Path, help="JSON report path inside the repository")
    parser.add_argument("--diagnostics-dir", type=Path, help="diagnostic output directory inside the repository")
    parser.add_argument("--fast", action="store_true", help="skip multi-view visibility metrics; not valid as formal gate evidence")
    args = parser.parse_args(argv)
    art_root = Path(__file__).resolve().parents[2]
    try:
        output_path = safe_output_path(args.output, art_root) if args.output else None
        diagnostics_dir = safe_output_path(args.diagnostics_dir, art_root) if args.diagnostics_dir else None
        report = run_audit(
            args.spec,
            art_root=art_root,
            heavy=not args.fast,
            diagnostics_dir=diagnostics_dir,
        )
        serialized = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(serialized, encoding="utf-8")
            print(f"{report['audit']['result'].upper()} {output_path}")
        else:
            print(serialized, end="")
        return 0 if report["audit"]["result"] in {"pass", "waived"} else 1
    except (OSError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
