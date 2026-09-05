# Generative probe flow v0.1

## Purpose

This is an experimental evidence flow beside the Astrion production pipeline. It receives deliberate deliveries from Meshy, Tripo, or a future provider pipeline and makes them comparable without treating them as production assets.

Provider generation pipelines remain separate. This flow does not reinterpret existing files under `source/3d-models/crudo/` or `source/3d-models/pulido/`, infer their provider from a directory name, or adopt an old candidate merely because its asset ID matches.

The only connection to the production pipeline is an explicit, reviewed evidence handoff:

```text
Asset Spec snapshot + approved references
                    |
               probe request
                    |
       +------------+------------+
       |                         |
external Meshy pipeline   external Tripo pipeline
       |                         |
       +---- explicit deliveries-+
                    |
          Astrion probe intake
                    |
       common diagnostics/review
                    |
          reviewed evidence pack
                    |
       explicit geometry decision
                    |
     optional production handoff
```

The production pipeline remains the only path that can construct or promote an Astrion Master Mesh and run Audit 1 or Audit 2.

## Ownership boundary

| Concern | Owner |
|---|---|
| Service account, credits, provider UI/API, generation queue, and provider-specific retries | External provider pipeline |
| Concept/reference preparation for a particular experiment | Probe request, with links back to approved sources |
| Downloaded candidate and provider metadata | Explicit delivery from the external pipeline |
| Hashing, safe intake, common metrics, diagnostic renders, and comparison | This flow |
| Geometry-origin selection and Master Mesh work | Astrion production pipeline |
| Promotion approval | Named human reviewer; never a probe tool |

An automated Meshy or Tripo adapter may be added later, but it must implement the same delivery contract. Manual delivery is the first supported mode.

## Lifecycle

### 1. Plan a fresh probe set

Create a unique `probe_id` and freeze the relevant Asset Spec and reference hashes. State the question the experiment is intended to answer, the requested providers, generation mode, evaluation profile, and stop conditions.

A probe must be justified. If prior evidence or the Asset Spec already selects `procedural_direct`, close the request as `skipped` without contacting a provider.

### 2. Dispatch provider requests

Create a request bundle for each selected provider. Provider-specific prompts or reference preparation may differ, but the bundle must retain a link to the same probe plan so the comparison is interpretable.

External execution is asynchronous and outside this flow. After dispatch, the probe set is considered `waiting_external`; that is not a production pipeline stage. The hashed plan remains frozen at `ready` rather than being edited as the probe advances.

### 3. Receive explicit deliveries

An operator or adapter supplies a delivery manifest and its files. Intake never searches legacy raw folders for apparent matches. Each delivery declares its provider, candidate ID, generation mode, known model/settings, operator or adapter, timestamps, and source location. Unknown values remain `unknown`.

Every received file is hashed before inspection. The original delivery is immutable for the duration of the run.

### 4. Inspect safely

Parse candidates read-only and record whether the file is usable. Any conversion or transform normalization writes a derived evaluation copy under the run directory and records its parent hash and exact command. It never overwrites the delivery.

This step is evaluation normalization only. It does not create a Master Mesh.

### 5. Evaluate under a common profile

All usable candidates receive the same provider-neutral evidence where applicable:

- parse/import result and file integrity;
- bounds, orientation, scale, mesh/primitive/material counts, triangles, and connected components;
- topology and density observations useful for estimating repair cost;
- semantic-piece and anchor observations without requiring production names yet;
- diagnostic views from the declared gameplay camera and screen size;
- identity/silhouette checklist derived from the frozen Asset Spec;
- visible defects, lost features, unwanted detail, and estimated cleanup work;
- suggested geometry outcome: `accept_normalize`, `repair`, `rebuild_reference`, or `procedural_direct`.

These are probe metrics, not Audit 1 results. A candidate cannot receive `geometry: pass` from this flow.

### 6. Compare and review

Produce one comparison for the probe set. Preserve individual evidence; do not collapse unlike failures into a single score. The reviewer records one of:

- `candidate_selected`: name the candidate and intended geometry outcome;
- `procedural_direct`: generation did not offer a cheaper authoritative path;
- `more_evidence_required`: the experiment is inconclusive;
- `no_selection`: close without a production handoff;
- `skipped`: generation was unnecessary.

The suggested outcome from tooling and the review decision are separate fields.

### 7. Hand off explicitly

A reviewed evidence pack may be referenced from `pipeline.generated_inputs` in the Asset Spec. That reference records evidence only. Starting normalization, repair, rebuild, or procedural work is a separate production action.

No command in this flow may write `pipeline.master_mesh`, change an audit status, or copy a candidate over a tracked working master.

## State model

Probe-set states are:

```text
draft -> ready -> waiting_external -> received -> evaluated -> reviewed -> closed
   |        |              |             |
   +--------+--------------+-------------+-> cancelled

ready -> skipped -> closed
```

These states are derived from the immutable plan and the delivery, evaluation, and decision records. They are not implemented by rewriting `probe-plan.json`. Plan state is limited to `draft`, `ready`, `skipped`, or `cancelled`; only a `ready` plan may accept deliveries.

Candidate states are independent: `expected`, `received`, `invalid`, `measured`, `evaluated`, or `withdrawn`. `measured` means automated metrics and diagnostics exist while identity criteria remain `not_assessed`; only review may advance it to `evaluated`. One missing provider must not fabricate a comparison; the probe may remain open or close as inconclusive.

## Minimal records

M5 should version four small JSON records rather than extending Asset Spec v0.1 with provider workflow state:

1. **Probe plan** — probe ID, asset/spec snapshot, question, providers, reference hashes, evaluation profile, and stop conditions.
2. **Delivery manifest** — provider-declared provenance, candidate ID, source URI or external job ID when available, file roles/hashes, settings, and delivery actor/time.
3. **Candidate evaluation** — input hash, derived artifacts, common metrics, diagnostic evidence, findings, and suggested outcome.
4. **Probe decision** — comparison status, selected candidate if any, explicit outcome, rationale, reviewer, and production handoff reference if approved.

Credentials, access tokens, cookies, and billing data are forbidden in all four records. Provider response data is untrusted and should be stored only when needed for provenance.

## M5A implementation

M5A implements the four contracts as JSON Schema Draft 2020-12 files:

- `schemas/probe-plan-v0.1.schema.json`;
- `schemas/probe-delivery-v0.1.schema.json`;
- `schemas/probe-evaluation-v0.1.schema.json`;
- `schemas/probe-decision-v0.1.schema.json`.

`tools/validate_probe.py` is the standard-library-only reference validator. It validates one record independently or several records as a set. Set validation checks shared probe identity, declared provider requests, delivery/evaluation lineage, provider-mode consistency, model hash references, decision references, and terminal records for every requested branch before a final selection.

From the `mex-orbit-art` repository root:

```powershell
python astrion-3d-pipeline/tools/validate_probe.py `
  <probe-plan.json> `
  <delivery.json> `
  <candidate-evaluation.json> `
  <decision.json>
```

The command returns 0 for valid records, 1 for contract errors, or 2 when a JSON file cannot be read. It does not require referenced paths to exist in M5A. Reading and hashing actual deliveries belongs to M5B.

Checked-in fixtures demonstrate a valid Meshy candidate plus an explicitly failed Tripo branch. An unavailable requested provider therefore cannot silently disappear before selection. Invalid fixtures cover unsafe paths, credentials in provider settings, contradictory evaluation states, and forbidden direct Master Mesh promotion.

## M5B intake implementation

`tools/intake_probe.py` implements local plan freezing and explicit delivery intake. It does not contact Meshy or Tripo.

First preview and freeze a `ready` plan. M5B requires the declared Asset Spec and references to exist and match their hashes:

```powershell
python astrion-3d-pipeline/tools/intake_probe.py init `
  --plan-source <ready-probe-plan.json> `
  --dry-run

python astrion-3d-pipeline/tools/intake_probe.py init `
  --plan-source <ready-probe-plan.json>
```

The second command copies the exact plan bytes to `work/generative-probes/<asset-id>/<probe-id>/probe-plan.json`. It refuses an existing run.

Then preview and receive explicit provider files:

```powershell
python astrion-3d-pipeline/tools/intake_probe.py receive `
  --plan astrion-3d-pipeline/work/generative-probes/<asset-id>/<probe-id>/probe-plan.json `
  --provider meshy `
  --candidate-id meshy-candidate-01 `
  --file model=<fresh-delivery.glb> `
  --delivered-by "operator name" `
  --dry-run
```

Repeat without `--dry-run` to copy the files and publish `delivery.json`. `--file` is repeatable and accepts `model`, `texture`, `preview`, `metadata`, or `other`. Provider, request ID, delivery mode, and generation mode come from the frozen plan rather than being re-entered.

The tool hashes every source before copying, verifies both source and copy afterward, rejects colliding filenames and existing candidate directories, and publishes atomically. It rejects credential-shaped keys in settings and refuses direct intake from the legacy `crudo/`, `pulido/`, and source-render trees. A future explicit migration flow may handle legacy candidates separately.

M5B is proven with the fresh `aci-01-test-probe-20260904-01` run. It froze one shared Asset Spec and the exact `geometria.png` generation-reference hash, then registered explicit Meshy and Tripo GLB deliveries with verified source/copy hashes. No legacy model was used as proof and no production asset was modified.

## M5C evaluation implementation

`tools/evaluate_probe.py` verifies the frozen plan, delivery manifest, Asset Spec, intake model, and their hashes before loading the active GLB scene with node transforms. It reuses the geometry metric engine and diagnostic renderer under the common camera and screen-size profile, but publishes a `measured` candidate record: identity stays `not_assessed`, the suggested outcome stays null, and Audit 1 remains unavailable.

Preview and measure one candidate:

```powershell
python astrion-3d-pipeline/tools/evaluate_probe.py `
  --plan astrion-3d-pipeline/work/generative-probes/<asset-id>/<probe-id>/probe-plan.json `
  --delivery astrion-3d-pipeline/work/generative-probes/<asset-id>/<probe-id>/intake/<provider>/<candidate-id>/delivery.json `
  --dry-run

python astrion-3d-pipeline/tools/evaluate_probe.py `
  --plan astrion-3d-pipeline/work/generative-probes/<asset-id>/<probe-id>/probe-plan.json `
  --delivery astrion-3d-pipeline/work/generative-probes/<asset-id>/<probe-id>/intake/<provider>/<candidate-id>/delivery.json
```

The full mode records common topology measurements and a gameplay-silhouette sheet. `--fast` skips expensive multi-view metrics. Diagnostics are written atomically under the candidate run directory and are never overwritten. An unreadable GLB produces an explicit `invalid` measurement rather than disappearing from the probe.

`tools/review_probe.py` then verifies the immutable measurement, delivery, model, and diagnostic hashes before applying an explicit review source. It publishes a separate `candidate-evaluation.json`; it never rewrites `candidate-measurement.json`. Every frozen identity criterion must be assessed as `pass`, `warning`, or `fail`, and the reviewer must state a suggested geometry outcome.

```powershell
python astrion-3d-pipeline/tools/review_probe.py `
  --measurement astrion-3d-pipeline/work/generative-probes/<asset-id>/<probe-id>/diagnostics/<provider>/<candidate-id>/candidate-measurement.json `
  --review-source <explicit-review.json> `
  --dry-run
```

Repeat without `--dry-run` to publish the evaluated record. A candidate-level suggestion is still not a probe decision or production handoff.

M5C is proven on both fresh `aci-01-test` candidates using the same `geometria.png` reference. The measured and explicitly reviewed records remain isolated in the probe run. Meshy suggests `rebuild_reference`; Tripo suggests `repair`. These candidate-level suggestions remain non-authoritative until M5D records a named human decision.

## M5D comparison and closeout implementation

`tools/close_probe.py` accepts an explicit closed decision plus every delivery and evaluated candidate in the frozen run. It revalidates the complete record set, verifies referenced plan/model/diagnostic/evaluation hashes, requires coverage for every received provider branch, and refuses an existing report directory. It then publishes `comparison.json` and `decision.json` atomically under `reports/generative-probes/<asset-id>/<probe-id>/`.

```powershell
python astrion-3d-pipeline/tools/close_probe.py `
  --plan <frozen-probe-plan.json> `
  --delivery <meshy-delivery.json> `
  --delivery <tripo-delivery.json> `
  --evaluation <meshy-candidate-evaluation.json> `
  --evaluation <tripo-candidate-evaluation.json> `
  --decision-source <reviewed-decision.json> `
  --dry-run
```

Repeat without `--dry-run` after inspecting the preview. The comparison preserves each candidate's distinct measurements and identity findings rather than collapsing them into an aggregate score. Closeout never creates a production handoff implicitly.

The proof run was closed by reviewer `E. Lopez` with `tripo-candidate-01` selected for `repair`. Its production handoff is `not_requested`: the candidate remains immutable probe evidence, no Master Mesh was promoted, and Audit 1 was not run.

## Run layout

The checked-in flow definition lives here. Executions are isolated by asset and probe ID:

```text
astrion-3d-pipeline/
  flows/generative-probes/README.md
  work/generative-probes/<asset-id>/<probe-id>/
    probe-plan.json
    requests/<provider>/
    intake/<provider>/<candidate-id>/
    derived/<provider>/<candidate-id>/
    diagnostics/<provider>/<candidate-id>/
    logs/
    run-manifest.json
  reports/generative-probes/<asset-id>/<probe-id>/
    comparison.json
    decision.json
```

`work/` is isolated execution state, not durable source authority. Heavy external artifacts require an explicit retention/backup location before a probe is closed. `reports/` contains small reviewed evidence records and must reference artifacts by hash rather than assuming a transient path is permanent.

## Safety invariants

- Never write to or overwrite `source/3d-models/crudo/`, `source/3d-models/pulido/`, tracked masters, or source render folders.
- Never infer provider or settings from a filename or directory.
- Never mutate an intake file; derived files have new paths and hashes.
- Never call an external service unless the run explicitly declares an adapter and the user authorizes that service interaction.
- Never store credentials in plans, logs, manifests, or reports.
- Never promote automatically, even when only one candidate succeeds.
- Never report Audit 1 or Audit 2 as passed from probe evidence.
- Never compare candidates prepared from different Asset Spec/reference snapshots without flagging the mismatch.
- Never hide missing provenance; use `unknown` and expose it to review.

## M5 implementation slices

1. **M5A — Contract (complete):** schemas, fixtures, and the no-write validator implement the four records and set relationships.
2. **M5B — Intake (complete):** one frozen real plan registered deliberate fresh Meshy and Tripo deliveries while the tool rejects unsafe paths, mutation, missing provider identity, and hash changes.
3. **M5C — Evaluation (complete):** the probe adapter produced transform-aware measurements, common diagnostic renders, and separate explicit reviews for both real candidates while keeping Audit 1 unavailable.
4. **M5D — Comparison (complete):** both fresh branches were compared and reviewer `E. Lopez` selected the Tripo candidate for `repair`; closeout explicitly records no production handoff.
5. **M5E — Optional automation:** only after manual intake works, add provider-specific adapters without changing the common records.

M5's required manual-flow exit criterion is complete: a fresh probe set was planned, received explicit deliveries from both providers, created comparable evidence, and closed with a reviewed decision without modifying any production asset. M5E remains an optional future optimization. Existing legacy candidates may later be imported only through a declared migration delivery; they are not the M5 proof case.
