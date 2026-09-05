#!/usr/bin/env python3
"""Runner local M4 para reproducir el pipeline probado de ``esfera-mecanica``.

Este runner orquesta herramientas existentes; no reimplementa Blender ni la
reproyeccion. Cada etapa escribe en su propia carpeta bajo un directorio nuevo
de ``astrion-3d-pipeline/work``. Soporta plan sin escrituras, corte por etapa y
reanudar despues de etapas completas cuyos hashes sigan intactos.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


TOOL = "astrion-m4-esfera-runner/0.1"
STAGES = ("repair", "audit1", "uv", "reproject", "audit2")
STAGE_DIRECTORIES = {
    "repair": "01-repair",
    "audit1": "02-audit1",
    "uv": "03-uv",
    "reproject": "04-reproject",
    "audit2": "05-audit2",
}


class RunnerError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def repo_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(path: Path, root: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RunnerError(f"artefacto esperado ausente: {path}")
    return {"path": repo_path(path, root), "bytes": path.stat().st_size, "sha256": sha256(path)}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_spec_validator(root: Path) -> Callable[[Any], list[str]]:
    path = root / "astrion-3d-pipeline/tools/validate_spec.py"
    module_spec = importlib.util.spec_from_file_location("astrion_validate_spec", path)
    if module_spec is None or module_spec.loader is None:
        raise RunnerError(f"no se pudo cargar el validador: {path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module.validate_spec


def require_valid_spec(data: Any, root: Path, label: str) -> None:
    errors = load_spec_validator(root)(data)
    if errors:
        raise RunnerError(label + " invalido:\n  - " + "\n  - ".join(errors))


def resolve_inputs(
    root: Path,
    spec_path: Path,
    source_blend: Path,
    appearance_source: Path,
    output_dir: Path,
    *,
    resume: bool,
    dry_run: bool,
) -> tuple[Path, Path, Path, Path]:
    root = root.resolve()
    spec_path = spec_path.resolve()
    source_blend = source_blend.resolve()
    appearance_source = appearance_source.resolve()
    output_dir = output_dir.resolve()
    for label, path in (
        ("spec", spec_path),
        ("source blend", source_blend),
        ("appearance source", appearance_source),
    ):
        if not path.is_file() or not is_within(path, root):
            raise RunnerError(f"{label} debe ser un archivo existente dentro del repositorio: {path}")
    if source_blend.suffix.lower() != ".blend":
        raise RunnerError("--source-blend debe ser .blend")
    if appearance_source.suffix.lower() != ".glb":
        raise RunnerError("--appearance-source debe ser .glb")
    work_root = (root / "astrion-3d-pipeline/work").resolve()
    if not is_within(output_dir, work_root) or output_dir == work_root:
        raise RunnerError("--output-dir debe ser una carpeta hija de astrion-3d-pipeline/work")
    if is_within(output_dir, root / "source"):
        raise RunnerError("la salida no puede estar bajo source/")
    if output_dir in (source_blend.parent, appearance_source.parent):
        raise RunnerError("la salida no puede compartir carpeta con una entrada")
    manifest = output_dir / "run-manifest.json"
    if resume:
        if not output_dir.is_dir() or not manifest.is_file():
            raise RunnerError("--resume requiere un run-manifest.json existente")
    elif output_dir.exists():
        raise RunnerError("la salida ya existe; elija una carpeta nueva o use --resume")
    if dry_run and resume and not manifest.is_file():
        raise RunnerError("el dry-run de reanudacion requiere un manifest existente")
    return spec_path, source_blend, appearance_source, output_dir


def blender_candidates(explicit: Path | None) -> list[Path]:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    configured = os.environ.get("ASTRION_BLENDER")
    if configured:
        candidates.append(Path(configured).expanduser())
    found = shutil.which("blender")
    if found:
        candidates.append(Path(found))
    if os.name == "nt":
        for base in (Path(os.environ.get("ProgramFiles", r"C:\Program Files")), Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))):
            parent = base / "Blender Foundation"
            if parent.is_dir():
                candidates.extend(sorted(parent.glob("Blender */blender.exe"), reverse=True))
    else:
        candidates.extend((Path("/Applications/Blender.app/Contents/MacOS/Blender"), Path("/usr/bin/blender")))
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        key = os.path.normcase(str(resolved))
        if key not in seen:
            unique.append(resolved)
            seen.add(key)
    return unique


def discover_blender(explicit: Path | None) -> tuple[Path, str]:
    attempts: list[str] = []
    for candidate in blender_candidates(explicit):
        if not candidate.is_file():
            attempts.append(f"{candidate} (no existe)")
            continue
        try:
            completed = subprocess.run(
                [str(candidate), "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            attempts.append(f"{candidate} ({exc})")
            continue
        first_line = (completed.stdout or completed.stderr).splitlines()
        if completed.returncode == 0 and first_line and first_line[0].startswith("Blender "):
            return candidate, first_line[0].removeprefix("Blender ")
        attempts.append(f"{candidate} (codigo {completed.returncode})")
    detail = "\n  - ".join(attempts) if attempts else "sin candidatos"
    raise RunnerError(
        "Blender no disponible. Use --blender, ASTRION_BLENDER o PATH. Intentos:\n  - " + detail
    )


def stage_range(from_stage: str | None, to_stage: str) -> tuple[str, ...]:
    start = STAGES.index(from_stage) if from_stage else 0
    end = STAGES.index(to_stage)
    if start > end:
        raise RunnerError("--from-stage no puede estar despues de --to-stage")
    return STAGES[start:end + 1]


def stage_dir(output_dir: Path, stage: str) -> Path:
    return output_dir / "stages" / STAGE_DIRECTORIES[stage]


def verify_artifact_record(record: dict[str, Any], root: Path) -> bool:
    path = root / record["path"]
    return path.is_file() and path.stat().st_size == record["bytes"] and sha256(path) == record["sha256"]


def verify_completed_stage(manifest: dict[str, Any], stage: str, root: Path) -> bool:
    record = manifest.get("stages", {}).get(stage)
    return bool(
        record
        and record.get("status") == "complete"
        and record.get("outputs")
        and all(verify_artifact_record(item, root) for item in record["outputs"])
    )


def verify_resume_inputs(manifest: dict[str, Any], inputs: dict[str, dict[str, Any]], root: Path) -> None:
    if manifest.get("tool") != TOOL or manifest.get("asset_id") != "esfera-mecanica":
        raise RunnerError("el manifest no pertenece a este runner/activo")
    stored = manifest.get("inputs", {})
    for name, current in inputs.items():
        if stored.get(name) != current or not verify_artifact_record(current, root):
            raise RunnerError(f"la entrada {name} cambio desde el inicio del run")


def display_command(command: list[str], root: Path) -> list[str]:
    result = []
    for item in command:
        candidate = Path(item)
        if candidate.is_absolute() and is_within(candidate, root):
            result.append(repo_path(candidate, root))
        else:
            result.append(item)
    return result


def run_command(command: list[str], log_path: Path, stage: str, root: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    shown = display_command(command, root)
    with log_path.open("w", encoding="utf-8", newline="") as log:
        log.write("COMMAND " + json.dumps(shown, ensure_ascii=False) + "\n")
        log.flush()
        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "1"
        process = subprocess.Popen(
            command,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
        )
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
            log.flush()
            print(f"[{stage}] {line}", end="")
        return process.wait()


def stage_outputs(paths: list[Path], root: Path, log_path: Path) -> list[dict[str, Any]]:
    return [artifact(path, root) for path in paths] + [artifact(log_path, root)]


def prepare_stage(output_dir: Path, stage: str, manifest: dict[str, Any]) -> Path:
    directory = stage_dir(output_dir, stage)
    if directory.exists() and any(directory.iterdir()) and manifest.get("stages", {}).get(stage, {}).get("status") != "complete":
        raise RunnerError(
            f"la etapa {stage} contiene salida parcial; por seguridad no se sobrescribe. Use un --output-dir nuevo: {directory}"
        )
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def ensure_source_tool(spec: dict[str, Any], path: str, role: str) -> None:
    inputs = spec["pipeline"]["source_inputs"]
    if not any(item["path"] == path for item in inputs):
        inputs.append({"path": path, "role": role, "authority": "astrion_source"})


def verify_reviewed_waiver_scope(base: dict[str, Any], repair_dir: Path, root: Path) -> None:
    """No transporta una waiver a geometria distinta de la que fue revisada."""
    reference = base["pipeline"]["audits"]["geometry"]
    if reference.get("status") != "waived":
        return
    provenance = base["pipeline"].get("provenance", {})
    reviewed_report_value = provenance.get("repair_report")
    if reviewed_report_value:
        reviewed_report_path = root / reviewed_report_value
    else:
        master_value = provenance.get("geometry_master_before_uv")
        reviewed_report_path = (root / master_value).parent / "repair-report.json" if master_value else None
    if reviewed_report_path is None or not reviewed_report_path.is_file():
        raise RunnerError("la waiver de Audit 1 no tiene repair-report revisado para verificar su alcance")
    reviewed = load_json(reviewed_report_path)
    current = load_json(repair_dir / "repair-report.json")
    expected_hash = reviewed["outputs"]["glb"]["sha256"]
    current_hash = current["outputs"]["glb"]["sha256"]
    if current_hash != expected_hash:
        raise RunnerError(
            "la geometria reparada no coincide con el hash revisado por la waiver de Audit 1: "
            f"esperado {expected_hash}, actual {current_hash}"
        )


def geometry_audit_input_spec(
    base: dict[str, Any], root: Path, repair_dir: Path, audit_report: Path
) -> dict[str, Any]:
    spec = copy.deepcopy(base)
    pipeline = spec["pipeline"]
    pipeline["stage"] = "master_mesh_candidate"
    pipeline["geometry_outcome"] = "repair"
    pipeline["master_mesh"] = {
        "status": "candidate",
        "source_path": repo_path(repair_dir / "esfera-mecanica-repaired.blend", root),
        "exchange_path": repo_path(repair_dir / "esfera-mecanica-repaired.glb", root),
    }
    pipeline["outputs"] = [{
        "path": repo_path(repair_dir / "repair-report.json", root),
        "role": "repair_evidence",
        "authority": "derived",
    }]
    previous = base["pipeline"]["audits"]["geometry"]
    if previous.get("status") == "waived" and previous.get("waivers"):
        pipeline["audits"]["geometry"] = {
            "status": "waived",
            "report": repo_path(audit_report, root),
            "waivers": copy.deepcopy(previous["waivers"]),
        }
    else:
        pipeline["audits"]["geometry"] = {"status": "not_run", "report": None}
    pipeline["audits"]["uv_textures"] = {"status": "not_run", "report": None}
    pipeline["provenance"] = {
        "m4_runner": TOOL,
        "base_spec": base["identity"]["asset_id"],
        "repair_report": repo_path(repair_dir / "repair-report.json", root),
        "source_asset_unchanged": True,
    }
    pipeline["notes"] = "M4 geometry-audit input; only reviewed waivers from the supplied spec are carried forward."
    ensure_source_tool(spec, "tools/reparar-esfera-mecanica.py", "deterministic_geometry_repair")
    return spec


def geometry_complete_spec(
    audit_input: dict[str, Any], report: dict[str, Any], root: Path, audit_report: Path
) -> dict[str, Any]:
    spec = copy.deepcopy(audit_input)
    result = report["audit"]["result"]
    pipeline = spec["pipeline"]
    pipeline["stage"] = "geometry_audited" if result in {"pass", "waived"} else "master_mesh_candidate"
    pipeline["master_mesh"]["status"] = "approved" if result in {"pass", "waived"} else "candidate"
    reference: dict[str, Any] = {"status": result, "report": repo_path(audit_report, root)}
    if result == "waived":
        reference["waivers"] = copy.deepcopy(audit_input["pipeline"]["audits"]["geometry"]["waivers"])
    pipeline["audits"]["geometry"] = reference
    pipeline["outputs"].append({
        "path": repo_path(audit_report, root), "role": "geometry_audit_report", "authority": "derived",
    })
    return spec


def exported_spec(
    geometry_spec: dict[str, Any], root: Path, output_dir: Path, audit2_report: Path,
    blender_version: str, appearance_source: Path,
) -> dict[str, Any]:
    spec = copy.deepcopy(geometry_spec)
    pipeline = spec["pipeline"]
    uv_dir = stage_dir(output_dir, "uv")
    repro_dir = stage_dir(output_dir, "reproject")
    repair_dir = stage_dir(output_dir, "repair")
    audit1_dir = stage_dir(output_dir, "audit1")
    pipeline["stage"] = "exported"
    pipeline["master_mesh"] = {
        "status": "approved",
        "source_path": repo_path(repro_dir / "esfera-mecanica-v3-tex.blend", root),
        "exchange_path": repo_path(repro_dir / "esfera-mecanica-v3-tex.glb", root),
    }
    for path, role in (
        ("tools/esfera-mecanica-uv.py", "authoritative_uv_material_emission_preparation"),
        ("tools/reproyectar-texturas.py", "appearance_reprojection"),
        ("astrion-3d-pipeline/tools/audit_m3_esfera.py", "m3_audit_2_recorder"),
        ("astrion-3d-pipeline/tools/run_m4_esfera.py", "m4_local_runner"),
    ):
        ensure_source_tool(spec, path, role)
    pipeline["generated_inputs"] = [
        item for item in pipeline["generated_inputs"] if item.get("role") != "appearance_source"
    ] + [{
        "path": repo_path(appearance_source, root),
        "role": "appearance_source",
        "authority": "external_input",
        "notes": "Appearance only; never authoritative for geometry, UVs, material IDs or emission.",
    }]
    pipeline["outputs"] = [
        {"path": repo_path(repair_dir / "repair-report.json", root), "role": "repair_evidence", "authority": "derived"},
        {"path": repo_path(audit1_dir / "geometry-audit-v0.1.json", root), "role": "geometry_audit_report", "authority": "derived"},
        {"path": repo_path(uv_dir / "esfera-mecanica-v2-uv.blend", root), "role": "authoritative_uv_material_source", "authority": "derived"},
        {"path": repo_path(uv_dir / "esfera-mecanica-v2-uv.glb", root), "role": "uv_material_exchange", "authority": "derived"},
        {"path": repo_path(repro_dir / "emission-mask.png", root), "role": "deterministic_emission_mask", "authority": "derived"},
        {"path": repo_path(repro_dir / "esfera-mecanica-v3-tex.blend", root), "role": "authoritative_textured_source", "authority": "derived"},
        {"path": repo_path(repro_dir / "esfera-mecanica-v3-tex.glb", root), "role": "godot_ready_glb", "authority": "derived"},
        {"path": repo_path(audit2_report, root), "role": "audit_2_report", "authority": "derived"},
    ]
    pipeline["audits"]["uv_textures"] = {"status": "pass", "report": repo_path(audit2_report, root)}
    pipeline["provenance"].update({
        "m4_runner": TOOL,
        "m4_run_manifest": repo_path(output_dir / "run-manifest.json", root),
        "blender_version": blender_version,
        "source_asset_unchanged": True,
        "stage_output_isolation": True,
    })
    pipeline["notes"] = "M4 reproducible export. Godot verification remains a separate post-export gate."
    return spec


def validate_uv_report(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"UV: en rango 0\.\.1=(True|False)\s+pixeles con solape=(\d+)", text)
    topology = re.search(r"triangulos evaluados antes=(\d+) despues=(\d+)", text)
    if not match or match.group(1) != "True" or int(match.group(2)) != 0:
        raise RunnerError("la etapa UV no cumple rango 0..1 y cero solapes")
    if not topology or topology.group(1) != topology.group(2):
        raise RunnerError("la etapa UV cambio el conteo geometrico")


def validate_reprojection_report(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "-> IDENTICA" not in text:
        raise RunnerError("la reproyeccion no demostro geometria identica")


def execute_stage(
    stage: str,
    command: list[str],
    expected: list[Path],
    manifest: dict[str, Any],
    manifest_path: Path,
    root: Path,
    output_dir: Path,
    postcheck: Callable[[], None] | None = None,
) -> None:
    log_path = output_dir / "logs" / f"{stage}.log"
    record = {
        "status": "running", "started_at_utc": utc_now(),
        "command": display_command(command, root), "log": repo_path(log_path, root),
    }
    manifest["stages"][stage] = record
    manifest["status"] = "running"
    write_json(manifest_path, manifest)
    print(f"== {stage} ==")
    try:
        exit_code = run_command(command, log_path, stage, root)
        if exit_code != 0:
            raise RunnerError(f"{stage} termino con codigo {exit_code}; revise {log_path}")
        if postcheck:
            postcheck()
        record.update({
            "status": "complete", "completed_at_utc": utc_now(), "exit_code": exit_code,
            "outputs": stage_outputs(expected, root, log_path),
        })
        write_json(manifest_path, manifest)
    except Exception as exc:
        record.update({"status": "failed", "completed_at_utc": utc_now(), "error": str(exc)})
        manifest["status"] = "failed"
        write_json(manifest_path, manifest)
        raise


def run_pipeline(args: argparse.Namespace, root: Path) -> int:
    spec_path, source_blend, appearance_source, output_dir = resolve_inputs(
        root, args.spec, args.source_blend, args.appearance_source, args.output_dir,
        resume=args.resume, dry_run=args.dry_run,
    )
    base_spec = load_json(spec_path)
    require_valid_spec(base_spec, root, "spec de entrada")
    if base_spec["identity"]["asset_id"] != "esfera-mecanica":
        raise RunnerError("M4 v0.1 solo reproduce esfera-mecanica")
    blender, blender_version = discover_blender(args.blender)
    inputs = {
        "spec": artifact(spec_path, root),
        "source_blend": artifact(source_blend, root),
        "appearance_source": artifact(appearance_source, root),
    }
    requested = stage_range(args.from_stage, args.to_stage)
    manifest_path = output_dir / "run-manifest.json"

    if args.resume:
        manifest = load_json(manifest_path)
        verify_resume_inputs(manifest, inputs, root)
    else:
        manifest = {
            "schema_version": "m4-run-0.1",
            "tool": TOOL,
            "tool_sha256": sha256(Path(__file__).resolve()),
            "asset_id": "esfera-mecanica",
            "created_at_utc": utc_now(),
            "status": "planned" if args.dry_run else "running",
            "inputs": inputs,
            "environment": {
                "python": sys.version.split()[0],
                "python_executable": str(Path(sys.executable).resolve()),
                "blender": str(blender),
                "blender_version": blender_version,
            },
            "requested_stages": list(requested),
            "stages": {},
        }

    if args.dry_run:
        plan = copy.deepcopy(manifest)
        plan["dry_run"] = True
        plan["output_dir"] = repo_path(output_dir, root)
        plan["requested_stages"] = list(requested)
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0

    if not args.resume:
        output_dir.mkdir(parents=True)
        (output_dir / "logs").mkdir()
        write_json(manifest_path, manifest)

    first_requested = STAGES.index(requested[0])
    for prerequisite in STAGES[:first_requested]:
        if not verify_completed_stage(manifest, prerequisite, root):
            raise RunnerError(f"no se puede iniciar en {requested[0]}: falta etapa completa {prerequisite}")

    repair_dir = stage_dir(output_dir, "repair")
    audit1_dir = stage_dir(output_dir, "audit1")
    uv_dir = stage_dir(output_dir, "uv")
    repro_dir = stage_dir(output_dir, "reproject")
    audit2_dir = stage_dir(output_dir, "audit2")
    geometry_spec_path = audit1_dir / "asset-spec.geometry.json"

    for stage in requested:
        if verify_completed_stage(manifest, stage, root):
            print(f"SKIP {stage}: etapa completa, hashes validos")
            continue
        for prerequisite in STAGES[:STAGES.index(stage)]:
            if not verify_completed_stage(manifest, prerequisite, root):
                raise RunnerError(f"{stage} requiere la etapa completa {prerequisite}")
        directory = prepare_stage(output_dir, stage, manifest)

        if stage == "repair":
            command = [
                str(blender), "--background", "--factory-startup",
                "--python", str(root / "tools/reparar-esfera-mecanica.py"), "--",
                "--input", str(source_blend), "--output-dir", str(directory),
                "--repo-root", str(root), "--epsilon", str(args.epsilon),
            ]
            execute_stage(stage, command, [
                directory / "esfera-mecanica-repaired.blend",
                directory / "esfera-mecanica-repaired.glb",
                directory / "repair-report.json",
            ], manifest, manifest_path, root, output_dir)

        elif stage == "audit1":
            report_path = directory / "geometry-audit-v0.1.json"
            audit_input_path = directory / "asset-spec.audit1-input.json"
            verify_reviewed_waiver_scope(base_spec, repair_dir, root)
            audit_input = geometry_audit_input_spec(base_spec, root, repair_dir, report_path)
            require_valid_spec(audit_input, root, "spec de entrada Audit 1")
            write_json(audit_input_path, audit_input)
            command = [
                sys.executable, str(root / "astrion-3d-pipeline/tools/audit_geometry.py"),
                str(audit_input_path), "--output", str(report_path),
                "--diagnostics-dir", str(directory / "diagnostics"),
            ]

            def finish_audit1() -> None:
                report = load_json(report_path)
                if report["audit"]["result"] not in {"pass", "waived"}:
                    raise RunnerError(f"Audit 1 no cerro: {report['audit']['result']}")
                complete = geometry_complete_spec(audit_input, report, root, report_path)
                require_valid_spec(complete, root, "spec posterior a Audit 1")
                write_json(geometry_spec_path, complete)

            execute_stage(stage, command, [
                audit_input_path, geometry_spec_path, report_path,
                directory / "diagnostics/silhouette-esfera-mecanica.png",
            ], manifest, manifest_path, root, output_dir, finish_audit1)

        elif stage == "uv":
            shutil.copy2(repair_dir / "esfera-mecanica-repaired.blend", directory / "esfera-mecanica.blend")
            shutil.copy2(repair_dir / "esfera-mecanica-repaired.glb", directory / "esfera-mecanica-master.glb")
            command = [
                str(blender), "--background", "--factory-startup",
                "--python", str(root / "tools/esfera-mecanica-uv.py"), "--", str(directory),
            ]
            execute_stage(stage, command, [
                directory / "esfera-mecanica.blend", directory / "esfera-mecanica-master.glb",
                directory / "esfera-mecanica-v2-uv.blend", directory / "esfera-mecanica-v2-uv.glb",
                directory / "uv-layout.png", directory / "emission-mask.png",
                directory / "reporte-uv.txt", directory / "renders/three-quarter-clean.png",
            ], manifest, manifest_path, root, output_dir, lambda: validate_uv_report(directory / "reporte-uv.txt"))

        elif stage == "reproject":
            for filename in (
                "esfera-mecanica-v2-uv.blend", "esfera-mecanica-v2-uv.glb",
                "emission-mask.png", "uv-layout.png", "reporte-uv.txt",
            ):
                shutil.copy2(uv_dir / filename, directory / filename)
            shutil.copy2(repair_dir / "repair-report.json", directory / "repair-report.json")
            command = [
                str(blender), "--background", "--factory-startup",
                "--python", str(root / "tools/reproyectar-texturas.py"), "--",
                str(directory), str(appearance_source),
            ]
            execute_stage(stage, command, [
                directory / "esfera-mecanica-v3-tex.blend", directory / "esfera-mecanica-v3-tex.glb",
                directory / "reporte-reproyeccion.txt", directory / "emission-mask.png",
                directory / "textures/basecolor.png", directory / "textures/normal.png",
                directory / "textures/orm.png", directory / "textures/1024/basecolor.png",
                directory / "textures/1024/normal.png", directory / "textures/1024/orm.png",
                directory / "renders/compare-three-quarter.png", directory / "renders/compare-top-256px.png",
            ], manifest, manifest_path, root, output_dir, lambda: validate_reprojection_report(directory / "reporte-reproyeccion.txt"))

        elif stage == "audit2":
            report_path = directory / "uv-texture-audit-m3-v0.1.json"
            final_spec_path = output_dir / "asset-spec.m4.json"
            command = [
                sys.executable, str(root / "astrion-3d-pipeline/tools/audit_m3_esfera.py"),
                "--work-dir", str(repro_dir), "--spec", str(geometry_spec_path),
                "--output", str(report_path), "--appearance-source", str(appearance_source),
            ]

            def finish_audit2() -> None:
                report = load_json(report_path)
                if report["audit"]["result"] != "pass":
                    raise RunnerError(f"Audit 2 no paso: {report['audit']['result']}")
                complete = exported_spec(
                    load_json(geometry_spec_path), root, output_dir, report_path,
                    blender_version, appearance_source,
                )
                require_valid_spec(complete, root, "spec final M4")
                write_json(final_spec_path, complete)

            execute_stage(stage, command, [report_path, final_spec_path], manifest, manifest_path, root, output_dir, finish_audit2)

    manifest["status"] = "complete" if all(verify_completed_stage(manifest, stage, root) for stage in STAGES) else "paused"
    manifest["completed_at_utc"] = utc_now()
    write_json(manifest_path, manifest)
    print(f"{manifest['status'].upper()} {output_dir}")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--spec", required=True, type=Path)
    result.add_argument(
        "--source-blend", type=Path,
        default=Path("source/3d-models/procedural/esfera-mecanica/esfera-mecanica.blend"),
    )
    result.add_argument(
        "--appearance-source", type=Path,
        default=Path("source/3d-models/crudo/esfera-mecanica-v2-meshy.glb"),
    )
    result.add_argument("--output-dir", required=True, type=Path)
    result.add_argument("--blender", type=Path, help="ruta explicita; si se omite usa ASTRION_BLENDER, PATH y rutas conocidas")
    result.add_argument("--dry-run", action="store_true", help="valida y muestra el plan sin crear archivos")
    result.add_argument("--resume", action="store_true", help="continua un run existente y verifica hashes antes de omitir etapas")
    result.add_argument("--from-stage", choices=STAGES, help="primera etapa solicitada; requiere previas completas al reanudar")
    result.add_argument("--to-stage", choices=STAGES, default="audit2")
    result.add_argument("--epsilon", type=float, default=1.0e-5)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not 0 < args.epsilon <= 1.0e-3:
        print("ERROR: --epsilon debe estar en (0, 0.001]", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parents[2]
    try:
        return run_pipeline(args, root)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, RunnerError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
