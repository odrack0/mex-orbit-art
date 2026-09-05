# Repository map

## Boundary and status

Discovery was performed on 2026-09-04 from:

```text
C:\Source\MexOrbit\mex-orbit-v1\mex-orbit-art\astrion-3d-pipeline
```

The Git root is the parent repository:

```text
C:\Source\MexOrbit\mex-orbit-v1\mex-orbit-art
```

`astrion-3d-pipeline/` was empty before this M0 documentation pass. It is not a separate Git repository.

The enclosing worktree was already dirty. Existing changes included a modified `source/3d-models/README.md`, numerous deleted render files, a modified local credentials file, and untracked procedural/audit/reprojection work. Those changes were inspected where relevant and not altered by M0.

## Top-level map

| Path | Observed role |
|---|---|
| `README.md` | Large chronological art/pipeline lab notebook; includes current findings and explicitly retired/historical workflows |
| `.gitignore` | Excludes raw Meshy/Tripo model sources, Blender files, extracted frames, and selected render intermediates |
| `astrion-3d-pipeline/` | New orchestration contracts and documentation; no implementation yet |
| `astrion-3d-pipeline/flows/generative-probes/` | M5 experimental evidence-flow contract; receives explicit external-pipeline deliveries and cannot promote a Master Mesh |
| `docs/` | Existing vertical-slice asset inventory, largely documenting earlier 2D/render workflows |
| `exports/` | Generated/exported art outputs (15 files observed) |
| `fx/`, `npcs/`, `ships/`, `world/` | Game-art source/output groupings outside the new 3D orchestration layer |
| `placeholders/` | Retained obsolete placeholders, explicitly marked as such in existing docs |
| `preview/` | Preview artifact(s) |
| `prompts/` | Eighteen prompt/reference documents for asset generation and render contracts |
| `source/` | Heavy source material: 3D models, renders, and extracted frames |
| `testing/` | One local credentials file; not the main validator suite |
| `tools/` | Fifty-five observed files, including Blender/Python production scripts and untracked audit tools |

## 3D assets and artifacts

### `source/3d-models/`

- Eighteen tracked top-level GLB working masters were observed: `aci-01` through `aci-05`, `base`, `cargo-box`, `ferox`, `gravit`, `gravon`, `mordax`, `phoenix`, `portal`, `skarn`, `skarnox`, `vex`, `vexor`, and `vorax`.
- `crudo/` is ignored raw/generated material. It contains Meshy candidates, high meshes under `crudo/alto/`, and decimation experiment outputs. It is valuable and not backed up merely by existing on the same disk.
- `pulido/` is ignored Tripo polished/textured source material.
- `procedural/esfera-mecanica/` is an untracked end-to-end experiment containing source/staged Blender and GLB files, UV/emission diagnostics, reprojected PBR textures at 2048 and 1024, comparison renders, and text reports.
- `astrion-3d-pipeline/work/esfera-mecanica-m3-v4/` is the isolated completed M3 proof: final spec, repaired/UV/textured stages, Audit 2 evidence, renders, hashes, and a temporary Godot smoke project. It does not replace files under `source/`.
- `.blend` files are globally ignored because the older convention says they can be regenerated from GLB. The new procedural experiment uses `.blend` as the stated authoritative pre/post-UV master, creating an unresolved authority/versioning conflict.

No asset-spec YAML/JSON/TOML files or pipeline configuration manifests existed at M0 discovery. M1 subsequently added `source/3d-models/specs/esfera-mecanica.json`; it records an experimental candidate and does not promote or modify the asset.

## Important 3D tools

### Current tracked production scripts

| Script | Observed purpose |
|---|---|
| `tools/normalize-model.py` | Normalize generated GLB orientation/pivot, weld conservatively, resize textures, derive/respect emission, and export GLB |
| `tools/decimar-y-vestir.py` | Decimate a high mesh, generate UVs, and transfer color/metallic-roughness from a textured remesh |
| `tools/hornear-normales.py` | Bake high-to-low normal detail and export the low mesh |
| `tools/a-blend.py` | Convert GLB to inspectable packed `.blend` |
| `tools/riguear-modelo.py`, `animar-alas.py`, `animar-nodos.py` | Rig/animate generated assets |
| `tools/marcar-anclajes.py` | Add engine/cannon empties to a model using measured geometry and explicit engine count |
| `tools/find-anchors.py` | Measure 2D/render-space engine/cannon points for JSON; not the same contract as 3D empties |
| `tools/variantes-silueta.py` | Untracked high-mesh repair and independent decimation/shrinkwrap candidates with deviation report |
| `tools/salvaguarda.py` | Prevent selected tools from writing into `crudo/`/`renders/` or overwriting their input |

`decimar-y-vestir.py`, `hornear-normales.py`, and several other writers do not currently call the shared safeguard.

### Procedural/reprojection experiment (currently untracked)

| Script | Observed purpose |
|---|---|
| `tools/esfera-mecanica.py` | Deterministically builds, verifies, exports, and renders an eight-mesh mechanical sphere (4,170 evaluated triangles) |
| `tools/esfera-mecanica-uv.py` | Applies final Boolean/Mirror geometry, unwraps, assigns `MAT_HULL`/`MAT_RECESSES`/`MAT_EMISSION`, creates deterministic mask and diagnostics |
| `tools/reproyectar-texturas.py` | Transfers Meshy appearance onto Astrion UVs for near-identical geometry, including tangent-space normal rebasing and comparison renders |

The older experiment reports no overlap and 58.2% occupancy. The repaired M3 atlas reports zero overlap and 43.2% occupancy after preserving every closed semantic surface and isolating two folded triangles. The generic validator's 75% lower bound is not part of Asset Spec v0.1; M3 records the mismatch as a visible warning, and M6 must define a class-specific rule before production promotion.

### Asset audit bench (currently untracked)

`tools/asset-audit/` contains:

- `validate_asset.py` and `mesh_metrics.py` for GLB/OBJ metrics and current pass/fail rules;
- Blender/numpy diagnostic renderers and decimation comparisons;
- a primitive metric self-test;
- AWD readers/export/audits and legacy ATF texture inventory for technical reference studies;
- report merging and contact-sheet helpers.

Its documented dependencies are Python 3.12, NumPy, SciPy, Pillow, and Blender for Blender-based scripts. There is no checked-in dependency manifest.

## External repository relationships

Sibling repositories referenced by code/docs exist in the same `mex-orbit-v1` checkout:

- `mex-orbit-client`: consumer and Godot runtime/import behavior;
- `mex-orbit-docs`: includes the low-poly modeling standard and camera study;
- `mex-orbit-testing`: includes `assets/validar-modelo.py`, a separate GLB validator.

These are dependencies by relative checkout convention, not declared packages.

## Generated outputs versus authorities

| Material | Current location | Git status/convention | Authority note |
|---|---|---|---|
| Raw Meshy geometry/textures | `source/3d-models/crudo/` | Ignored | Expensive source/input, not authoritative master |
| Raw/polished Tripo source | `source/3d-models/pulido/` | Ignored | Source/input, not authoritative master |
| Existing working masters | `source/3d-models/*.glb` | Tracked | Current re-export source by older convention |
| Procedural sphere stages | `source/3d-models/procedural/esfera-mecanica/` | Untracked; `.blend` ignored | Experiment states Astrion `.blend`/UVs are authoritative, but persistence policy is unresolved |
| Diagnostic reports/renders | procedural folder and raw output folders | Mostly untracked/ignored | Evidence, not master data |
| Runtime assets | client repository / exports | Derived | Godot-facing output, not modeling authority |

## Environment observed during M0

- Git required a per-command `safe.directory` override because the worktree owner differs from the current process user. Global Git configuration was not changed.
- `python`, `py`, `blender`, `godot`, and `godot4` were not available on this session's PATH.
- No requirements, `pyproject.toml`, environment file, lockfile, or package manifest was found in `mex-orbit-art`.
- Existing scripts and assets were not executed or modified during discovery.

M1 adds a standard-library-only spec validator, so spec validation does not depend on Blender, Godot, or third-party Python packages. The Codex bundled Python runtime can run its tests when no system Python is on PATH.

## Duplicate, obsolete, or overlapping concepts

- The root README contains both retired 2D atlas/render paths and the newer all-3D path; it is history, not a clean current runbook.
- `find-anchors.py` measures 2D/render-space JSON points, while `marcar-anclajes.py` creates model-space 3D empties. Their names obscure the different contracts.
- `mex-orbit-testing/assets/validar-modelo.py` and `tools/asset-audit/validate_asset.py` overlap but enforce different eras/scopes.
- The legacy normalizer's color-dominance emission extraction conflicts with the new deterministic semantic emission policy.
- The older master convention favors tracked GLB and regenerable ignored `.blend`; the sphere experiment declares an ignored `.blend` to be authoritative.
- Older recipes treat Meshy high geometry as the game geometry source; the target architecture makes every generator non-authoritative after Astrion normalization/promotion.

Nothing in this list was removed or renamed in M0.
