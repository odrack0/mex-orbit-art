#!/usr/bin/env python3
"""Safely initialize a probe run and intake explicit provider deliveries.

This tool performs no provider API/UI interaction. It freezes a reviewed plan,
copies explicitly named delivery files into an isolated run, verifies hashes
before and after copying, and writes a validated delivery manifest. It never
modifies its inputs or production assets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import validate_probe  # noqa: E402


FILE_ROLES = {"model", "texture", "preview", "metadata", "other"}
PROTECTED_LEGACY_PREFIXES = (
    ("source", "3d-models", "crudo"),
    ("source", "3d-models", "pulido"),
    ("source", "renders"),
)


class IntakeError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_relative(path: Path, art_root: Path) -> str:
    try:
        return path.resolve().relative_to(art_root.resolve()).as_posix()
    except ValueError as exc:
        raise IntakeError(f"output must remain inside repository: {path}") from exc


def resolve_repo_input(value: str, art_root: Path) -> Path:
    errors: list[str] = []
    validate_probe._repo_path(value, "path", errors)
    if errors:
        raise IntakeError(errors[0])
    result = (art_root / Path(value)).resolve()
    try:
        result.relative_to(art_root.resolve())
    except ValueError as exc:
        raise IntakeError(f"repository path escapes repository: {value}") from exc
    return result


def ensure_file(path: Path, label: str) -> None:
    if not path.exists():
        raise IntakeError(f"{label} does not exist: {path}")
    if not path.is_file():
        raise IntakeError(f"{label} is not a file: {path}")


def is_protected_legacy_input(path: Path, art_root: Path) -> bool:
    try:
        relative = path.resolve().relative_to(art_root.resolve())
    except ValueError:
        return False
    lowered = tuple(part.lower() for part in relative.parts)
    return any(lowered[:len(prefix)] == prefix for prefix in PROTECTED_LEGACY_PREFIXES)


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    ensure_file(path, label)
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IntakeError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise IntakeError(f"{label} must contain a JSON object: {path}")
    return value


def validate_plan_record(plan: dict[str, Any], *, ready_required: bool) -> None:
    errors = validate_probe.validate_record(plan)
    if errors:
        raise IntakeError("invalid probe plan:\n  - " + "\n  - ".join(errors))
    if plan.get("record_type") != "probe_plan":
        raise IntakeError("input record is not a probe_plan")
    if ready_required and plan.get("state") != "ready":
        raise IntakeError("probe plan state must be 'ready'")


def verify_plan_sources(plan: dict[str, Any], art_root: Path) -> None:
    references = [("asset_spec", plan["asset_spec"])]
    references.extend((f"references[{index}]", item) for index, item in enumerate(plan["references"]))
    for label, item in references:
        path = resolve_repo_input(item["path"], art_root)
        ensure_file(path, label)
        actual = sha256_file(path)
        if actual != item["sha256"]:
            raise IntakeError(
                f"{label} hash mismatch for {item['path']}: expected {item['sha256']}, got {actual}"
            )


def run_dir_for(plan: dict[str, Any], art_root: Path) -> Path:
    result = (
        art_root / "astrion-3d-pipeline" / "work" / "generative-probes"
        / plan["asset_id"] / plan["probe_id"]
    ).resolve()
    work_root = (art_root / "astrion-3d-pipeline" / "work" / "generative-probes").resolve()
    try:
        result.relative_to(work_root)
    except ValueError as exc:
        raise IntakeError(f"unsafe generated run directory: {result}") from exc
    return result


def initialize_plan(plan_source: Path, art_root: Path, *, dry_run: bool = False) -> dict[str, Any]:
    plan_source = plan_source.resolve()
    plan = load_json_object(plan_source, "probe plan")
    validate_plan_record(plan, ready_required=True)
    verify_plan_sources(plan, art_root)
    run_dir = run_dir_for(plan, art_root)
    destination = run_dir / "probe-plan.json"
    if plan_source == destination.resolve():
        raise IntakeError("plan source already is the frozen run plan")
    if run_dir.exists():
        raise IntakeError(f"probe run already exists: {run_dir}")
    source_hash = sha256_file(plan_source)
    result = {
        "action": "initialize_probe",
        "dry_run": dry_run,
        "probe_id": plan["probe_id"],
        "asset_id": plan["asset_id"],
        "source": str(plan_source),
        "destination": repo_relative(destination, art_root),
        "sha256": source_hash,
        "size_bytes": plan_source.stat().st_size,
    }
    if dry_run:
        return result

    run_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{plan['probe_id']}-", dir=run_dir.parent))
    try:
        copied = temp_dir / "probe-plan.json"
        shutil.copyfile(plan_source, copied)
        if sha256_file(copied) != source_hash or sha256_file(plan_source) != source_hash:
            raise IntakeError("probe plan changed while being frozen")
        if run_dir.exists():
            raise IntakeError(f"probe run appeared during initialization: {run_dir}")
        os.replace(temp_dir, run_dir)
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        raise
    return result


def media_type(path: Path, role: str) -> str:
    if path.suffix.lower() == ".glb":
        return "model/gltf-binary"
    if path.suffix.lower() == ".gltf":
        return "model/gltf+json"
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    return "application/octet-stream" if role != "metadata" else "application/json"


def parse_file_spec(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("expected ROLE=PATH")
    role, value = raw.split("=", 1)
    if role not in FILE_ROLES:
        raise argparse.ArgumentTypeError(f"ROLE must be one of {', '.join(sorted(FILE_ROLES))}")
    if not value:
        raise argparse.ArgumentTypeError("PATH must not be empty")
    return role, Path(value)


def _provider_request(plan: dict[str, Any], provider: str) -> dict[str, Any]:
    matches = [item for item in plan["providers"] if item["provider"] == provider]
    if not matches:
        raise IntakeError(f"provider {provider!r} is not declared by the probe plan")
    if len(matches) != 1:
        raise IntakeError(f"provider {provider!r} is ambiguous in the probe plan")
    return matches[0]


def receive_delivery(
    plan_path: Path,
    art_root: Path,
    *,
    provider: str,
    candidate_id: str,
    files: list[tuple[str, Path]],
    delivered_by: str,
    model_name: str = "unknown",
    settings: dict[str, Any] | None = None,
    external_job_id: str | None = None,
    seed: str | int | None = None,
    generated_at: str | None = None,
    license_name: str = "unknown",
    delivered_at: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    plan_path = plan_path.resolve()
    plan = load_json_object(plan_path, "frozen probe plan")
    validate_plan_record(plan, ready_required=True)
    verify_plan_sources(plan, art_root)
    run_dir = run_dir_for(plan, art_root)
    expected_plan = (run_dir / "probe-plan.json").resolve()
    if plan_path != expected_plan:
        raise IntakeError(f"plan must be the frozen run plan: {expected_plan}")
    ensure_file(plan_path, "frozen probe plan")
    request = _provider_request(plan, provider)
    id_errors: list[str] = []
    validate_probe._identifier(candidate_id, "candidate_id", id_errors)
    if id_errors:
        raise IntakeError(id_errors[0])
    if not files:
        raise IntakeError("at least one delivery file is required")
    if not any(role == "model" for role, _ in files):
        raise IntakeError("a received delivery requires at least one model file")

    candidate_dir = run_dir / "intake" / provider / candidate_id
    if candidate_dir.exists():
        raise IntakeError(f"candidate intake already exists: {candidate_dir}")
    sources: list[tuple[str, Path, str, int, str]] = []
    target_names: list[str] = []
    for role, raw_path in files:
        if role not in FILE_ROLES:
            raise IntakeError(f"invalid file role: {role}")
        source = raw_path.resolve()
        ensure_file(source, f"{role} delivery file")
        if is_protected_legacy_input(source, art_root):
            raise IntakeError(
                f"legacy source is not accepted by the fresh M5 flow: {source}; use a future declared migration"
            )
        target_name = source.name
        if target_name.lower() in target_names:
            raise IntakeError(f"delivery filenames collide in candidate intake: {target_name}")
        target_names.append(target_name.lower())
        sources.append((role, source, sha256_file(source), source.stat().st_size, media_type(source, role)))

    plan_hash = sha256_file(plan_path)
    timestamp = delivered_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    file_records = []
    for role, source, digest, size, mime in sources:
        destination = candidate_dir / source.name
        file_records.append({
            "path": repo_relative(destination, art_root),
            "role": role,
            "media_type": mime,
            "sha256": digest,
            "size_bytes": size,
        })
    record = {
        "schema_version": "0.1",
        "record_type": "probe_delivery",
        "probe_id": plan["probe_id"],
        "asset_id": plan["asset_id"],
        "state": "received",
        "probe_plan": {
            "path": repo_relative(plan_path, art_root),
            "sha256": plan_hash,
        },
        "provider": provider,
        "request_id": request["request_id"],
        "candidate_id": candidate_id,
        "provenance": {
            "delivery_mode": request["delivery_mode"],
            "external_job_id": external_job_id,
            "model": model_name,
            "generation_mode": request["generation_mode"],
            "settings": settings if settings is not None else {},
            "seed": seed,
            "generated_at": generated_at,
            "license": license_name,
        },
        "files": file_records,
        "delivered_at": timestamp,
        "delivered_by": delivered_by,
    }
    errors = validate_probe.validate_record(record)
    if errors:
        raise IntakeError("generated delivery record is invalid:\n  - " + "\n  - ".join(errors))
    if dry_run:
        return record

    candidate_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{candidate_id}-", dir=candidate_dir.parent))
    try:
        for role, source, digest, _size, _mime in sources:
            copied = temp_dir / source.name
            shutil.copyfile(source, copied)
            if sha256_file(copied) != digest or sha256_file(source) != digest:
                raise IntakeError(f"{role} delivery file changed while being copied: {source}")
        manifest = temp_dir / "delivery.json"
        manifest.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        persisted = load_json_object(manifest, "generated delivery manifest")
        persisted_errors = validate_probe.validate_record(persisted)
        if persisted_errors:
            raise IntakeError("persisted delivery record is invalid:\n  - " + "\n  - ".join(persisted_errors))
        if candidate_dir.exists():
            raise IntakeError(f"candidate intake appeared during copy: {candidate_dir}")
        os.replace(temp_dir, candidate_dir)
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        raise
    return record


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Freeze a Generative Probe plan or safely intake an explicit provider delivery."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="freeze a ready plan into its isolated run directory")
    init.add_argument("--plan-source", required=True, type=Path)
    init.add_argument("--dry-run", action="store_true")

    receive = subparsers.add_parser("receive", help="copy and register explicit delivery files")
    receive.add_argument("--plan", required=True, type=Path)
    receive.add_argument("--provider", required=True, choices=sorted(validate_probe.PROVIDERS))
    receive.add_argument("--candidate-id", required=True)
    receive.add_argument("--file", action="append", type=parse_file_spec, required=True, metavar="ROLE=PATH")
    receive.add_argument("--delivered-by", required=True)
    receive.add_argument("--model-name", default="unknown")
    receive.add_argument("--settings-json", type=Path)
    receive.add_argument("--external-job-id")
    receive.add_argument("--seed")
    receive.add_argument("--generated-at")
    receive.add_argument("--license", dest="license_name", default="unknown")
    receive.add_argument("--delivered-at")
    receive.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    art_root = Path(__file__).resolve().parents[2]
    try:
        if args.command == "init":
            result = initialize_plan(args.plan_source, art_root, dry_run=args.dry_run)
        else:
            settings = {}
            if args.settings_json is not None:
                settings = load_json_object(args.settings_json.resolve(), "provider settings")
            result = receive_delivery(
                args.plan,
                art_root,
                provider=args.provider,
                candidate_id=args.candidate_id,
                files=args.file,
                delivered_by=args.delivered_by,
                model_name=args.model_name,
                settings=settings,
                external_job_id=args.external_job_id,
                seed=args.seed,
                generated_at=args.generated_at,
                license_name=args.license_name,
                delivered_at=args.delivered_at,
                dry_run=args.dry_run,
            )
    except IntakeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
