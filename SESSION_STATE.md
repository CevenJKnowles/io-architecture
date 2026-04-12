# SESSION_STATE

## IO-III Session State

**Project:** IO-III — Deterministic Local LLM Runtime Architecture

**Repository:** [CevenJKnowles/io-architecture](https://github.com/CevenJKnowles/io-architecture)

**Local Path:** `/home/cjk/Dev/IO-III/io-architecture`

> Phase 3–5 milestone detail archived to `history/session-states/phase-3-5-closeout.md`.

---

## Phase Status

**Current Phase:** Phase 7 — Open-Source Initialisation Layer (complete)

**Status:** Phase 7 complete. M7.0–M7.5 delivered. All invariants passing. Ready for tagging v0.7.0.

**Tag:** v0.7.0 (pending)

**Branch:** phase-7-0

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

## Phase 6 Close State — 2026-04-12

**Phase:** 6 — Memory Architecture | **Tag:** v0.6.0

| Milestone | Module | Tests |
| --- | --- | --- |
| M6.1 — Memory Store Architecture | `io_iii/memory/store.py` | `tests/test_memory_store_m61.py` |
| M6.2 — Memory Pack System | `io_iii/memory/packs.py` | `tests/test_memory_packs_m62.py` |
| M6.3 — Memory Retrieval Policy | `io_iii/memory/policy.py` | `tests/test_memory_policy_m63.py` |
| M6.4 — Memory Injection via Context Assembly | `io_iii/core/context_assembly.py`, `io_iii/core/execution_context.py` | `tests/test_memory_injection_m64.py` |
| M6.5 — Memory Safety Invariants | `architecture/runtime/scripts/validate_invariants.py`, `architecture/runtime/tests/invariants/inv-005-memory-content-safety.yaml` | `tests/test_invariants_m65.py` |
| M6.6 — Memory Write Contract | `io_iii/memory/write.py` | `tests/test_memory_write_m66.py` |
| M6.7 — SessionState Snapshot Export | `io_iii/core/snapshot.py` | `tests/test_session_snapshot_m67.py` |

**Test trajectory:** 419 (Ph5 close) → 472 (M6.1) → 537 (M6.2+M6.3) → 565 (M6.4) → 577 (M6.5) → **603 (M6.6+M6.7)**

**Invariant validator:** 5/5 PASS (INV-001 through INV-005)

**CLI additions (Phase 6):**

- `python -m io_iii memory write --scope <scope> --key <key> --value <value>` — M6.6
- `python -m io_iii session export --run-id <id> --mode <mode> [--output <path>]` — M6.7
- `python -m io_iii session import --snapshot <path>` — M6.7

**ADR freeze boundary respected:** engine.py, routing.py, telemetry.py unchanged throughout Phase 6.

---

## Phase 7 — Open-Source Initialisation Layer (Complete)

**Governing ADR:** ADR-023 — Open-Source Initialisation Contract (accepted)

**Phase 7 Prerequisite:** Config separation audit complete. All model names live in
`routing_table.yaml`. No identity-specific values in structural artefacts. `persona.yaml`
absent — Phase 7 M7.3 deliverable.

---

### M7.0 — Phase 7 ADR and Milestone Definition ✓

ADR-023 authored and accepted. Config separation audit confirms Phase 7 prerequisite
satisfied. Phase 7 milestones formally defined in SESSION_STATE.md.

**Deliverable:** `ADR/ADR-023-open-source-initialisation-contract.md`

---

### M7.1 — Initialisation Contract ✓

Init contract formalised in ADR-023 §3. Four required config files identified;
two optional. No prerequisite extraction needed — config separation confirmed clean.

---

### M7.2 — Init Command or Setup Guide ✓

CLI `init` subcommand: displays required config surface, shows file presence state,
runs portability validation, prints human-readable summary with next steps.

**Module:** `io_iii/cli/_init.py` — `cmd_init()`

**CLI:** `python -m io_iii init`

---

### M7.3 — Default Pack and Persona Templates ✓

Neutral, non-identity-specific template files created:

- `architecture/runtime/config/persona.yaml` — default persona template (executor,
  explorer, draft modes; annotated; placeholder `persona.name = "io-user"`)
- `architecture/runtime/config/templates/chat_session.yaml` — annotated YAML template
  (human-readable; schema reference)
- `architecture/runtime/config/templates/chat_session.json` — runnable JSON version
  (3-step `intent → execute → summarise` pattern; explorer → executor → draft)

---

### M7.4 — Portability Validation ✓

Validation pass confirming correct initialisation before first execution.

**Module:** `io_iii/core/portability.py` — `run_portability_checks()`, `validate_portability()`

**Checks (7):** required config files present and parseable; provider base_url declared;
model name declared; persona name present; storage root declared; storage root writable;
constellation guard passes (M5.3).

**CLI:** `python -m io_iii validate`

**New failure code:** `PORTABILITY_CHECK_FAILED` (ADR-013 extension)

**Tests:** `tests/test_portability_m74.py` — 24 tests

---

### M7.5 — Work Mode / Steward Mode ADR ✓

ADR-024 authored and accepted. Governance contract for `work` / `steward` session modes
established as Phase 8 M8.1 prerequisite.

**Deliverable:** `ADR/ADR-024-work-mode-steward-mode-contract.md`

**Prerequisite for:** Phase 8 M8.1. No Phase 8 code until ADR-024 is accepted.

---

### Phase 7 Definition of Done

- ADR-023 accepted and indexed ✓
- M7.1–M7.5 milestones delivered ✓
- A user with no prior context can clone, follow the init surface, and execute a governed
  run without modifying structural code ✓
- `chat_session.yaml` template present and runnable ✓
- ADR-024 (Work Mode / Steward Mode) accepted and indexed ✓
- No identity-specific values in any structural artefact ✓
- `pytest` passing ✓
- Invariant validator passing ✓
- SESSION_STATE.md updated with phase close state ✓
- Repository tagged `v0.7.0` (pending)

---

## Next Phase

**Phase 8** — Work Mode / Steward Mode

**Prerequisite:** ADR-024 accepted ✓

**Governing ADR:** ADR-024 — Work Mode / Steward Mode Contract
