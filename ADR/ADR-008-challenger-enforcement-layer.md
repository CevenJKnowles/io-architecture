# ADR-008 — Challenger Enforcement Layer (Audit + Gate)

Status: Accepted
Related: ADR-009 — Audit Gate Contract v1.0
Date: 2026-02-26  
Scope: IO-III Runtime Execution Path (`run` command)

---

## 1. Context

IO-III currently performs deterministic single-pass execution:

User Prompt → Executor (LLM) → Structured Output

This architecture produces functional results but lacks:

- Systematic compliance verification
- Structured factual risk detection
- Drift detection
- Boundary enforcement

To increase reliability and production readiness, a Challenger Enforcement Layer is introduced.

---

## 2. Decision

IO-III will implement a two-stage execution model:

Executor → Challenger → (Optional Revision) → Final Output

### 2.1 Challenger Role

The Challenger:

- Audits executor output
- Checks for:
  - Policy compliance
  - Boundary violations
  - Factual risk
  - Unverifiable claims
  - Internal contradictions
  - Missing verification steps
- MUST NOT introduce new facts
- MUST NOT rewrite the draft
- MUST produce structured JSON audit output

### 2.2 Enforcement Model

If Challenger verdict == "pass":
    → Executor draft is returned unchanged.

If Challenger verdict == "needs_work":
    → Executor receives:
        - Original prompt
        - Original draft
        - Challenger structured audit
    → Executor performs one revision pass.
    → Revised output becomes final output.

### 2.3 Loop Policy

- Maximum: 1 revision pass.
- No recursive critique loops.
- Deterministic bounded execution.

---

## 3. Output Contract

The CLI returns a single final output message.

Optional metadata may include:
- audit_used: true/false
- audit_verdict: pass|needs_work
- revised: true/false

The Challenger's raw critique is not returned to the user by default.

---

## 4. Activation Policy

Initial implementation:
- Enabled via CLI flag: `--audit`

Future possibility:
- Default enabled in production mode.

---

## 5. Determinism & Governance

- No new facts may be introduced during revision.
- Challenger must reference executor draft only.
- Revision must preserve original user intent.
- If Challenger fails (error/unavailable), executor result is returned unchanged.

---

## 6. Performance Impact

Adds:
- +1 LLM call (audit)
- +1 optional LLM call (revision)

Worst case: 3 total model invocations per run.

---

## 7. Rationale

- Improves reliability without architectural explosion.
- Preserves deterministic bounded execution.
- Maintains clear separation of roles:
  - Executor = generative
  - Challenger = compliance enforcement
- Avoids uncontrolled self-refinement loops.

---

## 8. Consequences

Positive:
- Higher output integrity
- Reduced hallucination risk
- Clear enforcement boundary

Tradeoffs:
- Increased latency
- Higher compute cost
- Additional implementation complexity

---

## 9. Future Extensions (Not in Scope)

- Multi-stage challenger scoring
- Cross-model adversarial audit
- Memory-aware challenger
- Auto-citation insertion

---

End of ADR-008