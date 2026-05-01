<p align="center">
  <img src="../../assets/logo/io_iii_256.png" alt="I0³ logo" width="50%" />
</p>
# Configuration — Identity and User Profile

This document covers the two user-configurable surfaces added in Phase 10:
the **identity block** in `persona.yaml`, and the **user profile** in `user_profile.yaml`.

Both files live in `architecture/runtime/config/`. Both are injected into the
system prompt at runtime by the context assembly layer (ADR-010). Neither affects
routing, audit gates, or execution semantics — they influence how the model
presents itself and calibrates its responses.

---

## Identity block

The `identity:` block in `persona.yaml` controls how Io presents itself to the user
and, by extension, to the underlying model via the system prompt. It has three fields.

```yaml
identity:
  name: "Io"
  description: "A deterministic AI assistant built on the I0³ runtime."
  style: "Concise, precise, and governance-first."
```

**`name`** — the name the assistant uses when asked who it is. This value is
injected as the opening of every system prompt: `Your name is {name}.` If you
deploy I0³ under a different assistant identity, replace this. Leave it as `"Io"`
for the default persona.

**`description`** — a single sentence describing what this assistant does.
Injected immediately after the name line. It tells the model how to answer "what
are you?" — keep it factual and concise. Omitting it leaves the model with only
the name and governance header.

**`style`** — a short phrase describing the preferred communication register.
Injected as `Communication style: {style}`. This is a soft instruction; the model
will tend toward it but governance-first constraints take precedence. Typical
values: `"Concise, precise, and governance-first."`, `"Technical and direct."`,
`"Clear and accessible."`.

All three fields are optional. If `persona.yaml` is missing or unreadable, the
runtime falls back silently to `name: "IO-III"` with no description or style.

### How the identity block appears in the system prompt

The context assembly layer builds the system prompt header as follows:

```
You are IO-III. Your name is Io. A deterministic AI assistant built on the I0³ runtime. Communication style: Concise, precise, and governance-first.
When asked your name, respond with your name only.
Operate under governance-first constraints.
Follow deterministic, bounded execution.
Output must be a single unified final response.
```

The persona contract for the active mode follows immediately after this header.
The identity block is always the outermost frame — it comes before the contract
and cannot be overridden by mode configuration.

### When to change the identity block

The most common use case is a personal instance: adjusting `style` to better
match how you prefer Io to communicate, or updating `description` as your use
of the runtime evolves. Changes take effect at the next request with no restart
required.

---

## User profile

`user_profile.yaml` tells the runtime about the person using the system.
The loaded values are injected into the system prompt as a `=== User Profile ===`
section — separate from Io's identity and from the governance contracts. The model
uses this to calibrate how it addresses the user and how much it explains.

```yaml
user:
  name: "Ceven"
  role: "Software architect and AI systems designer"
  expertise:
    - "AI governance and safety"
    - "Deterministic AI runtime design"
    - "Python"
    - "Software architecture"
  preferences:
    language: "British English"
    style: "Direct, technically precise, no unnecessary preamble"
  notes: ""
```

**`name`** — how the assistant addresses you. Injected as `Name: {name}`. The model
will use this in greetings and direct address.

**`role`** — your professional context. Injected as `Role: {role}`. Helps the model
pitch explanations at the right level without you needing to re-establish context
at the start of each prompt.

**`expertise`** — a YAML list of domains you are comfortable with. Injected as
`Expertise: {comma-separated list}`. The model will avoid over-explaining concepts
in these areas. Keep entries short — one to four words each.

**`preferences`** — a free-form key/value map. Each non-empty entry is injected as
`{Key}: {value}`. The two most useful keys are `language` (for locale and spelling
standard) and `style` (for response register). You can add any keys you find useful;
the runtime does not validate them.

**`notes`** — free text for anything else the model should hold in mind. Injected as
`Notes: {text}` when non-empty. Leave blank if you have nothing to add.

All fields are optional. If every field is empty, the `=== User Profile ===` section
is omitted entirely from the system prompt. If `user_profile.yaml` is missing or
unreadable, the section is silently omitted.

### How the user profile appears in the system prompt

For the example above (with `notes` empty), the injected section reads:

```
=== User Profile ===
Name: Ceven
Role: Software architect and AI systems designer
Expertise: AI governance and safety, Deterministic AI runtime design, Python, Software architecture
Language: British English
Style: Direct, technically precise, no unnecessary preamble
```

This section appears after the persona contract and before the runtime boundaries
summary. It is not logged, not included in audit records, and not visible in
telemetry output.

### What the user profile does not do

The user profile does not affect routing. The model assigned to a given mode is
determined entirely by `routing_table.yaml`, regardless of what is in the user
profile. It does not change audit gate behaviour. It does not extend the context
window — the injected text counts against `context_limit_chars` in `runtime.yaml`,
but it is typically a few hundred characters at most.

---

## Applying changes

Both files are read at request time. There is no cache and no restart required —
edit the file, then send your next prompt. The updated values will appear in the
system prompt on the next execution.

To verify what is being injected, run the context assembly diagnostic (when
available) or inspect the `--debug` output of any `run` command.
