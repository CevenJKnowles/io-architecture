# IO-III Architecture

This repository defines the **governance-first control-plane architecture** for **IO-III**, a **deterministic, bounded local LLM orchestration system** designed around **structural guarantees** rather than feature expansion.

The project prioritizes:

- deterministic routing
- bounded execution
- explicit audit gates
- contract-level invariants
- architecture-first governance

The repository contains both:

1. a formal architecture specification layer (ADRs, invariants, contracts, governance rules)
2. a minimal reference implementation of the control plane (config loading, routing resolution, bounded execution, audit enforcement)

It does **not** attempt to implement a full autonomous agent or feature-complete runtime.

---

## Design Intent

IO-III is intentionally engineered under strict structural constraints:

- Deterministic routing
- Bounded execution
- No recursion loops
- No unbounded chains
- Governance before feature expansion
- Local-first architecture
- Contract + invariant enforcement as stability mechanisms

Structural integrity is prioritized over capability growth.

---

## Governance Model (ADR‑First)

All structural changes must follow an **ADR-first process**.

Any modification affecting:

- control-plane design
- routing logic or fallback policy
- provider/model selection
- audit gates or execution bounds
- persona binding or mode governance
- memory or persistence contracts
- cross-model behavior

requires a new ADR in:

ADR/

before implementation or documentation updates occur.

This repository is the **source of truth for IO-III architecture and runtime boundaries**.

---

## Repository Contents

### ADR Set

Architecture decisions are defined in:

ADR/

Current ADR coverage:

| ADR | Topic |
|-----|------|
| ADR-001 | LLM runtime control plane selection |
| ADR-002 | Deterministic routing and fallback policy |
| ADR-003 | Telemetry logging and retention posture |
| ADR-004 | Cloud provider enablement and key security |
| ADR-005 | Evaluation and regression enforcement |
| ADR-006 | Persona binding and mode governance |
| ADR-007 | Memory persistence and drift control boundaries |
| ADR-008 | Challenger enforcement layer |
| ADR-009 | Audit gate contract and bounded execution |
| ADR-010 | Context assembly layer |

---

### Canonical Runtime Configuration

Runtime configuration lives under:

architecture/runtime/config/

Key files:

- routing_table.yaml
- providers.yaml
- logging.yaml

These define the canonical runtime configuration used by the reference control-plane implementation.

---

### Control‑Plane Reference Implementation

The repository includes a **minimal Python implementation** of the IO‑III control plane.

Core modules:

io_iii/

Important components:

| Module | Responsibility |
|------|----------------|
| config.py | runtime config loading |
| routing.py | deterministic route resolution |
| core/engine.py | execution engine |
| core/context_assembly.py | context assembly (ADR‑010) |
| core/session_state.py | control‑plane state container |
| core/execution_context.py | engine‑local runtime container |
| providers/null_provider.py | null provider adapter |
| providers/ollama_provider.py | Ollama provider adapter |
| cli.py | CLI entrypoint |

Execution path:

CLI → Engine.run() → ExecutionContext → Context Assembly → Provider → Challenger (optional)

This layering enforces a **single deterministic execution path**.

---

### Invariant Suite

Invariant fixtures ensure architectural guarantees remain intact.

Location:

architecture/runtime/tests/invariants/

Validator:

architecture/runtime/scripts/validate_invariants.py

These fixtures protect structural properties such as:

- routing table integrity
- cloud providers disabled by default
- logging defaults (metadata-only)

---

### Regression Enforcement

Critical execution guarantees are protected through regression tests.

Example:

tests/test_audit_gate_contract.py

This test ensures the **audit gate contract** cannot accidentally expand beyond defined bounds.

---

## Core Invariants

The architecture enforces the following guarantees:

- deterministic routing only
- challenger enforcement internal to the engine
- audit execution explicitly user‑toggled
- bounded audit passes (MAX_AUDIT_PASSES = 1)
- bounded revision passes (MAX_REVISION_PASSES = 1)
- no recursion loops
- no multi‑pass execution chains
- single unified final output

These guarantees are treated as **contract‑level invariants**.

---

## Non‑Goals (Intentional Constraints)

This repository intentionally does **not** implement:

- persistent memory
- retrieval systems (RAG / embeddings)
- autonomous planning
- agent loops
- model arbitration beyond deterministic routing
- streaming execution
- automatic audit policies

Future expansion must preserve:

- deterministic control‑plane execution
- bounded runtime guarantees
- invariant enforcement

---

## Milestones

### Phase 1 — Control Plane Stabilisation ✅

- deterministic routing
- challenger enforcement (ADR‑008)
- bounded audit gate contract (ADR‑009)
- invariant validation suite
- regression enforcement

---

### Phase 2 — Structural Consolidation ✅

- SessionState v0 implemented
- execution engine extracted
- CLI → engine boundary established
- context assembly integrated (ADR‑010)
- ExecutionContext introduced (engine‑local runtime container)
- challenger ownership consolidated inside the engine
- provider injection seams implemented
- tests passing (pytest)
- invariant validator passing

---

### Phase 3 — Capability Layer (Planned)

Phase 3 introduces **additional engine‑local capability boundaries** while preserving deterministic execution.

Planned work includes:

- expanding provider abstraction contracts
- strengthening test seams and injection boundaries
- defining engine‑local capability interfaces

No autonomous behaviour or dynamic routing will be introduced in this phase.

---

## Project Status

Phase 1 — Control Plane Stabilised  
Phase 2 — Structural Consolidation Complete  
Phase 3 — Capability Layer (Next)

IO‑III prioritises **structural guarantees, determinism, and governance discipline** over feature velocity.
