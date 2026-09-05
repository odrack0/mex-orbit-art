# Astrion 3D pipeline architecture

## Scope

This document separates the repository as discovered on 2026-09-04 from the architecture Astrion is moving toward. The orchestration folder was empty at discovery time; current behavior is implemented by scripts and conventions in the parent `mex-orbit-art` repository.

## Current architecture

The current system is a collection of working, mostly script-driven production paths. M4 adds one bounded orchestration runner for the mechanical-sphere reference flow; it is proof of the target stage-runner contract, not yet a general application.

1. **Creative and source inputs.** The parent repository stores prompts, renders, raw/generated models, procedural builders, and legacy 2D sources. Generated Meshy inputs live under the ignored `source/3d-models/crudo/`; Tripo sources live under the ignored `source/3d-models/pulido/`.
2. **Geometry processing.** Blender scripts in `../tools/` normalize generated GLBs, repair/decimate high meshes, transfer appearance, bake normals, add anchors, rig assets, and build one procedural mechanical sphere. Most are executable scripts with positional arguments and asset-specific constants, not a reusable Python package.
3. **Master storage.** Tracked GLBs directly under `../source/3d-models/` are described as working masters. The procedural sphere experiment keeps staged `.blend`, `.glb`, reports, textures, and diagnostic renders under `../source/3d-models/procedural/esfera-mecanica/`, but that directory and several supporting scripts are currently untracked.
4. **Validation.** Geometry Audit v0.1 is spec-driven and produces a versioned report; the M3 sphere also has an asset-specific structured Audit 2 recorder. Legacy `asset-audit` and sibling `mex-orbit-testing` checks still contain policies that have not been generalized into the Asset Spec.
5. **Orchestration.** `astrion-3d-pipeline/tools/run_m4_esfera.py` now wraps the five proven sphere stages with explicit Blender discovery, dry-run, output isolation, logs, manifests, hash-bound resume, and waiver safeguards. Other assets still use individual scripts.
6. **Export/runtime.** Scripts emit GLB files consumed by `mex-orbit-client`. The M3 reference GLB has a passing isolated Godot import/runtime-emission smoke report, but there is no cross-asset export adapter or general build command yet.
7. **Documentation.** The parent `README.md` is a valuable chronological lab notebook, but it includes retired and historical recipes alongside current findings. This folder now carries the operational contract, audit records, milestone roadmap, and M4 runner guide.

The current flow is therefore implicit:

```text
prompts/concepts or generated GLB
    -> one of several Blender scripts
    -> source/3d-models/<asset>.glb
    -> optional rig/anchor/export scripts
    -> mex-orbit-client / Godot
```

### Existing authority assumptions

The older generated-asset path often treats a repaired/decimated Meshy high mesh as the geometry source. The mechanical-sphere experiment already demonstrates the desired stronger model: Astrion geometry and UVs remain authoritative, Meshy supplies appearance, and appearance is reprojected back.

### Current coupling

- Camera constants and asset-class budgets are embedded in `asset-audit` code.
- Script inputs, outputs, thresholds, and provenance are conveyed through CLI arguments, environment variables, README prose, and output reports.
- Several tools import Blender's `bpy`; others require Python 3.12, NumPy, SciPy, and Pillow. No dependency manifest pins these versions.
- Cross-repository checks depend on sibling checkouts (`mex-orbit-client`, `mex-orbit-docs`, and `mex-orbit-testing`).
- Safety is implemented by `tools/salvaguarda.py`, but only some file-writing scripts use it.

## Target architecture

The target is one local, parametrizable orchestration pipeline. It is not a second modeling pipeline and does not require every asset to visit every external service.

```text
Concept(s)
   -> Asset Spec
   -> optional reviewed evidence handoff from the generative probe flow
   -> geometry-origin decision
   -> Master Mesh construction/normalization
   -> Audit 1: Geometry
   -> UV + material IDs
   -> appearance generation/authoring
   -> reprojection when appearance UVs differ
   -> deterministic emission
   -> Audit 2: UV/Textures
   -> export package
   -> Godot presentation/runtime FX
```

### Proposed components

- **Asset Spec loader/validator:** reads a small versioned spec and resolves class-aware defaults without hiding explicit decisions.
- **Stage runner:** invokes existing Blender/Python scripts through adapters, records exact commands and versions, and refuses invalid stage transitions.
- **Artifact registry:** records inputs, outputs, hashes, authority, and provenance without moving existing source folders in early milestones.
- **Geometry-origin adapter:** represents `accept_normalize`, `repair`, `rebuild_reference`, and `procedural_direct` as outcomes of one decision point.
- **Generative probe flow:** a separate experimental workflow that receives explicit outputs from provider-specific pipelines and returns reviewed evidence. It owns neither service acquisition nor Master Mesh promotion; see [flows/generative-probes/README.md](../flows/generative-probes/README.md).
- **Audit adapters:** split current measurements into pre-UV geometry checks and post-UV appearance checks, with structured reports and explicit waivers.
- **Blender utility layer:** gradually extracts reusable, deterministic operations from proven scripts. It should grow from real asset work, not from speculative primitives.
- **Export adapter:** emits deterministic GLB plus metadata and validates the package expected by Godot.
- **CLI:** eventually exposes one `astrion build <asset-spec>` command with resumable stages and dry-run/inspect modes.

### Authority and ownership

| Information | Authority | External/derived contribution |
|---|---|---|
| Identity, gameplay class, intended screen size, allowed origins | Asset Spec | Concept metadata may seed it |
| Geometry, scale, orientation, topology, semantic pieces | Astrion Master Mesh | Meshy/Tripo may be accepted, repaired, or used as reference |
| Material IDs, UVs, anchors, export metadata | Astrion Master Mesh | External tools may propose, never silently replace |
| Metal, paint, wear, rust, dirt | Approved Astrion texture set | AI appearance may be reprojected into it |
| Emission regions/mask | Deterministic Astrion data | AI color may inform review, not final truth |
| Emission color/energy, bloom, particles, engines, lasers, shields, lighting | Godot/runtime configuration | Not baked into geometry or glow halos |
| Audit results and provenance | Pipeline records | Tool output is evidence, not authority by itself |

### Design constraints

- A triangle ceiling is a rejection boundary, never a target. The preferred mesh is the least geometry that preserves silhouette, major volumes, identity, and gameplay readability.
- Mechanical and organic assets share the lifecycle but receive different rule profiles.
- The Master Mesh must survive replacement of Meshy, Tripo, or any texturing service.
- Every mutation must name its input and write a distinct output until promotion is explicit.
- Reprojections must handle tangent-space normals as a basis conversion problem; copying normal pixels between unrelated UV layouts is invalid.

## Migration approach

M1-M4 keep source paths stable, add contracts and structured reports, and wrap proven scripts before generalizing them. The M4 sphere runner establishes the stage/manifest/resume contract. Continue extracting reusable adapters only from additional real asset work, then converge on the M7 top-level command. See [roadmap.md](roadmap.md) and [m4-runner.md](m4-runner.md).
