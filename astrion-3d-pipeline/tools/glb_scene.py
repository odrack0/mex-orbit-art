"""Transform-aware GLB scene loader for Astrion Geometry Audit v0.1."""
from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


COMPONENT_DTYPES = {
    5120: np.dtype("<i1"),
    5121: np.dtype("<u1"),
    5122: np.dtype("<i2"),
    5123: np.dtype("<u2"),
    5125: np.dtype("<u4"),
    5126: np.dtype("<f4"),
}
TYPE_COMPONENTS = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}


@dataclass
class SceneMesh:
    vertices: np.ndarray
    faces: np.ndarray
    normals: np.ndarray | None
    components: list[dict[str, Any]]
    nodes: list[dict[str, Any]]
    normals_complete: bool
    transformed_node_count: int
    active_scene: int | None


def _read_glb(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    if len(raw) < 20 or raw[:4] != b"glTF":
        raise ValueError("input is not a binary glTF (.glb) file")
    _magic, version, declared_length = struct.unpack_from("<4sII", raw, 0)
    if version != 2:
        raise ValueError(f"unsupported GLB version {version}; expected 2")
    if declared_length != len(raw):
        raise ValueError(f"GLB length header is {declared_length}, actual size is {len(raw)}")

    document = None
    binary = b""
    offset = 12
    while offset < len(raw):
        if offset + 8 > len(raw):
            raise ValueError("truncated GLB chunk header")
        length, chunk_type = struct.unpack_from("<II", raw, offset)
        offset += 8
        chunk = raw[offset:offset + length]
        if len(chunk) != length:
            raise ValueError("truncated GLB chunk")
        offset += length
        if chunk_type == 0x4E4F534A:
            document = json.loads(chunk.decode("utf-8").rstrip(" \t\r\n\x00"))
        elif chunk_type == 0x004E4942:
            binary = chunk
    if not isinstance(document, dict):
        raise ValueError("GLB has no JSON document chunk")
    return document, binary


def read_glb_document(path: Path) -> dict[str, Any]:
    """Return the embedded glTF JSON document without modifying the GLB."""
    document, _binary = _read_glb(path)
    return document


def _accessor_reader(document: dict[str, Any], binary: bytes):
    def read(index: int) -> np.ndarray:
        accessor = document["accessors"][index]
        if "sparse" in accessor:
            raise ValueError(f"sparse accessor {index} is not supported by Audit v0.1")
        if "bufferView" not in accessor:
            raise ValueError(f"accessor {index} has no bufferView")
        component_type = accessor["componentType"]
        if component_type not in COMPONENT_DTYPES:
            raise ValueError(f"accessor {index} has unsupported componentType {component_type}")
        component_count = TYPE_COMPONENTS.get(accessor["type"])
        if component_count is None:
            raise ValueError(f"accessor {index} has unsupported type {accessor['type']!r}")
        view = document["bufferViews"][accessor["bufferView"]]
        if view.get("buffer", 0) != 0:
            raise ValueError("Audit v0.1 supports only the GLB embedded buffer")

        dtype = COMPONENT_DTYPES[component_type]
        item_size = dtype.itemsize * component_count
        stride = int(view.get("byteStride", item_size))
        if stride < item_size:
            raise ValueError(f"accessor {index} byteStride is smaller than its item size")
        start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
        count = int(accessor["count"])
        end = start + max(count - 1, 0) * stride + item_size
        if start < 0 or end > len(binary):
            raise ValueError(f"accessor {index} exceeds the GLB binary chunk")
        if count == 0:
            values = np.empty((0, component_count), dtype=dtype)
        else:
            values = np.ndarray(
                shape=(count, component_count),
                dtype=dtype,
                buffer=binary,
                offset=start,
                strides=(stride, dtype.itemsize),
            ).copy()
        if accessor.get("normalized") and component_type != 5126:
            values = _normalize_integer_accessor(values, component_type)
        return values

    return read


def _normalize_integer_accessor(values: np.ndarray, component_type: int) -> np.ndarray:
    values = values.astype(np.float64)
    if component_type in (5120, 5122):
        maximum = 127.0 if component_type == 5120 else 32767.0
        return np.maximum(values / maximum, -1.0)
    maximum = {5121: 255.0, 5123: 65535.0, 5125: 4294967295.0}[component_type]
    return values / maximum


def _quaternion_matrix(raw: list[float]) -> np.ndarray:
    x, y, z, w = (float(value) for value in raw)
    length = math.sqrt(x * x + y * y + z * z + w * w)
    if length == 0:
        raise ValueError("node rotation quaternion has zero length")
    x, y, z, w = x / length, y / length, z / length, w / length
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0],
        [0, 0, 0, 1],
    ], dtype=np.float64)


def _local_matrix(node: dict[str, Any]) -> np.ndarray:
    if "matrix" in node:
        if any(field in node for field in ("translation", "rotation", "scale")):
            raise ValueError("a GLB node cannot declare both matrix and TRS")
        values = node["matrix"]
        if len(values) != 16:
            raise ValueError("node matrix must contain 16 values")
        return np.asarray(values, dtype=np.float64).reshape(4, 4, order="F")
    translation = np.eye(4)
    translation[:3, 3] = np.asarray(node.get("translation", [0, 0, 0]), dtype=np.float64)
    rotation = _quaternion_matrix(node.get("rotation", [0, 0, 0, 1]))
    scale = np.eye(4)
    scale[:3, :3] = np.diag(np.asarray(node.get("scale", [1, 1, 1]), dtype=np.float64))
    return translation @ rotation @ scale


def _triangles(indices: np.ndarray, mode: int) -> np.ndarray:
    indices = np.asarray(indices, dtype=np.int64).reshape(-1)
    if mode == 4:
        if len(indices) % 3:
            raise ValueError("triangle primitive index count is not divisible by three")
        return indices.reshape(-1, 3)
    if mode == 5:
        faces = []
        for index in range(len(indices) - 2):
            a, b, c = indices[index:index + 3]
            faces.append((b, a, c) if index % 2 else (a, b, c))
        return np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if mode == 6:
        return np.asarray(
            [(indices[0], indices[index], indices[index + 1]) for index in range(1, len(indices) - 1)],
            dtype=np.int64,
        ).reshape(-1, 3)
    raise ValueError(f"unsupported GLB primitive mode {mode}; expected TRIANGLES, STRIP, or FAN")


def load_glb_scene(path: Path) -> SceneMesh:
    document, binary = _read_glb(path)
    read_accessor = _accessor_reader(document, binary)
    nodes = document.get("nodes", [])
    meshes = document.get("meshes", [])

    if document.get("scenes"):
        active_scene = int(document.get("scene", 0))
        if active_scene >= len(document["scenes"]):
            raise ValueError(f"active scene index {active_scene} is out of range")
        roots = list(document["scenes"][active_scene].get("nodes", []))
    else:
        active_scene = None
        children = {int(child) for node in nodes for child in node.get("children", [])}
        roots = [index for index in range(len(nodes)) if index not in children]

    vertex_chunks: list[np.ndarray] = []
    face_chunks: list[np.ndarray] = []
    normal_chunks: list[np.ndarray] = []
    component_records: list[dict[str, Any]] = []
    node_records: list[dict[str, Any]] = []
    normals_complete = True
    transformed_node_count = 0
    vertex_base = 0
    active_stack: set[int] = set()
    visited: set[int] = set()

    def visit(node_index: int, parent_index: int | None, parent_world: np.ndarray) -> None:
        nonlocal vertex_base, normals_complete, transformed_node_count
        if node_index in active_stack:
            raise ValueError(f"cycle detected at GLB node {node_index}")
        if node_index in visited:
            raise ValueError(f"GLB node {node_index} is referenced by more than one parent/root")
        if node_index < 0 or node_index >= len(nodes):
            raise ValueError(f"GLB node index {node_index} is out of range")
        active_stack.add(node_index)
        visited.add(node_index)
        node = nodes[node_index]
        local = _local_matrix(node)
        world = parent_world @ local
        transformed = not np.allclose(local, np.eye(4), atol=1e-12)
        if transformed:
            transformed_node_count += 1
        name = node.get("name") or f"node_{node_index}"
        node_records.append({
            "index": node_index,
            "name": name,
            "parent": parent_index,
            "children": [int(value) for value in node.get("children", [])],
            "has_mesh": "mesh" in node,
            "local_transform_is_identity": not transformed,
            "world_translation": [round(float(value), 9) for value in world[:3, 3]],
        })

        if "mesh" in node:
            mesh_index = int(node["mesh"])
            if mesh_index < 0 or mesh_index >= len(meshes):
                raise ValueError(f"node {node_index} mesh index {mesh_index} is out of range")
            mesh = meshes[mesh_index]
            component_name = node.get("name") or mesh.get("name") or f"mesh_{mesh_index}"
            component_triangles = 0
            component_vertices = 0
            primitive_count = 0
            for primitive_index, primitive in enumerate(mesh.get("primitives", [])):
                attributes = primitive.get("attributes", {})
                if "POSITION" not in attributes:
                    raise ValueError(f"mesh {mesh_index} primitive {primitive_index} has no POSITION")
                positions = read_accessor(int(attributes["POSITION"])).astype(np.float64)
                if positions.shape[1] != 3:
                    raise ValueError("POSITION accessor must be VEC3")
                if "indices" in primitive:
                    raw_indices = read_accessor(int(primitive["indices"])).reshape(-1)
                else:
                    raw_indices = np.arange(len(positions), dtype=np.int64)
                faces = _triangles(raw_indices, int(primitive.get("mode", 4)))
                # glTF renderers reverse front-face winding for a world matrix
                # with negative determinant. Do the same while flattening so
                # geometric winding and transformed normal vectors still agree.
                if np.linalg.det(world[:3, :3]) < 0:
                    faces = faces[:, [0, 2, 1]]
                if len(faces) and (faces.min() < 0 or faces.max() >= len(positions)):
                    raise ValueError(f"mesh {mesh_index} primitive {primitive_index} has an invalid index")

                homogeneous = np.column_stack([positions, np.ones(len(positions))])
                world_positions = (homogeneous @ world.T)[:, :3]
                vertex_chunks.append(world_positions)
                face_chunks.append(faces + vertex_base)

                normal_index = attributes.get("NORMAL")
                if normal_index is None:
                    normals_complete = False
                    normal_chunks.append(np.zeros_like(world_positions))
                else:
                    normals = read_accessor(int(normal_index)).astype(np.float64)
                    if normals.shape != positions.shape:
                        raise ValueError("NORMAL accessor must be VEC3 and match POSITION count")
                    linear = world[:3, :3]
                    try:
                        world_normals = normals @ np.linalg.inv(linear)
                    except np.linalg.LinAlgError as exc:
                        raise ValueError(f"node {node_index} has a singular transform") from exc
                    lengths = np.linalg.norm(world_normals, axis=1)
                    world_normals /= np.maximum(lengths, 1e-20)[:, None]
                    normal_chunks.append(world_normals)

                primitive_count += 1
                component_triangles += len(faces)
                component_vertices += len(positions)
                vertex_base += len(positions)
            component_records.append({
                "name": component_name,
                "node_index": node_index,
                "mesh_index": mesh_index,
                "primitive_count": primitive_count,
                "vertices": component_vertices,
                "triangles": component_triangles,
                "world_transform": [[round(float(value), 9) for value in row] for row in world],
            })

        for child in node.get("children", []):
            visit(int(child), node_index, world)
        active_stack.remove(node_index)

    for root in roots:
        visit(int(root), None, np.eye(4))
    if not vertex_chunks or not face_chunks:
        raise ValueError("active GLB scene contains no triangle mesh primitives")

    vertices = np.concatenate(vertex_chunks, axis=0)
    faces = np.concatenate(face_chunks, axis=0)
    normals = np.concatenate(normal_chunks, axis=0) if normals_complete else None
    node_records.sort(key=lambda item: item["index"])
    return SceneMesh(
        vertices=vertices,
        faces=faces,
        normals=normals,
        components=component_records,
        nodes=node_records,
        normals_complete=normals_complete,
        transformed_node_count=transformed_node_count,
        active_scene=active_scene,
    )
