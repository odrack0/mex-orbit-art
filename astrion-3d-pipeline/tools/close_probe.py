#!/usr/bin/env python3
"""Close a reviewed Generative Probe and publish comparison evidence.

The command verifies the complete frozen lineage and every referenced file
before atomically publishing comparison.json and decision.json. It never
modifies an Asset Spec, candidate, Master Mesh, or audit state.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import intake_probe  # noqa: E402
import validate_probe  # noqa: E402


class CloseError(RuntimeError):
    pass


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        return intake_probe.load_json_object(path.resolve(), label)
    except intake_probe.IntakeError as exc:
        raise CloseError(str(exc)) from exc


def _verify_record(record: dict[str, Any], expected_type: str, label: str) -> None:
    errors = validate_probe.validate_record(record)
    if errors or record.get("record_type") != expected_type:
        raise CloseError(
            f"invalid {label}:\n  - " + "\n  - ".join(errors or [f"expected {expected_type}"])
        )


def _verify_hashed_path(item: dict[str, Any], art_root: Path, label: str) -> Path:
    try:
        path = intake_probe.resolve_repo_input(item["path"], art_root)
        intake_probe.ensure_file(path, label)
    except intake_probe.IntakeError as exc:
        raise CloseError(str(exc)) from exc
    actual = intake_probe.sha256_file(path)
    if actual != item["sha256"]:
        raise CloseError(f"{label} hash mismatch: expected {item['sha256']}, got {actual}")
    return path


def _identity_summary(evaluation: dict[str, Any]) -> dict[str, int]:
    result = {"pass": 0, "warning": 0, "fail": 0}
    for row in evaluation["identity_review"]:
        result[row["status"]] += 1
    return result


def close_probe(
    plan_path: Path,
    delivery_paths: list[Path],
    evaluation_paths: list[Path],
    decision_source_path: Path,
    art_root: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    plan_path = plan_path.resolve()
    plan = _load(plan_path, "probe plan")
    _verify_record(plan, "probe_plan", "probe plan")
    if plan.get("state") != "ready":
        raise CloseError("probe plan state must be 'ready'")
    run_dir = intake_probe.run_dir_for(plan, art_root)
    expected_plan = (run_dir / "probe-plan.json").resolve()
    if plan_path != expected_plan:
        raise CloseError(f"plan must be the frozen run plan: {expected_plan}")
    try:
        intake_probe.verify_plan_sources(plan, art_root)
    except intake_probe.IntakeError as exc:
        raise CloseError(str(exc)) from exc

    deliveries: list[dict[str, Any]] = []
    deliveries_by_candidate: dict[tuple[str, str], dict[str, Any]] = {}
    for raw_path in delivery_paths:
        path = raw_path.resolve()
        delivery = _load(path, "delivery manifest")
        _verify_record(delivery, "probe_delivery", "delivery manifest")
        key = (delivery["provider"], delivery["candidate_id"])
        if key in deliveries_by_candidate:
            raise CloseError(f"duplicate delivery for {key[0]}/{key[1]}")
        expected = (
            run_dir / "intake" / delivery["provider"] / delivery["candidate_id"] / "delivery.json"
        ).resolve()
        if path != expected:
            raise CloseError(f"delivery must be the candidate intake manifest: {expected}")
        if delivery["probe_plan"]["path"] != intake_probe.repo_relative(plan_path, art_root):
            raise CloseError(f"delivery {key[1]} references a different plan path")
        if delivery["probe_plan"]["sha256"] != intake_probe.sha256_file(plan_path):
            raise CloseError(f"delivery {key[1]} references a different plan hash")
        for index, item in enumerate(delivery["files"]):
            file_path = _verify_hashed_path(item, art_root, f"delivery {key[1]} file[{index}]")
            if file_path.stat().st_size != item["size_bytes"]:
                raise CloseError(f"delivery {key[1]} file[{index}] size mismatch")
        deliveries.append(delivery)
        deliveries_by_candidate[key] = delivery

    evaluations: list[dict[str, Any]] = []
    evaluations_by_candidate: dict[tuple[str, str], tuple[dict[str, Any], Path]] = {}
    for raw_path in evaluation_paths:
        path = raw_path.resolve()
        evaluation = _load(path, "candidate evaluation")
        _verify_record(evaluation, "candidate_evaluation", "candidate evaluation")
        if evaluation.get("state") != "evaluated":
            raise CloseError(f"candidate {evaluation.get('candidate_id')} must be evaluated before closeout")
        key = (evaluation["provider"], evaluation["candidate_id"])
        if key in evaluations_by_candidate:
            raise CloseError(f"duplicate evaluation for {key[0]}/{key[1]}")
        delivery = deliveries_by_candidate.get(key)
        if delivery is None:
            raise CloseError(f"evaluation {key[0]}/{key[1]} has no supplied delivery")
        expected = (
            run_dir / "diagnostics" / key[0] / key[1] / "candidate-evaluation.json"
        ).resolve()
        if path != expected:
            raise CloseError(f"evaluation must be the candidate run record: {expected}")
        delivery_path = _verify_hashed_path(evaluation["delivery"], art_root, f"{key[1]} delivery")
        if delivery_path != (
            run_dir / "intake" / key[0] / key[1] / "delivery.json"
        ).resolve():
            raise CloseError(f"evaluation {key[1]} references a different delivery")
        _verify_hashed_path(evaluation["input_model"], art_root, f"{key[1]} intake model")
        for index, artifact in enumerate(evaluation["derived_artifacts"]):
            _verify_hashed_path(artifact, art_root, f"{key[1]} derived artifact[{index}]")
        for index, artifact in enumerate(evaluation["diagnostics"]):
            _verify_hashed_path(artifact, art_root, f"{key[1]} diagnostic[{index}]")
        evaluations.append(evaluation)
        evaluations_by_candidate[key] = (evaluation, path)

    received_keys = {
        key for key, delivery in deliveries_by_candidate.items() if delivery["state"] == "received"
    }
    if set(evaluations_by_candidate) != received_keys:
        missing = sorted(received_keys - set(evaluations_by_candidate))
        extra = sorted(set(evaluations_by_candidate) - received_keys)
        raise CloseError(f"evaluations must cover every received branch; missing={missing}, extra={extra}")

    decision = _load(decision_source_path, "decision source")
    _verify_record(decision, "probe_decision", "decision source")
    if decision.get("state") != "closed":
        raise CloseError("decision source state must be 'closed'")
    decision_keys = {
        (item["provider"], item["candidate_id"]) for item in decision["evaluations"]
    }
    if decision_keys != set(evaluations_by_candidate):
        raise CloseError("decision must reference every supplied evaluated candidate exactly once")
    for item in decision["evaluations"]:
        evaluation, path = evaluations_by_candidate[(item["provider"], item["candidate_id"])]
        expected_path = intake_probe.repo_relative(path, art_root)
        if item["path"] != expected_path:
            raise CloseError(f"decision evaluation path mismatch for {item['candidate_id']}")
        actual_hash = intake_probe.sha256_file(path)
        if item["sha256"] != actual_hash:
            raise CloseError(f"decision evaluation hash mismatch for {item['candidate_id']}")
    record_set = [plan, *deliveries, *evaluations, decision]
    set_errors = validate_probe.validate_record_set(record_set)
    if set_errors:
        raise CloseError("invalid closeout record set:\n  - " + "\n  - ".join(set_errors))

    selected_key = None
    if decision["selected_candidate_id"] is not None:
        matches = [key for key in evaluations_by_candidate if key[1] == decision["selected_candidate_id"]]
        if len(matches) != 1:
            raise CloseError("selected_candidate_id is ambiguous or absent from evaluated candidates")
        selected_key = matches[0]
    comparison = {
        "schema_version": "0.1",
        "report_type": "generative_probe_comparison",
        "probe_id": plan["probe_id"],
        "asset_id": plan["asset_id"],
        "question": plan["question"],
        "references": plan["references"],
        "evaluation_profile": plan["evaluation_profile"],
        "candidates": [
            {
                "provider": evaluation["provider"],
                "candidate_id": evaluation["candidate_id"],
                "evaluation": {
                    "path": intake_probe.repo_relative(path, art_root),
                    "sha256": intake_probe.sha256_file(path),
                },
                "metrics": evaluation["metrics"],
                "topology_observations": evaluation["topology_observations"],
                "identity_summary": _identity_summary(evaluation),
                "suggested_outcome": evaluation["suggested_outcome"],
            }
            for evaluation, path in sorted(
                evaluations_by_candidate.values(), key=lambda item: (item[0]["provider"], item[0]["candidate_id"])
            )
        ],
        "decision": {
            "comparison_status": decision["comparison_status"],
            "selected_provider": selected_key[0] if selected_key else None,
            "selected_candidate_id": decision["selected_candidate_id"],
            "intended_outcome": decision["intended_outcome"],
            "rationale": decision["rationale"],
            "reviewer": decision["reviewer"],
            "reviewed_at": decision["reviewed_at"],
        },
        "authority": {
            "scope": "probe_evidence_only",
            "audit_1_result": None,
            "master_mesh_promoted": False,
            "production_handoff": decision["production_handoff"]["status"],
        },
    }

    report_dir = (
        art_root / "astrion-3d-pipeline" / "reports" / "generative-probes"
        / plan["asset_id"] / plan["probe_id"]
    ).resolve()
    reports_root = (art_root / "astrion-3d-pipeline" / "reports" / "generative-probes").resolve()
    try:
        report_dir.relative_to(reports_root)
    except ValueError as exc:
        raise CloseError(f"unsafe report directory: {report_dir}") from exc
    if report_dir.exists():
        raise CloseError(f"probe report directory already exists: {report_dir}")
    preview = {
        "action": "close_probe",
        "dry_run": dry_run,
        "probe_id": plan["probe_id"],
        "selected_candidate_id": decision["selected_candidate_id"],
        "intended_outcome": decision["intended_outcome"],
        "reviewer": decision["reviewer"],
        "report_dir": intake_probe.repo_relative(report_dir, art_root),
        "production_handoff": decision["production_handoff"]["status"],
    }
    if dry_run:
        return preview

    report_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{plan['probe_id']}-", dir=report_dir.parent))
    try:
        (temp_dir / "comparison.json").write_text(
            json.dumps(comparison, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (temp_dir / "decision.json").write_text(
            json.dumps(decision, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if report_dir.exists():
            raise CloseError(f"probe report directory appeared during closeout: {report_dir}")
        os.replace(temp_dir, report_dir)
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        raise
    return comparison


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Close a reviewed Generative Probe safely.")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--delivery", required=True, action="append", type=Path)
    parser.add_argument("--evaluation", required=True, action="append", type=Path)
    parser.add_argument("--decision-source", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    art_root = Path(__file__).resolve().parents[2]
    try:
        result = close_probe(
            args.plan,
            args.delivery,
            args.evaluation,
            args.decision_source,
            art_root,
            dry_run=args.dry_run,
        )
    except CloseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
