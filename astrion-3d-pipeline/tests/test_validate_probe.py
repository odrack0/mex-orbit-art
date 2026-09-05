from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
MODULE_PATH = PIPELINE_ROOT / "tools" / "validate_probe.py"
SPEC = importlib.util.spec_from_file_location("validate_probe", MODULE_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fixture(name: str):
    return load_json(FIXTURES / name)


def local_refs(value):
    if isinstance(value, dict):
        if isinstance(value.get("$ref"), str) and value["$ref"].startswith("#/$defs/"):
            yield value["$ref"]
        for child in value.values():
            yield from local_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from local_refs(child)


class ValidateProbeTests(unittest.TestCase):
    VALID_FIXTURES = {
        "probe-valid-plan.json": "probe_plan",
        "probe-valid-delivery.json": "probe_delivery",
        "probe-valid-tripo-unavailable-delivery.json": "probe_delivery",
        "probe-valid-evaluation.json": "candidate_evaluation",
        "probe-valid-decision.json": "probe_decision",
    }

    def test_each_valid_record_passes(self):
        for filename, record_type in self.VALID_FIXTURES.items():
            with self.subTest(filename=filename):
                data = fixture(filename)
                self.assertEqual(record_type, data["record_type"])
                self.assertEqual([], VALIDATOR.validate_record(data))

    def test_valid_record_set_passes(self):
        records = [fixture(filename) for filename in self.VALID_FIXTURES]
        self.assertEqual([], VALIDATOR.validate_record_set(records))

    def test_checked_in_schemas_match_validator_contract(self):
        names = {
            "probe-plan-v0.1.schema.json": "probe_plan",
            "probe-delivery-v0.1.schema.json": "probe_delivery",
            "probe-evaluation-v0.1.schema.json": "candidate_evaluation",
            "probe-decision-v0.1.schema.json": "probe_decision",
        }
        for filename, record_type in names.items():
            with self.subTest(filename=filename):
                schema = load_json(PIPELINE_ROOT / "schemas" / filename)
                self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
                self.assertEqual("0.1", schema["properties"]["schema_version"]["const"])
                self.assertEqual(record_type, schema["properties"]["record_type"]["const"])
                for ref in local_refs(schema):
                    self.assertIn(ref.removeprefix("#/$defs/"), schema["$defs"], ref)
        plan = load_json(PIPELINE_ROOT / "schemas" / "probe-plan-v0.1.schema.json")
        self.assertEqual(VALIDATOR.PLAN_STATES, set(plan["properties"]["state"]["enum"]))
        self.assertEqual(VALIDATOR.PROVIDERS, set(plan["$defs"]["providerRequest"]["properties"]["provider"]["enum"]))
        decision = load_json(PIPELINE_ROOT / "schemas" / "probe-decision-v0.1.schema.json")
        self.assertEqual(VALIDATOR.COMPARISON_STATUSES, set(decision["properties"]["comparison_status"]["enum"]))

    def test_invalid_fixtures_expose_safety_errors(self):
        cases = {
            "probe-invalid-path.json": "must be repository-relative",
            "probe-invalid-secret.json": "sensitive credential field is forbidden",
            "probe-invalid-evaluation-state.json": "must be 'invalid' when state is 'invalid'",
            "probe-invalid-promotion.json": "$.master_mesh: unknown field",
        }
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                errors = VALIDATOR.validate_record(fixture(filename))
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_delivery_is_bound_to_its_intake_directory(self):
        data = fixture("probe-valid-delivery.json")
        data["files"][0]["path"] = (
            "astrion-3d-pipeline/work/generative-probes/test-prop/"
            "another-probe/intake/meshy/meshy-candidate-01/model.glb"
        )
        errors = VALIDATOR.validate_record(data)
        self.assertTrue(any("must be inside" in error for error in errors), errors)

    def test_evaluation_cannot_claim_an_audit_result(self):
        data = fixture("probe-valid-evaluation.json")
        data["audit_status"] = "pass"
        errors = VALIDATOR.validate_record(data)
        self.assertIn("$.audit_status: unknown field", errors)

    def test_measured_state_requires_diagnostics_and_defers_judgment(self):
        data = fixture("probe-valid-evaluation.json")
        data["state"] = "measured"
        data["suggested_outcome"] = None
        data["identity_review"][0]["status"] = "not_assessed"
        self.assertEqual([], VALIDATOR.validate_record(data))
        data["identity_review"][0]["status"] = "pass"
        errors = VALIDATOR.validate_record(data)
        self.assertTrue(any("while state is 'measured'" in error for error in errors), errors)

    def test_decision_relationships_are_explicit(self):
        data = fixture("probe-valid-decision.json")
        data["selected_candidate_id"] = None
        errors = VALIDATOR.validate_record(data)
        self.assertTrue(any("required when comparison_status" in error for error in errors), errors)

        data = fixture("probe-valid-decision.json")
        data["intended_outcome"] = "procedural_direct"
        errors = VALIDATOR.validate_record(data)
        self.assertTrue(any("candidate selection requires" in error for error in errors), errors)

    def test_approved_handoff_contains_only_evidence_pointers(self):
        data = fixture("probe-valid-decision.json")
        data["production_handoff"] = {
            "status": "approved",
            "asset_spec_path": "source/3d-models/specs/test-prop.json",
            "evidence_report_path": (
                "astrion-3d-pipeline/reports/generative-probes/test-prop/"
                "test-prop-probe-20260904-01/decision.json"
            ),
        }
        self.assertEqual([], VALIDATOR.validate_record(data))

    def test_unknown_provenance_is_explicitly_valid(self):
        data = fixture("probe-valid-delivery.json")
        self.assertEqual("unknown", data["provenance"]["model"])
        self.assertEqual("unknown", data["provenance"]["license"])
        self.assertEqual([], VALIDATOR.validate_record(data))

    def test_paths_do_not_need_to_exist_in_m5a(self):
        data = fixture("probe-valid-plan.json")
        data["asset_spec"]["path"] = "does/not/exist/spec.json"
        data["references"][0]["path"] = "does/not/exist/reference.png"
        self.assertEqual([], VALIDATOR.validate_record(data))

    def test_record_set_rejects_undeclared_provider_request(self):
        plan = fixture("probe-valid-plan.json")
        delivery = fixture("probe-valid-delivery.json")
        delivery["request_id"] = "undeclared-request"
        errors = VALIDATOR.validate_record_set([plan, delivery])
        self.assertTrue(any("does not match a provider request" in error for error in errors), errors)

    def test_record_set_rejects_provider_setting_mismatch(self):
        plan = fixture("probe-valid-plan.json")
        delivery = fixture("probe-valid-delivery.json")
        delivery["provenance"]["generation_mode"] = "text_to_3d"
        errors = VALIDATOR.validate_record_set([plan, delivery])
        self.assertTrue(any("does not match plan value" in error for error in errors), errors)

    def test_record_set_requires_delivery_before_evaluation(self):
        plan = fixture("probe-valid-plan.json")
        evaluation = fixture("probe-valid-evaluation.json")
        errors = VALIDATOR.validate_record_set([plan, evaluation])
        self.assertTrue(any("has no matching delivery" in error for error in errors), errors)

    def test_final_selection_cannot_silently_omit_planned_provider(self):
        records = [
            fixture("probe-valid-plan.json"),
            fixture("probe-valid-delivery.json"),
            fixture("probe-valid-evaluation.json"),
            fixture("probe-valid-decision.json"),
        ]
        errors = VALIDATOR.validate_record_set(records)
        self.assertTrue(any("cannot omit planned provider branch" in error for error in errors), errors)

    def test_record_set_rejects_identity_mismatch(self):
        plan = fixture("probe-valid-plan.json")
        delivery = fixture("probe-valid-delivery.json")
        delivery["asset_id"] = "another-asset"
        errors = VALIDATOR.validate_record_set([plan, delivery])
        self.assertIn("record set: all records must share asset_id and probe_id", errors)

    def test_evaluation_input_must_match_delivery(self):
        plan = fixture("probe-valid-plan.json")
        delivery = fixture("probe-valid-delivery.json")
        evaluation = fixture("probe-valid-evaluation.json")
        evaluation["input_model"]["sha256"] = "0" * 64
        errors = VALIDATOR.validate_record_set([plan, delivery, evaluation])
        self.assertTrue(any("input_model does not match" in error for error in errors), errors)

    def test_multi_record_set_requires_plan(self):
        records = [fixture("probe-valid-delivery.json"), fixture("probe-valid-evaluation.json")]
        errors = VALIDATOR.validate_record_set(records)
        self.assertIn("record set: a multi-record set requires one probe_plan", errors)

    def test_timestamp_requires_timezone(self):
        data = fixture("probe-valid-plan.json")
        data["created_at"] = "2026-09-04T17:30:00"
        errors = VALIDATOR.validate_record(data)
        self.assertTrue(any("timestamp with timezone" in error for error in errors), errors)

    def test_nested_credential_names_are_rejected(self):
        data = fixture("probe-valid-delivery.json")
        data["provenance"]["settings"] = {"provider": {"temporary_access_token": "forbidden"}}
        errors = VALIDATOR.validate_record(data)
        self.assertTrue(any("temporary_access_token" in error for error in errors), errors)

    def test_malformed_values_do_not_crash(self):
        data = fixture("probe-valid-evaluation.json")
        data["metrics"] = []
        data["diagnostics"] = {}
        data["selected_candidate_id"] = []
        errors = VALIDATOR.validate_record(data)
        self.assertTrue(errors)

    def test_validation_does_not_mutate_records(self):
        data = fixture("probe-valid-delivery.json")
        before = copy.deepcopy(data)
        VALIDATOR.validate_record(data)
        self.assertEqual(before, data)

    def test_empty_or_unknown_record_is_invalid(self):
        self.assertEqual(["$: expected object"], VALIDATOR.validate_record([]))
        errors = VALIDATOR.validate_record({"record_type": "provider_job"})
        self.assertTrue(any("expected one of" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
