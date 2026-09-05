from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ART_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ART_ROOT / "astrion-3d-pipeline" / "tools" / "audit_m3_esfera.py"
SPEC = importlib.util.spec_from_file_location("audit_m3_esfera", SCRIPT_PATH)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class M3SphereAuditTests(unittest.TestCase):
    def test_uv_report_parses_dynamic_repaired_topology(self):
        report = """
  Core_Lens              MAT_HULL=0  MAT_RECESSES=0  MAT_EMISSION=190
  TOTAL                  MAT_HULL=1510  MAT_RECESSES=2466  MAT_EMISSION=190
reparacion UV de pliegues: poligonos aislados=['Plates_Band_Equator:282']
UV: en rango 0..1=True  pixeles con solape=0  ocupacion=43.2%  texeles/unidad (visibles): media=244 p5=210 p95=276
mascara: 31351 px blancos de 4194304 (0.75%), sangrado 4 px, valores solo 0/1
triangulos evaluados antes=4166 despues=4166
"""
        parsed = AUDIT.parse_uv_report(report)
        self.assertEqual(0, parsed["overlap_pixels"])
        self.assertEqual(4166, parsed["triangles_after"])
        self.assertEqual(["Core_Lens"], parsed["components"])
        self.assertNotIn("TOTAL", parsed["components"])

    def test_reprojection_report_uses_master_count_not_legacy_constant(self):
        report = """
triangulos nuestros=4166 con gemelo exacto=4130 resueltos por BVH (n-gonos retriangulados)=36
muestras=7250710 texeles cubiertos=1842306 (43.9%)  distancia max punto->malla Meshy en los no gemelos=6.85e-05
geometria: 4166 triangulos evaluados (master UV: 4166; vertices GLB almacenados: 4826) -> IDENTICA
comparativa three-quarter: diferencia media=0.0069 p99=0.1176 max=0.639
mip 256px top: diferencia media Meshy vs reproyectado=0.0107
"""
        parsed = AUDIT.parse_reprojection_report(report)
        self.assertEqual(4166, parsed["master_uv_triangles"])
        self.assertEqual(36, parsed["bvh_triangles"])
        self.assertAlmostEqual(6.85e-5, parsed["max_bvh_distance"])

    def test_tool_is_explicitly_m3_asset_specific(self):
        self.assertEqual("astrion-m3-audit-esfera/0.1", AUDIT.TOOL)


if __name__ == "__main__":
    unittest.main()
