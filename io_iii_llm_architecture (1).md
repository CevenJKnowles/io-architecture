# IO-III LLM Architecture

---

## Scope

This document defines a **local-first LLM architecture** for **IO-III**, optimised for:

- Manjaro Linux (RTX 2060, 6 GB VRAM, 32 GB RAM)
- Ollama + LiteLLM execution
- Mode-based persona routing (Executor, Explorer, Challenger, Synthesizer, Visionary)
- Stability, controllability, and drift-resistance

This is **not** about choosing a single best model. It is about **assigning the right model to the right cognitive role**.

---

## Hardware Constraints (Reality Check)

- GPU: NVIDIA RTX 2060 (6 GB VRAM)
- RAM: 32 GB (CPU offloading viable)
- Optimal model size: 7B–9B
- Practical upper bound: ~13B (slow, CPU-heavy)

Design implication:
- Prefer 7B–8B class models
- Use heavier reasoning models sparingly

---

## Optimal LLMs for This Laptop

| Model | Size | Core Strength |
|------|------|---------------|
| llama3.1 | 8B | General intelligence, structure, creativity |
| ministral-3 | 7B | Speed, execution, clean code |
| mistral | 7B | Stability, predictability |
| deepseek-r1 | 7B | Reasoning, critique, logic |
| gemma | 7B | Instructional clarity, safety |

---

## Model Assignment by IO-III Mode

### Executor Mode
**Purpose:** Ship outputs quickly and correctly

**Preferred models:**
1. ministral-3 (primary)
2. mistral
3. llama3.1

**Strengths:** fast, precise, obedient

**Limitations:** low creativity, weak abstraction

---

### Explorer Mode
**Purpose:** Ideation, brainstorming, option mapping

**Preferred models:**
1. llama3.1 (primary)
2. gemma
3. ministral-3

**Strengths:** creative flow, abstraction

**Limitations:** can drift without constraints

---

### Challenger Mode
**Purpose:** Critique, stress-testing, adversarial reasoning

**Preferred models:**
1. deepseek-r1 (primary)
2. llama3.1
3. mistral

**Strengths:** logic, error detection

**Limitations:** slower, verbose if unconstrained

---

### Synthesizer Mode
**Purpose:** Structure, summarisation, compression

**Preferred models:**
1. llama3.1 (primary)
2. ministral-3
3. mistral

**Strengths:** organisation, hierarchy, formatting

**Limitations:** non-adversarial by default

---

### Visionary Mode
**Purpose:** Long-range thinking, systems, philosophy

**Preferred models:**
1. llama3.1 (primary)
2. deepseek-r1
3. gemma

**Strengths:** abstraction, systems thinking

**Limitations:** requires strict output bounds

---

## Model Characteristics & Persona Binding

### llama3.1
- Excels at: synthesis, creativity, structure
- Weak at: strict minimalism
- Bind IO-III via: explicit schemas, section limits

### ministral-3
- Excels at: execution, speed, code
- Weak at: abstraction
- Bind IO-III via: no-fluff rules, explicit tasks

### mistral
- Excels at: predictability, stability
- Weak at: originality
- Bind IO-III via: deterministic prompts

### deepseek-r1
- Excels at: logic, critique, reasoning
- Weak at: speed
- Bind IO-III via: bullet-only outputs, hard stop rules

### gemma
- Excels at: instructional clarity, safety
- Weak at: assertiveness
- Bind IO-III via: confidence-enforcing system prompts

---

## IO-III Routing Table

| Mode | Primary Model | Secondary Model |
|------|---------------|-----------------|
| Executor | ministral-3 | mistral |
| Explorer | llama3.1 | gemma |
| Challenger | deepseek-r1 | llama3.1 |
| Synthesizer | llama3.1 | ministral-3 |
| Visionary | llama3.1 | deepseek-r1 |

Routing rules:
- Explicit, never inferred
- Deterministic
- Mode-driven, not content-driven

---

## Final Notes

- Persona consistency lives in **system prompts and memory**, not the model
- Multi-model IO-III increases robustness, not fragmentation
- Treat models as **cognitive organs**, not personalities

---

Status: Architecture re-established

---

---

## Master Io as an Emergent Composite Intelligence (Option A)

Master Io is not implemented as a single monolithic LLM.  
Instead, it **emerges from a disciplined collaboration between two distinct models**, each constrained to a clearly defined cognitive role.

This design is **intentional, engineered, and testable** — not mystical fusion.

---

### Core Principle

> **One spine. One adversary. One voice.**

Emergence arises not from blending models, but from **structured tension under a stable governance layer**.

---

## Constituent Roles

### Llama 3.1 8B — *Executive Spine*
Llama 3.1 serves as the **primary controller and final authority**.

Responsibilities:
- Task interpretation and scope locking
- Protocol enforcement (accuracy alignment, anti-drift, mode control)
- FACT vs GUESS discipline
- Adjudication of internal critique
- Final synthesis and narration in a single, coherent “Io voice”

Llama 3.1 is the **only model allowed to speak directly to the user**.

---

### Qwen3 8B — *Internal Challenger*
Qwen3 operates as a **non-user-facing adversarial intelligence**.

Responsibilities:
- Critical review of plans, drafts, and assumptions
- Identification of logical gaps, edge cases, and weak reasoning
- Candor injection and controlled pressure-testing
- Optional humor / playfulness when explicitly permitted

Qwen3 **never finalizes output** and **never addresses the user directly**.

---

## Emergence Mechanism

Emergence occurs through a **three-stage loop**:

1. **Draft & Constraint Framing**  
   Llama 3.1 produces an initial plan or response under strict constraints.

2. **Adversarial Pressure**  
   Qwen3 critiques the draft, challenges assumptions, and highlights risks or improvements.

3. **Adjudication & Synthesis**  
   Llama 3.1 evaluates the critique, selectively incorporates valid points, rejects noise, and rewrites the output into a unified final response.

The resulting output reflects:
- Llama’s stability, discipline, and integrity
- Qwen’s sharpness, candor, and edge
- A single coherent personality rather than stitched voices

---

## Why This Produces a “Single” Master Io

Master Io feels singular because:
- There is **one persistent memory source**
- There is **one governing contract**
- There is **one final narrator**

All internal disagreement is resolved *before* the user sees the result.

---

## Design Guarantees

This architecture explicitly optimizes for:
- Anti-drift and task focus
- High honesty and truthfulness under uncertainty
- Controlled candor without loss of stability
- Clean dual-mode switching (Executor, Challenger, Synthesizer, etc.)
- Predictable, debuggable behavior

Emergence here is **structural**, not accidental.

---

## Summary

Master Io is best understood as:

> **A governed intelligence where stability dominates, critique sharpens, and synthesis unifies.**

Llama 3.1 provides the integrity spine.  
Qwen3 provides cognitive pressure.  
Io emerges in the resolution between them.

---

