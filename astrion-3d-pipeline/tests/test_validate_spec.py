from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
ART_ROOT = PIPELINE_ROOT.parent
FIXTURES = Path(__file__).parent / "fixtures"
MODULE_PATH = PIPELINE_ROOT / "tools" / "validate_spec.py"
SPEC = importlib.util.spec_from_file_location("validate_spec", MODULE_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class ValidateSpecTests(unittest.TestCase):
    def test_minimal_fixture_is_valid(self):
        self.assertEqual([], VALIDATOR.validate_spec(load_json(FIXTURES / "valid-minimal.json")))

    def test_reviewed_sphere_example_is_valid(self):
        path = ART_ROOT / "source" / "3d-models" / "specs" / "esfera-mecanica.json"
        self.assertEqual([], VALIDATOR.validate_spec(load_json(path)))

    def test_checked_in_schema_is_json_and_matches_validator_contract(self):
        schema = load_json(PIPELINE_ROOT / "schemas" / "asset-spec-v0.1.schema.json")
        self.assertEqual("0.1", schema["properties"]["schema_version"]["const"])
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        definitions = schema["$defs"]
        self.assertEqual(VALIDATOR.CATEGORIES, set(definitions["identity"]["properties"]["category"]["enum"]))
        self.assertEqual(VALIDATOR.ORIGINS, set(definitions["geometry"]["properties"]["allowed_origins"]["items"]["enum"]))
        self.assertEqual(VALIDATOR.OUTCOMES, set(definitions["pipeline"]["properties"]["geometry_outcome"]["enum"]))
        self.assertEqual(VALIDATOR.STAGES, definitions["pipeline"]["properties"]["stage"]["enum"])
        self.assertEqual(VALIDATOR.MAPS, set(definitions["appearance"]["properties"]["maps_required"]["items"]["enum"]))

    def test_invalid_fixtures_report_expected_contract_errors(self):
        cases = {
            "invalid-missing-identity.json": "$.identity: expected object",
            "invalid-category.json": "$.identity.category: expected one of",
            "invalid-origin.json": "$.geometry.preferred_origin: must also appear in allowed_origins",
            "invalid-triangle-order.json": "$.geometry.soft_triangle_target: must be <= triangle_ceiling",
            "invalid-stage-outcome.json": "$.pipeline.geometry_outcome: must be decided",
            "invalid-path.json": "$.pipeline.source_inputs[0].path: invalid repository path",
        }
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                errors = VALIDATOR.validate_spec(load_json(FIXTURES / filename))
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_unknown_critical_field_is_rejected(self):
        data = load_json(FIXTURES / "valid-minimal.json")
        data["geometry"]["triangle_celing"] = 900
        errors = VALIDATOR.validate_spec(data)
        self.assertIn("$.geometry.triangle_celing: unknown field", errors)

    def test_provenance_is_extensible(self):
        data = copy.deepcopy(load_json(FIXTURES / "valid-minimal.json"))
        data["pipeline"]["provenance"]["future_field"] = {"allowed": True}
        self.assertEqual([], VALIDATOR.validate_spec(data))

    def test_validation_does_not_require_paths_to_exist(self):
        data = copy.deepcopy(load_json(FIXTURES / "valid-minimal.json"))
        data["pipeline"]["source_inputs"].append({
            "path": "does/not/exist.glb",
            "role": "reference",
            "authority": "external_input",
        })
        self.assertEqual([], VALIDATOR.validate_spec(data))

    def test_empty_or_non_object_root_is_invalid(self):
        self.assertTrue(VALIDATOR.validate_spec({}))
        self.assertEqual(["$: expected object"], VALIDATOR.validate_spec([]))

    def test_audit_waiver_requires_complete_traceability(self):
        valid = {
            "status": "waived",
            "report": "reports/geometry.json",
            "waivers": [{
                "check_id": "never_visible_geometry",
                "reason": "Closed semantic shells intentionally overlap the core.",
                "scope": "Mechanical sphere v1 plate bases only.",
                "reviewer": "repository owner",
                "revisit_condition": "Revisit if topology, camera, or animation changes.",
                "expires": None,
            }],
        }
        errors = []
        VALIDATOR._audit_reference(valid, "$.audit", errors)
        self.assertEqual([], errors)
        invalid = copy.deepcopy(valid)
        del invalid["waivers"][0]["reviewer"]
        errors = []
        VALIDATOR._audit_reference(invalid, "$.audit", errors)
        self.assertTrue(any("reviewer: required" in error for error in errors), errors)

    def test_malformed_value_types_do_not_crash(self):
        data = copy.deepcopy(load_json(FIXTURES / "valid-minimal.json"))
        data["identity"]["category"] = []
        data["appearance"]["texture_resolutions"] = [{}]
        data["pipeline"]["stage"] = []
        errors = VALIDATOR.validate_spec(data)
        self.assertTrue(any("$.identity.category" in error for error in errors))
        self.assertTrue(any("$.appearance.texture_resolutions[0]" in error for error in errors))
        self.assertTrue(any("$.pipeline.stage" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
