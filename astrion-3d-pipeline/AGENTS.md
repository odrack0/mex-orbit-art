# Astrion 3D pipeline

This folder is the orchestration and contract layer for Astrion's local 3D asset pipeline. The implementations and current assets still live in the parent `mex-orbit-art` repository; start with [docs/repository-map.md](docs/repository-map.md) and [docs/architecture.md](docs/architecture.md).

## Working rules

- Preserve the principle: **Geometry defines identity. Texture sells complexity. Godot provides the light.** Judge geometry at the gameplay camera and intended screen size, not by close-up polish.
- The authoritative order is: approved Asset Spec and concept intent; Astrion Master Mesh (geometry, transforms, topology, semantic parts, material IDs, UVs, anchors, metadata); deterministic Astrion outputs; AI-generated geometry or appearance. Meshy and Tripo are inputs, never authorities.
- Use the single parametrizable lifecycle in [docs/pipeline.md](docs/pipeline.md). Keep geometry and UV/texture validation as distinct gates; see [docs/audits.md](docs/audits.md).
- Before changing anything, inspect Git status and repository boundaries, read the asset's spec/provenance and relevant scripts, and identify ignored source material. Existing uncommitted work belongs to the user.
- Do not overwrite or write into `source/3d-models/crudo/` or source render folders. Do not replace an input in place. Do not modify a 3D asset merely to inspect it. Prefer deterministic Blender CLI scripts over manual UI work.
- Preserve semantic pieces, UVs, material IDs, anchors, scale, orientation, and provenance unless the active stage explicitly owns that field. Emission masks are deterministic Astrion data; glow, energy, particles, shields, lasers, and dynamic lighting belong in Godot.
- Before completion, run the checks appropriate to the changed stage, inspect diagnostic views at gameplay scale, review every changed file, verify documentation links, and report `git diff --stat` plus any checks that could not run.

## Documentation

- [Architecture](docs/architecture.md)
- [Pipeline](docs/pipeline.md)
- [Asset Spec v0.1](docs/asset-spec.md)
- [Audit gates](docs/audits.md)
- [Repository map](docs/repository-map.md)
- [Roadmap](docs/roadmap.md)
- [M4 local runner](docs/m4-runner.md)
- [Generative probe flow](flows/generative-probes/README.md)
