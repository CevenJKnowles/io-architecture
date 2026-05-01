<p align="center">
  <img src="../../assets/logo/io_iii_256.png" alt="I0³ logo" width="50%" />
</p>
# Why I0³ exists

## The problem with calling a model directly

When you call a language model directly (through an API, a library, or a chat interface), the model decides almost everything. It decides how long to respond. It decides what to include. If you ask it to stay within a certain scope, it might do so most of the time. Whether it does depends on the model's training and the quality of your prompt. There is no structural guarantee.

This is fine for exploration. It is a problem when you need to know what the system will and will not do before it runs, and to have that enforced in code rather than hoped for through careful prompting.

---

## What I0³ does differently

I0³ sits between your prompt and the model. Before anything reaches the model, the runtime has already resolved exactly one provider and model from a static routing table (no dynamic selection), checked that execution is within hard token and step limits, confirmed that the content safety invariants are met, and, if audit mode is on, prepared the challenger gate to review the draft before it reaches you.

None of these are optional defaults you can prompt your way around. They are enforced structurally, in the execution core, which is frozen after Phase 1 and does not change.

The model is one component in the pipeline. It does not decide the routing, the limits, what gets logged, or whether its output is released.

---

## Who this is for

**You are building something where predictability matters.** You need to know that a given input will always produce a structurally consistent result, not just usually but by design. I0³ gives you that through deterministic routing and bounded execution.

**You need an audit trail.** Every execution is logged with structured metadata. Prompts, completions, and memory values never appear in logs (content safety is a hard invariant, not a configuration option). What you get is timing, routing decisions, token counts, and challenger verdicts: everything needed to reconstruct what happened without exposing sensitive content.

**You want human supervision at configurable gates.** Steward mode pauses a session when it reaches a threshold (step count, token budget, capability class) and waits for a human to approve before continuing. The pause is structural: the session cannot proceed without it.

**You are evaluating AI governance patterns.** I0³ is a reference implementation of a deterministic control plane. Its 26 Architecture Decision Records document every structural choice, including what was explicitly ruled out and why. It is a concrete answer to the question of what governed AI tooling looks like in practice.

---

## What I0³ is not trying to be

I0³ is not a capability amplifier. It adds no retrieval, tool use, or agentic planning, and routes deterministically to exactly one model per request. All of that is out of scope by design. The project's position is that before you add capability, you should be able to answer the question: can I reason about what this system will do? I0³ is the layer that makes that question answerable.
