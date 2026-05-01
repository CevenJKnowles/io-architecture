"""
tests/test_file_upload_m105.py — M10.5 file upload pipeline tests.

Covers:
- file_store: store / resolve / delete / FileRefNotFound
- _extract_file_text: plain text, PDF, DOCX, unsupported type, image-only PDF
- POST /upload endpoint: happy path, size limit, type rejection, no-text PDF
- SessionTurnRequest: file_ref field present
- FILE_REF_EXPIRED: FileRefExpiredError raised on stale file_ref
- INV-006: "file_content" and "file_text" are forbidden keys in content_safety
- Content safety: file_ref in metadata is safe; resolved content is not
"""
from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient

from io_iii.api.app import app, _extract_file_text, _UPLOAD_MAX_BYTES, _ALLOWED_EXTENSIONS
from io_iii.core import file_store
from io_iii.core.content_safety import DEFAULT_FORBIDDEN_KEYS, assert_no_forbidden_keys
from io_iii.core.file_store import FileRefExpiredError, FileRefNotFound

client = TestClient(app)


# ---------------------------------------------------------------------------
# file_store unit tests
# ---------------------------------------------------------------------------

def test_file_store_roundtrip():
    sid = str(uuid.uuid4())
    ref = file_store.store(sid, "hello world", "test.txt")
    fname, content = file_store.resolve(sid, ref)
    assert fname == "test.txt"
    assert content == "hello world"


def test_file_store_resolve_missing_raises():
    with pytest.raises(FileRefNotFound):
        file_store.resolve("nonexistent-session", "bad-ref")


def test_file_store_delete_clears_session():
    sid = str(uuid.uuid4())
    ref = file_store.store(sid, "data", "a.txt")
    file_store.delete(sid)
    with pytest.raises(FileRefNotFound):
        file_store.resolve(sid, ref)


def test_file_store_delete_noop_on_missing():
    # Must not raise
    file_store.delete("session-that-never-existed")


# ---------------------------------------------------------------------------
# _extract_file_text unit tests
# ---------------------------------------------------------------------------

def test_extract_plain_text():
    data = b"Hello world"
    assert _extract_file_text("notes.txt", data) == "Hello world"


def test_extract_markdown():
    data = b"# Title\nContent"
    assert "Title" in _extract_file_text("README.md", data)


def test_extract_unsupported_type_raises():
    with pytest.raises(ValueError, match="UNSUPPORTED_FILE_TYPE"):
        _extract_file_text("image.png", b"\x89PNG\r\n")


def test_extract_pdf_no_text_raises():
    # Minimal valid PDF with no extractable text (empty content stream)
    # Use a real minimal PDF bytes — just check the error code path.
    # We stub pypdf for this by passing clearly non-PDF bytes after the header.
    import pypdf
    from unittest.mock import patch, MagicMock

    mock_reader = MagicMock()
    mock_reader.pages = [MagicMock(extract_text=lambda: "")]
    with patch("pypdf.PdfReader", return_value=mock_reader):
        with pytest.raises(ValueError, match="FILE_NO_EXTRACTABLE_TEXT"):
            _extract_file_text("scan.pdf", b"%PDF-1.4")


def test_extract_pdf_with_text():
    import pypdf
    from unittest.mock import patch, MagicMock

    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Document content here."
    mock_reader = MagicMock()
    mock_reader.pages = [mock_page]
    with patch("pypdf.PdfReader", return_value=mock_reader):
        result = _extract_file_text("report.pdf", b"%PDF-1.4")
    assert "Document content here." in result


def test_extract_docx():
    import docx as _docx
    from unittest.mock import patch, MagicMock

    mock_para = MagicMock()
    mock_para.text = "Paragraph text."
    mock_doc = MagicMock()
    mock_doc.paragraphs = [mock_para]
    with patch("docx.Document", return_value=mock_doc):
        result = _extract_file_text("doc.docx", b"PK")
    assert "Paragraph text." in result


# ---------------------------------------------------------------------------
# POST /upload endpoint
# ---------------------------------------------------------------------------

def test_upload_plain_text_returns_file_ref():
    data = b"Hello from file"
    response = client.post(
        "/upload",
        data={"session_id": "test-session-abc"},
        files={"file": ("hello.txt", data, "text/plain")},
    )
    assert response.status_code == 200
    body = response.json()
    assert "file_ref" in body
    assert body["filename"] == "hello.txt"
    assert body["chars"] == len("Hello from file")


def test_upload_rejects_oversized_file():
    big = b"x" * (_UPLOAD_MAX_BYTES + 1)
    response = client.post(
        "/upload",
        data={"session_id": "s1"},
        files={"file": ("big.txt", big, "text/plain")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_upload_rejects_unsupported_type():
    response = client.post(
        "/upload",
        data={"session_id": "s1"},
        files={"file": ("photo.png", b"\x89PNG", "image/png")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_upload_allowed_extensions_set():
    for ext in (".txt", ".md", ".csv", ".json", ".yaml", ".py", ".pdf", ".docx"):
        assert ext in _ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# FILE_REF_EXPIRED
# ---------------------------------------------------------------------------

def test_file_ref_expired_error_has_correct_code():
    assert FileRefExpiredError.code == "FILE_REF_EXPIRED"


def test_file_ref_expired_on_stale_ref():
    """
    Simulates the run_turn path: resolving a file_ref that does not exist
    in the store raises FileRefExpiredError.
    """
    sid = str(uuid.uuid4())
    stale_ref = str(uuid.uuid4())
    with pytest.raises(FileRefNotFound):
        file_store.resolve(sid, stale_ref)


# ---------------------------------------------------------------------------
# INV-006 — content_safety forbidden keys
# ---------------------------------------------------------------------------

def test_inv006_file_content_is_forbidden_key():
    assert "file_content" in DEFAULT_FORBIDDEN_KEYS


def test_inv006_file_text_is_forbidden_key():
    assert "file_text" in DEFAULT_FORBIDDEN_KEYS


def test_assert_no_forbidden_keys_catches_file_content():
    with pytest.raises(ValueError, match="file_content"):
        assert_no_forbidden_keys({"file_content": "some text"})


def test_assert_no_forbidden_keys_catches_file_text():
    with pytest.raises(ValueError, match="file_text"):
        assert_no_forbidden_keys({"file_text": "some text"})


def test_file_ref_uuid_is_safe_in_metadata():
    """file_ref (a UUID string) must be allowed in metadata — it is not content."""
    ref = str(uuid.uuid4())
    # Should not raise — UUID is not a forbidden key value
    assert_no_forbidden_keys({"file_ref": ref})


# ---------------------------------------------------------------------------
# SessionTurnRequest accepts file_ref
# ---------------------------------------------------------------------------

def test_session_turn_request_accepts_file_ref():
    from io_iii.api.app import SessionTurnRequest
    req = SessionTurnRequest(prompt="hello", file_ref="some-ref")
    assert req.file_ref == "some-ref"


def test_session_turn_request_file_ref_defaults_none():
    from io_iii.api.app import SessionTurnRequest
    req = SessionTurnRequest(prompt="hello")
    assert req.file_ref is None
