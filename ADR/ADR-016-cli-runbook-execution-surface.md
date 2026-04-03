---
id: ADR-016
title: CLI Runbook Execution Surface
type: adr
status: accepted
version: v1.0
canonical: true
scope: io-iii-phase-4
audience:
  - developer
  - maintainer
created: "2026-04-03"
updated: "2026-04-03"
tags:
  - io-iii
  - adr
  - phase-4
  - runbook
  - cli
roles_focus:
  - executor
  - challenger
provenance: io-iii-runtime-development
milestone: M4.9
subordinate_to: ADR-015
---

# ADR-016 — CLI Runbook Execution Surface

## Status

Accepted

## Subordination

This ADR subordinates itself entirely to **ADR-015 — Runbook Traceability and Metadata
Correlation**, **ADR-014 — Bounded Runbook Layer Contract**, and, through them, to
**ADR-012 — Bounded Orchestration Layer Contract**.

Every constraint in ADR-015, ADR-014, and ADR-012 applies to this surface without
exception. The frozen-kernel doctrine applies: this ADR defines a layer above the
existing M4.7 + M4.8 execution layer, not inside it.

---

## Context

M4.7 (ADR-014) introduced the bounded runbook runner. M4.8 (ADR-015) added a
deterministic observability layer above it. Both are proven through their respective
test suites.

Neither milestone exposed runbook execution through the CLI. As a result, runbooks
can only be invoked programmatically. For external tooling and automation, a stable
CLI surface is required that delegates directly into the existing bounded execution
contract without adding orchestration power.

---

## Milestone Scope

M4.9 is a **CLI exposure milestone only**.

Its sole purpose is to expose the already-bounded runbook execution contract through
a deterministic CLI surface.

M4.9 **must not**:

- increase orchestration power
- add replay or resume semantics
- add persistence
- add partial execution flags (`--from-step`, `--to-step`)
- add workflow builders
- add YAML input
- add inline JSON runbook definitions
- add interactive prompts
- widen `TaskSpec`
- widen `Runbook`
- widen routing semantics
- widen engine semantics
- create a second execution path
- create CLI-specific failure taxonomies
- bypass the existing runbook execution boundary

---

## Decision

IO-III will expose runbook execution through the CLI as a thin veneer above the
existing M4.7 + M4.8 bounded execution path.

The CLI surface is implemented entirely in `io_iii/cli.py` as a new `runbook`
subcommand. It does not alter the semantic behaviour of M4.7, M4.8, or any lower
runtime contract.

---

## 1. Command Identity

Exactly two command forms are defined. No aliases. No alternate syntax. No additional
flags beyond `--audit`.

```
python -m io_iii runbook <json-file>
python -m io_iii runbook <json-file> --audit
```

`<json-file>` is a path to a JSON file that conforms to the existing `Runbook`
serialisation boundary produced by `Runbook.to_dict()`.

`--audit` passes the audit flag through to the existing runbook execution path. It
adds no CLI-specific audit semantics.

---

## 2. Input Boundary

**JSON file only.** The CLI accepts a single file path. The file must be a JSON object
conforming to the `Runbook` serialisation schema.

Mandatory reuse:

- existing runbook deserialisation contract: `Runbook.from_dict()`
- existing `TaskSpec.from_dict()` path (called internally by `Runbook.from_dict()`)

Explicitly forbidden input forms:

- YAML files
- inline JSON strings passed as arguments
- flag-built step lists
- embedded DSLs
- interactive input collection
- stdin runbook definitions

---

## 3. Validation Order

Validation must occur in this exact order. This ordering is contractual.

1. **File exists and is readable** — the path must resolve to an existing, readable file.
2. **Valid JSON** — the file contents must parse as a JSON object.
3. **Valid runbook schema** — `Runbook.from_dict()` must succeed on the parsed object.
4. **Execute** — delegate to the existing runbook execution path.
5. **Emit stable structural result** — print the result as a JSON object.

Failure at any validation step terminates processing immediately. Steps after the
failing step are not reached.

---

## 4. Execution Path

The CLI is a **thin veneer only**. It must delegate into the existing bounded runbook
execution path via `runbook_runner.run()`.

It must not:

- call `engine.run()` directly
- construct routes directly
- own orchestration semantics
- duplicate the execution path
- add a second runbook execution path

The full execution chain remains:

```
CLI (validation + config/deps assembly)
→ runbook_runner.run()
→ orchestrator.run() per step
→ engine.run()
→ ...
```

---

## 5. Audit Contract

`--audit` is passthrough only. It threads the audit flag into `runbook_runner.run()`
without modification. The CLI adds no audit semantics of its own.

---

## 6. Output Contract

Output is structural and JSON-safe. The CLI prints a single JSON object to stdout.

**Success output** (all steps complete without failure):

```json
{
  "status": "ok",
  "runbook_id": "<runbook_id>",
  "steps_completed": <int>,
  "terminated_early": false,
  "failed_step_index": null,
  "metadata_projection": {
    "runbook_id": "<runbook_id>",
    "event_count": <int>
  }
}
```

**Runbook failure output** (a step failed; `terminated_early=True`):

```json
{
  "status": "error",
  "runbook_id": "<runbook_id>",
  "steps_completed": <int>,
  "terminated_early": true,
  "failed_step_index": <int>,
  "failure_kind": "<kind>",
  "failure_code": "<code>",
  "metadata_projection": {
    "runbook_id": "<runbook_id>",
    "event_count": <int>
  }
}
```

**Pre-execution failure output** (file/JSON/schema validation failed):

```json
{
  "status": "error",
  "error_code": "<RUNBOOK_FILE_NOT_FOUND | RUNBOOK_INVALID_JSON | RUNBOOK_SCHEMA_ERROR>"
}
```

Requirements:

- output is always a single JSON object
- no colour formatting
- no progress bars
- no streaming UX
- no prose-first summaries
- no mixed output ambiguity

The exit code is `0` on success and `1` on any failure.

---

## 7. Failure Contract

ADR-013 failure semantics are reused **exactly as-is**. No CLI-specific failure
taxonomy is introduced.

The CLI may surface only the following fields from the `RunbookResult`:

- `failure_kind` — sourced from `RunbookStepOutcome.failure.kind.value` (ADR-013 envelope)
- `failure_code` — sourced from `RunbookStepOutcome.failure.code` (ADR-013 envelope)
- `failed_step_index` — sourced from `RunbookResult.failed_step_index`
- `terminated_early` — sourced from `RunbookResult.terminated_early`

Pre-execution validation failures use stable CLI-layer error codes:

- `RUNBOOK_FILE_NOT_FOUND` — file does not exist or is not a file
- `RUNBOOK_INVALID_JSON` — file contents are not parseable as JSON
- `RUNBOOK_SCHEMA_ERROR` — `Runbook.from_dict()` rejected the parsed object

These codes are not ADR-013 failure kinds. They represent input validation failures
that occur before the runbook execution path is entered.

The CLI does not introduce:

- retry hints
- alternate CLI error taxonomies
- wrapper exception types
- failure-specific exit codes beyond 0/1

---

## 8. Metadata Contract

The M4.8 `RunbookMetadataProjection` **may** be surfaced in CLI output when present.
The CLI surfaces a structural summary only (`runbook_id`, `event_count`). It does not
surface individual event details.

The CLI must not:

- persist the metadata projection
- export trace bundles
- write sidecar files
- aggregate across runs
- introduce replay checkpoints

---

## 9. Explicit Non-Goals

The following are explicitly forbidden from M4.9:

- YAML runbook input
- inline runbook definitions (JSON string arguments)
- interactive runbook building
- `--from-step` / `--to-step` partial execution
- replay
- resume
- persistence of any kind
- trace export
- nested runbooks
- directory execution (run all JSON files in a directory)
- batch execution (run multiple JSON files per invocation)
- workflow generation
- branch/condition CLI syntax
- health check flags (not in the frozen command surface)

---

## 10. Relationship to M4.10 Replay/Resume Boundary

M4.10 (if implemented) may introduce replay or resume semantics above the M4.9
surface. M4.9 does not prepare for this: it introduces no checkpoint state, no
run identifiers beyond `runbook_id`, and no persistence that could be consumed by
a replay layer.

M4.9 is the final phase of the bounded CLI execution surface. Any M4.10 replay or
resume capability must be introduced as a new layer above M4.9, not as an extension
of the M4.9 command surface.

---

## 11. Verification Expectations

The following must be provable through the M4.9 test suite:

1. CLI command registration — `runbook` subcommand is registered and dispatched.
2. Valid JSON runbook success path — `status=ok`, correct field values surfaced.
3. Invalid JSON hard failure — `RUNBOOK_INVALID_JSON` error code, exit 1.
4. Missing file hard failure — `RUNBOOK_FILE_NOT_FOUND` error code, exit 1.
5. Invalid runbook schema hard failure — `RUNBOOK_SCHEMA_ERROR` error code, exit 1.
6. Audit passthrough correctness — `--audit` flag threads to runner without addition.
7. Structural output correctness — output is valid JSON, all required fields present.
8. Failure propagation correctness — `failure_kind`, `failure_code`, `failed_step_index`, `terminated_early` from ADR-013 envelope.
9. Metadata projection surfaced when available — `metadata_projection` in output.
10. No regression — existing CLI command surfaces (capabilities, config, route, capability, about) unaffected.

---

## Scope Boundary

This ADR covers:

- the frozen CLI command identity and syntax
- the frozen input boundary (JSON file only)
- the frozen validation order
- the output contract (success, failure, pre-execution failure)
- the audit passthrough semantics
- the ADR-013 failure reuse contract
- the M4.8 metadata projection surfacing contract
- the explicit non-goals
- the M4.10 replay/resume boundary relationship
- focused M4.9 CLI test strategy

This ADR does **not** cover:

- YAML input (non-goal)
- inline runbook definitions (non-goal)
- replay or resume (M4.10 boundary)
- persistence of any kind
- batch or directory execution
- health check flags
- trace export

---

## Implementation Order

1. Add `cmd_runbook()` to `io_iii/cli.py`.
2. Register the `runbook` subparser in `main()` within `io_iii/cli.py`.
3. Write focused M4.9 contract tests in `tests/test_runbook_m49.py`.
4. Create `ADR/ADR-016` (this document).
5. Update `docs/architecture/DOC-ARCH-012-phase-4-guide.md` — add M4.9 milestone.
6. Update `SESSION_STATE.md` — reflect M4.9 complete.
7. Update `ADR/README.md` — add ADR-016 entry.

---

## Alternatives Considered

### 1. Accept inline JSON string as input

Rejected. Inline JSON strings require shell escaping, are error-prone for multi-step
runbooks, and blur the boundary between definition and execution. The JSON file form
is unambiguous, machine-friendly, and consistent with the `Runbook.to_dict()` /
`Runbook.from_dict()` serialisation contract.

### 2. Accept YAML runbook files

Rejected. The existing serialisation contract is JSON-based (`to_dict()` / `from_dict()`).
Introducing YAML would require a second deserialisation path and a new schema boundary,
contradicting the thin-veneer constraint.

### 3. Add --from-step / --to-step flags for partial execution

Rejected. Partial execution is a resume/replay semantic deferred to M4.10. M4.9
exposes the full bounded execution contract only.

### 4. Stream per-step output during execution

Rejected. Streaming UX is explicitly forbidden by the output contract. Output must
be a single stable JSON object emitted after execution completes.

### 5. Write metadata.jsonl sidecar file

Rejected. Persistence is not in scope for M4.9. The CLI surfaces the M4.8 projection
summary in the output object only; it does not write files.

---

## Relationship to Other ADRs

- **ADR-009** — per-step bounded execution bounds. Unaffected; enforced by orchestrator/engine.
- **ADR-012** — orchestration layer contract. CLI is above this layer; does not alter it.
- **ADR-013** — failure semantics. `failure_kind` and `failure_code` reused exactly.
- **ADR-014** — bounded runbook layer. CLI delegates into this layer unchanged.
- **ADR-015** — runbook traceability. CLI surfaces projection summary from `RunbookResult.metadata`.
- **ADR-016** (this document) — CLI runbook execution surface.

---

## Consequences

### Positive

- Runbooks are now executable from the CLI without modifying Python source.
- The execution contract (M4.7 + M4.8) is unchanged; only exposure is added.
- ADR-013 failure fields are surfaced at the CLI boundary for external tooling.
- M4.8 metadata projection is available in CLI output for structural inspection.
- No new orchestration power; frozen-kernel doctrine preserved.

### Negative

- `io_iii/cli.py` grows one additional command function and subparser registration.
- External callers that rely on `python -m io_iii` must now be aware of `runbook`.

### Neutral

- M4.10 replay/resume boundary is unaffected; M4.9 makes no replay-enabling changes.
- Health checks are not exposed for the `runbook` command; provider failures propagate
  through the existing ADR-013 failure path.

---

## Decision Summary

IO-III will adopt a thin CLI veneer over the existing M4.7 + M4.8 bounded runbook
execution contract in Phase 4 M4.9.

This surface will:

- accept exactly one JSON file path as input
- validate in the frozen order (file → JSON → schema → execute → emit)
- delegate entirely into `runbook_runner.run()` without adding orchestration
- thread `--audit` through without modification
- emit a single stable JSON object (success or failure)
- surface ADR-013 `failure_kind` and `failure_code` on step failure
- surface M4.8 `RunbookMetadataProjection` summary when present
- add no orchestration power, no persistence, no replay/resume semantics
- preserve all frozen-kernel invariants

The CLI is the final exposure layer. It must not become an execution layer.