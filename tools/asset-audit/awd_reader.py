#!/usr/bin/env python3
"""awd_reader - AWD2 (Away3D) block reader for mesh auditing.

Reads the AWD container (header, optional zlib body) and walks its blocks,
returning geometries, material stubs, mesh instances and metadata. It is a
*reader*, not a converter: no axis conversion is applied here, so the numbers
reported downstream are the numbers actually stored in the file.

Block types handled (AWD2):
    1   TriangleGeometry   (sub-meshes with vertex/index/uv/normal streams)
    11  PrimitiveGeometry  (parametric primitive, no explicit streams)
    22  Container3D        (scene node)
    23  Mesh instance      (transform + geometry ref + material refs)
    81  Material
    82  Texture
    254 Namespace / 255 Metadata (ignored, kept in the block histogram)

Stream types: 1=positions, 2=indices, 3=uv0, 4=normals, 5=uv1, 6=joint idx,
7=joint weights.

Usage as a library:
    from awd_reader import read_awd
    doc = read_awd("goliath.awd")
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

# AWD numeric field types -> (byte size, struct code)
_SIZE = {1: 1, 2: 2, 3: 4, 4: 1, 5: 2, 6: 4, 7: 4, 8: 8}
_CODE = {1: "b", 2: "h", 3: "i", 4: "B", 5: "H", 6: "I", 7: "f", 8: "d"}

STREAM_NAMES = {
    1: "positions", 2: "indices", 3: "uv0", 4: "normals",
    5: "uv1", 6: "joint_index", 7: "joint_weight",
}


@dataclass
class SubMesh:
    positions: list = field(default_factory=list)
    indices: list = field(default_factory=list)
    uv0: list = field(default_factory=list)
    uv1: list = field(default_factory=list)
    normals: list = field(default_factory=list)
    joint_index: list = field(default_factory=list)
    joint_weight: list = field(default_factory=list)
    streams: list = field(default_factory=list)   # stream type ids as stored


@dataclass
class Geometry:
    block_id: int
    name: str
    subs: list = field(default_factory=list)      # list[SubMesh]


@dataclass
class MeshInstance:
    block_id: int
    name: str
    parent_id: int
    geometry_id: int
    material_ids: list = field(default_factory=list)
    matrix: tuple = ()                            # 12 floats (3x4), as stored


@dataclass
class Material:
    block_id: int
    name: str
    kind: int                                     # 1 = color, 2 = texture
    num_methods: int
    props: dict = field(default_factory=dict)     # raw {key: bytes}
    method_types: list = field(default_factory=list)


@dataclass
class Texture:
    block_id: int
    name: str
    kind: int                                     # 0 = external url, 1 = embedded
    url: str = ""
    embedded_bytes: int = 0


@dataclass
class AwdDoc:
    path: str
    version: tuple
    compression: int
    body_bytes: int
    block_histogram: dict = field(default_factory=dict)
    geometries: list = field(default_factory=list)
    meshes: list = field(default_factory=list)
    materials: list = field(default_factory=list)
    textures: list = field(default_factory=list)
    primitives: int = 0
    skeletons: int = 0
    vertex_anim_blocks: int = 0
    errors: list = field(default_factory=list)


# --------------------------------------------------------------------------- #
# low level readers
# --------------------------------------------------------------------------- #
def _varstr(buf: bytes, pos: int):
    n = struct.unpack_from("<H", buf, pos)[0]
    return buf[pos + 2:pos + 2 + n].decode("utf-8", "replace"), pos + 2 + n


def _props(buf: bytes, pos: int):
    """Property list: u32 total length, then (u16 key, u32 len, data)*."""
    total = struct.unpack_from("<I", buf, pos)[0]
    end = pos + 4 + total
    p = pos + 4
    out = {}
    while p + 6 <= end:
        key = struct.unpack_from("<H", buf, p)[0]
        ln = struct.unpack_from("<I", buf, p + 2)[0]
        out[key] = buf[p + 6:p + 6 + ln]
        p += 6 + ln
    return out, end


def _skip_props(buf: bytes, pos: int):
    return pos + 4 + struct.unpack_from("<I", buf, pos)[0]


def _stream(buf: bytes, pos: int):
    stype = buf[pos]
    dtype = buf[pos + 1]
    ln = struct.unpack_from("<I", buf, pos + 2)[0]
    n = ln // _SIZE[dtype]
    data = struct.unpack_from("<" + _CODE[dtype] * n, buf, pos + 6)
    return stype, list(data), pos + 6 + ln


# --------------------------------------------------------------------------- #
# block parsers
# --------------------------------------------------------------------------- #
def _parse_geometry(buf, start, blen, bid) -> Geometry:
    p = start
    name, p = _varstr(buf, p)
    n_subs = struct.unpack_from("<H", buf, p)[0]
    p += 2
    p = _skip_props(buf, p)
    geo = Geometry(block_id=bid, name=name)
    for _ in range(n_subs):
        sub_len = struct.unpack_from("<I", buf, p)[0]
        p += 4
        sub_end = p + sub_len
        p = _skip_props(buf, p)
        sm = SubMesh()
        while p < sub_end:
            stype, data, p = _stream(buf, p)
            sm.streams.append(stype)
            attr = STREAM_NAMES.get(stype)
            if attr:
                setattr(sm, attr, data)
        p = _skip_props(buf, p)          # per-sub user attributes
        geo.subs.append(sm)
    return geo


def _parse_mesh(buf, start, blen, bid) -> MeshInstance:
    p = start
    parent = struct.unpack_from("<I", buf, p)[0]
    p += 4
    mtx = struct.unpack_from("<12f", buf, p)
    p += 48
    name, p = _varstr(buf, p)
    geo_id = struct.unpack_from("<I", buf, p)[0]
    p += 4
    n_mat = struct.unpack_from("<H", buf, p)[0]
    p += 2
    mats = list(struct.unpack_from("<" + "I" * n_mat, buf, p)) if n_mat else []
    return MeshInstance(bid, name, parent, geo_id, mats, mtx)


def _parse_material(buf, start, blen, bid) -> Material:
    p = start
    name, p = _varstr(buf, p)
    kind = buf[p]
    n_methods = buf[p + 1]
    p += 2
    props, p = _props(buf, p)
    methods = []
    for _ in range(n_methods):
        if p + 2 > start + blen:
            break
        methods.append(struct.unpack_from("<H", buf, p)[0])
        p += 2
        p = _skip_props(buf, p)
        p = _skip_props(buf, p)
    return Material(bid, name, kind, n_methods, props, methods)


def _parse_texture(buf, start, blen, bid) -> Texture:
    p = start
    name, p = _varstr(buf, p)
    kind = buf[p]
    p += 1
    url, nbytes = "", 0
    if kind == 0:
        url, p = _varstr(buf, p)
    else:
        nbytes = struct.unpack_from("<I", buf, p)[0]
    return Texture(bid, name, kind, url, nbytes)


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def read_awd(path: str) -> AwdDoc:
    raw = open(path, "rb").read()
    if raw[:3] != b"AWD":
        raise ValueError(f"{path}: not an AWD file")
    ver = (raw[3], raw[4])
    comp = raw[7]
    body = raw[12:]
    if comp == 1:
        body = zlib.decompress(body)
    elif comp != 0:
        raise ValueError(f"{path}: unsupported compression {comp}")

    doc = AwdDoc(path=path, version=ver, compression=comp, body_bytes=len(body))
    pos = 0
    while pos + 11 <= len(body):
        bid, _ns, btype, _flags = struct.unpack_from("<IBBB", body, pos)
        blen = struct.unpack_from("<I", body, pos + 7)[0]
        start = pos + 11
        pos = start + blen
        doc.block_histogram[btype] = doc.block_histogram.get(btype, 0) + 1
        try:
            if btype == 1:
                doc.geometries.append(_parse_geometry(body, start, blen, bid))
            elif btype == 11:
                doc.primitives += 1
            elif btype == 23:
                doc.meshes.append(_parse_mesh(body, start, blen, bid))
            elif btype == 81:
                doc.materials.append(_parse_material(body, start, blen, bid))
            elif btype == 82:
                doc.textures.append(_parse_texture(body, start, blen, bid))
            elif btype in (101, 102, 103):
                doc.skeletons += 1
            elif btype in (111, 112, 113, 121, 122):
                doc.vertex_anim_blocks += 1
        except Exception as exc:                                  # noqa: BLE001
            doc.errors.append(f"block {bid} type {btype}: {exc!r}")
    return doc


if __name__ == "__main__":
    import sys
    for f in sys.argv[1:]:
        d = read_awd(f)
        tris = sum(len(s.indices) // 3 for g in d.geometries for s in g.subs)
        verts = sum(len(s.positions) // 3 for g in d.geometries for s in g.subs)
        print(f"{f}: v{d.version} geo={len(d.geometries)} "
              f"subs={sum(len(g.subs) for g in d.geometries)} "
              f"meshes={len(d.meshes)} mats={len(d.materials)} "
              f"verts={verts} tris={tris} blocks={d.block_histogram}")
        for m in d.materials[:6]:
            print(f"    mat '{m.name}' kind={m.kind} methods={m.method_types} "
                  f"props={ {k: v.hex() for k, v in m.props.items()} }")
