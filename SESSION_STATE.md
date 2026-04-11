# SESSION_STATE

## IO-III Session State

**Project:** IO-III — Deterministic Local LLM Runtime Architecture

**Repository:** [CevenJKnowles/io-architecture](https://github.com/CevenJKnowles/io-architecture)

**Local Path:** `/home/cjk/Dev/IO-III/io-architecture`

---

## Phase Status

**Current Phase:** Phase 5 — Runtime Observability & Optimisation (complete) / Phase 6 — Memory Architecture (pending)

**Status:** Phase 5 complete (M5.0–M5.3 delivered; tagged v0.5.0). Phase 6 not yet started.

**Tag:** v0.5.0

**Branch:** phase-5-0

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

## Verification

Verification status:

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

## Current Repository State

**Branch:** main

**Tag:** v0.3.2

**Pull request:** Phase 3 Hardening merged. Phase 4 implementation active on `main`.

**Repository state:** Phase 4 complete. M4.0–M4.11 delivered. Taggable as v0.4.0.

---

## Runtime Guarantees

The runtime currently guarantees:

- deterministic routing
- bounded execution
- max audit passes = 1
- max revision passes = 1
- explicit capability invocation only
- no autonomous tool selection
- no recursive orchestration
- no dynamic routing
- no prompt or completion content in logs

Forbidden logging fields:

- prompt
- completion
- draft
- revision
- content

---

## Post-Phase 3 Gap Closure — 2026-04-01

Work performed against gaps identified during Phase 3 review.

---

### G1 — Capability bounds docstring corrected

File: `io_iii/core/capabilities.py`

The `CapabilityBounds` docstring stated that bounds were "NOT yet enforced by a dedicated capability runner." This was incorrect. Enforcement was already present in `_invoke_capability_once` (engine.py) as part of M3.15. Docstring updated to accurately describe enforcement points and error codes.

---

### G2 — Capability bounds test coverage completed

File: `tests/test_capability_invocation.py`

Input-too-large enforcement was tested. Timeout and output-too-large enforcement were not. Two tests added:

- `test_capability_enforces_timeout` — verifies `CAPABILITY_TIMEOUT` on a slow capability
- `test_capability_enforces_output_size` — verifies `CAPABILITY_OUTPUT_TOO_LARGE` on an oversized result

---

### G3 — ADR-003 promoted to active

File: `ADR/ADR-003-telemetry-logging-and-retention-policy.md`

Status promoted from `draft v0.1` to `active v1.0`. Implementation Notes updated from aspirational notes to a factual record of what was built (`metadata_logging.py`, `logging.yaml`, `content_safety.py`).

---

### G4 — `latency_ms` auto-capture in SessionState

File: `io_iii/core/engine.py`

`SessionState.latency_ms` was declared and validated but never populated by the engine. Both return paths in `engine.run()` (null route and ollama route) now compute and set `latency_ms` from `started_at_ms` before returning the final state. Test added:

- `test_engine_sets_latency_ms_on_returned_state`

---

### G5 — Provider health check (ADR-011)

Files:

- `ADR/ADR-011-provider-health-check-policy.md`
- `io_iii/providers/ollama_provider.py`
- `io_iii/cli.py`
- `io_iii/tests/test_provider_health_check.py`

New ADR written and indexed. Adds a pre-flight provider reachability check at the CLI boundary (between routing resolution and SessionState creation). Key properties:

- Lightweight `GET <host>/` check on Ollama root endpoint
- Raises `PROVIDER_UNAVAILABLE: ollama` on failure with metadata log entry
- No implicit cloud fallback (ADR-004 preserved)
- Skipped for null provider and via `--no-health-check` flag (offline/CI use)
- `check_reachable()` method added to `OllamaProvider`
- Three tests added covering reachable, connection error, and timeout cases

---

### G6 — ADR-011 added to index

File: `ADR/README.md`

ADR-011 added to the index. (ADR-010 was already present.)

---

### G7 — Provider config key mismatch corrected

File: `io_iii/providers/ollama_provider.py`

`OllamaProvider.from_config()` was reading `cfg.get("host")` but `providers.yaml` defines the key as `base_url`. The config value was silently ignored at runtime; the provider always fell back to the hardcoded default or `OLLAMA_HOST` env var. Fixed to read `base_url`, aligning code with the canonical config schema and ADR-011.

---

### Gap Closure Verification

Tests: **44 passing**

Invariant validator: **8/8 PASS**

---

## Next Phase

Phase 4 — Post-Capability Architecture Layer

Focus areas:

- bounded orchestration above the runtime kernel
- explicit task specifications or runbooks
- structured execution pipelines without agent behaviour
- preserving all Phase 3 invariants

Phase 4 must not introduce:

- autonomous behaviour
- recursive execution loops
- dynamic routing
- planner behaviour
- uncontrolled multi-step orchestration

---

## Session Reset Point

This document serves as the canonical session alignment file.

Future sessions should read this file first before performing any architectural work.

It should be treated as the authoritative handoff state between Phase 3 and Phase 4.

End of Phase 3.

---

## Phase 4 Progress — M4.10 Complete

**Status:** Active

**Phase:** 4 — Post-Capability Architecture Layer

**Current Milestone:** M4.10 complete — M4.11 next (implementation-safe)

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

### Verification Snapshot (M4.11)

- `pytest`: 353 passing
- invariant validator: passing

### Phase 4 Close State

Phase 4 is complete. All milestones M4.0–M4.11 delivered.
The frozen M4.7–M4.9 execution stack was not modified.
Replay/resume is structurally isolated above it.
Repository is in a taggable phase-close state (v0.4.0 candidate).

---

## Phase 5 Close State — v0.5.0

**Status:** Complete

**Phase:** 5 — Runtime Observability and Optimisation

All three Phase 5 milestones are implemented, tested, and committed.
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

---

## Post-Phase 5 Hardening — 2026-04-12

Architectural optimality audit and gap closure performed against the v0.5.0 baseline.
No new ADRs required. No invariants modified. No execution paths changed.

---

### H1 — Context Assembly unit test suite (ADR-010)

File: `tests/test_context_assembly_adr010.py`

ADR-010 (`context_assembly.py`, 221 lines) had zero direct unit tests. The module is
foundational — it owns prompt hash stability, section ordering, and safe-key filtering.
46 tests added covering: `_canonical_json`, `_compute_prompt_hash`, `_build_messages`,
`_build_system_prompt`, `_format_boundaries_section`, `_build_assembly_metadata`,
and `assemble_context` end-to-end.

Key assertions:

- same inputs → same `prompt_hash` across 5 iterations
- section ordering is deterministic (persona < boundaries < envelope)
- `_format_boundaries_section` excludes unsafe keys (prompt, completion, etc.)
- `assembly_metadata` passes `assert_no_forbidden_keys`

---

### H2 — Routing fallback test suite (ADR-002)

File: `tests/test_routing_adr002.py`

ADR-002 routing fallback (primary → secondary → null) was exercised by only one
determinism test. The critical failure paths were unexercised. 32 tests added covering:
primary selection, primary-disabled fallback, unsupported-provider fallback,
both-unavailable → null fallback, `_parse_target`, `_namespace_to_provider`,
`_is_provider_enabled`, input validation, and determinism over 10 iterations.

---

### H3 — Engine revision path and challenger fail-open tests

File: `tests/test_engine_revision_paths.py`

The audit→`needs_work`→revision path (engine.py lines 593–623) and the challenger
JSON-parse fail-open (engine.py lines 164–181) were untested. 18 tests added covering:

- `needs_work` verdict → `provider.generate()` called twice, `revised=True` in audit_meta
- `pass` verdict → generate called once, `revised=False`
- `audit=False` → challenger never called, `audit_meta` is None
- `_run_challenger` fail-open: invalid JSON → auto-pass dict returned
- `_run_challenger` fail-open: provider unavailable (null route) → auto-pass dict returned

---

### H4 — `_heuristic_input_tokens` precision rename

File: `io_iii/core/engine.py`

Variable `_heuristic_input_tokens` renamed to `_heuristic_char_count`. The estimator
(`estimate_chars`) returns a character count, not a token count. The old name implied
token-level precision that does not exist. Clarifying comment added at the call site.

---

### H5 — Engine helper extraction: `_do_challenger_pass` and `_do_revision`

File: `io_iii/core/engine.py`

The challenger audit block and revision inference block were extracted from `engine.run()`
into two named helper functions:

- `_do_challenger_pass(cfg, user_prompt, text, challenger_fn, trace, obs, rid, tsid, audit_passes)`
  — records trace step, calls `challenger_fn`, emits `CHALLENGER_AUDIT_COMPLETE`, returns `audit_result`
- `_do_revision(user_prompt, text, audit_result, provider, model, trace, obs, rid, tsid, revision_passes)`
  — constructs revision prompt, records trace step, calls `provider.generate`, emits `REVISION_COMPLETE`, returns revised text

Bound enforcement (`MAX_AUDIT_PASSES`, `MAX_REVISION_PASSES`) and `_phase` assignment
remain in `run()` so the failure handler retains accurate phase context.

---

### H6 — `pyproject.toml` tooling and pytest configuration

File: `pyproject.toml`

- Added `mypy>=1.8` and `ruff>=0.4` to `[project.optional-dependencies] dev`
- Added `[tool.ruff]` configuration: `line-length = 100`, `target-version = "py311"`, lint selects E/F/W/I
- Added `[tool.mypy]` configuration: `python_version = "3.11"`, `ignore_missing_imports = true`
- Set `testpaths = ["tests", "io_iii/tests"]` — both test directories now explicit
- Added `--tb=short --strict-markers` to pytest `addopts`

---

### Hardening Verification

Tests: **515 passing**

Invariant validator: **4/4 PASS**

Capability registry: **3 capabilities, all bounded**

---

## Roadmap Extension — 2026-04-12

A comparative analysis of IO-II planning conversations against the IO-III roadmap
was performed. Gaps, divergences, and missing phases were identified and resolved.
The following documents were updated.

### Analysis Findings

Key divergences between IO-II's projected roadmap and IO-III's actual plan:

- IO-II's "Phase 5: Structured Workflows" content landed in IO-III Phase 4 (runbooks);
  IO-III Phase 5 was an observability insertion with no IO-II equivalent
- IO-II's Phase 7 ("Agent Interaction Layer") was replaced by an open-source init layer;
  the agent framing was explicitly rejected in favour of governed dialogue
- IO-II's Phase 8 ("System Integration: API, UI") had no IO-III equivalent — now planned
- Work Mode / Steward Mode was a "frozen design decision" with no implementation home
- Task graph / conditional runbook branches were never formalised
- No interface plan beyond the terminal existed

### Documents Updated

**DOC-ARCH-003** — Master roadmap extended with Phase 6–9 entries:

- Phase 6 (Pending): memory architecture summary + M6.7 cross-phase dependency noted
- Phase 7 (Pending): init layer summary + M7.5 cross-phase dependency noted
- Phase 8 (Planned): Governed Dialogue Layer — M8.0–M8.6 defined; TUI option noted on M8.3
- Phase 9 (Planned): API & Integration Surface — M9.0–M9.5 defined; web UI at M9.5
- Non-goals list corrected: items now phased (persistent memory, steward mode, API)
  moved out of active non-goals

**DOC-ARCH-014** (Phase 6 Guide) — M6.7 added: governed SessionState snapshot export;
portable session artefact carrying workflow position and memory pack state;
prerequisite for Phase 8 M8.3 (`session continue`).

**DOC-ARCH-015** (Phase 7 Guide) — two additions:

- M7.3 extended: `chat_session.yaml` runbook template added to default pack templates
- M7.5 added: Work Mode / Steward Mode ADR — governance contract prerequisite for
  Phase 8 M8.1; `SessionMode` type, transition rules, steward threshold definition

**DOC-ARCH-002** (Structural Elevation Roadmap) — three corrections:

- Duplicate `updated:` frontmatter key removed
- Phase 4 status updated from `(Active)` to `(Complete)`
- Non-goals list corrected to match DOC-ARCH-003: phased items moved out

### Interface Plan

Three interface tiers documented in DOC-ARCH-003:

| Tier | Interface | Phase | Milestone |
| --- | --- | --- | --- |
| 1 | CLI | Phase 1 (always) | — |
| 2 | TUI (rich terminal) | Phase 8 | M8.3 extension |
| 3 | Web UI (self-hosted) | Phase 9 | M9.5 |

Constraint recorded: all interfaces must route through the governed session layer;
no execution bypass permitted from any surface.

### No Code Changes

This session made no code changes. All changes are documentation only.
Tests remain at 515 passing. Invariants remain at 4/4 PASS.
