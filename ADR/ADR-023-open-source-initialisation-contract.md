---
id: ADR-023
title: Open-Source Initialisation Contract
type: adr
status: accepted
version: v1.0
canonical: true
scope: io-iii-phase-7
audience:
  - developer
  - maintainer
created: "2026-04-12"
updated: "2026-04-12"
tags:
  - io-iii
  - adr
  - phase-7
  - portability
  - open-source
  - initialisation
roles_focus:
  - executor
  - governance
provenance: io-iii-runtime-development
milestone: M7.0
---

# ADR-023 — Open-Source Initialisation Contract

## Status

Accepted

---

## Context

Phase 6 is complete. All seven Phase 6 milestones (M6.1–M6.7) are implemented, tested,
and committed. The repository is tagged `v0.6.0`.

The config separation audit conducted at the start of Phase 7 confirms:

- All model names live exclusively in `architecture/runtime/config/routing_table.yaml`
- The storage root is declared in `architecture/runtime/config/memory_packs.yaml` as a
  configurable path (no hardcoded repository path)
- No model names, local paths, or persona strings are embedded in engine code, ADRs,
  or invariant contracts
- No `persona.yaml` exists — this is a Phase 7 deliverable, not a pre-existing gap

The config separation prerequisite stated in DOC-ARCH-015 is satisfied. Phase 7 may
begin.

Phase 7 makes the IO-III runtime distributable and self-initialising for external users.
The goal is that any user can clone this repository, change a small, well-documented set
of configuration values — their Ollama models, persona definition, and memory pack
content — and have a functioning, governance-compliant IO-III runtime without touching
structural code.

This phase does not extend the runtime. It formalises the surface between what is
structural (owned by the architecture) and what is configurable (owned by the user), and
provides the tooling, templates, and validation for a new user to cross that surface
confidently.

---

## Decision

IO-III introduces an open-source initialisation layer under Phase 7. All five milestones
(M7.1–M7.5) are governed by this ADR. The frozen Phase 1–6 execution stack is not
modified by this ADR or any milestone it governs.

The initialisation layer is:

- **minimal** — a new user must change as few values as possible to reach a working state
- **explicit** — the configuration surface is declared, documented, and bounded
- **non-invasive** — the init process configures only user-owned config files; it does
  not modify structural artefacts
- **validatable** — a portability validation pass confirms correct initialisation before
  first execution

---

## 1. Governance Freeze Boundary

### 1.1 Frozen surface

The following components are frozen for the duration of Phase 7. No Phase 7 milestone
may modify them:

- `io_iii/routing.py` — routing resolution logic
- `io_iii/core/engine.py` — execution engine
- `io_iii/core/runbook.py` — runbook definition
- `io_iii/core/runbook_runner.py` — bounded runner
- `io_iii/core/replay_resume.py` — replay/resume execution layer
- `io_iii/core/preflight.py` — token pre-flight estimator
- `io_iii/core/telemetry.py` — execution telemetry
- `io_iii/core/constellation.py` — constellation integrity guard
- `io_iii/memory/store.py` — memory store
- `io_iii/memory/packs.py` — memory pack system
- `io_iii/memory/policy.py` — memory retrieval policy
- `io_iii/memory/write.py` — memory write contract
- `io_iii/core/context_assembly.py` — context assembly layer
- `io_iii/core/snapshot.py` — session snapshot export
- All ADR-002, ADR-007, ADR-008, ADR-009, ADR-010, ADR-013, ADR-014, ADR-016,
  ADR-017, ADR-020, ADR-021, ADR-022 contracts

### 1.2 Permissible surfaces

Phase 7 milestones may add to or create:

- `architecture/runtime/config/` — template files and annotated config examples for the
  user-configurable surface; existing config files are not modified by the init process
- `io_iii/cli.py` — an `init` subcommand (M7.2) and a `validate` subcommand (M7.4);
  no modification to existing subcommands
- `io_iii/core/portability.py` — new module for the portability validation pass (M7.4)
- `docs/` — user-facing initialisation documentation and templates
- `SESSION_STATE.md` — phase progress tracking only

---

## 2. Config / Structural Separation Contract

The following table defines the boundary between what a new user must configure and what
is owned by the architecture. This boundary is the foundation of the init surface.

| Configurable (user-owned) | Structural (architecture-owned) |
|---|---|
| Ollama model names | Routing logic |
| Persona definition | Engine invariants |
| Memory pack content | ADR contracts |
| Storage root path | Execution bounds |
| Sensitivity classifications | Failure codes |
| Retrieval policy allowlists | Capability registry |

The init process (M7.2) and portability validation (M7.4) operate exclusively on the
left column. No Phase 7 milestone may alter the right column.

---

## 3. Initialisation Contract (M7.1)

### 3.1 Required configuration surface

A new user must provide or confirm the following config files to reach a working state:

| File | Purpose | Required values |
|---|---|---|
| `architecture/runtime/config/providers.yaml` | Ollama base URL and provider enablement | `providers.ollama.base_url` |
| `architecture/runtime/config/routing_table.yaml` | Model name bindings per role | `models.<role>.name` for each active role |
| `architecture/runtime/config/memory_packs.yaml` | Storage root and pack definitions | `storage_root` |
| `architecture/runtime/config/persona.yaml` | Persona identity and mode definitions | `persona.name`, `persona.modes` |

### 3.2 Minimal working state

A runtime is in a minimal working state when:

- `providers.yaml` declares at least one enabled provider with a non-empty `base_url`
- `routing_table.yaml` declares at least one role with a non-empty model `name`
- `memory_packs.yaml` declares a `storage_root` that is a non-empty string
- `persona.yaml` exists and declares a non-empty `persona.name`

No other configuration is required for first execution.

### 3.3 Optional configuration surface

The following files are optional at initialisation. Their absence is safe — the runtime
skips the relevant feature:

- `architecture/runtime/config/memory_retrieval_policy.yaml` — absence means memory
  injection is skipped for all routes (ADR-022 §4.4)
- `architecture/runtime/config/runtime.yaml` — absence means default context limit
  applies (`32000` chars)

---

## 4. Init Command or Setup Guide (M7.2)

### 4.1 Init surface

The init surface covers the transition from a freshly cloned repository to a correctly
configured working state:

```text
clone → configure → validate → first run
```

### 4.2 Init command properties

The `init` subcommand (or equivalent documented setup procedure) must:

- walk the user through each required config file in the M7.1 surface
- not modify any structural artefact (ADRs, engine code, invariant contracts)
- produce a human-readable summary of what was configured and what, if anything, remains
- invoke the portability validation pass (M7.4) on completion

### 4.3 CLI surface

```text
python -m io_iii init
```

If a full CLI `init` command is not introduced, a step-by-step setup guide must be
provided at `docs/SETUP.md` covering the same surface with equivalent clarity.

---

## 5. Default Pack and Persona Templates (M7.3)

### 5.1 Template purpose

Templates are instructional — they demonstrate the config format without encoding the
author's personal configuration. They are the starting point a new user copies and edits.

### 5.2 Required templates

| Template | Path | Purpose |
|---|---|---|
| Persona definition | `architecture/runtime/config/persona.yaml` | Default persona demonstrating the format |
| Starter memory pack | already exists: `pack.default.starter` in `memory_packs.yaml` | Demonstrates pack config format |
| Annotated providers | already exists: `providers.yaml` | Already sufficiently annotated |
| Annotated routing table | already exists: `routing_table.yaml` | Model names are the user-owned surface |
| Chat session runbook | `architecture/runtime/config/templates/chat_session.yaml` | Demonstrates a 3-step bounded session |

### 5.3 Chat session template

The `chat_session.yaml` runbook template demonstrates a 3-step bounded session using the
`intent → execute → summarise` pattern. It must be:

- runnable against any correctly initialised runtime
- free of author-specific model names, paths, or persona content
- annotated with inline comments explaining each field

### 5.4 Persona template

`persona.yaml` must declare:

- `persona.name` — a placeholder name (e.g. `"io-user"`)
- `persona.modes` — at least one mode definition demonstrating the schema
- inline comments explaining each field

---

## 6. Portability Validation (M7.4)

### 6.1 Purpose

The portability validation pass confirms the runtime is correctly initialised before
first execution. It is the machine-verifiable counterpart to the M7.1 init contract.

### 6.2 Validation checks

| Check | Condition |
|---|---|
| Required config files present | `providers.yaml`, `routing_table.yaml`, `memory_packs.yaml`, `persona.yaml` exist and are parseable YAML |
| Provider declared | `providers.ollama.base_url` is non-empty |
| Model name declared | At least one role in `routing_table.yaml` has a non-empty model `name` |
| Persona present | `persona.yaml` exists and `persona.name` is non-empty |
| Storage root declared | `memory_packs.yaml` declares a non-empty `storage_root` |
| Storage root writable | The declared `storage_root` path exists and is writable |
| Constellation guard passes | M5.3 constellation integrity check passes against the declared models |

### 6.3 Validation trigger

Validation runs:

- when invoked explicitly via `python -m io_iii validate`
- automatically on the first `run` invocation if no prior execution has been recorded

### 6.4 Failure contract

A validation failure produces a `RuntimeFailure` under ADR-013:

| Field | Value |
|---|---|
| `kind` | `contract_violation` |
| `code` | `PORTABILITY_CHECK_FAILED` |
| `retryable` | `False` |
| `summary` | which check failed and why — no config values included |

### 6.5 New failure code

| Code | Condition |
|---|---|
| `PORTABILITY_CHECK_FAILED` | One or more portability validation checks failed |

This code extends the ADR-013 failure taxonomy. It is `retryable = False`. The failure
summary identifies the failed check by name — no model name, path, or persona content
appears in the summary.

---

## 7. Work Mode / Steward Mode ADR (M7.5)

### 7.1 Purpose

M7.5 authors the governance ADR for the two operating modes introduced in Phase 8
(`work` and `steward`). It is a Phase 7 deliverable because no Phase 8 implementation
code may be written until the governance contract exists.

### 7.2 ADR number

The Work Mode / Steward Mode ADR will be **ADR-024**.

### 7.3 Contract preview

The following are pre-established constraints that ADR-024 must formalise:

- `SessionMode` is a two-value type: `work` and `steward`
- Mode is an explicit field on `SessionState` — not inferred from context
- Mode transitions are user-initiated only — no autonomous mode switching
- Steward thresholds are declared in config, not hardcoded
- A steward threshold pause surfaces a content-safe state summary and waits for explicit
  user action (`approve`, `redirect`, or `close`)
- No execution proceeds past a steward threshold without explicit user action

ADR-024 is a prerequisite for Phase 8 M8.1. No Phase 8 code may be written until
ADR-024 is accepted.

---

## 8. Explicit Non-Goals

### Not in scope for this ADR

- Python implementation of M7.1–M7.5
- Tests
- New execution surfaces or runtime behaviours
- Changes to routing logic, engine logic, or invariant contracts
- Autonomous configuration detection or self-configuration
- Cloud deployment packaging
- Container or CI/CD configuration

### Out of scope permanently for Phase 7

- Phase 8 session shell implementation
- Any modification to the frozen Phase 1–6 execution stack

---

## 9. Scope Boundary

This ADR covers:

- the Phase 7 governance freeze boundary and permissible surfaces (§1)
- the config/structural separation contract (§2)
- the initialisation contract: required and optional config surface (§3)
- the init command or setup guide: properties and CLI surface (§4)
- default pack and persona templates: purpose, required templates, chat session and
  persona template contracts (§5)
- portability validation: checks, trigger, failure contract (§6)
- Work Mode / Steward Mode ADR pre-establishment (§7)
- a new failure code extending ADR-013 (§6.5)

This ADR does **not** cover:

- implementation of any milestone
- Phase 8 contracts or implementation
- any modification to the frozen execution stack

---

## 10. Relationship to Other ADRs

- **ADR-002** — model routing. The routing table remains frozen. Phase 7 templates
  document the user-configurable model name fields; they do not alter routing logic.
- **ADR-003** — content safety. Portability validation failure summaries must comply in
  full. No config values (model names, paths, persona content) may appear in failure
  output.
- **ADR-006** — persona binding and mode governance. `persona.yaml` (M7.3) provides the
  user-facing configuration surface for the persona binding defined in ADR-006.
- **ADR-013** — failure semantics. Extended by §6.5 with one new `contract_violation`
  code. All existing failure contracts unchanged.
- **ADR-021** — runtime observability. M5.3 constellation integrity guard is consumed
  by M7.4 portability validation. ADR-021 is not modified.
- **ADR-022** — memory architecture. The `storage_root` and memory pack config are part
  of the M7.1 initialisation surface. ADR-022 contracts are unchanged.

---

## 11. Consequences

### Positive

- Any user can clone the repository, configure four files, and have a functioning
  governance-compliant IO-III runtime.
- The portability validation pass provides machine-verifiable confidence that the runtime
  is correctly initialised before first execution.
- The `persona.yaml` template (M7.3) closes the only config gap identified in the Phase 7
  audit.
- The `chat_session.yaml` runbook template gives a new user a concrete, runnable starting
  point.
- ADR-024 (M7.5) being authored in Phase 7 prevents Phase 8 from beginning without
  governance — the pattern established by all prior phases.

### Negative

- A new `persona.yaml` config file is introduced as a required config surface. Existing
  users without this file will fail portability validation until they create it.

### Neutral

- This ADR produces no code, no tests, and no changes to any existing runtime surface.

---

## Decision Summary

IO-III introduces an open-source initialisation layer under Phase 7. The config/structural
separation is confirmed clean from Phase 6. The initialisation surface is minimal:
four config files (`providers.yaml`, `routing_table.yaml`, `memory_packs.yaml`,
`persona.yaml`). An init command or setup guide walks a new user from clone to first
execution. A portability validation pass (`PORTABILITY_CHECK_FAILED`) provides
machine-verifiable confirmation of correct initialisation. Default templates — including
a `chat_session.yaml` bounded runbook — provide a concrete starting point. The Work
Mode / Steward Mode ADR (ADR-024) is authored in Phase 7 as the governance prerequisite
for Phase 8. The frozen Phase 1–6 execution stack is not modified.