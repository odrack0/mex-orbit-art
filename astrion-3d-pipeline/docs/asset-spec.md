# Asset Spec v0.1

## Purpose

The Asset Spec is the small machine-readable contract that lets one pipeline choose policies and record progress per asset. M1 freezes v0.1 as JSON with a checked-in schema, a standard-library read-only validator, fixtures, and one reviewed experimental example.

It is based on the requested authority model and repository facts already encoded in `tools/asset-audit/validate_asset.py`, `source/3d-models/README.md`, the model/anchor scripts, the runtime's `screen_size` convention, and `mex-orbit-docs/05-arte/05-pipeline-unificado.md`.

## Files and commands

Specs live at `source/3d-models/specs/<asset-id>.json`. The schema and validator live in this orchestration folder:

- `schemas/asset-spec-v0.1.schema.json`
- `tools/validate_spec.py`
- `tests/`

From the `mex-orbit-art` repository root:

```powershell
python astrion-3d-pipeline/tools/validate_spec.py source/3d-models/specs/esfera-mecanica.json
python -m unittest discover -s astrion-3d-pipeline/tests -v
```

The validator returns 0 for valid, 1 for invalid, or 2 when JSON cannot be read. It never writes, invokes Blender/Godot, or requires referenced paths to exist.

## Contract outline

```json
{
  "schema_version": "0.1",
  "identity": {
    "asset_id": "test-prop",
    "category": "prop",
    "family": "mechanical",
    "tier": "standard",
    "status": "experimental"
  },
  "visual": {
    "screen_size_world_units": 40,
    "camera_profile": "top_down_default_v1",
    "symmetry": {"type": "bilateral_x"},
    "silhouette_complexity": "low",
    "major_masses": ["body"],
    "identity_features": ["wedge silhouette"]
  },
  "geometry": {
    "preferred_origin": "auto",
    "allowed_origins": ["meshy", "procedural_blender"],
    "soft_triangle_target": 400,
    "triangle_ceiling": 800,
    "coordinate_profile": "astrion_blender_to_godot_v1",
    "components": {"min": 1, "max": 4, "required": ["body"]},
    "anchors": {"required": []}
  },
  "appearance": {
    "texture_resolutions": [512],
    "maps_required": ["base_color", "normal", "orm"],
    "metallic": "mixed",
    "roughness": "medium",
    "wear": "light",
    "rust": "none",
    "emission": {"policy": "none", "material_ids": [], "bake_glow_halo": false}
  },
  "pipeline": {
    "stage": "spec_ready",
    "geometry_outcome": "undecided",
    "source_inputs": [],
    "generated_inputs": [],
    "master_mesh": null,
    "outputs": [],
    "audits": {
      "geometry": {"status": "not_run", "report": null},
      "uv_textures": {"status": "not_run", "report": null}
    },
    "provenance": {}
  }
}
```

The full reviewed example is `source/3d-models/specs/esfera-mecanica.json`. It explicitly keeps the sphere experimental and at `master_mesh_candidate`; existing later artifacts do not imply either audit has passed.

## Field guidance

### `identity`

- `asset_id` is stable, filesystem-safe, and unique.
- `category` initially maps to an existing validation profile where possible: `prop`, `prop_grande`, `dron`, `pet`, `npc_normal`, `npc_complejo`, `elite`, `boss`, `uber`, `player_ship`, `estructura`, `portal`, or `fx`.
- `family` expresses art/game taxonomy without changing validation rules by itself.
- `tier` records gameplay importance; it must not silently inflate geometry.
- `status` distinguishes an experimental reference from a production asset.

### `visual`

- `screen_size_world_units` is exactly the client's `screen_size`: the desired maximum X/Z footprint in world units after loading. `entity_node.gd` scales by `screen_size / extent_3d(model)`.
- `camera_profile` is `top_down_default_v1`: FOV 30°, distance 1740/zoom, elevation 45° at zoom 1 falling to 25° at zoom 3, with map azimuth 0° or 25°. The audit derives pixels; they are not hand-authored here.
- `symmetry` supports `none`, `bilateral_x`, `bilateral_y`, `bilateral_z`, and `radial`; radial symmetry requires an order.
- `major_masses` and `identity_features` are short review checklists. They are not a geometry recipe.

### `geometry`

- `preferred_origin` may be `auto`, `meshy`, `tripo`, or `procedural_blender`; `allowed_origins` constrains experiments.
- `pipeline.geometry_outcome` records the selected result: `accept_normalize`, `repair`, `rebuild_reference`, or `procedural_direct`.
- `soft_triangle_target` is a planning estimate. Going below it is desirable if readability survives.
- `triangle_ceiling` is a hard boundary or escalation trigger, never a fill target.
- Component, primitive, flatness, symmetry, and anchor rules are explicit and class-aware. Mechanical rules must not be imposed on organic assets.
- `astrion_blender_to_godot_v1` means Blender +X right, +Y forward, +Z up; glTF/Godot +X right, −Z forward, +Y up. The normalized source is scaled uniformly at runtime to `screen_size_world_units`.

### `appearance`

- Declare required map roles and permitted resolutions rather than filenames where possible.
- Metallic/roughness/wear/rust values can start as controlled qualitative terms; avoid an elaborate material ontology in v0.1.
- Emission policy must state how the deterministic mask is derived. Runtime color/energy belong to a referenced Godot profile, not baked appearance.
- Map color spaces belong in the texture/export policy: base color is sRGB; normal, ORM, metallic, roughness, and masks are non-color data.

### `pipeline`

- `stage` should be one controlled value corresponding to [pipeline.md](pipeline.md).
- Inputs and outputs are repository-relative paths with roles. Content hashes can be added by tooling rather than hand-authored.
- Provenance should capture generator/service, settings, tool versions, commands, and decisions only when they exist. Unknown is preferable to invented metadata.
- Audit files remain separate structured artifacts and are referenced here.

## Validation implemented in M1

The standard-library validator checks:

1. schema version, required identity, and a known category;
2. positive world-unit screen size plus camera profile;
3. allowed/preferred origin consistency;
4. `soft_triangle_target <= triangle_ceiling` when both exist;
5. valid stage and geometry outcome combinations;
6. repository-relative path normalization with no writes or existence requirements during a pure validation command;
7. rejection of unknown keys only where a typo would be dangerous; keep `notes` extensible.

Critical structured objects reject unknown fields so policy typos fail. `pipeline.provenance` stays extensible. M1 deliberately adds no database, inheritance hierarchy, remote service API, or workflow engine.

Audit references may include `waivers`. A waiver is valid only when the audit status is `waived` and must contain an exact `check_id`, non-empty `reason` and `scope`, a named `reviewer`, and a `revisit_condition`; `expires` may be a date/string or `null`. A `pass` audit cannot carry waivers, and a `waived` audit cannot omit them. Audit tooling applies waivers only to an existing error with the same check ID; a missing or non-error target is not silently waived.

## Resolved M1 decisions

- **Format/location:** JSON at `source/3d-models/specs/<asset-id>.json`. JSON avoids introducing an undeclared YAML dependency and matches current game data.
- **Screen size:** store the runtime X/Z footprint in world units; compute pixels from the camera profile. At 1440p/zoom 1, the current approximation is 1.544 px per world unit.
- **Coordinates:** use the named Blender-to-Godot profile described above rather than repeating axes per asset.
- **Budgets:** v0.1 keeps a soft planning target and hard ceiling only. M2 must reconcile the two conflicting class tables before enforcing defaults; lower bounds are not pass requirements.
- **Anchors:** list exact required names per asset. Current runtime consumes `tobera_*`/`canon_*`, while the low-poly standard proposes different prefixes; M2 must expose or coordinate that conflict rather than alias silently.
- **Promotion:** no existing GLB was promoted in M1. The sphere is an experimental candidate until formal Audit 1 passes.

## Existing CLI mapping

| Asset Spec field | Existing interface | Mapping for M2 |
|---|---|---|
| `identity.category` | `validate_asset.py --type` | Direct; v0.1 enum names match the current validator |
| `visual.screen_size_world_units` | `validate_asset.py --screen-size` | Direct; the CLI receives world units despite its name |
| `visual.camera_profile` | `mesh_metrics.py` constants and client `camera.json` | Replace embedded assumptions with the named profile |
| `visual.symmetry.type` | `validate_asset.py --organic` | Replace the boolean proxy with explicit policy |
| `geometry.soft_triangle_target` | Existing range lower bound/operator choice | Informational only; never a required minimum |
| `geometry.triangle_ceiling` | Existing range upper bound and external validator `tris` | Hard boundary or explicit waiver |
| `geometry.components` | `PIECES` and island metrics | Spec requirements plus class-aware defaults |
| `geometry.flatness_range` | `FLATNESS` | Explicit override or class default |
| `geometry.primitive_rules` | `radial_slots`/`rot_order` warnings | Only for declared mechanical geometry |
| `geometry.anchors.required` | No general validator | New Audit 1 GLB-node check |
| `appearance.texture_resolutions` | External validator `lado_textura` | Audit 2 resolution policy |
| `appearance.maps_required` | Partial GLB/ATF inspection | New Audit 2 map/channel check |
| `appearance.emission` | `normalize-model.py` color-channel dials | Replace inferred final truth with semantic material IDs or authored mask |
| `pipeline.geometry_outcome` | Operator/script choice | Provenance and rule filtering, never automatic promotion |

`--world-scale` has no v0.1 field. It remains a diagnostic escape hatch; production validation uses the declared screen-size footprint.

## Deferred to later milestones

- Class defaults and reconciliation of conflicting budget tables
- A general Audit 2 report schema and class-specific UV/texture policy (the M3 sphere uses an explicitly asset-specific evidence recorder)
- File-existence and artifact-graph validation
- Blender/Godot invocation and generator APIs
- Credential handling, inheritance, databases, and remote orchestration
