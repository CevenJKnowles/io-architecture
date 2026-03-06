from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_contributing_exists() -> None:
    assert (REPO_ROOT / "CONTRIBUTING.md").is_file()


def test_phase4_guide_exists() -> None:
    assert (REPO_ROOT / "docs" / "architecture" / "DOC-ARCH-012-phase-4-guide.md").is_file()


def test_session_state_doc_updated_to_v032() -> None:
    p = REPO_ROOT / "docs" / "overview" / "DOC-OVW-006-io-iii-session-state-2026-03-06.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "version: v0.3.2" in text
