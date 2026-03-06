---
id: DOC-ARCH-012
title: Phase 4 Guide — Post-Capability Architecture Layer
type: architecture
status: draft
version: v0.1
canonical: true
scope: phase-4
audience: developer
created: "2026-03-06"
updated: "2026-03-06"
tags:
- io-iii
- phase-4
- architecture
roles_focus:
- executor
- challenger
provenance: io-iii-runtime-development
---

# Phase 4 Guide — Post-Capability Architecture Layer

---

## Purpose

Phase 4 introduces the architectural layer above capabilities while preserving IO-III invariants.

---

## Invariants that must remain true

- deterministic routing
- bounded execution (ADR-009)
- explicit capability invocation only
- content-safe logging (no prompts or model outputs)
- no agent behaviour
- no recursion
- no dynamic routing

---

## What Phase 4 may add

- a bounded orchestration layer that composes a single execution path
- explicit task specs or runbooks that compile to one bounded run
- stricter lifecycle contracts for execution traces and session state

---

## What Phase 4 must not add

- autonomous tool selection
- multi-step loops
- planner behaviour
- self-directed recursion
- dynamic routing based on heuristics

---

## Definition of done for Phase 4 entry

- runtime kernel remains stable
- docs reflect the new layer’s contract
- invariant tests updated if new invariants are introduced