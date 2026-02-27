# IO-III Architecture

This repository defines a **governance-first control-plane architecture** for IO-III: a **deterministic, bounded** local LLM orchestration system designed around **structural guarantees** (routing discipline, execution bounds, audit gates, and invariant enforcement).

It includes both:
1) a **formal specification layer** (ADRs, docs, invariants, contracts), and  
2) a **minimal reference implementation** of the control plane (config loading, routing resolution, provider adapters, audit gate enforcement).

It does **not** aim to be a full autonomous agent or feature-complete product runtime.

---

## Design Intent

IO-III is engineered under explicit constraints:

- **Deterministic routing**
- **Bounded execution** (no recursion loops, no unbounded chains)
- **Governance before feature expansion**
- **Local-first posture**
- **Contract + invariant enforcement** as the primary stability mechanism

Structural integrity takes priority over capability growth.

---

## Governance Model (ADR-First)

Any structural change affecting:

- control plane design
- routing logic or fallback policy
- model/provider selection
- audit gates and execution bounds
- persona binding / mode governance
- memory or persistence contracts
- cross-model behavior

requires a new ADR in `./ADR/` **before** implementation or documentation updates.

This repository is the **source of truth** for IO-III architecture and runtime boundaries.

---

## What’s Included

### 1) ADR Set (ADR-001 → ADR-009)

Formal architectural decisions covering:

- control-plane selection (`ADR-001`)
- routing + fallback policy (`ADR-002`)
- telemetry/logging + retention posture (`ADR-003`)
- cloud enablement + key security (disabled-by-default posture) (`ADR-004`)
- evaluation + regression enforcement (`ADR-005`)
- persona binding + mode governance (`ADR-006`)
- memory/persistence + drift control boundaries (`ADR-007`)
- **challenger enforcement layer** (internal-only) (`ADR-008`)
- **audit gate contract** + hard pass bounds (`ADR-009`)

See: `./ADR/`

### 2) Canonical Runtime Configuration (IO-III)

- `IO-III/runtime/config/routing_table.yaml`
- `IO-III/runtime/config/providers.yaml`
- `IO-III/runtime/config/logging.yaml`

These files define the canonical runtime configuration used by the reference control-plane implementation.

### 3) Minimal Control-Plane Reference Implementation

A small Python package that loads config, resolves routes, and enforces bounded audit behavior:

- `io_iii/config.py` (default config dir resolves to `IO-III/runtime/config/`)
- `io_iii/routing.py` (deterministic route resolution)
- `io_iii/providers/` (`null_provider.py`, `ollama_provider.py`)
- `io_iii/cli.py` (CLI entry; `--audit` bounded by ADR-009)
- `io_iii/persona_contract.py` (persona contract injection)

### 4) Invariant Suite + Validation

- Invariant fixtures: `IO-III/tests/invariants/`
- Validation script: `IO-III/runtime/scripts/validate_invariants.py`

### 5) Regression Enforcement (Audit Bounds)

- Regression test: `tests/test_audit_gate_contract.py`

This locks the audit gate contract and prevents accidental multi-pass expansion beyond defined bounds.

### 6) Architecture + Docs

- `ARCHITECTURE.md`
- `docs/architecture/`
- `docs/implementation/`
- `docs/runtime/`
- `docs/governance/`
- `docs/overview/`

---

## Core Invariants (Contract-Level)

The architecture enforces the following guarantees:

- deterministic routing only
- challenger is **internal-only** (enforced boundary)
- audit is **explicitly toggled** (`--audit`)
- bounded audit passes (**MAX_AUDIT_PASSES = 1**)
- bounded revision passes (**MAX_REVISION_PASSES = 1**)
- no recursion loops
- no multi-pass execution chains
- single unified final output

These are treated as **non-negotiable control-plane guarantees** and are protected via validation fixtures and regression tests.

---

## Non-Goals (By Design)

This repository does not attempt to deliver (yet):

- persistent memory layer
- steward mode execution
- verification module (live fact verification)
- retrieval systems (RAG / embeddings)
- multi-model arbitration beyond deterministic routing rules
- autonomous planning or long-horizon agent loops
- automatic audit policy (audit remains user-toggled)

Future expansion must preserve the deterministic control plane and bounded execution guarantees.

---

## Status

- Architecture baseline: **stabilized**
- ADR set: **complete through ADR-009**
- Invariants + regression enforcement: **present**
- Control plane reference implementation: **present (minimal)**
- Full feature runtime (memory/verification/steward/retrieval): **intentionally out of scope**

IO-III prioritizes **structural guarantees** over feature velocity.