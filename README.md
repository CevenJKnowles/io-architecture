# IO Persona Blueprint

This repository contains the working material, architecture notes, and documentation related to the evolution of the Io Persona (v1.x series).  
Currently private and used for iterative research + development.

## Governance

Architectural changes that affect runtime, routing, model selection, safety policies, or cross-model behavior require a new ADR in `./ADR/` **before** implementation or doc updates.


---

## IO-III Architecture Status (Baseline)

This repository defines the **governance-complete architecture baseline** for IO-III.

### What is included

- **ADR-001 → ADR-007**  
  Formal decisions covering:
  - control plane selection
  - model routing and fallback
  - telemetry and retention
  - cloud provider security
  - evaluation and regression testing
  - persona and mode governance
  - memory, persistence, and drift control

- **Canonical runtime configuration**
  - `routing_table.yaml` (mode-driven, local-first)
  - `providers.yaml` (cloud disabled by default)
  - `logging.yaml` (metadata-only, local)

- **Executable invariant validation**
  - YAML-based invariant specs
  - Python validator enforcing ADR guarantees
  - Local, deterministic, dependency-minimal

### Status

- Architecture: **frozen**
- Governance: **complete**
- Verification: **passing**
- Runtime implementation: **not included**

This repository serves as the **contract and source of truth** for any IO-III runtime implementation.

See:
- `./docs/architecture/`
- `./docs/implementation/`
- `./ADR/`

---
