---
id: ADR-027
title: Project Identity and Rename Contract
type: adr
status: accepted
version: v1.0
canonical: true
scope: io-iii-phase-10
audience:
  - developer
  - maintainer
  - operator
created: "2026-05-01"
updated: "2026-05-01"
tags:
  - io-iii
  - adr
  - phase-10
  - identity
  - branding
  - governance
roles_focus:
  - executor
  - governance
provenance: io-iii-runtime-development
milestone: M10.0
---

# ADR-027 — Project Identity and Rename Contract

## Status

Accepted

---

## 1. Context

Phase 10 formalises the public identity of the project prior to open-source release. The
project has been developed internally as IO-III. The public display identity adopts the
notation I0³, which preserves full semantic continuity — Io as the project name, ³ as the
third generation expressed as an exponent rather than Roman numerals — while producing a
more distinctive and typographically precise mark.

The critical constraint is that the identity change must be cosmetic only. No structural
change to the runtime, no package rename, no import path modification, and no change to
any ADR governance contract is permitted under this ADR.

---

## 2. Decision

### §1 Display name

The public display name of the project is **I0³** (Unicode: Io followed by U+00B3
SUPERSCRIPT THREE). This name is used in the README, all user-facing documentation,
the pyproject.toml description field, and all new marketing or positioning content
produced from Phase 10 onward.

### §2 Package and module identity — unchanged

The Python package name remains `io_iii`. The CLI entry point remains
`python -m io_iii`. All import statements throughout the codebase remain unchanged.
No file or directory in `io_iii/` is renamed under this ADR.

### §3 Scope of changes permitted under this ADR

The following changes are in scope and may be made without a new ADR:

- `README.md` title and header updated to I0³
- `pyproject.toml` description field updated to `I0³ — Deterministic AI Runtime`
- All user-facing documentation updated to use the I0³ display name
- Logo assets added to `assets/logo/` (PNG exports at standard sizes)
- `ARCHITECTURE.md` frontmatter updated: `audience: portfolio` removed, `status` corrected

The following are explicitly out of scope and require a separate ADR if pursued:

- Any rename of the `io_iii/` package directory
- Any change to the CLI entry point
- Any modification to ADR-001 through ADR-026

### §4 Logo and visual identity

The canonical logo mark is I0³ rendered in Impact (letterforms) and Lexend Exa (subtitle
wordmark) against the primary palette: #ff6700 (orange) and #010f1d (deep navy). Both
orange-field and dark-field variants are provided. All variants meet WCAG AAA contrast
(7.03:1 minimum). The master source file is kept locally and is not committed to the
repository. PNG exports are committed to `assets/logo/`.

### §5 Subtitle

The canonical subtitle is **Deterministic AI Runtime**. This subtitle appears beneath the
I0³ mark in the logo, in the README header, and in all positioning and documentation
contexts where a subtitle is used.

### §6 ADR record governance

ADR-001 through ADR-026 remain authoritative and are not amended by this record.
References within those documents to IO-III or io-iii are considered equivalent to I0³
for all governance purposes. No retroactive editing of prior ADRs is required.

---

## 3. Consequences

- The pyproject.toml version is bumped to `1.0.0-rc.1` at M10.1 close and to `1.0.0`
  at M10.7 tag.
- All new ADRs from ADR-027 onward use I0³ in their title and scope fields.
- External references to the project (GitHub, PyPI, documentation) use I0³ as the
  display name. The GitHub repository URL path remains `io-architecture` until a
  repository rename is explicitly decided in a future ADR.

---

## 4. Non-goals

- This ADR does not rename the Python package.
- This ADR does not modify the CLI entry point.
- This ADR does not change any runtime behaviour, routing logic, or execution semantics.
- This ADR does not amend any prior ADR.