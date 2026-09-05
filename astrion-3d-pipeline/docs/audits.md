# Audit gates

## Rule

Astrion has two distinct gates. Audit 1 judges the Master Mesh before UV/texturing. Audit 2 judges authoritative UVs, material IDs, maps, and reprojection. A tool may calculate metrics for both, but reports and pass/fail decisions must remain stage-specific.

All automatic results are evidence. Silhouette/readability, semantic identity, and intentional exceptions require review at the declared gameplay camera and screen size.

## Audit 1 — Geometry

### Inputs

- Asset Spec and camera/class policy;
- candidate Master Mesh with transforms and semantic components;
- optional concept and generative/reference meshes for comparison.

UVs and textures are not prerequisites.

### Checks

| Area | Expected checks |
|---|---|
| Budget | Triangle count against a soft target and ceiling; stored/split vertices; density per projected screen area |
| Hygiene | Degenerate and duplicate faces, loose vertices/geometry, boundaries, non-manifold edges under class policy, normals/winding |
| Readability | Gameplay-camera silhouette, major masses, identity features, subpixel geometry, overly thin pieces |
| Visibility | Hidden/interior geometry, with declared exceptions for animation or alternate views |
| Structure | Semantic components, required piece names, component bounds, parentage, accidental islands/intersections |
| Mechanical primitives | Deliberate segment counts and regularity, only when the class/spec calls for them |
| Transforms | Units, scale, orientation, pivot/origin, applied transforms, symmetry intent |
| Anchors | Required names, count, placement, axes, parentage, and no accidental mesh geometry |
| Provenance | Geometry origin/outcome and exact source/tool parameters |

### Existing coverage

- `tools/asset-audit/mesh_metrics.py`: broad geometry metrics, visibility rasterization, screen-space density inputs, symmetry, connected islands, rotational order, and sphere fit.
- `tools/asset-audit/validate_asset.py`: class budgets, scale/origin, density, topology hygiene, hidden geometry, piece ranges, flatness, symmetry, and primitive warnings.
- `tools/asset-audit/render_diagnostics.py`, `render_silhouette_map.py`, `decimation_test.py`, and `contact_sheet.py`: visual and decimation evidence.
- `tools/asset-audit/selftest_primitives.py`: a small regression probe for primitive/symmetry metrics.
- `tools/esfera-mecanica.py`: asset-specific manifold, closure, duplicate, radial, and export checks for the procedural sphere.
- `tools/variantes-silueta.py`: generated high-mesh repair and multiple independent decimation candidates with surface-deviation reports.
- `tools/marcar-anclajes.py`: anchor insertion, but not a general anchor-contract validator.
- `mex-orbit-testing/assets/validar-modelo.py`: external GLB preflight for triangle ceiling, texture budget, orientation, pivot, emission declaration, and some packaging concerns.

### Gaps and changes required

- Split UV presence/coverage out of `validate_asset.py`; it currently makes a UV-less pre-texture master fail.
- Replace lower triangle bounds as quality targets with warnings or class-aware perceptual floors. The ceiling must remain a ceiling.
- Drive camera, class, screen size, organic/mechanical rules, symmetry, anchors, and exceptions from the Asset Spec.
- Make node transforms reliable. `mesh_metrics.load_glb()` currently concatenates primitives and ignores node hierarchy/transforms.
- Add semantic component and anchor validation.
- Distinguish intentional open surfaces/intersections from invalid topology by class/policy.
- Emit a versioned geometry-only JSON report with tool/version/spec provenance.

## Audit 2 — UV / Textures

### Inputs

- Geometry-approved Master Mesh;
- authoritative UVs and material IDs;
- final/reprojected texture set;
- Asset Spec appearance and emission policy.

### Checks

| Area | Expected checks |
|---|---|
| UV layout | UV set presence, 0..1/tile policy, occupancy, allowed overlaps/mirroring, island count, orientation where relevant |
| Sampling | Texel density and variation, target resolutions, per-class budgets, padding and mip safety |
| Materials | Required semantic material IDs, assignment coverage, stable piece/material relationships, draw-call policy |
| Maps | Required maps, dimensions, bit depth/format, channel packing, alpha use, normal convention |
| Color space | Base color as sRGB; normal/ORM/metallic/roughness/masks as non-color data |
| Reprojection | Geometry alignment/correspondence, coverage, unmapped samples, source-to-result visual error at gameplay size |
| Normal maps | Tangent-basis rebasing or rebake, expected MikkTSpace/export behavior, plausible vector length/inclination |
| Emission | Deterministic region/mask, permitted values, no AI-authored truth, no baked glow halo, runtime energy policy |
| Export | Textures embedded/referenced as intended, material flags, required attributes, deterministic package |

### Existing coverage

- `mesh_metrics.py` already calculates UV coverage, overlap factor, tiling, and texel-density variation, though these need an Audit 2 policy wrapper.
- `esfera-mecanica-uv.py` provides strong asset-specific evidence: material assignment counts, overlap pixels, coverage, visible texel density, emission mask values/components, and unchanged triangle count.
- `reproyectar-texturas.py` validates alignment, exact/BVH correspondence, coverage, texture roles/color spaces, unchanged geometry, and rendered source/reprojection differences for the mechanical sphere.
- `asset-audit/audit_textures.py` inventories legacy ATF headers/channels; it is reference tooling and does not validate the current PBR GLB texture contract.
- `mex-orbit-testing/assets/validar-modelo.py` checks texture sizes, material emission declaration, and some GLB packaging concerns, but it is not a complete UV/texture gate.

### Gaps and changes required

- Generalize sphere-specific UV/material/emission checks into spec-driven tooling.
- Define overlap, mirrored-island, UDIM/tile, padding, and texel-density policies by asset class.
- Inspect GLB images/materials/accessors and confirm color-space/import expectations against Godot.
- Add required map/channel validation for base color, normal, ORM, and deterministic emission masks.
- Add mip-safe padding tests and a repeatable gameplay-size visual comparison.
- Record reprojection errors and normal-basis method in structured reports.
- Validate that emission masks are semantic and halo-free; do not infer final emission solely from color dominance.

## Current tool classification

| Tool | Gate | Status |
|---|---|---|
| `asset-audit/validate_asset.py` | Mixed | Useful current validator; must be split/configured |
| `asset-audit/mesh_metrics.py` | Both | Reusable measurement engine with GLB transform limitation |
| `asset-audit/render_*`, `decimation_test.py` | Audit 1 | Diagnostic evidence; requires Blender for some views |
| `esfera-mecanica.py` | Audit 1 | Proven but asset-specific |
| `esfera-mecanica-uv.py` | Audit 2 (plus geometry regression) | Proven but asset-specific |
| `reproyectar-texturas.py` | Audit 2 | Proven on near-identical sphere geometry only |
| `mex-orbit-testing/assets/validar-modelo.py` | Mixed/export preflight | Cross-repo legacy/current contract check |
| `asset-audit/audit_awd.py`, `audit_islands.py`, `audit_textures.py` | Research/reference | DarkOrbit measurements; never Astrion art inputs |

## Gate result

Each audit should eventually return `pass`, `fail`, or `waived`. A waiver records the exact rule, reason, scope, reviewer, and expiry/revisit condition. Warnings do not become silent passes, and a metric threshold never substitutes for a gameplay-size visual review.

## Geometry Audit v0.1 command

M2 adds `tools/audit_geometry.py`, a read-only, spec-driven Audit 1 wrapper around the existing `tools/asset-audit/mesh_metrics.py` measurement engine. It reads only the candidate exchange GLB's geometry, normals, active scene, nodes, and transforms. UVs, materials, images, textures, appearance, and emission are explicitly excluded from the decision.

The loader evaluates inherited GLB matrix/TRS transforms before metrics, validates semantic mesh-node names and anchor-node names, and records hashes plus runtime dependency versions. It supports indexed or unindexed triangle, triangle-strip, and triangle-fan primitives. Sparse accessors and non-GLB exchange inputs stop with an actionable error in v0.1 instead of being interpreted partially.

Run the formal audit from the `mex-orbit-art` root:

```powershell
python astrion-3d-pipeline/tools/audit_geometry.py `
  source/3d-models/specs/esfera-mecanica.json `
  --output astrion-3d-pipeline/reports/esfera-mecanica/geometry-audit-v0.1.json `
  --diagnostics-dir astrion-3d-pipeline/reports/esfera-mecanica/diagnostics
```

`--fast` skips multi-view visibility evidence and is for development only. Exact direct dependencies are recorded in `requirements-audit-v0.1.txt`; when SciPy is absent, the wrapper supplies the bounded spatial query used by the existing metric engine. Reports conform to `schemas/geometry-audit-v0.1.schema.json`. Output safety rejects paths outside the repository or anywhere under the repository's source-asset tree.

The first report for `esfera-mecanica` is a deliberate failure record, not an asset modification or promotion. Its GLB has duplicate/non-manifold topology and substantial never-visible geometry, while the authoritative `.blend` n-gon rule cannot be proven from a triangulated exchange file without Blender inspection. The explicit 5,000-triangle spec ceiling controls the gate; the older `prop_grande` range is retained as a visible policy-conflict warning.

## Mechanical sphere repair helper

`tools/reparar-esfera-mecanica.py` is the asset-specific, non-destructive repair used to investigate that failure. Run it with Blender 5.x and a new output directory:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" `
  --background --factory-startup `
  --python tools/reparar-esfera-mecanica.py -- `
  --input source/3d-models/procedural/esfera-mecanica/esfera-mecanica.blend `
  --output-dir astrion-3d-pipeline/work/esfera-mecanica-repair-v3
```

The helper applies evaluated modifiers in the isolated copy, bakes object transforms, triangulates all components, removes coincident opposed face pairs, recalculates winding, verifies per-component and globally welded topology, and exports a new BLEND/GLB plus a hash-bound repair report. It refuses output under `source/`, outside the repository, or over an existing repair artifact.

The verified v3 candidate reduces the mesh from 4,170 to 4,166 triangles and has zero duplicate faces, non-manifold edges, boundary edges, degenerate triangles, and n-gons. It preserves the eight semantic components and the visible silhouette. Audit 1 reports 25.5% never-visible geometry because the design intentionally closes the raised plates below the sphere surface. M3 closes that error with a hash- and camera-scoped waiver: removing the faces automatically would require a union/redesign that changes semantic component ownership. The waiver must be revisited if geometry, components, animation exposure, camera, screen size, or production status changes.

## Mechanical sphere M3 Audit 2

`tools/audit_m3_esfera.py` is the deliberately asset-specific M3 evidence recorder; it is not the general M6 Audit 2 implementation. It reads the UV and reprojection reports, inspects PNG content and embedded glTF images/materials, compares UV-stage and textured geometry signatures, verifies the original source hash, and writes a structured JSON result without changing the asset.

```powershell
python astrion-3d-pipeline/tools/audit_m3_esfera.py `
  --work-dir astrion-3d-pipeline/work/esfera-mecanica-m3-v4 `
  --spec astrion-3d-pipeline/work/esfera-mecanica-m3-v4/asset-spec-input.json `
  --output astrion-3d-pipeline/work/esfera-mecanica-m3-v4/uv-texture-audit-m3-v0.1.json
```

The recorded result is 11 passes, one policy warning, and zero errors. UVs stay in 0..1 with zero overlapping texels; the 4,166-triangle geometry signature is unchanged; all eight pieces and three material IDs survive; the 2048/1024 PBR maps and binary emission mask are present; 4,130 reprojection triangles use exact correspondence and 36 use BVH with a maximum distance of `6.85e-05`; and full-view mean sRGB differences remain between 0.0069 and 0.0113.

The isolated `godot-smoke` project then imports the final GLB in Godot 4.7.1 and verifies eight mesh components, 4,166 triangles, normals, UV0, base/normal/metallic/roughness textures, semantic emission-mask binding, finite bounds, and runtime-owned cyan/energy settings. Its report passes eight checks. This proves import compatibility without adding the experimental asset to `mex-orbit-client`.
