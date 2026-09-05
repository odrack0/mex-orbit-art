from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
ART_ROOT = PIPELINE_ROOT.parent
WORK_ROOT = PIPELINE_ROOT / "work"
TOOLS_ROOT = PIPELINE_ROOT / "tools"
TESTS_ROOT = PIPELINE_ROOT / "tests"
for search_path in (TOOLS_ROOT, TESTS_ROOT):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

import evaluate_probe  # noqa: E402
import intake_probe  # noqa: E402
import review_probe  # noqa: E402
import close_probe  # noqa: E402
import validate_probe  # noqa: E402
from test_audit_geometry import test_spec, write_test_glb  # noqa: E402


class EvaluateProbeTests(unittest.TestCase):
    def setUp(self):
        token = uuid.uuid4().hex[:12]
        self.asset_id = f"measure-test-{token}"
        self.probe_id = f"{self.asset_id}-probe-01"
        self.candidate_id = "meshy-candidate-01"
        self.fixture_dir = WORK_ROOT / "test-evaluate-probe" / token
        self.fixture_dir.mkdir(parents=True)
        self.run_asset_dir = WORK_ROOT / "generative-probes" / self.asset_id
        self.run_dir = self.run_asset_dir / self.probe_id
        self.report_asset_dir = PIPELINE_ROOT / "reports" / "generative-probes" / self.asset_id
        self.report_dir = self.report_asset_dir / self.probe_id

        self.reference_path = self.fixture_dir / "geometry-reference.png"
        self.reference_path.write_bytes(b"geometry-reference")
        self.spec_path = self.fixture_dir / "asset-spec.json"
        spec = test_spec()
        spec["identity"]["asset_id"] = self.asset_id
        spec["pipeline"]["stage"] = "generative_probe"
        spec["pipeline"]["geometry_outcome"] = "undecided"
        spec["pipeline"]["master_mesh"] = None
        self.spec_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")

        self.plan_source = self.fixture_dir / "probe-plan-source.json"
        plan = {
            "schema_version": "0.1",
            "record_type": "probe_plan",
            "probe_id": self.probe_id,
            "asset_id": self.asset_id,
            "state": "ready",
            "asset_spec": {
                "path": self.spec_path.relative_to(ART_ROOT).as_posix(),
                "sha256": intake_probe.sha256_file(self.spec_path),
            },
            "question": "Does this generated cube preserve the geometry reference?",
            "providers": [{
                "provider": "meshy",
                "request_id": "meshy-primary",
                "delivery_mode": "manual",
                "generation_mode": "image_to_3d",
            }],
            "references": [{
                "path": self.reference_path.relative_to(ART_ROOT).as_posix(),
                "role": "geometry-reference",
                "sha256": intake_probe.sha256_file(self.reference_path),
            }],
            "evaluation_profile": {
                "camera_profile": "top_down_default_v1",
                "screen_size_world_units": 40,
                "coordinate_profile": "astrion_blender_to_godot_v1",
            },
            "stop_conditions": ["Stop if the primary silhouette is not preserved."],
            "created_at": "2026-09-04T20:00:00-06:00",
            "created_by": "test operator",
        }
        self.plan_source.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        self.model_source = self.fixture_dir / "candidate.glb"
        write_test_glb(self.model_source, transformed=True)

    def tearDown(self):
        for target in (self.fixture_dir, self.run_asset_dir, self.report_asset_dir):
            if target.exists():
                shutil.rmtree(target)
        for empty_parent in (
            self.fixture_dir.parent,
            self.run_asset_dir.parent,
            self.report_asset_dir.parent,
        ):
            try:
                empty_parent.rmdir()
            except OSError:
                pass

    def prepare_candidate(self, *, invalid: bool = False) -> tuple[Path, Path]:
        if invalid:
            self.model_source.write_bytes(b"not a GLB")
        intake_probe.initialize_plan(self.plan_source, ART_ROOT)
        plan_path = self.run_dir / "probe-plan.json"
        intake_probe.receive_delivery(
            plan_path,
            ART_ROOT,
            provider="meshy",
            candidate_id=self.candidate_id,
            files=[("model", self.model_source)],
            delivered_by="test operator",
            delivered_at="2026-09-04T20:30:00-06:00",
        )
        delivery_path = self.run_dir / "intake" / "meshy" / self.candidate_id / "delivery.json"
        return plan_path, delivery_path

    def output_dir(self) -> Path:
        return self.run_dir / "diagnostics" / "meshy" / self.candidate_id

    def write_review_source(self, measurement: dict, *, status: str = "pass") -> Path:
        review_path = self.fixture_dir / "review-source.json"
        review = {
            "identity_review": [
                {
                    "criterion": row["criterion"],
                    "status": status,
                    "notes": "Explicit test review against the frozen geometry reference.",
                }
                for row in measurement["identity_review"]
            ],
            "suggested_outcome": "repair",
            "reviewed_at": "2026-09-04T21:00:00-06:00",
            "reviewed_by": "test reviewer",
            "notes": "Probe review only; this is not an Audit 1 result.",
        }
        review_path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
        return review_path

    def write_decision_source(self, evaluation_path: Path, *, sha256: str | None = None) -> Path:
        decision_path = self.fixture_dir / "decision-source.json"
        decision = {
            "schema_version": "0.1",
            "record_type": "probe_decision",
            "probe_id": self.probe_id,
            "asset_id": self.asset_id,
            "state": "closed",
            "comparison_status": "candidate_selected",
            "evaluations": [{
                "path": evaluation_path.relative_to(ART_ROOT).as_posix(),
                "sha256": sha256 or intake_probe.sha256_file(evaluation_path),
                "provider": "meshy",
                "candidate_id": self.candidate_id,
            }],
            "selected_candidate_id": self.candidate_id,
            "intended_outcome": "repair",
            "rationale": "The evaluated candidate preserves identity and is suitable for repair.",
            "reviewer": "test reviewer",
            "reviewed_at": "2026-09-04T21:30:00-06:00",
            "production_handoff": {
                "status": "not_requested",
                "asset_spec_path": None,
                "evidence_report_path": None,
            },
            "notes": "Closeout test; no production promotion.",
        }
        decision_path.write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")
        return decision_path

    def prepare_evaluation(self) -> tuple[Path, Path, Path]:
        plan_path, delivery_path = self.prepare_candidate()
        measurement = evaluate_probe.measure_candidate(
            plan_path, delivery_path, ART_ROOT, heavy=False
        )
        measurement_path = self.output_dir() / "candidate-measurement.json"
        review_path = self.write_review_source(measurement)
        review_probe.publish_review(measurement_path, review_path, ART_ROOT)
        return plan_path, delivery_path, self.output_dir() / "candidate-evaluation.json"

    def test_dry_run_verifies_inputs_without_writing_diagnostics(self):
        plan_path, delivery_path = self.prepare_candidate()
        preview = evaluate_probe.measure_candidate(
            plan_path, delivery_path, ART_ROOT, heavy=False, dry_run=True
        )
        self.assertTrue(preview["dry_run"])
        self.assertEqual("fast", preview["mode"])
        self.assertFalse(self.output_dir().exists())

    def test_valid_glb_writes_measured_record_and_hashed_diagnostics(self):
        plan_path, delivery_path = self.prepare_candidate()
        record = evaluate_probe.measure_candidate(
            plan_path, delivery_path, ART_ROOT, heavy=False
        )
        output_dir = self.output_dir()
        persisted = json.loads(
            (output_dir / "candidate-measurement.json").read_text(encoding="utf-8")
        )
        self.assertEqual(record, persisted)
        self.assertEqual("measured", record["state"])
        self.assertEqual("usable", record["metrics"]["parse_status"])
        self.assertEqual(12, record["metrics"]["triangles"])
        self.assertEqual(1, record["metrics"]["connected_components"])
        self.assertIsNone(record["suggested_outcome"])
        self.assertNotIn("audit", record)
        self.assertTrue(all(row["status"] == "not_assessed" for row in record["identity_review"]))
        self.assertEqual([], validate_probe.validate_record(record))
        for artifact in record["diagnostics"]:
            artifact_path = ART_ROOT / artifact["path"]
            self.assertTrue(artifact_path.is_file())
            self.assertEqual(artifact["sha256"], intake_probe.sha256_file(artifact_path))

    def test_tampered_intake_model_is_rejected_before_measurement(self):
        plan_path, delivery_path = self.prepare_candidate()
        delivered_model = delivery_path.parent / self.model_source.name
        delivered_model.write_bytes(delivered_model.read_bytes() + b"tampered")
        with self.assertRaisesRegex(evaluate_probe.EvaluationError, "hash mismatch"):
            evaluate_probe.measure_candidate(plan_path, delivery_path, ART_ROOT, heavy=False)
        self.assertFalse(self.output_dir().exists())

    def test_invalid_glb_publishes_invalid_measurement_without_diagnostic(self):
        plan_path, delivery_path = self.prepare_candidate(invalid=True)
        record = evaluate_probe.measure_candidate(
            plan_path, delivery_path, ART_ROOT, heavy=False
        )
        self.assertEqual("invalid", record["state"])
        self.assertEqual("invalid", record["metrics"]["parse_status"])
        self.assertEqual([], record["diagnostics"])
        self.assertEqual([], validate_probe.validate_record(record))
        self.assertTrue((self.output_dir() / "candidate-measurement.json").is_file())

    def test_existing_candidate_diagnostics_are_never_overwritten(self):
        plan_path, delivery_path = self.prepare_candidate()
        evaluate_probe.measure_candidate(plan_path, delivery_path, ART_ROOT, heavy=False)
        with self.assertRaisesRegex(evaluate_probe.EvaluationError, "already exist"):
            evaluate_probe.measure_candidate(plan_path, delivery_path, ART_ROOT, heavy=False)

    def test_explicit_review_publishes_separate_evaluated_record(self):
        plan_path, delivery_path = self.prepare_candidate()
        measurement = evaluate_probe.measure_candidate(
            plan_path, delivery_path, ART_ROOT, heavy=False
        )
        measurement_path = self.output_dir() / "candidate-measurement.json"
        review_path = self.write_review_source(measurement)
        preview = review_probe.publish_review(
            measurement_path, review_path, ART_ROOT, dry_run=True
        )
        self.assertTrue(preview["dry_run"])
        self.assertFalse((self.output_dir() / "candidate-evaluation.json").exists())
        evaluation = review_probe.publish_review(measurement_path, review_path, ART_ROOT)
        self.assertEqual("measured", measurement["state"])
        self.assertEqual("evaluated", evaluation["state"])
        self.assertEqual("repair", evaluation["suggested_outcome"])
        self.assertEqual([], validate_probe.validate_record(evaluation))
        self.assertTrue((self.output_dir() / "candidate-evaluation.json").is_file())

    def test_review_rejects_unassessed_identity_criterion(self):
        plan_path, delivery_path = self.prepare_candidate()
        measurement = evaluate_probe.measure_candidate(
            plan_path, delivery_path, ART_ROOT, heavy=False
        )
        review_path = self.write_review_source(measurement, status="not_assessed")
        with self.assertRaisesRegex(review_probe.ReviewError, "must be pass, warning, or fail"):
            review_probe.publish_review(
                self.output_dir() / "candidate-measurement.json", review_path, ART_ROOT
            )
        self.assertFalse((self.output_dir() / "candidate-evaluation.json").exists())

    def test_review_rejects_changed_diagnostic_hash(self):
        plan_path, delivery_path = self.prepare_candidate()
        measurement = evaluate_probe.measure_candidate(
            plan_path, delivery_path, ART_ROOT, heavy=False
        )
        review_path = self.write_review_source(measurement)
        diagnostic = ART_ROOT / measurement["diagnostics"][0]["path"]
        diagnostic.write_bytes(diagnostic.read_bytes() + b"changed")
        with self.assertRaisesRegex(review_probe.ReviewError, r"diagnostic\[0\] hash mismatch"):
            review_probe.publish_review(
                self.output_dir() / "candidate-measurement.json", review_path, ART_ROOT
            )

    def test_closeout_publishes_comparison_and_valid_closed_decision(self):
        plan_path, delivery_path, evaluation_path = self.prepare_evaluation()
        decision_source = self.write_decision_source(evaluation_path)
        preview = close_probe.close_probe(
            plan_path, [delivery_path], [evaluation_path], decision_source, ART_ROOT,
            dry_run=True,
        )
        self.assertTrue(preview["dry_run"])
        self.assertFalse(self.report_dir.exists())
        comparison = close_probe.close_probe(
            plan_path, [delivery_path], [evaluation_path], decision_source, ART_ROOT
        )
        decision = json.loads((self.report_dir / "decision.json").read_text(encoding="utf-8"))
        self.assertEqual([], validate_probe.validate_record(decision))
        self.assertEqual("closed", decision["state"])
        self.assertEqual("probe_evidence_only", comparison["authority"]["scope"])
        self.assertFalse(comparison["authority"]["master_mesh_promoted"])
        self.assertTrue((self.report_dir / "comparison.json").is_file())

    def test_closeout_rejects_wrong_evaluation_hash(self):
        plan_path, delivery_path, evaluation_path = self.prepare_evaluation()
        decision_source = self.write_decision_source(evaluation_path, sha256="0" * 64)
        with self.assertRaisesRegex(close_probe.CloseError, "evaluation hash mismatch"):
            close_probe.close_probe(
                plan_path, [delivery_path], [evaluation_path], decision_source, ART_ROOT
            )
        self.assertFalse(self.report_dir.exists())

    def test_closeout_never_overwrites_existing_report_directory(self):
        plan_path, delivery_path, evaluation_path = self.prepare_evaluation()
        decision_source = self.write_decision_source(evaluation_path)
        close_probe.close_probe(
            plan_path, [delivery_path], [evaluation_path], decision_source, ART_ROOT
        )
        with self.assertRaisesRegex(close_probe.CloseError, "already exists"):
            close_probe.close_probe(
                plan_path, [delivery_path], [evaluation_path], decision_source, ART_ROOT
            )


if __name__ == "__main__":
    unittest.main()
