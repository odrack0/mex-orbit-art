#!/usr/bin/env python3
"""Publish an explicit identity review for one measured probe candidate.

The measurement, delivery, input model, and diagnostic hashes are verified
before a separate evaluated record is written. The measured record remains
immutable. This tool records a suggested outcome only; it cannot select a
candidate, create a Master Mesh, or set an Audit 1 result.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import intake_probe  # noqa: E402
import validate_probe  # noqa: E402


class ReviewError(RuntimeError):
    pass


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        return intake_probe.load_json_object(path.resolve(), label)
    except intake_probe.IntakeError as exc:
        raise ReviewError(str(exc)) from exc


def _resolve_repo(value: str, art_root: Path, label: str) -> Path:
    try:
        path = intake_probe.resolve_repo_input(value, art_root)
        intake_probe.ensure_file(path, label)
        return path
    except intake_probe.IntakeError as exc:
        raise ReviewError(str(exc)) from exc


def _verify_hashed_file(item: dict[str, Any], art_root: Path, label: str) -> Path:
    path = _resolve_repo(item["path"], art_root, label)
    actual = intake_probe.sha256_file(path)
    if actual != item["sha256"]:
        raise ReviewError(f"{label} hash mismatch: expected {item['sha256']}, got {actual}")
    return path


def _validate_review_source(review: dict[str, Any], measurement: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    allowed = {"identity_review", "suggested_outcome", "reviewed_at", "reviewed_by", "notes"}
    missing = allowed - {"notes"} - set(review)
    unknown = set(review) - allowed
    if missing:
        errors.append("missing fields: " + ", ".join(sorted(missing)))
    if unknown:
        errors.append("unknown fields: " + ", ".join(sorted(unknown)))
    rows = review.get("identity_review")
    if not isinstance(rows, list):
        errors.append("identity_review must be an array")
        return errors
    measured_criteria = [row.get("criterion") for row in measurement["identity_review"]]
    reviewed_criteria = [row.get("criterion") for row in rows if isinstance(row, dict)]
    if reviewed_criteria != measured_criteria:
        errors.append("identity_review criteria must exactly match the measured record and its order")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"identity_review[{index}] must be an object")
            continue
        if set(row) != {"criterion", "status", "notes"}:
            errors.append(f"identity_review[{index}] must contain only criterion, status, and notes")
        if row.get("status") not in {"pass", "warning", "fail"}:
            errors.append(f"identity_review[{index}].status must be pass, warning, or fail")
        if not isinstance(row.get("notes"), str) or not row.get("notes", "").strip():
            errors.append(f"identity_review[{index}].notes must be a non-empty string")
    if review.get("suggested_outcome") not in validate_probe.OUTCOMES:
        errors.append("suggested_outcome must be an Astrion geometry outcome")
    for field in ("reviewed_at", "reviewed_by"):
        if not isinstance(review.get(field), str) or not review.get(field, "").strip():
            errors.append(f"{field} must be a non-empty string")
    return errors


def publish_review(
    measurement_path: Path,
    review_source_path: Path,
    art_root: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    measurement_path = measurement_path.resolve()
    measurement = _load(measurement_path, "candidate measurement")
    errors = validate_probe.validate_record(measurement)
    if errors or measurement.get("record_type") != "candidate_evaluation":
        raise ReviewError(
            "invalid candidate measurement:\n  - "
            + "\n  - ".join(errors or ["wrong record_type"])
        )
    if measurement.get("state") != "measured":
        raise ReviewError("candidate measurement state must be 'measured'")

    expected_dir = (
        art_root / "astrion-3d-pipeline" / "work" / "generative-probes"
        / measurement["asset_id"] / measurement["probe_id"] / "diagnostics"
        / measurement["provider"] / measurement["candidate_id"]
    ).resolve()
    expected_measurement = expected_dir / "candidate-measurement.json"
    if measurement_path != expected_measurement:
        raise ReviewError(f"measurement must be the candidate run record: {expected_measurement}")

    delivery_path = _verify_hashed_file(measurement["delivery"], art_root, "delivery manifest")
    delivery = _load(delivery_path, "delivery manifest")
    plan_path = _verify_hashed_file(delivery["probe_plan"], art_root, "frozen probe plan")
    plan = _load(plan_path, "frozen probe plan")
    _verify_hashed_file(measurement["input_model"], art_root, "intake model")
    for index, artifact in enumerate(measurement["diagnostics"]):
        _verify_hashed_file(artifact, art_root, f"diagnostic[{index}]")
    set_errors = validate_probe.validate_record_set([plan, delivery, measurement])
    if set_errors:
        raise ReviewError("invalid measurement lineage:\n  - " + "\n  - ".join(set_errors))

    review = _load(review_source_path, "review source")
    review_errors = _validate_review_source(review, measurement)
    if review_errors:
        raise ReviewError("invalid review source:\n  - " + "\n  - ".join(review_errors))

    evaluation = copy.deepcopy(measurement)
    evaluation["state"] = "evaluated"
    evaluation["identity_review"] = review["identity_review"]
    evaluation["suggested_outcome"] = review["suggested_outcome"]
    evaluation["evaluated_at"] = review["reviewed_at"]
    evaluation["evaluated_by"] = review["reviewed_by"]
    evaluation["notes"] = review.get(
        "notes",
        "Explicit identity review of probe evidence; this is not an Audit 1 result.",
    )
    record_errors = validate_probe.validate_record(evaluation)
    set_errors = validate_probe.validate_record_set([plan, delivery, evaluation])
    if record_errors or set_errors:
        raise ReviewError(
            "generated evaluation is invalid:\n  - " + "\n  - ".join(record_errors + set_errors)
        )

    output_path = expected_dir / "candidate-evaluation.json"
    if output_path.exists():
        raise ReviewError(f"candidate evaluation already exists: {output_path}")
    preview = {
        "action": "publish_probe_review",
        "dry_run": dry_run,
        "probe_id": evaluation["probe_id"],
        "provider": evaluation["provider"],
        "candidate_id": evaluation["candidate_id"],
        "measurement_sha256": intake_probe.sha256_file(measurement_path),
        "suggested_outcome": evaluation["suggested_outcome"],
        "output": intake_probe.repo_relative(output_path, art_root),
    }
    if dry_run:
        return preview

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", delete=False,
            prefix=".candidate-evaluation-", suffix=".json", dir=expected_dir,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(evaluation, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
        if output_path.exists():
            raise ReviewError(f"candidate evaluation appeared during review: {output_path}")
        os.replace(temp_path, output_path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    return evaluation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish an explicit review for a measured Generative Probe candidate."
    )
    parser.add_argument("--measurement", required=True, type=Path)
    parser.add_argument("--review-source", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    art_root = Path(__file__).resolve().parents[2]
    try:
        result = publish_review(
            args.measurement, args.review_source, art_root, dry_run=args.dry_run
        )
    except ReviewError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
