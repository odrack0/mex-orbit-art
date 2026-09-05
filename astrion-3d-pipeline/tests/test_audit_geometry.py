from __future__ import annotations

import json
import math
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
ART_ROOT = PIPELINE_ROOT.parent
TOOLS_ROOT = PIPELINE_ROOT / "tools"
sys.path.insert(0, str(TOOLS_ROOT))

import audit_geometry  # noqa: E402
from _mesh_engine import load_mesh_metrics  # noqa: E402
from glb_scene import load_glb_scene  # noqa: E402


CUBE_VERTICES = np.array(
    [[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)],
    dtype=np.float32,
)
CUBE_FACES = np.array(
    [
        [0, 1, 3], [0, 3, 2], [4, 7, 5], [4, 6, 7],
        [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
        [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3],
    ],
    dtype=np.uint16,
)
CUBE_NORMALS = CUBE_VERTICES / np.linalg.norm(CUBE_VERTICES, axis=1)[:, None]


def _pad4(data: bytes, byte: bytes = b"\x00") -> bytes:
    return data + byte * ((-len(data)) % 4)


def write_test_glb(path: Path, *, transformed: bool, include_unused_scene_node: bool = False) -> None:
    positions = CUBE_VERTICES.tobytes()
    normals = CUBE_NORMALS.astype(np.float32).tobytes()
    indices = CUBE_FACES.reshape(-1).tobytes()
    position_offset = 0
    normal_offset = len(positions)
    index_offset = normal_offset + len(normals)
    binary = _pad4(positions + normals + indices)
    nodes = []
    if transformed:
        nodes.extend([
            {"name": "Root", "translation": [10, 0, 0], "children": [1, 2]},
            {"name": "Body", "mesh": 0, "translation": [1, 0, 0], "scale": [2, 1, 3]},
            {"name": "muzzle", "translation": [0, 0, -2]},
        ])
        roots = [0]
    else:
        nodes.extend([
            {"name": "Body", "mesh": 0},
            {"name": "muzzle", "translation": [0, 0, -2]},
        ])
        roots = [0, 1]
    if include_unused_scene_node:
        nodes.append({"name": "Unused", "mesh": 0, "translation": [100, 0, 0]})
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"name": "Audited", "nodes": roots}],
        "nodes": nodes,
        "meshes": [{
            "name": "CubeMesh",
            "primitives": [{
                "attributes": {"POSITION": 0, "NORMAL": 1},
                "indices": 2,
                "mode": 4,
            }],
        }],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": position_offset, "byteLength": len(positions)},
            {"buffer": 0, "byteOffset": normal_offset, "byteLength": len(normals)},
            {"buffer": 0, "byteOffset": index_offset, "byteLength": len(indices)},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3"},
            {"bufferView": 1, "componentType": 5126, "count": 8, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5123, "count": 36, "type": "SCALAR"},
        ],
    }
    json_chunk = _pad4(json.dumps(document, separators=(",", ":")).encode("utf-8"), b" ")
    total = 12 + 8 + len(json_chunk) + 8 + len(binary)
    raw = (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<II", len(json_chunk), 0x4E4F534A)
        + json_chunk
        + struct.pack("<II", len(binary), 0x004E4942)
        + binary
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def test_spec() -> dict:
    return {
        "schema_version": "0.1",
        "identity": {"asset_id": "test-cube", "category": "prop", "family": "general", "tier": "standard", "status": "experimental"},
        "visual": {
            "screen_size_world_units": 40,
            "camera_profile": "top_down_default_v1",
            "symmetry": {"type": "none"},
            "silhouette_complexity": "low",
            "major_masses": ["body"],
            "identity_features": ["cube"],
        },
        "geometry": {
            "preferred_origin": "procedural_blender",
            "allowed_origins": ["procedural_blender"],
            "soft_triangle_target": 20,
            "triangle_ceiling": 30,
            "coordinate_profile": "astrion_blender_to_godot_v1",
            "components": {"min": 1, "max": 1, "required": ["Body"]},
            "anchors": {"required": ["muzzle"]},
        },
        "appearance": {
            "texture_resolutions": [512],
            "maps_required": ["base_color", "normal", "orm"],
            "metallic": "mixed", "roughness": "medium", "wear": "none", "rust": "none",
            "emission": {"policy": "none", "material_ids": [], "bake_glow_halo": False},
        },
        "pipeline": {
            "stage": "master_mesh_candidate",
            "geometry_outcome": "procedural_direct",
            "source_inputs": [], "generated_inputs": [], "outputs": [],
            "master_mesh": {"status": "candidate", "source_path": "models/cube.glb", "exchange_path": "models/cube.glb"},
            "audits": {"geometry": {"status": "not_run", "report": None}, "uv_textures": {"status": "not_run", "report": None}},
            "provenance": {},
        },
    }


class GlbSceneTests(unittest.TestCase):
    def test_active_scene_hierarchy_transforms_positions_and_normals(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "scene.glb"
            write_test_glb(path, transformed=True, include_unused_scene_node=True)
            scene = load_glb_scene(path)
            dimensions = scene.vertices.max(axis=0) - scene.vertices.min(axis=0)
            center = (scene.vertices.max(axis=0) + scene.vertices.min(axis=0)) / 2
            np.testing.assert_allclose(dimensions, [4, 2, 6])
            np.testing.assert_allclose(center, [11, 0, 0])
            self.assertEqual(12, len(scene.faces))
            self.assertEqual(["Body"], [item["name"] for item in scene.components])
            self.assertTrue(scene.normals_complete)
            self.assertEqual(3, scene.transformed_node_count)

    def test_geometry_report_is_spec_driven_and_contains_no_uv_metrics(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            model = root / "models" / "cube.glb"
            write_test_glb(model, transformed=False)
            spec_path = root / "specs" / "cube.json"
            spec_path.parent.mkdir(parents=True)
            spec_path.write_text(json.dumps(test_spec()), encoding="utf-8")
            report = audit_geometry.run_audit(spec_path, art_root=root, heavy=False)
            self.assertEqual("pass", report["audit"]["result"])
            self.assertEqual("geometry_only", report["audit"]["scope"])
            self.assertEqual(40, report["camera"]["declared_screen_size_world_units"])
            self.assertEqual(["Body"], [item["name"] for item in report["scene"]["components"]])
            self.assertFalse(any("uv" in key.lower() or "texel" in key.lower() for key in report["metrics"]))
            checks = {item["id"]: item for item in report["checks"]}
            self.assertEqual("pass", checks["required_anchors"]["status"])
            self.assertEqual("pass", checks["authoritative_source_ngons"]["status"])
            self.assertEqual(0, report["summary"]["waived"])

    def test_protected_source_output_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "refusing to write"):
            audit_geometry.safe_output_path(Path("source/3d-models/crudo/report.json"), ART_ROOT)


class PrimitiveRegressionTests(unittest.TestCase):
    def test_existing_engine_detects_twelve_segment_cylinder(self):
        segment_count = 12
        vertices = []
        faces = []
        for index in range(segment_count):
            angle = 2 * math.pi * index / segment_count
            vertices.append([math.cos(angle), -1, math.sin(angle)])
            vertices.append([math.cos(angle), 1, math.sin(angle)])
        for index in range(segment_count):
            current = 2 * index
            following = 2 * ((index + 1) % segment_count)
            faces.extend([[current, following, current + 1], [following, following + 1, current + 1]])
        engine, backend = load_mesh_metrics(ART_ROOT)
        metrics = engine.analyse(np.asarray(vertices), np.asarray(faces), UV=None, N=None, heavy=False)
        self.assertEqual(12, metrics["rot_sym_order"])
        self.assertIn(backend, {"scipy.spatial.cKDTree", "astrion.spatial_hash"})

    def test_report_schema_is_versioned(self):
        schema = json.loads((PIPELINE_ROOT / "schemas" / "geometry-audit-v0.1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual("0.1", schema["properties"]["schema_version"]["const"])
        self.assertEqual("geometry_only", schema["properties"]["audit"]["properties"]["scope"]["const"])


if __name__ == "__main__":
    unittest.main()
