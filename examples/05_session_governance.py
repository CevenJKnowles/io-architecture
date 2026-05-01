"""
examples/05_session_governance.py: Steward mode gate triggering

Steward mode is the human-in-the-loop governance model. The session runs
normally until it reaches a configured threshold, then pauses and exits
with code 3. The next `session continue` prompts the operator to approve
before the session can proceed.

This example starts a steward-mode session, runs two turns, and shows
what happens when the gate fires. The steward threshold is set to 2 steps
in this example via an inline runtime.yaml override.

In a real deployment, configure thresholds in:
  architecture/runtime/config/runtime.yaml

under the steward_thresholds block:
  steward_thresholds:
    step_count: 5        # pause every N turns
    token_budget: 50000  # pause when cumulative tokens exceed N

Prerequisites: Ollama running with the 'executor' and 'steward' modes configured.

Run from repo root:
  python examples/05_session_governance.py
"""

import json
import subprocess
import sys


def run_cli(*args):
    """Run an io_iii CLI command and return (returncode, parsed_json_or_text)."""
    result = subprocess.run(
        [sys.executable, "-m", "io_iii"] + list(args),
        capture_output=True,
        text=True,
    )
    try:
        return result.returncode, json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.returncode, result.stdout.strip()


# Step 1: Start a steward-mode session.
print("Starting steward-mode session...")
code, data = run_cli("session", "start", "--mode", "steward", "--output", "json")

if code != 0:
    print("Failed to start session:", data, file=sys.stderr)
    sys.exit(code)

session_id = data.get("session_id")
if not session_id:
    print("No session_id in response:", data, file=sys.stderr)
    sys.exit(1)

print(f"  Session started: {session_id}")
print(f"  Mode           : {data.get('session_mode', '?')}")

# Step 2: First turn.
print("\nTurn 1...")
code, data = run_cli(
    "session", "continue",
    "--session-id", session_id,
    "--prompt", "What is bounded execution?",
    "--output", "json",
)
print(f"  Exit code: {code} (0 = normal, 3 = steward pause)")
if data.get("response"):
    print(f"  Response : {data['response']}")

# Step 3: Second turn (may trigger the gate).
print("\nTurn 2...")
code, data = run_cli(
    "session", "continue",
    "--session-id", session_id,
    "--prompt", "What is deterministic routing?",
    "--output", "json",
)

print(f"  Exit code: {code}")
if code == 3:
    # Exit code 3 means the steward gate fired.
    # The session is paused and will not proceed until the operator approves.
    print("  Steward gate triggered; session is paused.")
    print("  To approve and continue, run:")
    print(f"    python -m io_iii session continue --session-id {session_id} --prompt '<next prompt>'")
    print("  The gate will prompt for approval before executing the turn.")
elif code == 0:
    print("  Gate did not fire (threshold not yet reached).")
    if data.get("response"):
        print(f"  Response : {data['response']}")

# Check session status.
print("\nSession status:")
code, status = run_cli("session", "status", "--session-id", session_id, "--output", "json")
print(f"  Status     : {status.get('status', '?')}")
print(f"  Turn count : {status.get('turn_count', '?')}")
print(f"  Mode       : {status.get('session_mode', '?')}")
