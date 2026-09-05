"""Load the legacy mesh metric engine with a deterministic SciPy fallback.

The existing engine only uses ``scipy.spatial.cKDTree.query`` with a finite
distance bound.  Audit 1 keeps reusing that engine, but can also run in the
small bundled Python runtime where SciPy is unavailable.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import numpy as np


class SpatialHashKDTree:
    """Small exact radius-query substitute for the cKDTree API we consume."""

    def __init__(self, points):
        self.points = np.asarray(points, dtype=np.float64).reshape(-1, 3)

    def query(self, queries, distance_upper_bound=np.inf):
        queries = np.asarray(queries, dtype=np.float64)
        flat = queries.reshape(-1, 3)
        radius = float(distance_upper_bound)
        if not np.isfinite(radius) or radius <= 0:
            raise ValueError("SpatialHashKDTree requires a finite positive distance bound")

        cells: dict[tuple[int, int, int], list[int]] = {}
        point_cells = np.floor(self.points / radius).astype(np.int64)
        for index, cell in enumerate(point_cells):
            cells.setdefault(tuple(int(value) for value in cell), []).append(index)

        distances = np.full(len(flat), np.inf, dtype=np.float64)
        indices = np.full(len(flat), len(self.points), dtype=np.int64)
        offsets = tuple(
            (x, y, z)
            for x in (-1, 0, 1)
            for y in (-1, 0, 1)
            for z in (-1, 0, 1)
        )
        for query_index, point in enumerate(flat):
            cell = np.floor(point / radius).astype(np.int64)
            candidates: list[int] = []
            for dx, dy, dz in offsets:
                key = (int(cell[0] + dx), int(cell[1] + dy), int(cell[2] + dz))
                candidates.extend(cells.get(key, ()))
            if not candidates:
                continue
            candidate_array = np.asarray(candidates, dtype=np.int64)
            delta = self.points[candidate_array] - point
            squared = np.einsum("ij,ij->i", delta, delta)
            local = int(np.argmin(squared))
            distance = float(np.sqrt(squared[local]))
            if distance <= radius:
                distances[query_index] = distance
                indices[query_index] = int(candidate_array[local])

        shape = queries.shape[:-1]
        return distances.reshape(shape), indices.reshape(shape)


def _edt_1d(values: np.ndarray) -> np.ndarray:
    """Squared Euclidean distance transform for one finite/infinite row."""
    count = len(values)
    sites = np.empty(count, dtype=np.int64)
    boundaries = np.empty(count + 1, dtype=np.float64)
    result = np.empty(count, dtype=np.float64)
    k = 0
    sites[0] = 0
    boundaries[0] = -np.inf
    boundaries[1] = np.inf
    for q in range(1, count):
        while True:
            previous = sites[k]
            intersection = (
                (values[q] + q * q) - (values[previous] + previous * previous)
            ) / (2.0 * (q - previous))
            if intersection > boundaries[k] or k == 0:
                break
            k -= 1
        k += 1
        sites[k] = q
        boundaries[k] = intersection
        boundaries[k + 1] = np.inf
    k = 0
    for q in range(count):
        while boundaries[k + 1] < q:
            k += 1
        delta = q - sites[k]
        result[q] = delta * delta + values[sites[k]]
    return result


def distance_transform_edt(mask):
    """NumPy implementation of the SciPy function used for silhouette bands."""
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2:
        raise ValueError("fallback distance_transform_edt supports 2D arrays")
    # The false border also models the background immediately outside an image.
    padded = np.pad(mask, 1, mode="constant", constant_values=False)
    large = float((padded.shape[0] + padded.shape[1]) ** 2)
    distances = np.where(padded, large, 0.0)
    for column in range(distances.shape[1]):
        distances[:, column] = _edt_1d(distances[:, column])
    for row in range(distances.shape[0]):
        distances[row, :] = _edt_1d(distances[row, :])
    return np.sqrt(distances[1:-1, 1:-1])


def _install_spatial_fallback() -> str:
    try:
        import scipy.spatial as spatial

        return "astrion.spatial_hash" if getattr(spatial, "__astrion_fallback__", False) else "scipy.spatial.cKDTree"
    except ImportError:
        scipy_module = types.ModuleType("scipy")
        spatial_module = types.ModuleType("scipy.spatial")
        ndimage_module = types.ModuleType("scipy.ndimage")
        spatial_module.cKDTree = SpatialHashKDTree
        spatial_module.__astrion_fallback__ = True
        ndimage_module.distance_transform_edt = distance_transform_edt
        scipy_module.spatial = spatial_module
        scipy_module.ndimage = ndimage_module
        sys.modules["scipy"] = scipy_module
        sys.modules["scipy.spatial"] = spatial_module
        sys.modules["scipy.ndimage"] = ndimage_module
        return "astrion.spatial_hash"


def load_mesh_metrics(art_root: Path):
    backend = _install_spatial_fallback()
    module_path = art_root / "tools" / "asset-audit" / "mesh_metrics.py"
    spec = importlib.util.spec_from_file_location("astrion_legacy_mesh_metrics", module_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load metric engine: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, backend
