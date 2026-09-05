# Single parametrizable asset pipeline

## Principle

Astrion production has one lifecycle with optional stages and class-aware policies. Meshy and Tripo may supply evidence to its geometry-origin decision, while their provider-specific acquisition pipelines remain outside the production lifecycle. Repair, reference rebuild, and procedural construction are production outcomes, not independent production pipelines.

The optimization target is gameplay readability:

> Geometry defines identity. Texture sells complexity. Godot provides the light.

## Stage model

| Stage | Required input | Output / gate |
|---|---|---|
| 0. Concept intake | Approved concept/reference and gameplay intent | Traceable source inputs |
| 1. Asset Spec | Concept plus game metadata | Valid spec with identity, screen size, class, constraints, and allowed origins |
| 2. Generative evidence handoff (optional) | Reviewed evidence from the separate [generative probe flow](../flows/generative-probes/README.md) | Declared candidates and provenance for an explicit origin decision |
| 3. Geometry-origin selection | Spec, candidates, prior evidence | One recorded outcome and rationale |
| 4. Master Mesh creation | Selected source/reference | Candidate authoritative Astrion Master Mesh |
| 5. Audit 1 — Geometry | Master Mesh candidate and geometry policy | Pass, explicit waiver, or return to stage 4 |
| 6. UV + material IDs | Geometry-approved Master Mesh | Authoritative UVs, semantic materials, deterministic emission regions |
| 7. Appearance | UV-ready master or appearance copy | PBR appearance source; it may use different UVs temporarily |
| 8. Reprojection (conditional) | Authoritative master plus appearance source | Appearance sampled onto Astrion UVs and materials |
| 9. Deterministic emission | Material/region contract | Binary or controlled mask owned by Astrion; no baked halo |
| 10. Audit 2 — UV/Textures | Final UVs/material IDs/maps | Pass, explicit waiver, or return to stages 6-9 |
| 11. Export | Audited master and export profile | Deterministic runtime GLB and metadata |
| 12. Godot verification | Export plus runtime scene/material policy | Gameplay-camera presentation approval |

Stages may be resumed, but their order cannot be collapsed in ways that erase authority. In particular, Audit 1 must not require UVs, and appearance generation must not silently promote altered geometry, UVs, pieces, or materials.

Meshy and Tripo acquisition have provider-specific processes and are not production stages. The separate probe flow plans fresh experiments, receives explicit deliveries, evaluates them under one profile, and hands back reviewed evidence. The production lifecycle may skip that flow entirely. It never searches legacy source folders for candidates or promotes a result.

M4 proves resumable execution for the mechanical sphere with `tools/run_m4_esfera.py`. It hashes completed outputs before skipping them and refuses to overwrite partial stage directories. This remains an asset-specific adapter; see [m4-runner.md](m4-runner.md).

## Geometry-origin decision

The spec defines `preferred_origin` and `allowed_origins`. Evidence determines one outcome:

### Accept / normalize

Use when generated geometry already preserves the concept's silhouette, volumes, identity features, and screen-space economy. Normalize transforms, scale, orientation, naming, semantic pieces, topology health, and metadata. Passing normalization does not make the generator authoritative; the normalized Astrion version becomes the candidate master.

### Repair

Use when most generated geometry is valuable but localized defects are cheaper to replace than rebuild. Typical repairs include dense cylinders/spheres, primitive topology, small parasitic islands, holes, invalid anchors, and scale/orientation. Record repaired regions and preserve an immutable input.

### Rebuild / reference

Use the generated mesh only as a volumetric reference when its topology or structure is unsuitable. Reconstruct the identity-bearing forms in Blender, then discard any dependency on generated topology from the master.

### Procedural direct

Skip generative geometry when the spec or prior evidence shows deterministic construction is cheaper and clearer. The existing mechanical sphere is the current proof of this route.

## Master Mesh contract

After promotion, the Astrion Master Mesh owns:

- geometry and topology;
- scale, orientation, origin, transforms, and symmetry intent;
- named semantic pieces/components;
- material IDs and authoritative UVs;
- anchors/empties and their names/transforms;
- export metadata and provenance links.

An appearance service receives a copy. Returned geometry is evidence for correspondence and appearance transfer, not a replacement master.

## Screen-space decisions

- Evaluate diagnostic views at the declared gameplay screen size and camera before close-up review.
- Preserve silhouette, major mass relationships, recognizable identity features, and volumes that survive the camera.
- Put seams, small panels, rivets, scratches, wear, micro-bevels, and similar non-silhouette detail in textures/normal maps.
- Select segment counts deliberately for mechanical curves; do not inherit Blender defaults or generated density.
- Treat subpixel and hidden geometry as review evidence. Do not delete animation-revealed or gameplay-significant geometry merely because one static camera hides it.

## Appearance and reprojection

AI appearance can provide paint, metal, roughness, wear, rust, dirt, and similar surface information. If it changes UVs or collapses pieces/materials:

1. retain the Astrion Master Mesh unchanged;
2. align the appearance copy geometrically;
3. transfer base color and scalar PBR channels onto Astrion UVs;
4. rebase tangent-space normals correctly between tangent frames, or rebake them;
5. pad islands for mip safety;
6. restore material IDs and verify semantic pieces;
7. compare source and reprojection at gameplay scale.

`tools/reproyectar-texturas.py` proves this for one near-identical Meshy return. It is not yet a general-purpose reprojection stage.

## Emission and runtime effects

Emission is deterministic and semantic. The final mask comes from Astrion-owned regions/material IDs or an explicitly authored mask. Generative output must not decide final emission, and textures must not contain glow halos.

Godot owns cyan color, energy, bloom/glow, particles, engine/laser/shield effects, pulsing, and dynamic lighting. Exported materials may carry a mask or neutral emission texture with runtime energy disabled/defaulted according to the runtime contract.

## Provenance requirements

Each completed stage should eventually record:

- input and output paths plus content hashes;
- Asset Spec version and stage status;
- tool/script and version, Blender/Python version, parameters, and random seed where applicable;
- source service/model/settings for generative work;
- audit report and waivers;
- promotion decision and responsible reviewer.

M0 documents this requirement; M1 should implement only the minimum spec fields needed to describe it.
