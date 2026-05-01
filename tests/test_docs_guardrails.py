from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_contributing_exists() -> None:
    assert (REPO_ROOT / "CONTRIBUTING.md").is_file()


def test_phase4_guide_exists() -> None:
    assert (
        REPO_ROOT / "docs" / "architecture" / "DOC-ARCH-012-phase-4-guide.md"
    ).is_file()
