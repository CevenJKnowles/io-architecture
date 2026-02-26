---
id: IOIII-NOTES-001
title: IO-III Working Notes
type: working_notes
status: active
version: v0.1
created: 2026-02-26
updated: 2026-02-26
author: Ceven Jupiter Knowles
project: IO-III
layer: DOC
scope: non_canonical
tags:
  - io-iii
  - working-notes
  - architecture
  - risks
  - todos
governance:
  canonical: false
  mutable: true
  review_required: false
description: >
  Non-canonical working notes for IO-III. Contains temporary reasoning,
  risk tracking, TODOs, and intermediate architectural thinking.
  Content is not authoritative and may change without version control constraints.
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