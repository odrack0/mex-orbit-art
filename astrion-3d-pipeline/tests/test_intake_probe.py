from __future__ import annotations

import importlib.util
import json
import shutil
import unittest
import uuid
from pathlib import Path


ART_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = ART_ROOT / "astrion-3d-pipeline"
WORK_ROOT = PIPELINE_ROOT / "work"
MODULE_PATH = PIPELINE_ROOT / "tools" / "intake_probe.py"
SPEC = importlib.util.spec_from_file_location("intake_probe", MODULE_PATH)
assert SPEC and SPEC.loader
INTAKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INTAKE)


class IntakeProbeTests(unittest.TestCase):
    def setUp(self):
        token = uuid.uuid4().hex[:12]
        self.asset_id = f"intake-test-{token}"
        self.probe_id = f"{self.asset_id}-probe-01"
        self.fixture_dir = WORK_ROOT / "test-intake-probe" / token
        self.fixture_dir.mkdir(parents=True)
        self.run_asset_dir = WORK_ROOT / "generative-probes" / self.asset_id
        self.run_dir = self.run_asset_dir / self.probe_id

        self.spec_path = self.fixture_dir / "asset-spec.json"
        self.reference_path = self.fixture_dir / "reference.png"
        self.spec_path.write_text('{"asset":"test"}\n', encoding="utf-8")
        self.reference_path.write_bytes(b"fresh-reference")
        self.plan_source = self.fixture_dir / "probe-plan-source.json"
        plan = {
            "schema_version": "0.1",
            "record_type": "probe_plan",
            "probe_id": self.probe_id,
            "asset_id": self.asset_id,
            "state": "ready",
            "asset_spec": {
                "path": self.spec_path.relative_to(ART_ROOT).as_posix(),
                "sha256": INTAKE.sha256_file(self.spec_path),
            },
            "question": "Does the fresh candidate preserve the primary silhouette?",
            "providers": [{
                "provider": "meshy",
                "request_id": "meshy-primary",
                "delivery_mode": "manual",
                "generation_mode": "image_to_3d",
            }],
            "references": [{
                "path": self.reference_path.relative_to(ART_ROOT).as_posix(),
                "role": "approved-concept",
                "sha256": INTAKE.sha256_file(self.reference_path),
            }],
            "evaluation_profile": {
                "camera_profile": "top_down_default_v1",
                "screen_size_world_units": 40,
                "coordinate_profile": "astrion_blender_to_godot_v1",
            },
            "stop_conditions": ["Stop if identity is not preserved."],
            "created_at": "2026-09-04T20:00:00-06:00",
            "created_by": "test operator",
        }
        self.plan_source.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        self.model_source = self.fixture_dir / "fresh-candidate.glb"
        self.model_source.write_bytes(b"glTF fresh candidate bytes")

    def tearDown(self):
        if self.fixture_dir.exists():
            shutil.rmtree(self.fixture_dir)
        if self.run_asset_dir.exists():
            shutil.rmtree(self.run_asset_dir)
        for empty_parent in (self.fixture_dir.parent, self.run_asset_dir.parent):
            try:
                empty_parent.rmdir()
            except OSError:
                pass

    def freeze_plan(self) -> Path:
        INTAKE.initialize_plan(self.plan_source, ART_ROOT)
        return self.run_dir / "probe-plan.json"

    def receive(self, **overrides):
        arguments = {
            "provider": "meshy",
            "candidate_id": "meshy-candidate-01",
            "files": [("model", self.model_source)],
            "delivered_by": "test operator",
            "delivered_at": "2026-09-04T20:30:00-06:00",
        }
        arguments.update(overrides)
        return INTAKE.receive_delivery(self.run_dir / "probe-plan.json", ART_ROOT, **arguments)

    def test_init_freezes_exact_plan_bytes_and_hash(self):
        before = self.plan_source.read_bytes()
        result = INTAKE.initialize_plan(self.plan_source, ART_ROOT)
        frozen = self.run_dir / "probe-plan.json"
        self.assertEqual(before, frozen.read_bytes())
        self.assertEqual(INTAKE.sha256_file(self.plan_source), result["sha256"])
        self.assertFalse(result["dry_run"])

    def test_init_dry_run_writes_nothing(self):
        result = INTAKE.initialize_plan(self.plan_source, ART_ROOT, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertFalse(self.run_dir.exists())

    def test_init_rejects_reference_hash_mismatch(self):
        plan = json.loads(self.plan_source.read_text(encoding="utf-8"))
        plan["references"][0]["sha256"] = "0" * 64
        self.plan_source.write_text(json.dumps(plan), encoding="utf-8")
        with self.assertRaisesRegex(INTAKE.IntakeError, "hash mismatch"):
            INTAKE.initialize_plan(self.plan_source, ART_ROOT)
        self.assertFalse(self.run_dir.exists())

    def test_receive_copies_without_mutating_source_and_writes_valid_manifest(self):
        plan_path = self.freeze_plan()
        source_before = self.model_source.read_bytes()
        record = self.receive()
        candidate_dir = self.run_dir / "intake" / "meshy" / "meshy-candidate-01"
        copied = candidate_dir / self.model_source.name
        manifest = candidate_dir / "delivery.json"
        self.assertEqual(source_before, self.model_source.read_bytes())
        self.assertEqual(source_before, copied.read_bytes())
        self.assertTrue(manifest.is_file())
        persisted = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(record, persisted)
        self.assertEqual([], INTAKE.validate_probe.validate_record(persisted))
        self.assertEqual(INTAKE.sha256_file(plan_path), persisted["probe_plan"]["sha256"])
        self.assertEqual(INTAKE.sha256_file(copied), persisted["files"][0]["sha256"])

    def test_receive_dry_run_hashes_but_writes_nothing(self):
        self.freeze_plan()
        record = self.receive(dry_run=True)
        self.assertEqual("probe_delivery", record["record_type"])
        self.assertFalse((self.run_dir / "intake").exists())

    def test_receive_rejects_reference_drift_after_freeze(self):
        self.freeze_plan()
        self.reference_path.write_bytes(b"changed reference")
        with self.assertRaisesRegex(INTAKE.IntakeError, "hash mismatch"):
            self.receive()
        self.assertFalse((self.run_dir / "intake").exists())

    def test_receive_refuses_existing_candidate_directory(self):
        self.freeze_plan()
        self.receive()
        with self.assertRaisesRegex(INTAKE.IntakeError, "already exists"):
            self.receive()

    def test_receive_rejects_provider_not_in_plan(self):
        self.freeze_plan()
        with self.assertRaisesRegex(INTAKE.IntakeError, "not declared"):
            self.receive(provider="tripo")

    def test_receive_requires_model_role(self):
        self.freeze_plan()
        with self.assertRaisesRegex(INTAKE.IntakeError, "requires at least one model"):
            self.receive(files=[("metadata", self.model_source)])

    def test_receive_rejects_credentials_before_writing(self):
        self.freeze_plan()
        with self.assertRaisesRegex(INTAKE.IntakeError, "credential field is forbidden"):
            self.receive(settings={"provider": {"access_token": "forbidden"}})
        self.assertFalse((self.run_dir / "intake").exists())

    def test_receive_rejects_non_object_settings(self):
        self.freeze_plan()
        with self.assertRaisesRegex(INTAKE.IntakeError, "settings: expected object"):
            self.receive(settings=[])
        self.assertFalse((self.run_dir / "intake").exists())

    def test_legacy_source_directories_are_detected_without_writing_them(self):
        raw = ART_ROOT / "source" / "3d-models" / "crudo" / "candidate.glb"
        polished = ART_ROOT / "source" / "3d-models" / "pulido" / "candidate.glb"
        render = ART_ROOT / "source" / "renders" / "candidate.png"
        self.assertTrue(INTAKE.is_protected_legacy_input(raw, ART_ROOT))
        self.assertTrue(INTAKE.is_protected_legacy_input(polished, ART_ROOT))
        self.assertTrue(INTAKE.is_protected_legacy_input(render, ART_ROOT))
        self.assertFalse(INTAKE.is_protected_legacy_input(self.model_source, ART_ROOT))


if __name__ == "__main__":
    unittest.main()
