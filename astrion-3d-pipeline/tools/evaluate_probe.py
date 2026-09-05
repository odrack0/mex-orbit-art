#!/usr/bin/env python3
"""Measure one intaken generative candidate without granting Audit 1 status.

The tool verifies the frozen plan, delivery manifest, and model hashes; loads
the active GLB scene with node transforms; reuses Astrion's geometry metric
engine; and writes an isolated measurement plus diagnostics. Identity remains
not_assessed and no geometry outcome is selected automatically.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import audit_geometry  # noqa: E402
import intake_probe  # noqa: E402
import validate_probe  # noqa: E402
from _mesh_engine import load_mesh_metrics  # noqa: E402
from glb_scene import load_glb_scene, read_glb_document  # noqa: E402
from validate_spec import validate_spec  # noqa: E402


TOOL_VERSION = "astrion-probe-measurement/0.1"


class EvaluationError(RuntimeError):
    pass


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        return intake_probe.load_json_object(path, label)
    except intake_probe.IntakeError as exc:
        raise EvaluationError(str(exc)) from exc


def _repo_relative(path: Path, art_root: Path) -> str:
    try:
        return intake_probe.repo_relative(path, art_root)
    except intake_probe.IntakeError as exc:
        raise EvaluationError(str(exc)) from exc


def _resolve_inputs(plan_path: Path, delivery_path: Path, art_root: Path):
    plan_path = plan_path.resolve()
    delivery_path = delivery_path.resolve()
    plan = _load_object(plan_path, "probe plan")
    plan_errors = validate_probe.validate_record(plan)
    if plan_errors or plan.get("record_type") != "probe_plan":
        raise EvaluationError("invalid probe plan:\n  - " + "\n  - ".join(plan_errors or ["wrong record_type"]))
    if plan.get("state") != "ready":
        raise EvaluationError("probe plan state must be 'ready'")
    run_dir = intake_probe.run_dir_for(plan, art_root)
    expected_plan = (run_dir / "probe-plan.json").resolve()
    if plan_path != expected_plan:
        raise EvaluationError(f"plan must be the frozen run plan: {expected_plan}")
    try:
        intake_probe.verify_plan_sources(plan, art_root)
    except intake_probe.IntakeError as exc:
        raise EvaluationError(str(exc)) from exc

    delivery = _load_object(delivery_path, "delivery manifest")
    delivery_errors = validate_probe.validate_record(delivery)
    if delivery_errors or delivery.get("record_type") != "probe_delivery":
        raise EvaluationError(
            "invalid delivery manifest:\n  - " + "\n  - ".join(delivery_errors or ["wrong record_type"])
        )
    set_errors = validate_probe.validate_record_set([plan, delivery])
    if set_errors:
        raise EvaluationError("invalid plan/delivery relationship:\n  - " + "\n  - ".join(set_errors))
    if delivery.get("state") != "received":
        raise EvaluationError("only a received delivery can be measured")
    if delivery["probe_plan"]["sha256"] != intake_probe.sha256_file(plan_path):
        raise EvaluationError("delivery is not bound to the current frozen plan hash")

    expected_delivery = (
        run_dir / "intake" / delivery["provider"] / delivery["candidate_id"] / "delivery.json"
    ).resolve()
    if delivery_path != expected_delivery:
        raise EvaluationError(f"delivery must be the candidate intake manifest: {expected_delivery}")
    model_records = [item for item in delivery["files"] if item["role"] == "model"]
    if len(model_records) != 1:
        raise EvaluationError("probe measurement v0.1 requires exactly one delivered model file")
    model_record = model_records[0]
    try:
        model_path = intake_probe.resolve_repo_input(model_record["path"], art_root)
        intake_probe.ensure_file(model_path, "delivered model")
    except intake_probe.IntakeError as exc:
        raise EvaluationError(str(exc)) from exc
    actual_hash = intake_probe.sha256_file(model_path)
    if actual_hash != model_record["sha256"]:
        raise EvaluationError(
            f"delivered model hash mismatch: expected {model_record['sha256']}, got {actual_hash}"
        )
    if model_path.stat().st_size != model_record["size_bytes"]:
        raise EvaluationError("delivered model size no longer matches its manifest")

    spec_path = intake_probe.resolve_repo_input(plan["asset_spec"]["path"], art_root)
    spec = _load_object(spec_path, "Asset Spec")
    spec_errors = validate_spec(spec)
    if spec_errors:
        raise EvaluationError("invalid Asset Spec:\n  - " + "\n  - ".join(spec_errors))
    if plan["asset_spec"]["sha256"] != intake_probe.sha256_file(spec_path):
        raise EvaluationError("Asset Spec no longer matches the hash frozen in the plan")

    output_dir = (
        run_dir / "diagnostics" / delivery["provider"] / delivery["candidate_id"]
    ).resolve()
    return plan, delivery, spec, model_path, delivery_path, output_dir


def _observation(code: str, severity: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


def _topology_observations(metrics: dict[str, Any], scene, spec: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key, code, label in (
        ("degenerate_tris", "degenerate_triangles", "degenerate triangles"),
        ("duplicate_faces", "duplicate_faces", "duplicate faces"),
        ("nonmanifold_edges", "nonmanifold_edges", "non-manifold edges"),
    ):
        count = int(metrics.get(key, 0))
        if count:
            rows.append(_observation(code, "error", f"Detected {count} {label}."))
    boundary = int(metrics.get("boundary_edges", 0))
    if boundary:
        rows.append(_observation(
            "boundary_edges", "warning",
            f"Detected {boundary} boundary edges; probe evidence does not decide whether they are intentional.",
        ))
    triangles = int(metrics.get("tris", 0))
    target = int(spec["geometry"]["soft_triangle_target"])
    ceiling = int(spec["geometry"]["triangle_ceiling"])
    if triangles > ceiling:
        rows.append(_observation(
            "triangle_ceiling_exceeded", "warning",
            f"Candidate has {triangles} triangles versus the future Master Mesh ceiling of {ceiling}.",
        ))
    elif triangles > target:
        rows.append(_observation(
            "triangle_soft_target_exceeded", "info",
            f"Candidate has {triangles} triangles versus the planning target of {target}.",
        ))
    components = len(scene.components)
    limits = spec["geometry"]["components"]
    if not int(limits["min"]) <= components <= int(limits["max"]):
        rows.append(_observation(
            "component_count_outside_plan", "warning",
            f"Active scene has {components} mesh components; the future Master Mesh range is {limits['min']}..{limits['max']}.",
        ))
    if not scene.normals_complete:
        rows.append(_observation("normals_missing", "warning", "One or more active primitives have no normal stream."))
    if scene.transformed_node_count:
        rows.append(_observation(
            "node_transforms_applied", "info",
            f"Applied {scene.transformed_node_count} non-identity node transforms for measurement.",
        ))
    return rows


def _identity_placeholders(spec: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for prefix, values in (
        ("major mass", spec["visual"]["major_masses"]),
        ("identity feature", spec["visual"]["identity_features"]),
    ):
        for value in values:
            rows.append({
                "criterion": f"{prefix}: {value}",
                "status": "not_assessed",
                "notes": "Compare the generated diagnostic with the frozen geometry reference before suggesting an outcome.",
            })
    return rows


def _base_record(
    plan: dict[str, Any],
    delivery: dict[str, Any],
    delivery_path: Path,
    model_path: Path,
    art_root: Path,
) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "record_type": "candidate_evaluation",
        "probe_id": plan["probe_id"],
        "asset_id": plan["asset_id"],
        "provider": delivery["provider"],
        "request_id": delivery["request_id"],
        "candidate_id": delivery["candidate_id"],
        "delivery": {
            "path": _repo_relative(delivery_path, art_root),
            "sha256": intake_probe.sha256_file(delivery_path),
        },
        "input_model": {
            "path": _repo_relative(model_path, art_root),
            "sha256": intake_probe.sha256_file(model_path),
        },
    }


def _invalid_record(base: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        **base,
        "state": "invalid",
        "derived_artifacts": [],
        "diagnostics": [],
        "metrics": {
            "parse_status": "invalid",
            "triangles": None,
            "vertices": None,
            "mesh_count": None,
            "primitive_count": None,
            "material_count": None,
            "connected_components": None,
            "bounds": None,
        },
        "topology_observations": [_observation("parse_failed", "error", message)],
        "identity_review": [],
        "suggested_outcome": None,
        "evaluated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "evaluated_by": TOOL_VERSION,
        "notes": "Invalid probe measurement record; this is not an Audit 1 result.",
    }


def _measured_record(
    base: dict[str, Any],
    plan: dict[str, Any],
    spec: dict[str, Any],
    delivery: dict[str, Any],
    scene,
    document: dict[str, Any],
    metrics: dict[str, Any],
    connected_components: int,
    diagnostic_records: list[dict[str, str]],
    *,
    heavy: bool,
) -> dict[str, Any]:
    dimensions = scene.vertices.max(axis=0) - scene.vertices.min(axis=0)
    return {
        **base,
        "state": "measured",
        "derived_artifacts": [],
        "diagnostics": diagnostic_records,
        "metrics": {
            "parse_status": "usable",
            "triangles": int(len(scene.faces)),
            "vertices": int(len(scene.vertices)),
            "mesh_count": int(len(scene.components)),
            "primitive_count": int(sum(item["primitive_count"] for item in scene.components)),
            "material_count": int(len(document.get("materials", []))),
            "connected_components": connected_components,
            "bounds": {
                "x": round(float(dimensions[0]), 9),
                "y": round(float(dimensions[1]), 9),
                "z": round(float(dimensions[2]), 9),
            },
        },
        "topology_observations": _topology_observations(metrics, scene, spec),
        "identity_review": _identity_placeholders(spec),
        "suggested_outcome": None,
        "evaluated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "evaluated_by": TOOL_VERSION,
        "notes": (
            f"Automated {'full' if heavy else 'fast'} probe measurement. "
            "Identity remains not_assessed and this record is not an Audit 1 result."
        ),
    }


def measure_candidate(
    plan_path: Path,
    delivery_path: Path,
    art_root: Path,
    *,
    heavy: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    plan, delivery, spec, model_path, delivery_path, output_dir = _resolve_inputs(
        plan_path, delivery_path, art_root
    )
    if output_dir.exists():
        raise EvaluationError(f"candidate diagnostics already exist: {output_dir}")
    preview = {
        "action": "measure_probe_candidate",
        "dry_run": dry_run,
        "probe_id": plan["probe_id"],
        "provider": delivery["provider"],
        "candidate_id": delivery["candidate_id"],
        "input_model": _repo_relative(model_path, art_root),
        "input_sha256": intake_probe.sha256_file(model_path),
        "output_dir": _repo_relative(output_dir, art_root),
        "mode": "full" if heavy else "fast",
    }
    if dry_run:
        return preview

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{delivery['candidate_id']}-", dir=output_dir.parent))
    base = _base_record(plan, delivery, delivery_path, model_path, art_root)
    try:
        try:
            document = read_glb_document(model_path)
            scene = load_glb_scene(model_path)
            source_dimensions = scene.vertices.max(axis=0) - scene.vertices.min(axis=0)
            source_footprint = float(max(source_dimensions[0], source_dimensions[2]))
            if source_footprint <= 1e-12:
                raise ValueError("candidate has zero X/Z footprint")
            scale = float(plan["evaluation_profile"]["screen_size_world_units"]) / source_footprint
            vertices = scene.vertices * scale
            engine, backend = load_mesh_metrics(Path(__file__).resolve().parents[2])
            metrics_raw = engine.analyse(
                vertices,
                scene.faces,
                UV=None,
                N=scene.normals,
                name=delivery["candidate_id"],
                heavy=heavy,
                res=384,
                px_per_unit=audit_geometry.PX_PER_UNIT_1440 if heavy else None,
            )
            metrics = audit_geometry._metric_subset(metrics_raw)
            islands = engine.analyse_islands(vertices, scene.faces, UV=None)
            diagnostic_path, diagnostic_stats = audit_geometry.write_gameplay_diagnostic(
                engine, vertices, scene.faces, delivery["candidate_id"], temp_dir
            )
            detail_path = temp_dir / "metrics-detail.json"
            final_diagnostic = output_dir / diagnostic_path.name
            final_detail = output_dir / detail_path.name
            diagnostic_stats["path"] = _repo_relative(final_diagnostic, art_root)
            detail = {
                "schema_version": "0.1",
                "record_type": "probe_metrics_detail",
                "tool_version": TOOL_VERSION,
                "probe_id": plan["probe_id"],
                "provider": delivery["provider"],
                "candidate_id": delivery["candidate_id"],
                "input_model": base["input_model"],
                "mode": "full" if heavy else "fast",
                "runtime": {
                    "python": ".".join(str(value) for value in sys.version_info[:3]),
                    "numpy": np.__version__,
                    "spatial_query_backend": backend,
                },
                "normalization": {
                    "mutated_input": False,
                    "in_memory_uniform_scale": round(scale, 12),
                    "declared_screen_size_world_units": plan["evaluation_profile"]["screen_size_world_units"],
                    "source_bounds": [round(float(value), 9) for value in source_dimensions],
                },
                "scene": {
                    "active_scene": scene.active_scene,
                    "transformed_node_count": scene.transformed_node_count,
                    "normals_complete": scene.normals_complete,
                    "components": scene.components,
                    "nodes": scene.nodes,
                },
                "metrics": metrics,
                "islands": audit_geometry._json_value(islands),
                "gameplay_diagnostic": diagnostic_stats,
            }
            detail_path.write_text(
                json.dumps(detail, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            diagnostic_records = [
                {
                    "path": _repo_relative(final_diagnostic, art_root),
                    "role": "gameplay-silhouette",
                    "sha256": intake_probe.sha256_file(diagnostic_path),
                },
                {
                    "path": _repo_relative(final_detail, art_root),
                    "role": "geometry-metrics-detail",
                    "sha256": intake_probe.sha256_file(detail_path),
                },
            ]
            record = _measured_record(
                base, plan, spec, delivery, scene, document, metrics,
                len(islands), diagnostic_records, heavy=heavy,
            )
        except (OSError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
            record = _invalid_record(base, f"Could not measure delivered GLB: {exc}")

        record_errors = validate_probe.validate_record(record)
        if record_errors:
            raise EvaluationError("generated measurement is invalid:\n  - " + "\n  - ".join(record_errors))
        measurement_path = temp_dir / "candidate-measurement.json"
        measurement_path.write_text(
            json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if output_dir.exists():
            raise EvaluationError(f"candidate diagnostics appeared during measurement: {output_dir}")
        os.replace(temp_dir, output_dir)
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        raise
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure one intaken Generative Probe candidate without running Audit 1."
    )
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--delivery", required=True, type=Path)
    parser.add_argument("--fast", action="store_true", help="skip multi-view visibility metrics")
    parser.add_argument("--dry-run", action="store_true", help="validate and show paths without writing")
    args = parser.parse_args(argv)
    art_root = Path(__file__).resolve().parents[2]
    try:
        result = measure_candidate(
            args.plan, args.delivery, art_root,
            heavy=not args.fast,
            dry_run=args.dry_run,
        )
    except EvaluationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result.get("state") == "invalid" else 0


if __name__ == "__main__":
    raise SystemExit(main())
