---
id: ADR-024
title: Work Mode / Steward Mode Contract
type: adr
status: accepted
version: v1.0
canonical: true
scope: io-iii-phase-8-prerequisite
audience:
  - developer
  - maintainer
created: "2026-04-12"
updated: "2026-04-12"
tags:
  - io-iii
  - adr
  - phase-7
  - phase-8
  - session-mode
  - steward
  - governance
roles_focus:
  - executor
  - governance
provenance: io-iii-runtime-development
milestone: M7.5
---

# ADR-024 — Work Mode / Steward Mode Contract

## Status

Accepted

---

## Context

Phase 7 is complete. The IO-III runtime supports deterministic execution with full
observability (telemetry, audit, constellation guard, snapshot export, memory architecture)
across all Phases 1–7.

Phase 8 will introduce a session shell — a top-level orchestration surface that manages
multi-turn dialogue and runbook execution across a user session. For the session shell to
be well-governed, it requires a formal concept of **operating mode**: a declared,
user-owned property that determines whether execution proceeds without human-review pauses
(`work`) or with deliberate threshold-gated pauses for human review (`steward`).

Without this ADR:

- Phase 8 code would have no governance contract defining valid mode states or transitions
- The boundary between autonomous execution and human-supervised execution would be
  implicit, undocumented, and unenforceable
- Steward threshold behaviour — what happens when a threshold fires, what the user is
  shown, and what actions they may take — would be left to implementation-time decisions

This ADR formalises the `SessionMode` type, the contracts for each mode, the transition
rules, and the steward threshold protocol. It is a Phase 7 deliverable (M7.5) and a
formal prerequisite for Phase 8 M8.1.

No Phase 8 code may be written until this ADR is accepted.

---

## Decision

IO-III introduces a two-value `SessionMode` type governing how the session shell operates.
The mode is explicit, user-owned, and transition-controlled. Steward thresholds are
declared in config and produce a content-safe pause requiring explicit user action before
execution continues.

---

## 1. `SessionMode` Type Definition

### 1.1 Valid values

`SessionMode` is a two-value type:

| Value | Meaning |
|---|---|
| `work` | Active execution. Session proceeds through steps without human-review pauses. |
| `steward` | Human-supervised execution. Session pauses at declared thresholds and waits for explicit user action. |

No other values are valid. The type is closed.

### 1.2 Default value

The default `SessionMode` at session start is `work` unless the session configuration
explicitly sets it to `steward`.

### 1.3 Placement on `SessionState`

`mode` is an **explicit field** on `SessionState`:

```python
@dataclass
class SessionState:
    ...
    mode: SessionMode
```

`mode` is **never inferred from context** — not from step count, token usage, elapsed
time, or any other runtime observable. Its value is always set by an explicit
user-initiated transition or by the session config at start-up.

---

## 2. Work Mode Contract

### 2.1 Behaviour

In `work` mode the session shell executes runbook steps sequentially without pausing for
human review. All existing runtime invariants apply in full:

- deterministic routing (ADR-002)
- bounded execution (ADR-012, ADR-014)
- challenger enforcement (ADR-008, ADR-009)
- telemetry and audit (ADR-003, ADR-015)
- memory retrieval policy (ADR-022)

Work mode does **not** mean unobserved. Telemetry, audit, and challenger checks run as
normal. It means that execution does not pause mid-session for human review.

### 2.2 Steward threshold behaviour in work mode

Steward thresholds (§5) are **not evaluated** in `work` mode. If a session is in `work`
mode and crosses a threshold boundary, execution continues without pause.

---

## 3. Steward Mode Contract

### 3.1 Behaviour

In `steward` mode the session shell evaluates declared thresholds (§5) at each step
boundary. When a threshold fires, execution **pauses immediately** — the current step does
not begin — and the pause protocol (§6) is invoked.

### 3.2 Invariants in steward mode

All work mode invariants (§2.1) apply in steward mode. Steward mode does not weaken any
existing runtime guarantee. It adds human-review pause points on top of them.

### 3.3 Execution continuation

Execution in steward mode may only continue when the user has taken one of the three
explicit pause actions (`approve`, `redirect`, or `close`) defined in §6. No automatic
continuation is permitted.

---

## 4. Mode Transition Contract

### 4.1 Transitions are user-initiated only

All mode transitions are user-initiated. The runtime **never autonomously switches modes**.

| Transition | Initiator |
|---|---|
| `work` → `steward` | User only |
| `steward` → `work` | User only |

### 4.2 Transition surface

Mode transitions are exposed as explicit user actions on the session shell (Phase 8 M8.1).
They are not exposed as internal runtime calls or inferred from execution state.

### 4.3 No mid-step transitions

A mode transition takes effect at the **next step boundary**, not mid-step. If the user
requests a transition while a step is in progress, the transition is queued and applied
when the current step completes.

### 4.4 Transition is always explicit

There is no implicit work ↔ steward transition. The session mode field on `SessionState`
changes only in response to an explicit user action. No runtime observable — token count,
step count, elapsed time, failure count — may trigger an autonomous mode switch.

---

## 5. Steward Threshold Contract

### 5.1 Purpose

Steward thresholds are the conditions that cause a steward-mode session to pause and
request human review. They are the mechanism by which the operator declares where they
want deliberate oversight injected into execution.

### 5.2 Threshold declaration

Steward thresholds are declared in configuration — not hardcoded. The threshold
configuration surface is part of the user-owned configurable layer (ADR-023 §2).

Thresholds are declared in `architecture/runtime/config/runtime.yaml` under a
`steward_thresholds` key:

```yaml
steward_thresholds:
  step_count: 5          # pause every N steps
  token_budget: 50000    # pause when cumulative tokens exceed N
  capability_classes: [] # pause when any listed capability class is invoked
```

All threshold fields are optional. A `steward_thresholds` key with no sub-keys means no
thresholds are declared — steward mode will never fire a pause on its own (transitions
between steps will still pause on demand if the user requests them through the session
shell).

### 5.3 Threshold evaluation

Thresholds are evaluated at each **step boundary** — after a step completes and before the
next step begins. Thresholds are not evaluated mid-step.

### 5.4 Threshold resolution

When multiple thresholds are declared, **any** threshold firing causes a pause. Threshold
evaluation is not ordered; all declared thresholds are checked at each step boundary.

### 5.5 Threshold reset

A `step_count` threshold is evaluated cumulatively from session start. It is not reset
after a pause. This ensures the operator receives regular oversight without relying on
step numbering to remain predictable.

### 5.6 No hardcoded thresholds

No default steward threshold values are hardcoded in the runtime. If `steward_thresholds`
is absent from `runtime.yaml`, no thresholds exist. The absence of a threshold
declaration is valid and means no automatic pauses will fire.

---

## 6. Pause Protocol

### 6.1 Trigger

The pause protocol fires when:

- the session is in `steward` mode, **and**
- at least one declared threshold has been met at the current step boundary

### 6.2 Pause surface

On pause, the session shell surfaces a **content-safe state summary** to the user. The
summary must:

- state which threshold fired (by threshold key name — e.g. `step_count`)
- state the current step index and total step count
- state the current `SessionMode`
- state what run identity is active (ADR-018)

The summary must **not** contain:

- model names
- prompt content or task descriptions
- persona content
- config values (paths, URLs, thresholds as numbers)
- any content that would fail the ADR-003 content safety invariant

### 6.3 User actions

At a pause point the user must take one of three explicit actions:

| Action | Meaning |
|---|---|
| `approve` | Continue execution from where it paused. The next step proceeds immediately. |
| `redirect` | Provide new direction (e.g. a revised prompt, a step skip, a mode change). Execution resumes with the redirect applied. |
| `close` | Terminate the session. A content-safe session summary is produced and execution ends. |

No action other than `approve`, `redirect`, or `close` may resume execution. The session
remains paused until one of these three actions is received.

### 6.4 No timeout continuation

There is no timeout that causes a paused session to auto-continue. A paused session stays
paused indefinitely until the user acts. If the process terminates while paused, the
session checkpoint (ADR-019) allows a future `resume` to return to the pause point.

---

## 7. Configuration Contract

### 7.1 Session-start mode

The session mode at start-up is declared in the session invocation or session config. The
default is `work`. To begin a session in steward mode, the user passes `--mode steward`
(or equivalent) on the CLI or sets `session_mode: steward` in the runbook metadata.

### 7.2 Threshold configuration surface

Steward thresholds are declared in `architecture/runtime/config/runtime.yaml`. The
`steward_thresholds` key is optional. If absent, no thresholds exist.

Supported threshold keys (Phase 8 M8.1 implementation surface):

| Key | Type | Meaning |
|---|---|---|
| `step_count` | integer | Pause every N steps |
| `token_budget` | integer | Pause when cumulative session tokens exceed N |
| `capability_classes` | list of strings | Pause when any listed capability class is invoked |

### 7.3 Mode in `SessionState`

`SessionState.mode` is initialised from the session-start declaration and updated only by
explicit user-initiated transitions. It is persisted to the session checkpoint (ADR-019)
so that a resumed session restores the mode that was active when the checkpoint was
written.

---

## 8. Relationship to Existing ADRs

- **ADR-003** — content safety. The pause state summary (§6.2) must comply in full with
  the ADR-003 content safety invariant. No model names, prompt content, persona content,
  or config values may appear in the pause output.
- **ADR-012** — bounded orchestration. The bounded execution contract applies in full in
  both modes. Steward mode does not extend or weaken execution bounds.
- **ADR-013** — failure semantics. A session terminated by `close` at a pause point
  produces a clean session termination, not a failure. A session that times out or loses
  the user process while paused is handled by the checkpoint/resume contract (ADR-019,
  ADR-020).
- **ADR-017** — replay/resume boundary. The pause point is a valid checkpoint boundary.
  A paused session may be resumed via ADR-020 `resume`. The resumed session returns to the
  pause state and re-surfaces the pause prompt.
- **ADR-018** — run identity. The run identity is included in the pause state summary
  (§6.2) as a safe, non-sensitive identifier.
- **ADR-019** — checkpoint persistence. `SessionState.mode` and the pause state (if any)
  are persisted to the checkpoint so a resumed session restores the correct mode and
  threshold state.
- **ADR-021** — runtime observability. Session mode transitions are logged to telemetry
  with the transition direction and the user action that triggered them. Threshold fires
  are logged with the threshold key — no threshold values.
- **ADR-023** — open-source initialisation contract. Steward threshold configuration is
  part of the user-owned configurable surface. `runtime.yaml` is an optional config file
  (ADR-023 §3.3) — its absence is safe.

---

## 9. Phase 8 Dependency

ADR-024 is a formal prerequisite for Phase 8 M8.1 (Work Mode / Steward Mode
implementation).

No Phase 8 code may be written until this ADR is accepted.

Phase 8 M8.1 will implement:

- `SessionMode` as a Python type
- `SessionState.mode` field
- mode transition user actions on the session shell
- steward threshold evaluation at step boundaries
- the pause protocol and pause state summary
- `--mode` CLI flag for session-start mode declaration
- `steward_thresholds` config loading from `runtime.yaml`

The implementation contract for each of these is established by this ADR. Phase 8 M8.1
may not deviate from the contracts in §§1–7 without authoring a superseding ADR.

---

## 10. Explicit Non-Goals

### Not in scope for this ADR

- Python implementation of `SessionMode`, `SessionState.mode`, or the pause protocol
- Tests
- New execution surfaces beyond what the session shell will consume in Phase 8
- Changes to routing logic, engine logic, or any frozen Phase 1–7 component
- Autonomous threshold adjustment or adaptive mode switching
- Multi-user or concurrent session considerations

### Out of scope permanently for this ADR

- Any mode that is not `work` or `steward` — the type is closed
- Autonomous mode transitions of any kind

---

## 11. Scope Boundary

This ADR covers:

- the `SessionMode` type: two values, default, placement on `SessionState` (§1)
- the work mode contract: behaviour, invariants, threshold non-evaluation (§2)
- the steward mode contract: behaviour, invariants, continuation rule (§3)
- the mode transition contract: user-initiated only, transition surface, mid-step
  handling, no implicit transitions (§4)
- the steward threshold contract: purpose, declaration, evaluation, resolution, reset,
  no hardcoded values (§5)
- the pause protocol: trigger, content-safe summary, three user actions, no timeout
  continuation (§6)
- the configuration contract: session-start mode, threshold surface, `SessionState`
  persistence (§7)

This ADR does **not** cover implementation of any of the above.

---

## 12. Consequences

### Positive

- Phase 8 has a complete governance contract before any implementation begins, consistent
  with the pattern established across all prior phases.
- The `SessionMode` type is minimal and closed — exactly two values — preventing mode
  proliferation.
- User-initiated-only transitions make mode changes auditable, predictable, and never
  surprising.
- Threshold configuration in `runtime.yaml` means the operator can tune oversight without
  touching any structural code.
- The pause protocol's content-safe summary contract ensures that steward pauses never
  leak sensitive config values, consistent with ADR-003.
- The pause-indefinite-until-action rule (§6.4) combined with ADR-019 checkpoint
  persistence means that human oversight cannot be bypassed by process termination.

### Negative

- Adding `SessionState.mode` requires Phase 8 to extend the existing `SessionState`
  structure. If `SessionState` is already complex by Phase 8, this adds one more field.

### Neutral

- This ADR produces no code, no tests, and no changes to any existing runtime surface.

---

## Decision Summary

IO-III introduces a closed two-value `SessionMode` type (`work` | `steward`). Mode is an
explicit field on `SessionState` — never inferred. All transitions are user-initiated
only. In `work` mode execution proceeds without pause. In `steward` mode, declared
thresholds (in `runtime.yaml`) fire pauses at step boundaries. A pause surfaces a
content-safe state summary and waits indefinitely for one of three user actions: `approve`,
`redirect`, or `close`. No threshold values are hardcoded; no autonomous continuation is
permitted. This ADR is the governance prerequisite for Phase 8 M8.1 — no Phase 8
implementation code may be written until it is accepted.