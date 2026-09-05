from __future__ import annotations

import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path


ART_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ART_ROOT / "tools" / "reparar-esfera-mecanica.py"
SPEC = importlib.util.spec_from_file_location("repair_esfera", SCRIPT_PATH)
assert SPEC and SPEC.loader
REPAIR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPAIR)


class RepairSphereSafetyTests(unittest.TestCase):
    def test_script_imports_without_blender_for_cli_tests(self):
        self.assertIsNone(REPAIR.bpy)
        self.assertEqual("astrion-repair-esfera-mecanica/0.1", REPAIR.SCRIPT_VERSION)

    def test_source_output_is_rejected(self):
        source = ART_ROOT / "source" / "3d-models" / "procedural" / "esfera-mecanica" / "esfera-mecanica.blend"
        with self.assertRaisesRegex(ValueError, "source/"):
            REPAIR.validate_paths(source, ART_ROOT / "source" / "repair-test", ART_ROOT)

    def test_existing_output_artifact_is_rejected(self):
        source = ART_ROOT / "source" / "3d-models" / "procedural" / "esfera-mecanica" / "esfera-mecanica.blend"
        with tempfile.TemporaryDirectory(dir=ART_ROOT) as raw:
            output = Path(raw)
            (output / "repair-report.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ya contiene artefactos"):
                REPAIR.validate_paths(source, output, ART_ROOT)

    def test_invalid_epsilon_is_rejected(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                REPAIR.blender_arguments([
                    "--input", "in.blend", "--output-dir", "out", "--epsilon", "0",
                ])


if __name__ == "__main__":
    unittest.main()
