#!/usr/bin/env python3
"""Read-only validator for Astrion Generative Probe records v0.1.

The validator uses only the Python standard library. It validates individual
records and, when several are supplied, their shared probe identity and
references. It never checks path existence, hashes files, invokes providers,
or writes output.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "0.1"
RECORD_TYPES = {
    "probe_plan",
    "probe_delivery",
    "candidate_evaluation",
    "probe_decision",
}
PROVIDERS = {"meshy", "tripo"}
PLAN_STATES = {"draft", "ready", "skipped", "cancelled"}
DELIVERY_STATES = {"received", "invalid", "withdrawn"}
EVALUATION_STATES = {"measured", "evaluated", "invalid"}
DELIVERY_MODES = {"manual", "adapter"}
GENERATION_MODES = {"image_to_3d", "multi_image_to_3d", "text_to_3d", "other"}
OUTCOMES = {"accept_normalize", "repair", "rebuild_reference", "procedural_direct"}
COMPARISON_STATUSES = {
    "candidate_selected", "procedural_direct", "more_evidence_required",
    "no_selection", "skipped",
}
SENSITIVE_KEYS = {
    "api_key", "apikey", "authorization", "cookie", "cookies", "password",
    "secret", "token", "access_token", "refresh_token",
}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _object(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path}: expected object")
        return {}
    return value


def _unknown(obj: Any, path: str, allowed: set[str], errors: list[str]) -> None:
    if isinstance(obj, dict):
        for key in sorted(set(obj) - allowed):
            errors.append(f"{path}.{key}: unknown field")


def _required(obj: dict[str, Any], path: str, keys: set[str], errors: list[str]) -> None:
    for key in sorted(keys - set(obj)):
        errors.append(f"{path}.{key}: required field is missing")


def _string(value: Any, path: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}: expected non-empty string")
        return False
    return True


def _enum(value: Any, path: str, choices: set[str], errors: list[str]) -> None:
    if not isinstance(value, str) or value not in choices:
        errors.append(f"{path}: expected one of {', '.join(sorted(choices))}; got {value!r}")


def _identifier(value: Any, path: str, errors: list[str]) -> None:
    if _string(value, path, errors) and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
        errors.append(f"{path}: use lowercase kebab-case")


def _check_sha256(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        errors.append(f"{path}: expected lowercase SHA-256 hex digest")


def _timestamp(value: Any, path: str, errors: list[str], *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not _string(value, path, errors):
        return
    assert isinstance(value, str)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{path}: expected RFC 3339 timestamp with timezone")
        return
    if parsed.tzinfo is None:
        errors.append(f"{path}: expected RFC 3339 timestamp with timezone")


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


def _under_run_path(
    value: Any,
    path: str,
    errors: list[str],
    *,
    asset_id: Any,
    probe_id: Any,
    area: str,
    provider: Any | None = None,
    candidate_id: Any | None = None,
) -> None:
    _repo_path(value, path, errors)
    if not all(isinstance(item, str) and item for item in (value, asset_id, probe_id)):
        return
    segments = ["astrion-3d-pipeline", "work", "generative-probes", asset_id, probe_id, area]
    if provider is not None:
        if not isinstance(provider, str):
            return
        segments.append(provider)
    if candidate_id is not None:
        if not isinstance(candidate_id, str):
            return
        segments.append(candidate_id)
    prefix = "/".join(segments) + "/"
    if not value.startswith(prefix):
        errors.append(f"{path}: must be inside {prefix}")


def _string_list(value: Any, path: str, errors: list[str], *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{path}: expected array")
        return []
    if nonempty and not value:
        errors.append(f"{path}: expected at least one item")
    result = []
    for index, item in enumerate(value):
        if _string(item, f"{path}[{index}]", errors):
            result.append(item)
    if len(result) != len(set(result)):
        errors.append(f"{path}: duplicate items are not allowed")
    return result


def _reject_sensitive_keys(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
            parts = set(normalized.split("_"))
            compound_markers = {"api_key", "access_token", "refresh_token"}
            if (
                normalized in SENSITIVE_KEYS
                or any(marker in normalized for marker in compound_markers)
                or parts.intersection({"authorization", "cookie", "cookies", "password", "secret", "token"})
            ):
                errors.append(f"{path}.{key}: sensitive credential field is forbidden")
            _reject_sensitive_keys(child, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_keys(child, f"{path}[{index}]", errors)


def _hashed_path(raw: Any, path: str, errors: list[str]) -> dict[str, Any]:
    value = _object(raw, path, errors)
    _unknown(value, path, {"path", "sha256"}, errors)
    _required(value, path, {"path", "sha256"}, errors)
    if "path" in value:
        _repo_path(value["path"], f"{path}.path", errors)
    if "sha256" in value:
        _check_sha256(value["sha256"], f"{path}.sha256", errors)
    return value


def _validate_header(root: dict[str, Any], record_type: str, errors: list[str]) -> None:
    if root.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"$.schema_version: expected {SCHEMA_VERSION!r}; got {root.get('schema_version')!r}")
    if root.get("record_type") != record_type:
        errors.append(f"$.record_type: expected {record_type!r}; got {root.get('record_type')!r}")
    for field in ("probe_id", "asset_id"):
        if field in root:
            _identifier(root[field], f"$.{field}", errors)


def validate_plan(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        _object(data, "$", errors)
        return errors
    root = data
    allowed = {
        "schema_version", "record_type", "probe_id", "asset_id", "state",
        "asset_spec", "question", "providers", "references",
        "evaluation_profile", "stop_conditions", "created_at", "created_by", "notes",
    }
    required = allowed - {"notes"}
    _unknown(root, "$", allowed, errors)
    _required(root, "$", required, errors)
    _validate_header(root, "probe_plan", errors)
    if "state" in root:
        _enum(root["state"], "$.state", PLAN_STATES, errors)
    if "asset_spec" in root:
        _hashed_path(root["asset_spec"], "$.asset_spec", errors)
    if "question" in root:
        _string(root["question"], "$.question", errors)

    providers = root.get("providers")
    provider_names: list[str] = []
    request_ids: list[str] = []
    if not isinstance(providers, list):
        errors.append("$.providers: expected array")
    else:
        if not providers:
            errors.append("$.providers: expected at least one item")
        for index, raw in enumerate(providers):
            item_path = f"$.providers[{index}]"
            item = _object(raw, item_path, errors)
            fields = {"provider", "request_id", "delivery_mode", "generation_mode"}
            _unknown(item, item_path, fields, errors)
            _required(item, item_path, fields, errors)
            if "provider" in item:
                _enum(item["provider"], f"{item_path}.provider", PROVIDERS, errors)
                if isinstance(item["provider"], str):
                    provider_names.append(item["provider"])
            if "request_id" in item:
                _identifier(item["request_id"], f"{item_path}.request_id", errors)
                if isinstance(item["request_id"], str):
                    request_ids.append(item["request_id"])
            if "delivery_mode" in item:
                _enum(item["delivery_mode"], f"{item_path}.delivery_mode", DELIVERY_MODES, errors)
            if "generation_mode" in item:
                _enum(item["generation_mode"], f"{item_path}.generation_mode", GENERATION_MODES, errors)
        if len(provider_names) != len(set(provider_names)):
            errors.append("$.providers: only one request per provider is allowed in v0.1")
        if len(request_ids) != len(set(request_ids)):
            errors.append("$.providers: duplicate request_id values are not allowed")

    references = root.get("references")
    if not isinstance(references, list):
        errors.append("$.references: expected array")
    else:
        if not references:
            errors.append("$.references: expected at least one item")
        seen_paths = []
        for index, raw in enumerate(references):
            item_path = f"$.references[{index}]"
            item = _object(raw, item_path, errors)
            fields = {"path", "role", "sha256"}
            _unknown(item, item_path, fields, errors)
            _required(item, item_path, fields, errors)
            if "path" in item:
                _repo_path(item["path"], f"{item_path}.path", errors)
                if isinstance(item["path"], str):
                    seen_paths.append(item["path"])
            if "role" in item:
                _string(item["role"], f"{item_path}.role", errors)
            if "sha256" in item:
                _check_sha256(item["sha256"], f"{item_path}.sha256", errors)
        if len(seen_paths) != len(set(seen_paths)):
            errors.append("$.references: duplicate paths are not allowed")

    profile = _object(root.get("evaluation_profile"), "$.evaluation_profile", errors)
    profile_fields = {"camera_profile", "screen_size_world_units", "coordinate_profile"}
    _unknown(profile, "$.evaluation_profile", profile_fields, errors)
    _required(profile, "$.evaluation_profile", profile_fields, errors)
    if profile.get("camera_profile") != "top_down_default_v1":
        errors.append("$.evaluation_profile.camera_profile: expected 'top_down_default_v1'")
    screen_size = profile.get("screen_size_world_units")
    if not _is_number(screen_size) or screen_size <= 0:
        errors.append("$.evaluation_profile.screen_size_world_units: expected number greater than zero")
    if profile.get("coordinate_profile") != "astrion_blender_to_godot_v1":
        errors.append("$.evaluation_profile.coordinate_profile: expected 'astrion_blender_to_godot_v1'")

    _string_list(root.get("stop_conditions"), "$.stop_conditions", errors, nonempty=True)
    if "created_at" in root:
        _timestamp(root["created_at"], "$.created_at", errors)
    if "created_by" in root:
        _string(root["created_by"], "$.created_by", errors)
    _reject_sensitive_keys(root, "$", errors)
    return errors


def validate_delivery(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        _object(data, "$", errors)
        return errors
    root = data
    allowed = {
        "schema_version", "record_type", "probe_id", "asset_id", "state",
        "probe_plan", "provider", "request_id", "candidate_id", "provenance", "files",
        "delivered_at", "delivered_by", "notes",
    }
    _unknown(root, "$", allowed, errors)
    _required(root, "$", allowed - {"notes"}, errors)
    _validate_header(root, "probe_delivery", errors)
    if "probe_plan" in root:
        plan_ref = _hashed_path(root["probe_plan"], "$.probe_plan", errors)
        expected = None
        if isinstance(root.get("asset_id"), str) and isinstance(root.get("probe_id"), str):
            expected = (
                "astrion-3d-pipeline/work/generative-probes/"
                f"{root['asset_id']}/{root['probe_id']}/probe-plan.json"
            )
        if expected is not None and plan_ref.get("path") != expected:
            errors.append(f"$.probe_plan.path: expected {expected}")
    if "state" in root:
        _enum(root["state"], "$.state", DELIVERY_STATES, errors)
    if "provider" in root:
        _enum(root["provider"], "$.provider", PROVIDERS, errors)
    for field in ("request_id", "candidate_id"):
        if field in root:
            _identifier(root[field], f"$.{field}", errors)

    provenance = _object(root.get("provenance"), "$.provenance", errors)
    provenance_fields = {
        "delivery_mode", "external_job_id", "model", "generation_mode",
        "settings", "seed", "generated_at", "license",
    }
    _unknown(provenance, "$.provenance", provenance_fields, errors)
    _required(provenance, "$.provenance", provenance_fields, errors)
    if "delivery_mode" in provenance:
        _enum(provenance["delivery_mode"], "$.provenance.delivery_mode", DELIVERY_MODES, errors)
    if provenance.get("external_job_id") is not None:
        _string(provenance["external_job_id"], "$.provenance.external_job_id", errors)
    if "model" in provenance:
        _string(provenance["model"], "$.provenance.model", errors)
    if "generation_mode" in provenance:
        _enum(provenance["generation_mode"], "$.provenance.generation_mode", GENERATION_MODES, errors)
    if not isinstance(provenance.get("settings"), dict):
        errors.append("$.provenance.settings: expected object")
    seed = provenance.get("seed")
    if seed is not None and not isinstance(seed, (str, int)):
        errors.append("$.provenance.seed: expected string, integer, or null")
    if isinstance(seed, bool):
        errors.append("$.provenance.seed: expected string, integer, or null")
    elif isinstance(seed, str):
        _string(seed, "$.provenance.seed", errors)
    if "generated_at" in provenance:
        _timestamp(provenance["generated_at"], "$.provenance.generated_at", errors, nullable=True)
    if "license" in provenance:
        _string(provenance["license"], "$.provenance.license", errors)

    files = root.get("files")
    model_files = 0
    file_paths: list[str] = []
    if not isinstance(files, list):
        errors.append("$.files: expected array")
    else:
        if not files:
            errors.append("$.files: expected at least one item")
        for index, raw in enumerate(files):
            item_path = f"$.files[{index}]"
            item = _object(raw, item_path, errors)
            fields = {"path", "role", "media_type", "sha256", "size_bytes"}
            _unknown(item, item_path, fields, errors)
            _required(item, item_path, fields, errors)
            if "path" in item:
                _under_run_path(
                    item["path"], f"{item_path}.path", errors,
                    asset_id=root.get("asset_id"), probe_id=root.get("probe_id"), area="intake",
                    provider=root.get("provider"), candidate_id=root.get("candidate_id"),
                )
                if isinstance(item["path"], str):
                    file_paths.append(item["path"])
            if "role" in item:
                _enum(item["role"], f"{item_path}.role", {"model", "texture", "preview", "metadata", "other"}, errors)
                if item["role"] == "model":
                    model_files += 1
            if "media_type" in item:
                _string(item["media_type"], f"{item_path}.media_type", errors)
            if "sha256" in item:
                _check_sha256(item["sha256"], f"{item_path}.sha256", errors)
            if not _is_int(item.get("size_bytes")) or item.get("size_bytes", 0) < 0:
                errors.append(f"{item_path}.size_bytes: expected integer >= 0")
        if len(file_paths) != len(set(file_paths)):
            errors.append("$.files: duplicate paths are not allowed")
    if root.get("state") == "received" and model_files < 1:
        errors.append("$.files: a received delivery requires at least one model file")
    if root.get("state") in {"invalid", "withdrawn"} and not isinstance(root.get("notes"), str):
        errors.append("$.notes: required for an invalid or withdrawn delivery")
    elif root.get("state") in {"invalid", "withdrawn"}:
        _string(root["notes"], "$.notes", errors)
    if "delivered_at" in root:
        _timestamp(root["delivered_at"], "$.delivered_at", errors)
    if "delivered_by" in root:
        _string(root["delivered_by"], "$.delivered_by", errors)
    _reject_sensitive_keys(root, "$", errors)
    return errors


def _evaluation_artifacts(
    value: Any,
    path: str,
    errors: list[str],
    *,
    root: dict[str, Any],
    area: str,
) -> None:
    if not isinstance(value, list):
        errors.append(f"{path}: expected array")
        return
    seen = []
    for index, raw in enumerate(value):
        item_path = f"{path}[{index}]"
        item = _object(raw, item_path, errors)
        fields = {"path", "role", "sha256"}
        _unknown(item, item_path, fields, errors)
        _required(item, item_path, fields, errors)
        if "path" in item:
            _under_run_path(
                item["path"], f"{item_path}.path", errors,
                asset_id=root.get("asset_id"), probe_id=root.get("probe_id"), area=area,
                provider=root.get("provider"), candidate_id=root.get("candidate_id"),
            )
            if isinstance(item["path"], str):
                seen.append(item["path"])
        if "role" in item:
            _string(item["role"], f"{item_path}.role", errors)
        if "sha256" in item:
            _check_sha256(item["sha256"], f"{item_path}.sha256", errors)
    if len(seen) != len(set(seen)):
        errors.append(f"{path}: duplicate paths are not allowed")


def validate_evaluation(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        _object(data, "$", errors)
        return errors
    root = data
    allowed = {
        "schema_version", "record_type", "probe_id", "asset_id", "state",
        "provider", "request_id", "candidate_id", "delivery", "input_model",
        "derived_artifacts", "diagnostics", "metrics", "topology_observations",
        "identity_review", "suggested_outcome", "evaluated_at", "evaluated_by", "notes",
    }
    _unknown(root, "$", allowed, errors)
    _required(root, "$", allowed - {"notes"}, errors)
    _validate_header(root, "candidate_evaluation", errors)
    if "state" in root:
        _enum(root["state"], "$.state", EVALUATION_STATES, errors)
    if "provider" in root:
        _enum(root["provider"], "$.provider", PROVIDERS, errors)
    for field in ("request_id", "candidate_id"):
        if field in root:
            _identifier(root[field], f"$.{field}", errors)
    if "delivery" in root:
        delivery = _hashed_path(root["delivery"], "$.delivery", errors)
        if "path" in delivery:
            _under_run_path(
                delivery["path"], "$.delivery.path", errors,
                asset_id=root.get("asset_id"), probe_id=root.get("probe_id"), area="intake",
                provider=root.get("provider"), candidate_id=root.get("candidate_id"),
            )
    if "input_model" in root:
        model = _hashed_path(root["input_model"], "$.input_model", errors)
        if "path" in model:
            _under_run_path(
                model["path"], "$.input_model.path", errors,
                asset_id=root.get("asset_id"), probe_id=root.get("probe_id"), area="intake",
                provider=root.get("provider"), candidate_id=root.get("candidate_id"),
            )
    _evaluation_artifacts(root.get("derived_artifacts"), "$.derived_artifacts", errors, root=root, area="derived")
    _evaluation_artifacts(root.get("diagnostics"), "$.diagnostics", errors, root=root, area="diagnostics")

    metrics = _object(root.get("metrics"), "$.metrics", errors)
    metric_fields = {
        "parse_status", "triangles", "vertices", "mesh_count", "primitive_count",
        "material_count", "connected_components", "bounds",
    }
    _unknown(metrics, "$.metrics", metric_fields, errors)
    _required(metrics, "$.metrics", metric_fields, errors)
    if "parse_status" in metrics:
        _enum(metrics["parse_status"], "$.metrics.parse_status", {"usable", "invalid"}, errors)
    for field in ("triangles", "vertices", "mesh_count", "primitive_count", "material_count", "connected_components"):
        value = metrics.get(field)
        if value is not None and (not _is_int(value) or value < 0):
            errors.append(f"$.metrics.{field}: expected integer >= 0 or null")
    bounds = metrics.get("bounds")
    if bounds is not None:
        if not isinstance(bounds, dict):
            errors.append("$.metrics.bounds: expected object or null")
        else:
            _unknown(bounds, "$.metrics.bounds", {"x", "y", "z"}, errors)
            _required(bounds, "$.metrics.bounds", {"x", "y", "z"}, errors)
            for axis in ("x", "y", "z"):
                if not _is_number(bounds.get(axis)) or bounds.get(axis, 0) < 0:
                    errors.append(f"$.metrics.bounds.{axis}: expected number >= 0")

    observations = root.get("topology_observations")
    if not isinstance(observations, list):
        errors.append("$.topology_observations: expected array")
    else:
        for index, raw in enumerate(observations):
            item_path = f"$.topology_observations[{index}]"
            item = _object(raw, item_path, errors)
            fields = {"code", "severity", "message"}
            _unknown(item, item_path, fields, errors)
            _required(item, item_path, fields, errors)
            if "code" in item:
                if not isinstance(item["code"], str) or not re.fullmatch(r"[a-z][a-z0-9_]*", item["code"]):
                    errors.append(f"{item_path}.code: expected lowercase snake_case code")
            if "severity" in item:
                _enum(item["severity"], f"{item_path}.severity", {"info", "warning", "error"}, errors)
            if "message" in item:
                _string(item["message"], f"{item_path}.message", errors)

    review = root.get("identity_review")
    if not isinstance(review, list):
        errors.append("$.identity_review: expected array")
    else:
        if root.get("state") in {"measured", "evaluated"} and not review:
            errors.append("$.identity_review: measured/evaluated candidates require at least one criterion")
        for index, raw in enumerate(review):
            item_path = f"$.identity_review[{index}]"
            item = _object(raw, item_path, errors)
            fields = {"criterion", "status", "notes"}
            _unknown(item, item_path, fields, errors)
            _required(item, item_path, fields, errors)
            if "criterion" in item:
                _string(item["criterion"], f"{item_path}.criterion", errors)
            if "status" in item:
                _enum(item["status"], f"{item_path}.status", {"pass", "warning", "fail", "not_assessed"}, errors)
            if "notes" in item:
                _string(item["notes"], f"{item_path}.notes", errors)

    outcome = root.get("suggested_outcome")
    if outcome is not None:
        _enum(outcome, "$.suggested_outcome", OUTCOMES, errors)
    if root.get("state") == "evaluated":
        if metrics.get("parse_status") != "usable":
            errors.append("$.metrics.parse_status: must be 'usable' when state is 'evaluated'")
        if outcome is None:
            errors.append("$.suggested_outcome: required when state is 'evaluated'")
        for field in ("triangles", "vertices", "mesh_count", "primitive_count", "material_count", "connected_components"):
            if metrics.get(field) is None:
                errors.append(f"$.metrics.{field}: required when state is 'evaluated'")
        if bounds is None:
            errors.append("$.metrics.bounds: required when state is 'evaluated'")
    if root.get("state") == "measured":
        if metrics.get("parse_status") != "usable":
            errors.append("$.metrics.parse_status: must be 'usable' when state is 'measured'")
        if outcome is not None:
            errors.append("$.suggested_outcome: must be null when state is 'measured'")
        for field in ("triangles", "vertices", "mesh_count", "primitive_count", "material_count", "connected_components"):
            if metrics.get(field) is None:
                errors.append(f"$.metrics.{field}: required when state is 'measured'")
        if bounds is None:
            errors.append("$.metrics.bounds: required when state is 'measured'")
        if isinstance(review, list):
            for index, item in enumerate(review):
                if isinstance(item, dict) and item.get("status") != "not_assessed":
                    errors.append(
                        f"$.identity_review[{index}].status: must be 'not_assessed' while state is 'measured'"
                    )
        diagnostics = root.get("diagnostics")
        if isinstance(diagnostics, list) and not diagnostics:
            errors.append("$.diagnostics: measured candidates require at least one diagnostic")
    if root.get("state") == "invalid":
        if metrics.get("parse_status") != "invalid":
            errors.append("$.metrics.parse_status: must be 'invalid' when state is 'invalid'")
        if outcome is not None:
            errors.append("$.suggested_outcome: must be null when state is 'invalid'")
    if "evaluated_at" in root:
        _timestamp(root["evaluated_at"], "$.evaluated_at", errors)
    if "evaluated_by" in root:
        _string(root["evaluated_by"], "$.evaluated_by", errors)
    _reject_sensitive_keys(root, "$", errors)
    return errors


def validate_decision(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        _object(data, "$", errors)
        return errors
    root = data
    allowed = {
        "schema_version", "record_type", "probe_id", "asset_id", "state",
        "comparison_status", "evaluations", "selected_candidate_id",
        "intended_outcome", "rationale", "reviewer", "reviewed_at",
        "production_handoff", "notes",
    }
    _unknown(root, "$", allowed, errors)
    _required(root, "$", allowed - {"notes"}, errors)
    _validate_header(root, "probe_decision", errors)
    if "state" in root:
        _enum(root["state"], "$.state", {"reviewed", "closed"}, errors)
    status = root.get("comparison_status")
    if "comparison_status" in root:
        _enum(status, "$.comparison_status", COMPARISON_STATUSES, errors)

    evaluations = root.get("evaluations")
    candidate_ids: list[str] = []
    if not isinstance(evaluations, list):
        errors.append("$.evaluations: expected array")
    else:
        for index, raw in enumerate(evaluations):
            item_path = f"$.evaluations[{index}]"
            item = _object(raw, item_path, errors)
            fields = {"path", "sha256", "provider", "candidate_id"}
            _unknown(item, item_path, fields, errors)
            _required(item, item_path, fields, errors)
            if "path" in item:
                _under_run_path(
                    item["path"], f"{item_path}.path", errors,
                    asset_id=root.get("asset_id"), probe_id=root.get("probe_id"), area="diagnostics",
                    provider=item.get("provider"), candidate_id=item.get("candidate_id"),
                )
            if "sha256" in item:
                _check_sha256(item["sha256"], f"{item_path}.sha256", errors)
            if "provider" in item:
                _enum(item["provider"], f"{item_path}.provider", PROVIDERS, errors)
            if "candidate_id" in item:
                _identifier(item["candidate_id"], f"{item_path}.candidate_id", errors)
                if isinstance(item["candidate_id"], str):
                    candidate_ids.append(item["candidate_id"])
        if len(candidate_ids) != len(set(candidate_ids)):
            errors.append("$.evaluations: duplicate candidate_id values are not allowed")

    selected = root.get("selected_candidate_id")
    if selected is not None:
        _identifier(selected, "$.selected_candidate_id", errors)
    outcome = root.get("intended_outcome")
    if outcome is not None:
        _enum(outcome, "$.intended_outcome", OUTCOMES, errors)
    if status == "candidate_selected":
        if selected is None:
            errors.append("$.selected_candidate_id: required when comparison_status is 'candidate_selected'")
        elif selected not in candidate_ids:
            errors.append("$.selected_candidate_id: must reference an entry in evaluations")
        if outcome not in {"accept_normalize", "repair", "rebuild_reference"}:
            errors.append("$.intended_outcome: candidate selection requires accept_normalize, repair, or rebuild_reference")
    elif status == "procedural_direct":
        if selected is not None:
            errors.append("$.selected_candidate_id: must be null for procedural_direct")
        if outcome != "procedural_direct":
            errors.append("$.intended_outcome: must be 'procedural_direct' for procedural_direct")
    elif status in {"more_evidence_required", "no_selection", "skipped"}:
        if selected is not None:
            errors.append(f"$.selected_candidate_id: must be null when comparison_status is {status!r}")
        if outcome is not None:
            errors.append(f"$.intended_outcome: must be null when comparison_status is {status!r}")
    if status == "skipped" and isinstance(evaluations, list) and evaluations:
        errors.append("$.evaluations: must be empty when comparison_status is 'skipped'")

    for field in ("rationale", "reviewer"):
        if field in root:
            _string(root[field], f"$.{field}", errors)
    if "reviewed_at" in root:
        _timestamp(root["reviewed_at"], "$.reviewed_at", errors)

    handoff = _object(root.get("production_handoff"), "$.production_handoff", errors)
    handoff_fields = {"status", "asset_spec_path", "evidence_report_path"}
    _unknown(handoff, "$.production_handoff", handoff_fields, errors)
    _required(handoff, "$.production_handoff", handoff_fields, errors)
    handoff_status = handoff.get("status")
    if "status" in handoff:
        _enum(handoff_status, "$.production_handoff.status", {"not_requested", "approved"}, errors)
    for field in ("asset_spec_path", "evidence_report_path"):
        value = handoff.get(field)
        if value is not None:
            _repo_path(value, f"$.production_handoff.{field}", errors)
    if handoff_status == "not_requested":
        if handoff.get("asset_spec_path") is not None or handoff.get("evidence_report_path") is not None:
            errors.append("$.production_handoff: paths must be null when status is 'not_requested'")
    if handoff_status == "approved":
        if status not in {"candidate_selected", "procedural_direct"}:
            errors.append("$.production_handoff.status: approval requires a selected candidate or procedural_direct decision")
        if handoff.get("asset_spec_path") is None:
            errors.append("$.production_handoff.asset_spec_path: required when handoff is approved")
        evidence_path = handoff.get("evidence_report_path")
        if evidence_path is None:
            errors.append("$.production_handoff.evidence_report_path: required when handoff is approved")
        elif isinstance(root.get("asset_id"), str) and isinstance(root.get("probe_id"), str):
            prefix = f"astrion-3d-pipeline/reports/generative-probes/{root['asset_id']}/{root['probe_id']}/"
            if not evidence_path.startswith(prefix):
                errors.append(f"$.production_handoff.evidence_report_path: must be inside {prefix}")
    _reject_sensitive_keys(root, "$", errors)
    return errors


VALIDATORS = {
    "probe_plan": validate_plan,
    "probe_delivery": validate_delivery,
    "candidate_evaluation": validate_evaluation,
    "probe_decision": validate_decision,
}


def validate_record(data: Any) -> list[str]:
    """Validate one record without filesystem side effects."""
    if not isinstance(data, dict):
        return ["$: expected object"]
    record_type = data.get("record_type")
    validator = VALIDATORS.get(record_type)
    if validator is None:
        return [f"$.record_type: expected one of {', '.join(sorted(RECORD_TYPES))}; got {record_type!r}"]
    return validator(data)


def validate_record_set(records: list[dict[str, Any]]) -> list[str]:
    """Validate relationships among already structurally valid records."""
    errors: list[str] = []
    if not records:
        return ["record set: expected at least one record"]
    plans = [record for record in records if record.get("record_type") == "probe_plan"]
    if len(plans) > 1:
        errors.append("record set: at most one probe_plan is allowed")
    decisions = [record for record in records if record.get("record_type") == "probe_decision"]
    if len(decisions) > 1:
        errors.append("record set: at most one probe_decision is allowed in v0.1")
    identities = {(record.get("asset_id"), record.get("probe_id")) for record in records}
    if len(identities) > 1:
        errors.append("record set: all records must share asset_id and probe_id")
    if not plans:
        if len(records) > 1:
            errors.append("record set: a multi-record set requires one probe_plan")
        return errors

    plan = plans[0]
    requests = {
        (item.get("provider"), item.get("request_id")): item
        for item in plan.get("providers", []) if isinstance(item, dict)
    }
    delivery_records = [record for record in records if record.get("record_type") == "probe_delivery"]
    evaluation_records = [record for record in records if record.get("record_type") == "candidate_evaluation"]
    delivery_keys = [(record.get("provider"), record.get("request_id"), record.get("candidate_id")) for record in delivery_records]
    evaluation_keys = [(record.get("provider"), record.get("request_id"), record.get("candidate_id")) for record in evaluation_records]
    if len(delivery_keys) != len(set(delivery_keys)):
        errors.append("record set: duplicate delivery identity")
    if len(evaluation_keys) != len(set(evaluation_keys)):
        errors.append("record set: duplicate evaluation identity")
    deliveries = {key: record for key, record in zip(delivery_keys, delivery_records)}
    evaluations = {key: record for key, record in zip(evaluation_keys, evaluation_records)}
    for key in deliveries:
        if key[:2] not in requests:
            errors.append(f"record set: delivery {key[2]!r} does not match a provider request in the plan")
            continue
        request = requests[key[:2]]
        delivery = deliveries[key]
        for field in ("delivery_mode", "generation_mode"):
            actual = delivery.get("provenance", {}).get(field)
            if actual != request.get(field):
                errors.append(
                    f"record set: delivery {key[2]!r} {field} {actual!r} "
                    f"does not match plan value {request.get(field)!r}"
                )
    for key in evaluations:
        if key not in deliveries:
            errors.append(f"record set: evaluation {key[2]!r} has no matching delivery")
            continue
        delivery = deliveries[key]
        model_files = {
            (item.get("path"), item.get("sha256"))
            for item in delivery.get("files", [])
            if isinstance(item, dict) and item.get("role") == "model"
        }
        evaluation = evaluations[key]
        input_model = evaluation.get("input_model", {})
        if model_files and (input_model.get("path"), input_model.get("sha256")) not in model_files:
            errors.append(f"record set: evaluation {key[2]!r} input_model does not match its delivery")

    evaluated_candidates = {
        (key[0], key[2]) for key, record in evaluations.items()
        if record.get("state") == "evaluated"
    }
    for decision in decisions:
        decision_candidates = {
            (item.get("provider"), item.get("candidate_id"))
            for item in decision.get("evaluations", []) if isinstance(item, dict)
        }
        missing = sorted(candidate for candidate in decision_candidates if candidate not in evaluated_candidates)
        for provider, candidate in missing:
            errors.append(
                f"record set: decision references evaluation {provider!r}/{candidate!r} not present in the set"
            )
        if decision.get("comparison_status") in {"candidate_selected", "procedural_direct"}:
            delivered_requests = {key[:2] for key in deliveries}
            missing_requests = sorted(set(requests) - delivered_requests)
            for provider, request_id in missing_requests:
                errors.append(
                    "record set: final selection cannot omit planned provider branch "
                    f"{provider!r}/{request_id!r}; add a received, invalid, or withdrawn delivery"
                )
    return errors


def load_record(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Astrion Generative Probe v0.1 records without writing anything."
    )
    parser.add_argument("records", nargs="+", type=Path)
    args = parser.parse_args(argv)
    loaded: list[tuple[Path, Any]] = []
    for path in args.records:
        try:
            loaded.append((path, load_record(path)))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            print(f"ERROR: cannot read {path}: {exc}", file=sys.stderr)
            return 2

    invalid = False
    valid_objects: list[dict[str, Any]] = []
    for path, data in loaded:
        errors = validate_record(data)
        if errors:
            invalid = True
            print(f"INVALID {path} ({len(errors)} error{'s' if len(errors) != 1 else ''})")
            for error in errors:
                print(f"  - {error}")
        else:
            assert isinstance(data, dict)
            valid_objects.append(data)
            print(f"VALID {path} ({data['record_type']} v{SCHEMA_VERSION})")

    if invalid:
        return 1
    set_errors = validate_record_set(valid_objects)
    if set_errors:
        print(f"INVALID record set ({len(set_errors)} error{'s' if len(set_errors) != 1 else ''})")
        for error in set_errors:
            print(f"  - {error}")
        return 1
    if len(valid_objects) > 1:
        print(f"VALID record set ({len(valid_objects)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
