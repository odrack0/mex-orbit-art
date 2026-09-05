# M4 local Blender runner

## Scope

`tools/run_m4_esfera.py` reproduces the proven `esfera-mecanica` path. It is intentionally asset-specific: M4 validates orchestration, isolation, resume behavior, logs, hashes, and safeguards before M7 exposes a general `astrion build` command. It calls the existing repair, Geometry Audit, UV/material, reprojection, and M3 Audit 2 tools rather than duplicating their implementation.

The runner stops at the `exported` stage. Godot verification remains a separate post-export gate because runtime presentation is not a Blender operation.

## Blender discovery

Discovery order is explicit:

1. `--blender <path>`;
2. `ASTRION_BLENDER`;
3. `blender` on `PATH`;
4. known versioned Blender installation folders.

Every candidate is checked with `blender --version`; the selected absolute path and version are written to the run manifest. The runner does not download or install Blender.

## Safe output model

`--output-dir` must be a new child of `astrion-3d-pipeline/work/`. It cannot point into `source/`, an input folder, or an existing run unless `--resume` is present. Each stage has an isolated directory:

```text
<run>/
  run-manifest.json
  asset-spec.m4.json
  logs/
  stages/
    01-repair/
    02-audit1/
    03-uv/
    04-reproject/
    05-audit2/
```

The manifest records input hashes, tool/Blender/Python versions, exact argument arrays, logs, stage status, and output hashes. Resume skips a completed stage only while every recorded hash and size still matches. Partial or modified stage output is never overwritten automatically; use a fresh run directory.

A reviewed Audit 1 waiver is carried forward only when the newly repaired GLB hash matches the repair report bound to the supplied spec. A waiver therefore cannot silently approve different geometry.

## Commands

Preview the complete plan without creating the output directory:

```powershell
python astrion-3d-pipeline/tools/run_m4_esfera.py `
  --spec astrion-3d-pipeline/work/esfera-mecanica-m3-v4/esfera-mecanica-m3.spec.json `
  --output-dir astrion-3d-pipeline/work/esfera-mecanica-m4-run `
  --dry-run
```

Run through an intermediate stage:

```powershell
python astrion-3d-pipeline/tools/run_m4_esfera.py `
  --spec astrion-3d-pipeline/work/esfera-mecanica-m3-v4/esfera-mecanica-m3.spec.json `
  --output-dir astrion-3d-pipeline/work/esfera-mecanica-m4-run `
  --to-stage uv
```

Resume after the verified completed stages:

```powershell
python astrion-3d-pipeline/tools/run_m4_esfera.py `
  --spec astrion-3d-pipeline/work/esfera-mecanica-m3-v4/esfera-mecanica-m3.spec.json `
  --output-dir astrion-3d-pipeline/work/esfera-mecanica-m4-run `
  --resume --from-stage reproject
```

`--from-stage` cannot bypass incomplete prerequisites. `--to-stage` supports `repair`, `audit1`, `uv`, `reproject`, and `audit2`.

## Verified reference run

`work/esfera-mecanica-m4-run-v1/` was executed in two calls—first through UV, then resumed at reprojection. All five manifest stages are complete. Audit 1 returned `waived`; Audit 2 returned 11 passes, one documented occupancy-policy warning, and zero errors. The repaired, UV, and textured GLBs are byte-identical to the M3 references:

| Artifact | SHA-256 |
|---|---|
| Repaired GLB | `2a25a99667ccbb1cc64fa0d18daf73f802d9d23346fa7ac5c79264583022dd6c` |
| UV/material GLB | `9dc693dafca63c41ab1c4ebfed522cae75a555f3b74b0be19361bdcf100f7de0` |
| Textured/export GLB | `16e241d0840548205a8ac7ca0ca8242535d511c22bafe70428ef047346c519f4` |

Blender may emit non-fatal thumbnail/cache warnings in this sandbox. Stage success is determined by process exit, required artifacts, stage-specific checks, and hashes—not by suppressing those warnings.
