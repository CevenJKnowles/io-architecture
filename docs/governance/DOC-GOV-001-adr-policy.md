---
id: "GOV-ADR-POLICY"
title: "ADR Policy"
type: "governance"
status: "active"
version: "v1.0"
canonical: true
scope: "repo"
audience: "internal"
created: "2026-01-09"
updated: "2026-01-09"
tags:
  - "adr"
  - "governance"
  - "decision-records"
roles_focus:
  - "governance"
  - "executor"
provenance: "human"
---

# ADR Policy

## Purpose

ADRs (Architecture Decision Records) capture decisions that would otherwise cause silent divergence between architecture, implementation, and documentation.

## When an ADR is required

Create an ADR **before** implementing or documenting changes that affect any of the following:

- LLM runtime stack, serving, or control plane
- Routing rules (mode→model), fallbacks, retry strategy
- Safety posture, logging/telemetry, privacy boundaries
- Cross-model prompts, persona binding, regression tests
- Any change that alters the meaning of canonical architecture docs

## File naming and location

- ADRs live in: `./ADR/`
- Filename pattern: `ADR-###-kebab-case-title.md`
- Numbers are 3 digits, zero-padded, increasing (001, 002, …)

## Status lifecycle

- `draft` — being written; not yet authoritative
- `active` — authoritative decision; in effect
- `locked` — stable decision; changes require a new ADR that supersedes it
- `archived` — obsolete or superseded

## Editing and superseding

- Do not rewrite ADR meaning after it is `active`.
- If a decision changes: create a new ADR that **supersedes** the old one.
- Mark the old ADR `archived` and add a short note pointing to the new ADR.

## Required ADR structure

Each ADR should include:

- Context
- Decision
- Decision drivers
- Options considered
- Consequences
- Related documents
