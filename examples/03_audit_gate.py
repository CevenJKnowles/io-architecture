"""
examples/03_audit_gate.py: The challenger intercepting a draft

Runs a prompt with --audit to demonstrate the challenger gate.
The challenger reviews the draft before output is released.
If the challenger flags the draft, it is revised before you see it.

The audit gate is bounded: at most one audit pass and one revision pass
(MAX_AUDIT_PASSES = 1, MAX_REVISION_PASSES = 1). This is a hard limit,
not a configurable value.

Prerequisites: Ollama running with 'executor' and 'challenger' modes configured.

Run from repo root:
  python examples/03_audit_gate.py
"""

import json
import subprocess
import sys

result = subprocess.run(
    [
        sys.executable, "-m", "io_iii",
        "run", "executor",
        "--audit",
        "--output", "json",
        "--prompt", "Draft a brief summary of what a deterministic runtime does.",
    ],
    capture_output=True,
    text=True,
)

if result.returncode != 0:
    print("Error:", result.stderr.strip(), file=sys.stderr)
    sys.exit(result.returncode)

# With --output json, the CLI emits a structured JSON object.
data = json.loads(result.stdout)

print("=== Execution result ===")
print(f"  Request ID   : {data.get('request_id', '(not set)')}")
print(f"  Mode         : {data.get('mode', '(not set)')}")
print(f"  Provider     : {data.get('provider', '(not set)')}")

# The 'audit' key is present when --audit was passed.
# It shows whether the challenger accepted the draft or triggered a revision.
audit = data.get("audit", {})
if audit:
    print(f"\n=== Challenger verdict ===")
    print(f"  Verdict      : {audit.get('verdict', '(not set)')}")
    print(f"  Revised      : {audit.get('revised', False)}")
    # The challenger's reasoning is structural metadata only.
    # The prompt and draft never appear in this output (ADR-003).
else:
    print("\n  (no audit metadata; is content_release enabled in runtime.yaml?)")

# The model response appears only if content_release: true is set in runtime.yaml.
response = data.get("response")
if response:
    print(f"\n=== Response ===\n{response}")
else:
    print("\n  (response not surfaced; set content_release: true in runtime.yaml to enable)")
