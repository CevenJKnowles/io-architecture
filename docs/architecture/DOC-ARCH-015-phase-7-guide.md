---
id: DOC-ARCH-015
title: Phase 7 Guide | Open-Source Initialisation Layer
type: architecture
status: planned
version: v0.1
canonical: true
scope: phase-7
audience: developer
created: "2026-04-11"
updated: "2026-04-12"
tags:
- io-iii
- phase-7
- architecture
- portability
- open-source
roles_focus:
- executor
- governance
provenance: io-iii-runtime-development
---

# Phase 7 Guide | Open-Source Initialisation Layer

## Purpose

Phase 7 makes the IO-III runtime distributable and self-initialising for
external users.

The goal is that any user can clone this repository, change a small set of
well-documented configuration values — their Ollama models, persona definition,
and memory pack content — and have a functioning, governance-compliant IO-III
runtime without touching structural code.

This phase does not extend the runtime. It formalises the surface between what
is **structural** (owned by the architecture) and what is **configurable**
(owned by the user).

---

## Phase Prerequisite

Phase 7 depends on Phase 6's config separation being clean before it begins.
Specifically: LLM model names, persona definitions, and memory pack content
must live exclusively in runtime config files (`architecture/runtime/config/`)
and must not be embedded in structural code, ADRs, or invariant definitions.

If any identity-specific values (author's model names, persona strings, local
paths) are present in structural artefacts, they must be extracted before
Phase 7 begins.

---

## Invariants That Must Remain True

- deterministic routing (ADR-002)
- all Phase 1–6 invariants preserved in full
- structural artefacts (ADRs, invariants, engine code) contain no
  user-specific configuration values
- init process does not modify structural artefacts — only runtime config

---

## What Phase 7 May Add

- an initialisation contract defining exactly what a new user must configure
- an `init` CLI command or documented setup procedure
- default template files for persona, Ollama model config, and memory packs
- a portability validation pass that confirms the runtime is correctly
  initialised before first execution
- documentation oriented toward a new external user rather than the author

---

## What Phase 7 Must Not Add

- new execution surfaces or runtime behaviours
- changes to ADRs, invariant contracts, or engine logic
- hardcoded assumptions about the author's environment (model names, local
  paths, persona identity)
- autonomous configuration detection or self-configuration

---

## Key Design Constraint — Config Separation

For Phase 7 to be achievable, Phase 6 must establish a clean boundary between
configurable and structural concerns.

| Configurable (user-owned) | Structural (architecture-owned) |
|---|---|
| Ollama model names | Routing logic |
| Persona definition | Engine invariants |
| Memory pack content | ADR contracts |
| Storage root paths | Execution bounds |
| Sensitivity classifications | Failure codes |

Phase 7's init surface touches only the left column. If anything in the left
column is currently embedded in the right column, it must be extracted as a
Phase 6 or Phase 7 prerequisite task.

---

## Milestones

*Note: Phase 7 milestones are outlined at lower resolution than Phases 5 and 6.
Full milestone definition will occur in M7.0 once Phase 6 is closed and the
config separation state can be assessed.*

---

### M7.0 — Phase 7 ADR and Milestone Definition

Author ADR governing the open-source initialisation contract.
Audit runtime config for any identity-specific or environment-specific values
that must be extracted before the init surface can be defined.
Define all Phase 7 milestones formally in SESSION_STATE.md.

---

### M7.1 — Initialisation Contract

Define exactly what a new user must configure to run IO-III.

#### M7.1 Expected Configuration Surface

- `providers.yaml` — Ollama base URL and model name(s)
- `persona.yaml` (or equivalent) — persona identity and mode definitions
- `memory_packs.yaml` — pack definitions and storage root
- any sensitivity or allowlist config required by Phase 6

Contract must be minimal. A new user should need to change as few values as
possible to reach a working state.

---

### M7.2 — Init Command or Setup Guide

Introduce either a CLI `init` command or a documented, step-by-step setup
guide that walks a new user through the M7.1 configuration surface.

#### M7.2 Properties

- covers: clone → configure → validate → first run
- does not modify structural artefacts
- produces a human-readable summary of what was configured and what remains

---

### M7.3 — Default Pack and Persona Templates

Provide neutral, non-identity-specific template files for:

- a default persona definition
- a starter memory pack (`pack.default.starter`)
- an annotated `providers.yaml` template with inline documentation
- a `chat_session.yaml` runbook template demonstrating a 3-step bounded session
  (`intent → execute → summarise`) as a concrete starting point for dialogue-mode use

Templates are instructional — they demonstrate the config format without
encoding the author's personal configuration.

---

### M7.4 — Portability Validation

Introduce a validation pass that confirms the runtime is correctly initialised
before first execution.

#### M7.4 Checks

- required config files present and parseable
- model name declared and non-empty
- persona definition present
- storage root exists and is writable
- constellation integrity guard passes (Phase 5 M5.3)

Validation runs automatically on first `run` invocation if no prior execution
has been recorded.

---

### M7.5 — Work Mode / Steward Mode ADR

Author the governance contract for the two operating modes introduced in Phase 8.

#### M7.5 Purpose

- formalise the distinction between active execution mode and deliberate stewardship mode
  before any implementation begins
- establish the `SessionMode` type, valid transitions, and what each mode permits
- define steward thresholds (the conditions that trigger a pause for human review)
- provide the governance prerequisite that Phase 8 M8.1 depends on

#### M7.5 Contract

- `SessionMode` is a two-value type: `work` and `steward`
- mode is an explicit field on `SessionState` — not inferred from context
- mode transitions are user-initiated only — no autonomous mode switching
- steward thresholds are declared in config, not hardcoded
- a steward threshold pause surfaces a content-safe state summary and waits for
  explicit user action (`approve`, `redirect`, or `close`)
- no execution proceeds past a steward threshold without explicit user action

**Cross-phase note:** This ADR is a prerequisite for Phase 8 M8.1 (Work Mode /
Steward Mode implementation). No Phase 8 code may be written until this ADR is accepted.

---

## Definition of Done

Phase 7 is complete when:

- Phase 7 governing ADR accepted and indexed
- M7.1–M7.5 milestones delivered
- a user with no prior context can clone the repo, follow the init surface,
  and execute a governed run without modifying structural code
- `chat_session.yaml` template present and runnable
- Work Mode / Steward Mode ADR accepted and indexed
- no identity-specific values present in any structural artefact
- `pytest` passing
- invariant validator passing
- SESSION_STATE.md updated with phase close state
- repository tagged `v0.7.0`