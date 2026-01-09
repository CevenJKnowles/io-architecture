---
id: "IMPL-IOIII-RUNTIME-LAYOUT"
title: "IO-III Runtime and Testing Layout"
type: "implementation"
status: "active"
version: "v1.0"
canonical: true
scope: "io-iii"
audience: "internal"
created: "2026-01-09"
updated: "2026-01-09"
tags:
  - "implementation"
  - "runtime"
  - "tests"
  - "layout"
roles_focus:
  - "executor"
  - "governance"
provenance: "human"
---

# IO-III Runtime and Testing Layout

This document defines the canonical on-disk layout for IO-III runtime configuration, local artifacts, and tests.

## Directories

### Runtime (tracked)

- `./IO-III/runtime/config/`  
  Control-plane config, routing aliases, runtime settings (tracked).

- `./IO-III/runtime/scripts/`  
  Local helper scripts (tracked).

### Runtime (local-only, not tracked)

- `./IO-III/runtime/logs/`  
  Local logs (per ADR-003). **Gitignored.**

- `./IO-III/runtime/state/`  
  Optional session state (per ADR-007). **Gitignored.**

### Tests (tracked)

- `./IO-III/tests/corpus/`  
  Versioned prompt corpus (per ADR-005).

- `./IO-III/tests/invariants/`  
  “Must not drift” checks (per ADR-005 Layer A).

- `./IO-III/tests/quality/`  
  Non-gating quality evaluations (per ADR-005 Layer B).

### Tests (local-only, not tracked)

- `./IO-III/tests/results/`  
  Local run outputs and reports. **Gitignored.**

## Related ADRs

- `./ADR/ADR-003-telemetry-logging-and-retention-policy.md`
- `./ADR/ADR-005-evaluation-and-regression-testing-policy.md`
- `./ADR/ADR-007-memory-persistence-and-drift-control.md`

## Canonical runtime config files

Tracked config files (source-controlled):

- `./IO-III/runtime/config/routing_table.yaml`  
  Implements ADR-002 routing + fallback triggers.

- `./IO-III/runtime/config/providers.yaml`  
  Implements ADR-004 (cloud disabled by default; explicit opt-in only).

- `./IO-III/runtime/config/logging.yaml`  
  Implements ADR-003 (metadata ON; content OFF; local-only; retention).

## Invariant specifications (structure-only)

These YAML files define “must not drift” invariants. They are intentionally runner-agnostic:

- `./IO-III/tests/invariants/inv-001-routing-table-integrity.yaml`
- `./IO-III/tests/invariants/inv-002-cloud-disabled-by-default.yaml`
- `./IO-III/tests/invariants/inv-003-logging-defaults.yaml`

## Execution note (no runner yet)

A test runner is intentionally not implemented in this phase.  
These invariant specs exist to define stable governance guarantees first; a runner can be added later under `./IO-III/runtime/scripts/`.
