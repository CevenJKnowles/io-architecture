"""
test_invariants_m65.py — Phase 6 M6.5 memory safety invariant tests (ADR-022 §6).

Verifies:

  Unit — python_requires_pattern assertion type
  - found pattern returns empty failures list
  - missing pattern returns one failure
  - no files matching glob returns one failure
  - failure message cites glob when no files found
  - failure message cites pattern when pattern not found
  - pattern matched in any file (not just first) returns no failure

  Unit — python_forbids_pattern assertion type
  - no matching files returns empty failures list (not an error)
  - clean files return empty failures list
  - forbidden pattern on one line returns one failure
  - forbidden pattern on multiple lines returns multiple failures
  - failure message cites file path and line number

  Integration — INV-005 passes against current codebase
  - validate_invariants.py exits 0 when run from repo root
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load the validator module at test time
# ---------------------------------------------------------------------------

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "architecture" / "runtime" / "scripts" / "validate_invariants.py"
)


def _load_validator():
    """Import validate_invariants as a module without executing main()."""
    module_name = "validate_invariants"
    spec = importlib.util.spec_from_file_location(module_name, _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod  # register before exec so @dataclass can resolve __module__
    spec.loader.exec_module(mod)
    return mod


_v = _load_validator()
assert_python_requires_pattern = _v.assert_python_requires_pattern
assert_python_forbids_pattern = _v.assert_python_forbids_pattern
Failure = _v.Failure


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ctx(name: str = "test_assertion") -> dict:
    return {
        "invariant_id": "INV-TEST",
        "invariant_title": "Test Invariant",
        "assertion_name": name,
    }


# ---------------------------------------------------------------------------
# python_requires_pattern
# ---------------------------------------------------------------------------

def test_requires_pattern_found_in_file(tmp_path: Path) -> None:
    f = tmp_path / "source.py"
    f.write_text("def to_log_safe(self) -> dict:\n    pass\n")
    spec = {"glob": str(tmp_path / "*.py"), "pattern": "def to_log_safe"}
    failures = assert_python_requires_pattern(spec, _ctx())
    assert failures == []


def test_requires_pattern_not_found_returns_failure(tmp_path: Path) -> None:
    f = tmp_path / "source.py"
    f.write_text("def something_else(): pass\n")
    spec = {"glob": str(tmp_path / "*.py"), "pattern": "def to_log_safe"}
    failures = assert_python_requires_pattern(spec, _ctx())
    assert len(failures) == 1


def test_requires_pattern_no_matching_files_returns_failure(tmp_path: Path) -> None:
    spec = {"glob": str(tmp_path / "*.py"), "pattern": "anything"}
    failures = assert_python_requires_pattern(spec, _ctx())
    assert len(failures) == 1


def test_requires_pattern_no_files_message_cites_glob(tmp_path: Path) -> None:
    spec = {"glob": str(tmp_path / "*.py"), "pattern": "anything"}
    failures = assert_python_requires_pattern(spec, _ctx())
    assert str(tmp_path) in failures[0].message


def test_requires_pattern_missing_message_cites_pattern(tmp_path: Path) -> None:
    f = tmp_path / "source.py"
    f.write_text("x = 1\n")
    spec = {"glob": str(tmp_path / "*.py"), "pattern": "MISSING_PATTERN_XYZ"}
    failures = assert_python_requires_pattern(spec, _ctx())
    assert "MISSING_PATTERN_XYZ" in failures[0].message


def test_requires_pattern_found_in_second_file(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("def target_func(): pass\n")
    spec = {"glob": str(tmp_path / "*.py"), "pattern": "def target_func"}
    failures = assert_python_requires_pattern(spec, _ctx())
    assert failures == []


# ---------------------------------------------------------------------------
# python_forbids_pattern
# ---------------------------------------------------------------------------

def test_forbids_pattern_no_matching_files_is_ok(tmp_path: Path) -> None:
    spec = {"glob": str(tmp_path / "*.py"), "pattern": "forbidden_thing"}
    failures = assert_python_forbids_pattern(spec, _ctx())
    assert failures == []


def test_forbids_pattern_clean_file_returns_no_failures(tmp_path: Path) -> None:
    f = tmp_path / "clean.py"
    f.write_text("x = 1\ny = 2\n")
    spec = {"glob": str(tmp_path / "*.py"), "pattern": "\"memory_values\""}
    failures = assert_python_forbids_pattern(spec, _ctx())
    assert failures == []


def test_forbids_pattern_violation_returns_failure(tmp_path: Path) -> None:
    f = tmp_path / "bad.py"
    f.write_text('log({"memory_values": record.value})\n')
    spec = {"glob": str(tmp_path / "*.py"), "pattern": '"memory_values"'}
    failures = assert_python_forbids_pattern(spec, _ctx())
    assert len(failures) == 1


def test_forbids_pattern_multiple_lines_multiple_failures(tmp_path: Path) -> None:
    f = tmp_path / "bad.py"
    f.write_text(
        'log({"memory_values": x})\n'
        'other_line = 1\n'
        'also({"memory_values": y})\n'
    )
    spec = {"glob": str(tmp_path / "*.py"), "pattern": '"memory_values"'}
    failures = assert_python_forbids_pattern(spec, _ctx())
    assert len(failures) == 2


def test_forbids_pattern_failure_message_cites_file_and_line(tmp_path: Path) -> None:
    f = tmp_path / "offender.py"
    f.write_text('x = 1\nlog({"memory_values": v})\n')
    spec = {"glob": str(tmp_path / "*.py"), "pattern": '"memory_values"'}
    failures = assert_python_forbids_pattern(spec, _ctx())
    assert len(failures) == 1
    assert "offender.py" in failures[0].message
    assert ":2" in failures[0].message  # line 2


# ---------------------------------------------------------------------------
# Integration — INV-005 passes against current codebase
# ---------------------------------------------------------------------------

def test_inv005_passes_against_current_codebase() -> None:
    """INV-005 assertions all pass; covered by test_invariants_validator_script_passes
    but also explicitly verified here for M6.5 clarity."""
    import subprocess

    repo_root = Path(_SCRIPT_PATH).resolve().parents[3]
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH)],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"Invariant validator failed (INV-005 may be failing).\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    assert "INV-005" in proc.stdout
    assert "FAIL  INV-005" not in proc.stdout
