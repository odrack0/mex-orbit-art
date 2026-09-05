# Roadmap

## Milestone rule

Each milestone should produce a small usable contract, exercise it on real repository data, and preserve current assets/paths until a migration is explicitly approved. Do not build a speculative framework ahead of a proven asset flow.

## M0 — Repository/context documentation

**Goal:** establish operational context and distinguish current from target architecture.

Deliverables:

- short `AGENTS.md`;
- architecture, pipeline, Asset Spec proposal, audits, repository map, and roadmap docs;
- recorded repository boundary, existing dirty state, capabilities, gaps, contradictions, and environment limits.

Exit criteria: documentation links resolve; no asset/script is modified; diff contains only the M0 docs.

## M1 — Asset Spec v0.1

**Goal:** create the smallest machine-readable per-asset contract that can drive Audit 1 and record stage/provenance.

**Status:** implemented on 2026-09-04. The schema, read-only validator, fixtures/tests, and experimental sphere example are in place. M2 should consume the contract without expanding M1 into an orchestration framework.

Recommended task:

1. Resolve the six open decisions in [asset-spec.md](asset-spec.md), especially screen-size semantics, canonical axes/units, master format/location, and category budget interpretation.
2. Select one representative existing asset—preferably the mechanical sphere because its stages and reports are explicit—without silently declaring experimental files production masters.
3. Add a versioned schema and one reviewed example spec.
4. Add a read-only `validate-spec` command with fixture tests for required fields, enums, origin consistency, triangle target/ceiling, stage transitions, and safe repository-relative paths.
5. Document how existing validator CLI flags map to spec fields. Do not yet invoke Blender or modify the asset.

Exit criteria: a valid example passes; invalid fixtures fail with actionable messages; the command performs no asset writes; schema and example are reviewed against current scripts and Godot conventions.

## M2 — Geometry Audit v0.1

**Goal:** produce a geometry-only, spec-driven structured report.

**Status:** implemented on 2026-09-04. The transform-aware GLB loader, versioned report/schema, semantic component and anchor checks, gameplay-size diagnostic, pinned direct dependencies, and primitive regressions are in place. The selected sphere has a repeatable failure report and remains a candidate; M3 must not begin by treating it as geometry-approved.

- Wrap/reuse `mesh_metrics.py` rather than rewriting measurements.
- Remove UV requirements from the Audit 1 decision.
- Apply class/spec filtering for organic versus mechanical rules.
- Correctly evaluate GLB node transforms or explicitly require an audited flattened input.
- Add semantic component and anchor checks.
- Reframe triangle ranges around soft targets/ceilings and gameplay perception.
- Pin dependencies and run primitive regression tests.

Exit criteria: the selected M1 asset receives a repeatable JSON report plus gameplay-size diagnostic evidence without UV/textures being required.

## M3 — One asset end-to-end, manually orchestrated

**Goal:** prove the lifecycle and artifact/provenance contract before automating it.

**Status:** completed on 2026-09-04 for the experimental `esfera-mecanica` reference asset. The isolated M3 result repairs the topology, closes Audit 1 with a scoped never-visible-geometry waiver, creates authoritative UVs/material IDs and a deterministic emission mask, reprojects Meshy appearance, passes the asset-specific Audit 2 recorder, exports an embedded GLB, and passes a Godot 4.7.1 headless import/runtime-emission smoke test. The original source remains unchanged and the asset remains experimental rather than production-promoted.

- Walk one asset through geometry-origin decision, Master Mesh promotion, Audit 1, UV/material IDs, appearance/reprojection if needed, deterministic emission, Audit 2, export, and Godot review.
- Run existing scripts explicitly and record commands/versions/hashes.
- Capture every manual decision or waiver that future automation must represent.

Exit criteria: one traceable Godot-ready asset with both audits and no ambiguity about its authoritative files.

Completed evidence lives under `work/esfera-mecanica-m3-v4/`. `esfera-mecanica-m3.spec.json` is the final lifecycle manifest, `uv-texture-audit-m3-v0.1.json` is Audit 2, and `godot-smoke/godot-smoke-report.json` records the runtime import checks. The 43.2% UV occupancy is a documented M3 policy warning, not a hidden pass: Asset Spec v0.1 defines no occupancy threshold, and M6 must replace the generic 75% reference with class-specific occupancy and padding policy.

## M4 — Blender CLI orchestration

**Goal:** make proven M3 operations repeatable from a local runner.

**Status:** completed on 2026-09-04 for `esfera-mecanica`. `tools/run_m4_esfera.py` discovers and verifies Blender, supports no-write dry runs, isolates five stages, records commands/logs/hashes, refuses unsafe or partial-output overwrites, binds the reviewed Audit 1 waiver to the repaired GLB hash, and resumes only across completed untampered stages. The two-invocation reference run under `work/esfera-mecanica-m4-run-v1/` reproduced all three M3 GLBs byte-for-byte and finished Audit 2 with the same 11 pass / 1 warning / 0 error result. See [m4-runner.md](m4-runner.md).

- Discover/configure Blender explicitly rather than assuming PATH.
- Add dry-run, stage resume, output isolation, logs, and uniform safeguard enforcement.
- Introduce reusable Blender helpers only for operations exercised by M3.
- Never write into raw/source input folders or overwrite inputs.

Exit criteria: the selected asset's deterministic local stages can be rerun into a fresh output area with equivalent reports.

## M5 — Generative probe evidence flow

**Goal:** define and exercise a separate evidence workflow that accepts explicit deliveries from provider-specific Meshy/Tripo pipelines without granting either authority.

**Status:** complete for the required manual flow on 2026-09-04; M5E provider automation remains optional. The fresh `aci-01-test-probe-20260904-01` run froze the exact shared `geometria.png` reference, registered explicit Meshy and Tripo GLBs, verified immutable hashes, measured both through the transform-aware geometry engine, rendered common diagnostics, and published separate identity reviews. Reviewer `E. Lopez` selected `tripo-candidate-01` for `repair`, while Meshy remains `rebuild_reference` evidence. The closeout explicitly records no production handoff: no legacy or production asset was modified, no Master Mesh was promoted, and Audit 1 was not run. See [Generative probe flow v0.1](../flows/generative-probes/README.md).

- Add schemas and a read-only validator for probe plan, delivery, candidate evaluation, and decision records. **Complete.**
- Start from a fresh probe plan and explicit provider deliveries; keep provider account/API workflows outside the common flow. **Complete for the first two-provider proof.**
- Record comparisons by asset class and geometry outcome without claiming Audit 1. **Complete for the first probe: Tripo selected for repair.**
- Keep service interaction optional and manual delivery supported first.
- Require a named review decision; never promote or modify a production asset automatically.

Exit criteria: **met.** A fresh two-provider probe was closed with a reviewed decision and no production-asset modification.

## M6 — Appearance/reprojection automation

**Goal:** generalize the successful sphere appearance-transfer path safely.

- Detect whether returned geometry/UVs/materials changed.
- Support correspondence failure reporting and fallback rebake/reference decisions.
- Reproject scalar/color channels and correctly rebase or rebake normals.
- Restore Astrion material IDs/UVs and deterministic emission.
- Add Audit 2 structured reports, mip-safe padding, and gameplay-scale comparisons.

Exit criteria: appearance can change without changing Master Mesh authority, and failures stop with useful diagnostics.

## M7 — End-to-end `astrion build`

**Goal:** expose the validated lifecycle as one resumable local command.

- Load Asset Spec, plan stages, run required adapters, enforce both gates, and emit export/provenance manifests.
- Support inspect/dry-run, selective resume, deterministic output roots, and explicit external-service steps.
- Verify the Godot package/import contract and keep runtime FX ownership in Godot.

Exit criteria: `astrion build <spec>` can reproduce an approved asset from declared available inputs, stops at failed gates, and never treats AI output as authoritative by default.

## Cross-cutting risks to resolve incrementally

- Untracked/ignored authoritative experiments can be lost.
- Raw generated sources are ignored and currently have no declared backup strategy.
- The working tree contains unrelated user changes; automation must be path-scoped.
- Tool/runtime versions are unpinned and absent from the current PATH.
- Current validators overlap, mix audit stages, and encode policies in code.
- Root documentation contains superseded recipes that can be mistaken for current instructions.
- GLB hierarchy/transform handling differs across validators.
- Emission extraction by color and semantic deterministic emission represent incompatible authority models.
