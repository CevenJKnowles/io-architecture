#!/usr/bin/env python3
from __future__ import annotations

import sys
import glob
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

try:
    import yaml  # type: ignore
except Exception:
    print("ERROR: Missing dependency 'PyYAML'.", file=sys.stderr)
    print("Install with: python -m pip install pyyaml", file=sys.stderr)
    sys.exit(2)


@dataclass
class Failure:
    invariant_id: str
    invariant_title: str
    assertion_name: str
    message: str


def load_yaml(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_by_dot_path(obj: Any, path: str) -> Tuple[bool, Any]:
    """
    Navigate dictionaries using dot-separated path.
    Returns (found, value).
    """
    if path is None or path == "":
        return True, obj

    cur: Any = obj
    for key in path.split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return False, None
    return True, cur


def assert_yaml_equals(spec: Dict[str, Any], failure_ctx: Dict[str, str]) -> List[Failure]:
    fpath = spec["file"]
    dotpath = spec["path"]
    expected = spec["expected"]

    data = load_yaml(fpath)
    found, value = get_by_dot_path(data, dotpath)
    if not found:
        return [Failure(**failure_ctx, message=f"Path not found: {dotpath} in {fpath}")]
    if value != expected:
        return [Failure(**failure_ctx, message=f"Expected {expected!r} but got {value!r} at {dotpath} in {fpath}")]
    return []


def assert_yaml_has_keys(spec: Dict[str, Any], failure_ctx: Dict[str, str]) -> List[Failure]:
    fpath = spec["file"]
    dotpath = spec["path"]
    expected_keys = spec["expected_keys"]

    data = load_yaml(fpath)
    found, value = get_by_dot_path(data, dotpath)
    if not found:
        return [Failure(**failure_ctx, message=f"Path not found: {dotpath} in {fpath}")]
    if not isinstance(value, dict):
        return [Failure(**failure_ctx, message=f"Value at {dotpath} is not a mapping/dict in {fpath}")]
    missing = [k for k in expected_keys if k not in value]
    if missing:
        return [Failure(**failure_ctx, message=f"Missing keys at {dotpath} in {fpath}: {missing}")]
    return []


def assert_yaml_each_has_keys(spec: Dict[str, Any], failure_ctx: Dict[str, str]) -> List[Failure]:
    fpath = spec["file"]
    dotpath = spec["path"]
    required = spec["each_item_required_keys"]

    data = load_yaml(fpath)
    found, value = get_by_dot_path(data, dotpath)
    if not found:
        return [Failure(**failure_ctx, message=f"Path not found: {dotpath} in {fpath}")]
    if not isinstance(value, dict):
        return [Failure(**failure_ctx, message=f"Value at {dotpath} is not a mapping/dict in {fpath}")]

    failures: List[Failure] = []
    for item_key, item_val in value.items():
        if not isinstance(item_val, dict):
            failures.append(Failure(**failure_ctx, message=f"Item '{item_key}' at {dotpath} is not a dict in {fpath}"))
            continue
        missing = [k for k in required if k not in item_val]
        if missing:
            failures.append(Failure(**failure_ctx, message=f"Item '{item_key}' missing keys {missing} in {fpath}"))
    return failures


def _git_changed_files(scope: str) -> Tuple[bool, List[str], str]:
    """
    Returns (ok, files, error_message).
    scope: "staged" | "working" | "both"
    """
    scope = (scope or "both").strip().lower()
    if scope not in {"staged", "working", "both"}:
        return False, [], f"Invalid scope '{scope}'. Use 'staged', 'working', or 'both'."

    def run(cmd: List[str]) -> Tuple[bool, List[str], str]:
        try:
            p = subprocess.run(
                cmd,
                cwd=os.getcwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        except Exception as e:
            return False, [], f"Failed to run git: {e}"

        if p.returncode != 0:
            return False, [], p.stderr.strip() or f"git exited {p.returncode}"
        files = [line.strip() for line in p.stdout.splitlines() if line.strip()]
        return True, files, ""

    files: List[str] = []
    if scope in {"working", "both"}:
        ok, out, err = run(["git", "diff", "--name-only"])
        if not ok:
            return False, [], f"git diff failed: {err}"
        files.extend(out)

    if scope in {"staged", "both"}:
        ok, out, err = run(["git", "diff", "--name-only", "--cached"])
        if not ok:
            return False, [], f"git diff --cached failed: {err}"
        files.extend(out)

    # de-dup
    files = sorted(set(files))
    return True, files, ""


def assert_git_forbid_paths(spec: Dict[str, Any], failure_ctx: Dict[str, str]) -> List[Failure]:
    forbidden = spec.get("forbidden_paths", [])
    scope = spec.get("scope", "both")

    if not isinstance(forbidden, list) or not forbidden:
        return [Failure(**failure_ctx, message="forbidden_paths must be a non-empty list")]

    ok, changed, err = _git_changed_files(scope)
    if not ok:
        return [Failure(**failure_ctx, message=f"Unable to evaluate git changes ({scope}): {err}")]

    hits: List[str] = []
    for f in changed:
        for prefix in forbidden:
            # Normalize to repo-relative, forward-slash
            pfx = str(prefix).lstrip("./")
            if f.startswith(pfx):
                hits.append(f)

    if hits:
        return [Failure(**failure_ctx, message=f"Forbidden path(s) changed ({scope}): {hits}")]
    return []


def run_invariant(invariant_path: str) -> Tuple[str, str, List[Failure]]:
    inv = load_yaml(invariant_path) or {}
    inv_id = str(inv.get("id", "UNKNOWN"))
    inv_title = str(inv.get("title", "Untitled"))
    assertions = inv.get("assertions", [])

    failures: List[Failure] = []
    if not isinstance(assertions, list):
        failures.append(
            Failure(inv_id, inv_title, "INVARIANT_FORMAT", f"'assertions' must be a list in {invariant_path}")
        )
        return inv_id, inv_title, failures

    for a in assertions:
        if not isinstance(a, dict):
            failures.append(Failure(inv_id, inv_title, "ASSERTION_FORMAT", f"Assertion must be a dict in {invariant_path}"))
            continue

        name = str(a.get("name", "Unnamed assertion"))
        atype = a.get("type")
        ctx = {
            "invariant_id": inv_id,
            "invariant_title": inv_title,
            "assertion_name": name,
        }

        try:
            if atype == "yaml_equals":
                failures.extend(assert_yaml_equals(a, ctx))
            elif atype == "yaml_has_keys":
                failures.extend(assert_yaml_has_keys(a, ctx))
            elif atype == "yaml_each_has_keys":
                failures.extend(assert_yaml_each_has_keys(a, ctx))
            elif atype == "git_forbid_paths":
                failures.extend(assert_git_forbid_paths(a, ctx))
            else:
                failures.append(Failure(**ctx, message=f"Unknown assertion type: {atype!r} (in {invariant_path})"))
        except FileNotFoundError as e:
            failures.append(Failure(**ctx, message=f"File not found: {e}"))
        except Exception as e:
            failures.append(Failure(**ctx, message=f"Unhandled error: {e}"))

    return inv_id, inv_title, failures


def main() -> int:
    inv_paths = sorted(
        glob.glob("./IO-III/tests/invariants/*.yaml")
        + glob.glob("./IO-II/tests/invariants/*.yaml")
    )

    if not inv_paths:
        print("No invariants found at ./IO-III/tests/invariants/*.yaml or ./IO-II/tests/invariants/*.yaml")
        return 0

    all_failures: List[Failure] = []

    print("IO-III Invariant Validator")
    print(f"Found {len(inv_paths)} invariant file(s).")
    print("-" * 60)

    for p in inv_paths:
        inv_id, inv_title, failures = run_invariant(p)
        status = "PASS" if not failures else "FAIL"
        print(f"{status}  {inv_id} — {inv_title}  ({p})")
        for f in failures:
            all_failures.append(f)

    print("-" * 60)
    if all_failures:
        print(f"FAILED: {len(all_failures)} assertion failure(s).")
        for f in all_failures:
            print(f"- [{f.invariant_id}] {f.assertion_name}: {f.message}")
        return 1

    print("ALL PASSED ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
