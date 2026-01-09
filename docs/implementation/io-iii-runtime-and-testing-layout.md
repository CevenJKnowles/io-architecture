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
