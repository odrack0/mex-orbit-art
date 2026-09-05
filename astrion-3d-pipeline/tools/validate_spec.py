#!/usr/bin/env python3
"""Read-only validator for Astrion Asset Spec v0.1 JSON files.

This intentionally uses only the Python standard library. It mirrors the
checked-in JSON Schema and adds relationships JSON Schema cannot express
without non-portable extensions. It never checks path existence and never
writes files.

Usage:
    python astrion-3d-pipeline/tools/validate_spec.py \
        source/3d-models/specs/esfera-mecanica.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "0.1"
CATEGORIES = {
    "prop", "prop_grande", "dron", "pet", "npc_normal", "npc_complejo",
    "elite", "boss", "uber", "player_ship", "estructura", "portal", "fx",
}
ORIGINS = {"meshy", "tripo", "procedural_blender"}
PREFERRED_ORIGINS = ORIGINS | {"auto"}
OUTCOMES = {
    "undecided", "accept_normalize", "repair", "rebuild_reference",
    "procedural_direct",
}
STAGES = [
    "concept_intake", "spec_ready", "generative_probe",
    "geometry_origin_selected", "master_mesh_candidate", "geometry_audited",
    "uv_materials_ready", "appearance_ready", "appearance_reprojected",
    "emission_ready", "uv_textures_audited", "exported", "godot_verified",
]
STAGE_INDEX = {name: index for index, name in enumerate(STAGES)}
MAPS = {"base_color", "normal", "orm", "metallic", "roughness", "ao", "emission_mask"}
ARTIFACT_AUTHORITIES = {"external_input", "astrion_source", "derived"}
AUDIT_STATUSES = {"not_run", "pass", "fail", "waived"}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _unknown(obj: Any, path: str, allowed: set[str], errors: list[str]) -> None:
    if isinstance(obj, dict):
        for key in sorted(set(obj) - allowed):
            errors.append(f"{path}.{key}: unknown field")


def _object(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path}: expected object")
        return {}
    return value


def _required(obj: dict[str, Any], path: str, keys: set[str], errors: list[str]) -> None:
    for key in sorted(keys - set(obj)):
        errors.append(f"{path}.{key}: required field is missing")


def _string(value: Any, path: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}: expected non-empty string")
        return False
    return True


def _string_list(value: Any, path: str, errors: list[str], *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{path}: expected array")
        return []
    if nonempty and not value:
        errors.append(f"{path}: expected at least one item")
    result: list[str] = []
    for index, item in enumerate(value):
        if _string(item, f"{path}[{index}]", errors):
            result.append(item)
    if len(result) != len(set(result)):
        errors.append(f"{path}: duplicate items are not allowed")
    return result


def _repo_path(value: Any, path: str, errors: list[str]) -> None:
    if not _string(value, path, errors):
        return
    assert isinstance(value, str)
    reasons = []
    if value.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", value):
        reasons.append("must be repository-relative")
    if "\\" in value:
        reasons.append("must use forward slashes")
    if ":" in value:
        reasons.append("must not contain ':'")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        reasons.append("must not contain empty, '.' or '..' segments")
    if "\x00" in value:
        reasons.append("must not contain NUL")
    if reasons:
        errors.append(f"{path}: invalid repository path ({'; '.join(reasons)})")


def _enum(value: Any, path: str, choices: set[str], errors: list[str]) -> None:
    if not isinstance(value, str) or value not in choices:
        errors.append(f"{path}: expected one of {', '.join(sorted(choices))}; got {value!r}")


def _artifact_list(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{path}: expected array")
        return
    for index, raw in enumerate(value):
        item_path = f"{path}[{index}]"
        item = _object(raw, item_path, errors)
        allowed = {"path", "role", "authority", "notes"}
        _unknown(item, item_path, allowed, errors)
        _required(item, item_path, {"path", "role", "authority"}, errors)
        if "path" in item:
            _repo_path(item["path"], f"{item_path}.path", errors)
        if "role" in item:
            _string(item["role"], f"{item_path}.role", errors)
        if "authority" in item:
            _enum(item["authority"], f"{item_path}.authority", ARTIFACT_AUTHORITIES, errors)
        if "notes" in item:
            _string(item["notes"], f"{item_path}.notes", errors)


def _audit_reference(raw: Any, path: str, errors: list[str]) -> None:
    ref = _object(raw, path, errors)
    _unknown(ref, path, {"status", "report", "waivers"}, errors)
    _required(ref, path, {"status", "report"}, errors)
    status = ref.get("status")
    if "status" in ref:
        _enum(status, f"{path}.status", AUDIT_STATUSES, errors)
    report = ref.get("report")
    if report is not None:
        _repo_path(report, f"{path}.report", errors)
    if status == "not_run" and report is not None:
        errors.append(f"{path}.report: must be null when status is 'not_run'")
    if isinstance(status, str) and status in {"pass", "fail", "waived"} and report is None:
        errors.append(f"{path}.report: required when status is {status!r}")
    raw_waivers = ref.get("waivers", [])
    if not isinstance(raw_waivers, list):
        errors.append(f"{path}.waivers: expected array")
        raw_waivers = []
    waiver_ids = []
    for index, raw_waiver in enumerate(raw_waivers):
        waiver_path = f"{path}.waivers[{index}]"
        waiver = _object(raw_waiver, waiver_path, errors)
        allowed = {"check_id", "reason", "scope", "reviewer", "revisit_condition", "expires"}
        required = {"check_id", "reason", "scope", "reviewer", "revisit_condition"}
        _unknown(waiver, waiver_path, allowed, errors)
        _required(waiver, waiver_path, required, errors)
        for field in required:
            if field in waiver:
                _string(waiver[field], f"{waiver_path}.{field}", errors)
        check_id = waiver.get("check_id")
        if isinstance(check_id, str):
            waiver_ids.append(check_id)
            if not re.fullmatch(r"[a-z][a-z0-9_]*", check_id):
                errors.append(f"{waiver_path}.check_id: expected lowercase snake_case check id")
        if "expires" in waiver and waiver["expires"] is not None:
            _string(waiver["expires"], f"{waiver_path}.expires", errors)
    if len(waiver_ids) != len(set(waiver_ids)):
        errors.append(f"{path}.waivers: duplicate check_id values are not allowed")
    if status == "waived" and not raw_waivers:
        errors.append(f"{path}.waivers: at least one waiver is required when status is 'waived'")
    if status == "pass" and raw_waivers:
        errors.append(f"{path}.waivers: must be empty or omitted when status is 'pass'")


def validate_spec(data: Any) -> list[str]:
    """Return all validation errors. The function has no filesystem side effects."""
    errors: list[str] = []
    if not isinstance(data, dict):
        _object(data, "$", errors)
        return errors
    root = data

    root_allowed = {"schema_version", "identity", "visual", "geometry", "appearance", "pipeline", "notes"}
    _unknown(root, "$", root_allowed, errors)
    _required(root, "$", root_allowed - {"notes"}, errors)
    if root.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"$.schema_version: expected {SCHEMA_VERSION!r}; got {root.get('schema_version')!r}")

    identity = _object(root.get("identity"), "$.identity", errors)
    _unknown(identity, "$.identity", {"asset_id", "category", "family", "tier", "status", "notes"}, errors)
    _required(identity, "$.identity", {"asset_id", "category", "family", "tier", "status"}, errors)
    asset_id = identity.get("asset_id")
    if _string(asset_id, "$.identity.asset_id", errors) and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", asset_id):
        errors.append("$.identity.asset_id: use lowercase kebab-case")
    if "category" in identity:
        _enum(identity["category"], "$.identity.category", CATEGORIES, errors)
    for field in ("family", "tier"):
        if field in identity:
            _string(identity[field], f"$.identity.{field}", errors)
    if "status" in identity:
        _enum(identity["status"], "$.identity.status", {"experimental", "production"}, errors)

    visual = _object(root.get("visual"), "$.visual", errors)
    visual_allowed = {"screen_size_world_units", "camera_profile", "symmetry", "silhouette_complexity", "major_masses", "identity_features", "notes"}
    _unknown(visual, "$.visual", visual_allowed, errors)
    _required(visual, "$.visual", visual_allowed - {"notes"}, errors)
    screen_size = visual.get("screen_size_world_units")
    if not _is_number(screen_size) or screen_size <= 0:
        errors.append("$.visual.screen_size_world_units: expected number greater than zero")
    if visual.get("camera_profile") != "top_down_default_v1":
        errors.append("$.visual.camera_profile: expected 'top_down_default_v1'")
    symmetry = _object(visual.get("symmetry"), "$.visual.symmetry", errors)
    _unknown(symmetry, "$.visual.symmetry", {"type", "order"}, errors)
    _required(symmetry, "$.visual.symmetry", {"type"}, errors)
    symmetry_type = symmetry.get("type")
    if "type" in symmetry:
        _enum(symmetry_type, "$.visual.symmetry.type", {"none", "bilateral_x", "bilateral_y", "bilateral_z", "radial"}, errors)
    if symmetry_type == "radial":
        order = symmetry.get("order")
        if not _is_int(order) or order < 2:
            errors.append("$.visual.symmetry.order: radial symmetry requires an integer >= 2")
    elif "order" in symmetry:
        errors.append("$.visual.symmetry.order: allowed only for radial symmetry")
    if "silhouette_complexity" in visual:
        _enum(visual["silhouette_complexity"], "$.visual.silhouette_complexity", {"low", "medium", "high"}, errors)
    for field in ("major_masses", "identity_features"):
        _string_list(visual.get(field), f"$.visual.{field}", errors, nonempty=True)

    geometry = _object(root.get("geometry"), "$.geometry", errors)
    geometry_allowed = {"preferred_origin", "allowed_origins", "soft_triangle_target", "triangle_ceiling", "coordinate_profile", "components", "primitive_rules", "flatness_range", "anchors", "notes"}
    geometry_required = {"preferred_origin", "allowed_origins", "soft_triangle_target", "triangle_ceiling", "coordinate_profile", "components", "anchors"}
    _unknown(geometry, "$.geometry", geometry_allowed, errors)
    _required(geometry, "$.geometry", geometry_required, errors)
    preferred = geometry.get("preferred_origin")
    if "preferred_origin" in geometry:
        _enum(preferred, "$.geometry.preferred_origin", PREFERRED_ORIGINS, errors)
    allowed_origins = _string_list(geometry.get("allowed_origins"), "$.geometry.allowed_origins", errors, nonempty=True)
    for index, origin in enumerate(allowed_origins):
        _enum(origin, f"$.geometry.allowed_origins[{index}]", ORIGINS, errors)
    if isinstance(preferred, str) and preferred in ORIGINS and preferred not in allowed_origins:
        errors.append("$.geometry.preferred_origin: must also appear in allowed_origins")
    target, ceiling = geometry.get("soft_triangle_target"), geometry.get("triangle_ceiling")
    if not _is_int(target) or target < 1:
        errors.append("$.geometry.soft_triangle_target: expected positive integer")
    if not _is_int(ceiling) or ceiling < 1:
        errors.append("$.geometry.triangle_ceiling: expected positive integer")
    if _is_int(target) and _is_int(ceiling) and target > ceiling:
        errors.append("$.geometry.soft_triangle_target: must be <= triangle_ceiling")
    if geometry.get("coordinate_profile") != "astrion_blender_to_godot_v1":
        errors.append("$.geometry.coordinate_profile: expected 'astrion_blender_to_godot_v1'")

    components = _object(geometry.get("components"), "$.geometry.components", errors)
    _unknown(components, "$.geometry.components", {"min", "max", "required"}, errors)
    _required(components, "$.geometry.components", {"min", "max", "required"}, errors)
    comp_min, comp_max = components.get("min"), components.get("max")
    if not _is_int(comp_min) or comp_min < 1:
        errors.append("$.geometry.components.min: expected integer >= 1")
    if not _is_int(comp_max) or comp_max < 1:
        errors.append("$.geometry.components.max: expected integer >= 1")
    if _is_int(comp_min) and _is_int(comp_max) and comp_min > comp_max:
        errors.append("$.geometry.components.min: must be <= components.max")
    required_components = _string_list(components.get("required"), "$.geometry.components.required", errors)
    if _is_int(comp_max) and len(required_components) > comp_max:
        errors.append("$.geometry.components.required: contains more names than components.max")

    if "primitive_rules" in geometry:
        primitive = _object(geometry["primitive_rules"], "$.geometry.primitive_rules", errors)
        _unknown(primitive, "$.geometry.primitive_rules", {"max_rotational_segments"}, errors)
        if "max_rotational_segments" in primitive:
            value = primitive["max_rotational_segments"]
            if not _is_int(value) or value < 3:
                errors.append("$.geometry.primitive_rules.max_rotational_segments: expected integer >= 3")
    if "flatness_range" in geometry and geometry["flatness_range"] is not None:
        flatness = geometry["flatness_range"]
        if not isinstance(flatness, list) or len(flatness) != 2 or not all(_is_number(v) and v > 0 for v in flatness):
            errors.append("$.geometry.flatness_range: expected null or two positive numbers")
        elif flatness[0] > flatness[1]:
            errors.append("$.geometry.flatness_range: lower bound must be <= upper bound")
    anchors = _object(geometry.get("anchors"), "$.geometry.anchors", errors)
    _unknown(anchors, "$.geometry.anchors", {"required"}, errors)
    _required(anchors, "$.geometry.anchors", {"required"}, errors)
    _string_list(anchors.get("required"), "$.geometry.anchors.required", errors)

    appearance = _object(root.get("appearance"), "$.appearance", errors)
    appearance_allowed = {"texture_resolutions", "maps_required", "metallic", "roughness", "wear", "rust", "emission", "notes"}
    _unknown(appearance, "$.appearance", appearance_allowed, errors)
    _required(appearance, "$.appearance", appearance_allowed - {"notes"}, errors)
    resolutions = appearance.get("texture_resolutions")
    if not isinstance(resolutions, list) or not resolutions:
        errors.append("$.appearance.texture_resolutions: expected non-empty array")
    else:
        valid_resolutions = [value for value in resolutions if _is_int(value)]
        if len(valid_resolutions) != len(set(valid_resolutions)):
            errors.append("$.appearance.texture_resolutions: duplicate items are not allowed")
        for index, value in enumerate(resolutions):
            if not _is_int(value) or value < 16:
                errors.append(f"$.appearance.texture_resolutions[{index}]: expected integer >= 16")
    maps = _string_list(appearance.get("maps_required"), "$.appearance.maps_required", errors, nonempty=True)
    for index, map_name in enumerate(maps):
        _enum(map_name, f"$.appearance.maps_required[{index}]", MAPS, errors)
    for field, choices in {
        "metallic": {"none", "mixed", "mostly_metal"},
        "roughness": {"low", "medium", "high", "mixed"},
        "wear": {"none", "light", "medium", "heavy"},
        "rust": {"none", "light", "medium", "heavy"},
    }.items():
        if field in appearance:
            _enum(appearance[field], f"$.appearance.{field}", choices, errors)
    emission = _object(appearance.get("emission"), "$.appearance.emission", errors)
    _unknown(emission, "$.appearance.emission", {"policy", "material_ids", "runtime_profile", "bake_glow_halo"}, errors)
    _required(emission, "$.appearance.emission", {"policy", "material_ids", "bake_glow_halo"}, errors)
    emission_policy = emission.get("policy")
    if "policy" in emission:
        _enum(emission_policy, "$.appearance.emission.policy", {"none", "material_ids", "authored_mask"}, errors)
    material_ids = _string_list(emission.get("material_ids"), "$.appearance.emission.material_ids", errors)
    if emission_policy == "material_ids" and not material_ids:
        errors.append("$.appearance.emission.material_ids: required when policy is 'material_ids'")
    if emission_policy == "none" and material_ids:
        errors.append("$.appearance.emission.material_ids: must be empty when policy is 'none'")
    if emission.get("bake_glow_halo") is not False:
        errors.append("$.appearance.emission.bake_glow_halo: must be false; glow belongs in Godot")

    pipeline = _object(root.get("pipeline"), "$.pipeline", errors)
    pipeline_allowed = {"stage", "geometry_outcome", "source_inputs", "generated_inputs", "master_mesh", "outputs", "audits", "provenance", "notes"}
    _unknown(pipeline, "$.pipeline", pipeline_allowed, errors)
    _required(pipeline, "$.pipeline", pipeline_allowed - {"notes"}, errors)
    stage, outcome = pipeline.get("stage"), pipeline.get("geometry_outcome")
    if not isinstance(stage, str) or stage not in STAGE_INDEX:
        errors.append(f"$.pipeline.stage: expected one of {', '.join(STAGES)}; got {stage!r}")
    if "geometry_outcome" in pipeline:
        _enum(outcome, "$.pipeline.geometry_outcome", OUTCOMES, errors)
    if isinstance(stage, str) and stage in STAGE_INDEX:
        selected = STAGE_INDEX[stage] >= STAGE_INDEX["geometry_origin_selected"]
        if selected and outcome == "undecided":
            errors.append("$.pipeline.geometry_outcome: must be decided at geometry_origin_selected or later")
        if not selected and outcome is not None and outcome != "undecided":
            errors.append("$.pipeline.geometry_outcome: must be 'undecided' before geometry_origin_selected")
    if outcome == "procedural_direct" and "procedural_blender" not in allowed_origins:
        errors.append("$.geometry.allowed_origins: must include 'procedural_blender' for procedural_direct")
    for field in ("source_inputs", "generated_inputs", "outputs"):
        _artifact_list(pipeline.get(field), f"$.pipeline.{field}", errors)

    master = pipeline.get("master_mesh")
    master_required = isinstance(stage, str) and stage in STAGE_INDEX and STAGE_INDEX[stage] >= STAGE_INDEX["master_mesh_candidate"]
    if master_required and master is None:
        errors.append("$.pipeline.master_mesh: required at master_mesh_candidate or later")
    if not master_required and master is not None:
        errors.append("$.pipeline.master_mesh: must be null before master_mesh_candidate")
    if master is not None:
        master_obj = _object(master, "$.pipeline.master_mesh", errors)
        _unknown(master_obj, "$.pipeline.master_mesh", {"status", "source_path", "exchange_path"}, errors)
        _required(master_obj, "$.pipeline.master_mesh", {"status", "source_path", "exchange_path"}, errors)
        if "status" in master_obj:
            _enum(master_obj["status"], "$.pipeline.master_mesh.status", {"candidate", "approved"}, errors)
            if master_obj["status"] == "approved" and isinstance(stage, str) and stage in STAGE_INDEX and STAGE_INDEX[stage] < STAGE_INDEX["geometry_audited"]:
                errors.append("$.pipeline.master_mesh.status: cannot be 'approved' before geometry_audited")
        for field in ("source_path", "exchange_path"):
            if field in master_obj:
                _repo_path(master_obj[field], f"$.pipeline.master_mesh.{field}", errors)

    audits = _object(pipeline.get("audits"), "$.pipeline.audits", errors)
    _unknown(audits, "$.pipeline.audits", {"geometry", "uv_textures"}, errors)
    _required(audits, "$.pipeline.audits", {"geometry", "uv_textures"}, errors)
    for field in ("geometry", "uv_textures"):
        if field in audits:
            _audit_reference(audits[field], f"$.pipeline.audits.{field}", errors)
    if "provenance" in pipeline and not isinstance(pipeline["provenance"], dict):
        errors.append("$.pipeline.provenance: expected object")

    return errors


def load_spec(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an Astrion Asset Spec v0.1 JSON file without writing anything.")
    parser.add_argument("spec", type=Path)
    args = parser.parse_args(argv)
    try:
        data = load_spec(args.spec)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read {args.spec}: {exc}", file=sys.stderr)
        return 2

    errors = validate_spec(data)
    if errors:
        print(f"INVALID {args.spec} ({len(errors)} error{'s' if len(errors) != 1 else ''})")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"VALID {args.spec} (Asset Spec v{SCHEMA_VERSION})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
