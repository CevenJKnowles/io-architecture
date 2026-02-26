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