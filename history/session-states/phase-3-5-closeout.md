# SESSION_STATE — Phase 3–5 Archive

Extracted from SESSION_STATE.md on 2026-04-12.
These phases are complete and superseded by the codebase.

---

## Phase 3 Goal

Establish the deterministic runtime kernel of IO-III while preserving all architectural invariants.

The runtime now provides:

- deterministic routing
- bounded execution
- explicit capability invocation
- content-safe telemetry
- audit traceability
- invariant-protected architecture
- deterministic prompt assembly through a single context boundary

---

## Phase 3 Milestones

### M3.1 — Capability architecture definition

Document architectural design for the capability system.

File: `docs/architecture/DOC-ARCH-005-io-iii-capability-layer-definition.md`

---

### M3.2 — Capability contracts

Introduce capability specification structures.

Core components introduced:

- CapabilitySpec
- CapabilityContext
- CapabilityResult
- CapabilityBounds

---

### M3.3 — Capability registry

Introduce deterministic registry system for capabilities.

Properties:

- deterministic ordering
- explicit registration
- no dynamic loading

---

### M3.4 — Capability invocation path

Integrate capability execution path into the IO-III engine.

Execution pipeline:

```text
CLI → routing → engine → capability registry → capability execution → telemetry + trace
```

---

### M3.5 — Execution bounds enforcement

Introduce strict runtime bounds:

- max calls
- max input size
- max output size
- timeout

---

### M3.6 — Content safety guardrails

Ensure capability output cannot leak sensitive content into logs.

Only structured metadata may be logged.

---

### M3.7 — Execution trace integration

Capability execution is integrated into the IO-III execution trace system.

Trace stage: `capability_execution`

---

### M3.8 — Metadata logging integration

Capability executions produce content-safe metadata records.

Log location: `architecture/runtime/logs/metadata.jsonl`

---

### M3.9 — CLI capability execution

Introduce CLI command: `python -m io_iii capability <capability_id> <payload>`

---

### M3.10 — Capability registry exposure

CLI capability listing introduced: `python -m io_iii capabilities`

---

### M3.11 — Capability JSON inspection

Machine-readable output added: `python -m io_iii capabilities --json`

---

### M3.12 — Capability telemetry integration

Capability executions produce structured metadata:

- capability_id
- version
- duration
- success/failure

---

### M3.13 — Capability trace instrumentation

Execution trace records capability execution stage.

---

### M3.14 — Payload validation

Capability payload validation added.

---

### M3.15 — Capability bounds enforcement

Runtime guardrails ensure deterministic bounded execution.

---

### M3.16 — CLI capability command

Stable CLI execution command finalised.

---

### M3.17 — Demonstration capabilities

Introduce deterministic example capabilities:

- cap.echo_json
- cap.json_pretty
- cap.validate_json_schema

Purpose:

- demonstrate capability architecture
- provide deterministic runtime tools
- improve repository clarity

---

### M3.18 — Capability registry JSON inspection

Expose registry through deterministic CLI inspection.

Commands:

- `python -m io_iii capabilities`
- `python -m io_iii capabilities --json`

Purpose:

- allow tooling and automation
- enable runtime introspection
- improve system observability

---

### M3.19 — Session state enforcement

Wire `validate_session_state()` into the CLI execution path.

Purpose:

- fail fast on invalid runtime state
- strengthen runtime integrity
- align implementation with documented state model

---

### M3.20 — Invariant test integration

Integrate the invariant validator into pytest.

Purpose:

- make `pytest` a single-command architecture verification pass
- reduce drift between runtime and governance layer

---

### M3.21 — Routing determinism test

Add explicit routing determinism coverage.

Purpose:

- verify identical inputs produce identical route selection
- strengthen deterministic execution guarantees

---

### M3.22 — ADR-010 seam closure

Route challenger and revision prompt construction through the same context assembly boundary as executor prompts.

Execution path: `persona_contract → context_assembly → provider execution`

Purpose:

- remove inline prompt construction seam
- enforce structural consistency across runtime prompt paths

---

### M3.23 — Runtime kernel hardening

Decompose `engine.run()` into named helper paths and align state replacement to stdlib `dataclasses.replace()`.

Purpose:

- prevent kernel monolith growth
- prepare cleanly for Phase 4
- improve maintainability without changing behaviour

---

### M3.24 — Phase 3 polish and readiness docs

Add the remaining project-readiness artefacts:

- CONTRIBUTING.md
- DOC-ARCH-012 Phase 4 guide
- doc guardrail tests
- fail-open challenger policy note

Purpose:

- improve public professionalism
- reduce process drift
- create a clean entry point for Phase 4

---

## Phase 3 Result

IO-III now includes a complete deterministic runtime kernel.

The runtime can now:

- resolve deterministic routes
- execute bounded provider calls
- execute bounded capabilities
- assemble prompts through a single context boundary
- trace execution stages
- log content-safe metadata
- enforce runtime invariants through tests and validators

Execution architecture:

```text
CLI → routing → engine → context assembly / capability registry
  → bounded execution → execution trace → content-safe metadata logging
```

---

## Phase 3 Verification

- pytest passing
- invariant validator passing
- capability registry functioning
- metadata logging content-safe

Standard verification commands:

```bash
python -m pytest
python architecture/runtime/scripts/validate_invariants.py
python -m io_iii capabilities --json
```

All invariants PASS.

---

## Phase 3 Repository State

**Branch:** main | **Tag:** v0.3.2

---

## Post-Phase 3 Gap Closure — 2026-04-01

### G1 — Capability bounds docstring corrected

File: `io_iii/core/capabilities.py`

The `CapabilityBounds` docstring stated that bounds were "NOT yet enforced by a dedicated capability runner." This was incorrect. Enforcement was already present in `_invoke_capability_once` (engine.py) as part of M3.15. Docstring updated to accurately describe enforcement points and error codes.

---

### G2 — Capability bounds test coverage completed

File: `tests/test_capability_invocation.py`

Two tests added:

- `test_capability_enforces_timeout` — verifies `CAPABILITY_TIMEOUT` on a slow capability
- `test_capability_enforces_output_size` — verifies `CAPABILITY_OUTPUT_TOO_LARGE` on an oversized result

---

### G3 — ADR-003 promoted to active

File: `ADR/ADR-003-telemetry-logging-and-retention-policy.md`

Status promoted from `draft v0.1` to `active v1.0`.

---

### G4 — `latency_ms` auto-capture in SessionState

File: `io_iii/core/engine.py`

Both return paths in `engine.run()` now compute and set `latency_ms`.

---

### G5 — Provider health check (ADR-011)

New ADR written and indexed. Pre-flight provider reachability check at the CLI boundary. Lightweight `GET <host>/` check; `PROVIDER_UNAVAILABLE: ollama` on failure; skipped for null provider and `--no-health-check`.

---

### G6 — ADR-011 added to index

File: `ADR/README.md`

---

### G7 — Provider config key mismatch corrected

File: `io_iii/providers/ollama_provider.py`

Fixed to read `base_url` (aligning with `providers.yaml`); was silently reading `host`.

---

### Gap Closure Verification

Tests: **44 passing** | Invariant validator: **8/8 PASS**

---

## Phase 4 Progress — M4.0–M4.11 Complete

**Phase:** 4 — Post-Capability Architecture Layer

### Completed

- M4.0 governance freeze — ADR-012, `DOC-ARCH-012`, canonical milestone definition
- M4.1 `TaskSpec` introduced as a serialisable declarative execution contract
- M4.2 single-run bounded `Orchestrator` implemented and tested
- M4.3 `ExecutionTrace` lifecycle contracts added with explicit transition guards
- M4.4 `SessionState` promoted to v1 with explicit `task_spec_id` linkage
- M4.5 Engine Observability Groundwork — `EngineEventKind` lifecycle events, `EngineObservabilityLog`, engine events in `ExecutionResult.meta`
- M4.6 Deterministic Failure Semantics — `RuntimeFailureKind`, `RuntimeFailure`, ADR-013
- M4.7 Bounded Runbook Layer — `Runbook`, `RunbookResult`, `RunbookStepOutcome`, ADR-014
- M4.8 Runbook Traceability and Metadata Correlation — `RunbookLifecycleEvent`, `RunbookMetadataProjection`, ADR-015
- M4.9 CLI Runbook Execution Surface — `cmd_runbook()`, `runbook` subcommand, ADR-016
- M4.10 Replay/Resume Boundary Definition — upper layer freeze, ADR-017
- M4.10 Run Identity Contract — `run_id` UUIDv4, lineage via `source_run_id`, ADR-018
- M4.10 Checkpoint Persistence Contract — JSON at `<root>/<run_id>.json`, atomic writes, five integrity checks, ADR-019
- M4.10 Replay/Resume Execution Contract — replay from step 0, resume from first incomplete step, ADR-020
- M4.11 Replay/Resume Layer Implementation — `replay_resume.py`, CLI `replay`/`resume` subcommands, ADR-019/020 enforcement, 28 contract tests

### Phase 4 Verification (M4.11)

- `pytest`: 353 passing
- invariant validator: passing

### Phase 4 Close State

Phase 4 is complete. All milestones M4.0–M4.11 delivered.
The frozen M4.7–M4.9 execution stack was not modified.
Replay/resume is structurally isolated above it.
Repository tagged v0.4.0.

---

## Phase 5 Close State — v0.5.0

**Phase:** 5 — Runtime Observability and Optimisation

All three Phase 5 milestones implemented, tested, and committed.
Test count at phase close: 419 passing.
Test count after post-phase hardening pass: 515 passing.

### M5 Completed

- M5.0 Governance freeze and ADR authorship — ADR-021 accepted and indexed;
  Phase 5 milestone suite formally defined; freeze boundary established above M4.11
- M5.1 Token Pre-flight Estimator — `io_iii/core/preflight.py`; heuristic character-count
  estimator; `CONTEXT_LIMIT_EXCEEDED` failure code; configurable `runtime.context_limit_chars`;
  prerequisite for Phase 6 M6.4 unblocked
- M5.2 Execution Telemetry Metrics — `io_iii/core/telemetry.py` (`ExecutionMetrics`);
  `OllamaProvider.generate_with_metrics()` surfaces `prompt_eval_count`/`eval_count`;
  `ExecutionResult.meta["telemetry"]` and content-safe projection to `metadata.jsonl`
- M5.3 Constellation Integrity Guard — `io_iii/core/constellation.py`; config-time
  role-model collapse detection; required role binding validation; call chain bounds check;
  `CONSTELLATION_DRIFT` failure code; `--no-constellation-check` bypass with mandatory stderr warning

### Phase 5 Contracts

- ADR-021 — Runtime Observability and Optimisation Contract
- DOC-ARCH-013 — Phase 5 Guide

### Execution Stack Freeze Boundary

All Phase 1–4 components remain frozen.
Phase 5 observability capabilities operate alongside the execution stack, not inside it.
Phase 6 (Memory Architecture) is unblocked — M5.1 prerequisite satisfied.
