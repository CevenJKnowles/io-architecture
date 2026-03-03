---
id: "DOC-NOTE-001"
title: "IO-III Notes"
type: "working_notes"
status: "active"
version: "v0.1"
canonical: false
scope: "io-iii"
audience: "internal"
created: "2026-02-26"
updated: "2026-03-03"
tags:
  - "notes"
  - "working"
roles_focus:
  - "explorer"
provenance: "human"
---

# IO-III Working Notes v0.1

## Timestamp
2026-02-26 CET

---

## Hidden Risk Layer (Committed)

### Risk 1 — Model Bleed
If role boundaries are unclear:
- reasoning contaminates drafting
- drafting becomes non-deterministic
- output loses structural predictability

### Risk 2 — Routing Ambiguity
If routing rules are not explicit:
- system defaults to implicit heuristics
- violates deterministic routing principle

### Risk 3 — Overfitting Models to Tasks
Premature optimisation:
- tight coupling between model + role
- reduces swap-ability
- increases fragility

---

## Core Insight

Models are replaceable  
Roles are structural

---

## Reminder

Do not:
- optimise early
- introduce overlap
- collapse roles

System integrity > performance

---

---

## TODO — CLI Ergonomics

### Create Alias for IO-III

Objective:
Enable fast, consistent startup of IO-III without manual Python invocation.

Target:
- single command execution
- no need to remember module path
- portable across sessions

Example (future):
io-iii run "input"

or

io3 "input"

Notes:
- implement after provider integration
- must respect config-dir defaults
- should not bypass governance layer