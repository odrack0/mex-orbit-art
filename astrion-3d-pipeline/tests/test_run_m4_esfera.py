from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ART_ROOT = Path(__file__).resolve().parents[2]
WORK_ROOT = ART_ROOT / "astrion-3d-pipeline" / "work"
SCRIPT_PATH = ART_ROOT / "astrion-3d-pipeline" / "tools" / "run_m4_esfera.py"
SPEC = importlib.util.spec_from_file_location("run_m4_esfera", SCRIPT_PATH)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class M4RunnerTests(unittest.TestCase):
    def test_stage_range_rejects_reverse_order(self):
        with self.assertRaisesRegex(RUNNER.RunnerError, "despues"):
            RUNNER.stage_range("reproject", "uv")

    def test_output_must_be_new_and_under_work(self):
        with tempfile.TemporaryDirectory(dir=WORK_ROOT) as raw:
            base = Path(raw)
            spec = base / "input.json"
            blend = base / "input.blend"
            appearance = base / "appearance.glb"
            spec.write_text("{}", encoding="utf-8")
            blend.write_bytes(b"blend")
            appearance.write_bytes(b"glb")
            output = base / "run"
            resolved = RUNNER.resolve_inputs(
                ART_ROOT, spec, blend, appearance, output,
                resume=False, dry_run=True,
            )
            self.assertEqual(output.resolve(), resolved[3])
            output.mkdir()
            with self.assertRaisesRegex(RUNNER.RunnerError, "ya existe"):
                RUNNER.resolve_inputs(
                    ART_ROOT, spec, blend, appearance, output,
                    resume=False, dry_run=True,
                )

    def test_output_outside_pipeline_work_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=WORK_ROOT) as raw:
            base = Path(raw)
            spec = base / "input.json"
            blend = base / "input.blend"
            appearance = base / "appearance.glb"
            spec.write_text("{}", encoding="utf-8")
            blend.write_bytes(b"blend")
            appearance.write_bytes(b"glb")
            with self.assertRaisesRegex(RUNNER.RunnerError, "carpeta hija"):
                RUNNER.resolve_inputs(
                    ART_ROOT, spec, blend, appearance, ART_ROOT / "unsafe-run",
                    resume=False, dry_run=True,
                )

    def test_completed_stage_hash_detects_tampering(self):
        with tempfile.TemporaryDirectory(dir=WORK_ROOT) as raw:
            path = Path(raw) / "result.txt"
            path.write_text("approved", encoding="utf-8")
            manifest = {"stages": {"uv": {
                "status": "complete",
                "outputs": [RUNNER.artifact(path, ART_ROOT)],
            }}}
            self.assertTrue(RUNNER.verify_completed_stage(manifest, "uv", ART_ROOT))
            path.write_text("changed", encoding="utf-8")
            self.assertFalse(RUNNER.verify_completed_stage(manifest, "uv", ART_ROOT))

    def test_reviewed_waiver_is_bound_to_repair_hash(self):
        with tempfile.TemporaryDirectory(dir=WORK_ROOT) as raw:
            base_dir = Path(raw)
            reviewed_dir = base_dir / "reviewed"
            current_dir = base_dir / "current"
            reviewed_dir.mkdir()
            current_dir.mkdir()
            report = {"outputs": {"glb": {"sha256": "abc"}}}
            (reviewed_dir / "repair-report.json").write_text(json.dumps(report), encoding="utf-8")
            (current_dir / "repair-report.json").write_text(json.dumps(report), encoding="utf-8")
            base_spec = {"pipeline": {
                "audits": {"geometry": {"status": "waived", "waivers": [{"check_id": "x"}]}},
                "provenance": {
                    "repair_report": RUNNER.repo_path(reviewed_dir / "repair-report.json", ART_ROOT),
                },
            }}
            RUNNER.verify_reviewed_waiver_scope(base_spec, current_dir, ART_ROOT)
            report["outputs"]["glb"]["sha256"] = "different"
            (current_dir / "repair-report.json").write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(RUNNER.RunnerError, "hash revisado"):
                RUNNER.verify_reviewed_waiver_scope(base_spec, current_dir, ART_ROOT)


if __name__ == "__main__":
    unittest.main()
