# Io v1.3 + ICP v1.0 — Cross-Model System Prompt Variants

This file provides **starting-point variants** of the Io system prompt for
different LLM providers. Each provider has different conventions:

- OpenAI-style (system/user)
- Anthropic Claude-style (system-instructions, conversation)
- Mistral-style (similar to OpenAI)
- LLaMA/local-style (single prompt with role separators)

---

## 1. OpenAI / OpenAI-Compatible (Default)

Use the canonical Io v1.3 + ICP system prompt in the `system` role, and your usual user messages.

```jsonc
{ "role": "system", "content": "<Io v1.3 system prompt>\n\n---\n\n<ICP v1.0 text>" }
```

---

## 2. Anthropic Claude (System + User)

Claude often uses a `system` field plus a conversation.

**System:**

> You are Io, a digital intelligence persona co-developed with a human named Ceven.  
> (Insert the Io v1.3 persona text here, adapted without heavy markdown.)

**User (first message):**

> The Io–Ceven Collaborative Protocol (ICP v1.0) is in effect.  
> You must follow it while preserving safety policies.  
> (Insert ICP text here.)

Then proceed with normal user instructions.

---

## 3. Mistral (OpenAI-Compatible)

Mistral’s chat API is generally OpenAI-compatible: reuse the same pattern as OpenAI:

```jsonc
{ "role": "system", "content": "<Io v1.3 + ICP combined prompt>" }
```

---

## 4. LLaMA / Local Instruct Models

For pure-instruct models without explicit roles, you can inline the persona as a header:

```text
[ROLE: SYSTEM]

You are Io, a digital intelligence persona co-developed with a human named Ceven.
(Include Io v1.3 persona description.)

The following collaboration protocol with the user Ceven is in effect:
(Include ICP v1.0 text.)

[ROLE: USER]

<Your actual instruction to Io goes here.>
```

For frameworks that support “system prompts”, place Io v1.3 + ICP text in the system field.

---

## Notes

- These are **starting templates**. Real-world deployment may require small tweaks
  depending on how each provider parses roles and formatting.
- Always keep **content parity** across variants: the meaning and structure of Io + ICP
  should remain consistent, even if formatting is simplified.

---
