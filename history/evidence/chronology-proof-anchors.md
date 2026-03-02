# Chronology Proof Anchors

Purpose: lightweight proof anchors that help reviewers correlate major milestones with repository history
(commits, tags, ADRs, and documented snapshots) without depending on private context.

## Anchor format
Each anchor should link to one or more of:
- a commit hash
- an ADR ID (ADR-00X)
- a dated snapshot doc under `docs/runtime/`
- a file path that represents a stable milestone

Keep entries neutral and factual.

---

## A-001 — Architecture baseline freeze
- Evidence:
  - `ARCHITECTURE.md`
  - `docs/architecture/io-iii-llm-architecture.md`
  - `ADR/` (ADR-001 … ADR-009)

## A-002 — Deterministic runtime surface established
- Evidence:
  - Python package: `io_iii/`
  - Canonical config: `architecture/runtime/config/`
  - Canonical tests: `architecture/runtime/tests/`
  - CLI smoke test: `python -m io_iii route executor`

## A-003 — Session snapshot (v0.2)
- Evidence:
  - `docs/runtime/SESSION_SNAPSHOT_2026-02-27_v0.2.md`

## A-004 — History consolidation
- Evidence:
  - `history/io-i/`
  - `history/io-ii/`
  - `history/evolution-from-exploration-to-deterministic-runtime.md`
