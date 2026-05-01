"""
io_iii.api.app — Phase 9 HTTP API (ADR-025).

Transport adapter only: every endpoint wraps an existing CLI command function
by constructing an argparse.Namespace from the request body and capturing stdout
as the response payload.  Zero new execution semantics (ADR-025 §1).

Routes (ADR-025 §2):
    POST   /run                      → cmd_run
    POST   /runbook                  → cmd_runbook
    POST   /session/start            → cmd_session_start
    POST   /session/{id}/turn        → cmd_session_continue
    GET    /session/{id}/state       → cmd_session_status
    DELETE /session/{id}             → cmd_session_close
    GET    /session/{id}/stream      → SSE event stream (M9.2)
    GET    /health                   → liveness probe
    GET    /                         → static web UI (M9.5)

Content-safety (ADR-003): no prompt text, model output, persona content,
or memory values appear in any response body or SSE event.
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import io as _io
import json
import os
import time
from argparse import Namespace
from pathlib import Path, Path as _Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from io_iii.api import _bus as bus
from io_iii.api import _webhooks as webhooks

_UPLOAD_MAX_BYTES = 2 * 1024 * 1024  # 2 MB (ADR-029 §3)
_ALLOWED_EXTENSIONS = frozenset(
    {".txt", ".md", ".csv", ".json", ".yaml", ".py", ".pdf", ".docx"}
)

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="IO-III Runtime API",
    description="Transport adapter for the IO-III governed LLM control-plane runtime.",
    version="0.9.0",
    docs_url="/docs",
    redoc_url=None,
)

# ---------------------------------------------------------------------------
# CLI command import (lazy to keep startup fast)
# ---------------------------------------------------------------------------

def _cli():
    """Return the io_iii.cli module (import once)."""
    import io_iii.cli as _m
    return _m


# ---------------------------------------------------------------------------
# Invocation helper (ADR-025 §3)
# ---------------------------------------------------------------------------

def _invoke(cmd_fn, args_ns: Namespace) -> tuple[int, Dict[str, Any]]:
    """
    Call *cmd_fn(args_ns)* with stdout captured.

    Returns (exit_code, result_dict).  result_dict is parsed from the captured
    JSON output.  If the command prints nothing, result_dict is {}.
    Raises RuntimeError on non-JSON output (should never happen).
    """
    buf = io.StringIO()
    exit_code: int
    with contextlib.redirect_stdout(buf):
        try:
            exit_code = int(cmd_fn(args_ns))
        except SystemExit as exc:
            exit_code = int(exc.code) if exc.code is not None else 1
        except Exception as exc:
            # Surface the error code but do not expose message/stack.
            exit_code = 1
            buf.write(json.dumps({"status": "error", "error_code": type(exc).__name__}))

    raw = buf.getvalue().strip()
    if not raw:
        return exit_code, {}
    try:
        return exit_code, json.loads(raw)
    except json.JSONDecodeError:
        return exit_code, {"status": "error", "error_code": "INVALID_JSON_OUTPUT"}


def _http_status(exit_code: int) -> int:
    return 200 if exit_code == 0 else 422


def _cfg_dir(config_dir: Optional[str]) -> Optional[Path]:
    return Path(config_dir) if config_dir else None


# ---------------------------------------------------------------------------
# Request schemas (Pydantic)
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    mode: str
    prompt: Optional[str] = None
    audit: bool = False
    capability_id: Optional[str] = None
    capability_payload_json: Optional[str] = None
    no_health_check: bool = False
    no_constellation_check: bool = False
    config_dir: Optional[str] = None


class RunbookRequest(BaseModel):
    json_file: str
    audit: bool = False
    config_dir: Optional[str] = None


class SessionStartRequest(BaseModel):
    mode: str = "work"
    persona_mode: str = "executor"
    prompt: Optional[str] = None
    audit: bool = False
    config_dir: Optional[str] = None


class SessionTurnRequest(BaseModel):
    prompt: Optional[str] = None
    persona_mode: str = "executor"
    audit: bool = False
    action: Optional[str] = None
    config_dir: Optional[str] = None
    file_ref: Optional[str] = None          # ADR-029


# ---------------------------------------------------------------------------
# Webhook helper
# ---------------------------------------------------------------------------

def _runtime_cfg() -> Dict[str, Any]:
    """Load runtime config dict (best-effort; returns {} on failure)."""
    try:
        from io_iii.config import load_io3_config
        cfg = load_io3_config()
        return cfg.runtime
    except Exception:
        return {}


def _content_release_enabled() -> bool:
    """
    Return True when the operator has enabled the content release gate (ADR-026).

    Reads runtime.yaml per-request so the setting can be toggled without restart.
    Defaults to False (content-safe) when absent or unreadable.
    """
    return bool(_runtime_cfg().get("content_release", False))


def _extract_response(raw_result: Dict[str, Any], release: bool) -> Dict[str, Any]:
    """
    When the content release gate is open, lift the engine ``message`` field
    into a top-level ``response`` field on the API result (ADR-026 §3).

    ``_strip_content`` has already removed ``message``; we need the pre-strip
    value, so callers pass the raw CLI result before stripping.

    Checks two locations:
    - top-level ``message`` (session turn output from _emit_turn_result)
    - nested ``result.message`` (cmd_run payload structure)
    """
    if not release:
        return {}
    # Session turn path: top-level message key
    msg = raw_result.get("message")
    # cmd_run path: nested under result dict
    if msg is None:
        msg = (raw_result.get("result") or {}).get("message")
    if not msg:
        return {}
    return {"response": msg}


# ---------------------------------------------------------------------------
# Routes: POST /run
# ---------------------------------------------------------------------------

@app.post("/run")
def api_run(req: RunRequest) -> JSONResponse:
    """
    Execute a single run.  Transport adapter for cmd_run (ADR-025 §2).

    Content-safe response: no prompt text or model output.
    """
    args = Namespace(
        mode=req.mode,
        prompt=req.prompt,
        audit=req.audit,
        capability_id=req.capability_id,
        capability_payload_json=req.capability_payload_json,
        no_health_check=req.no_health_check,
        no_constellation_check=req.no_constellation_check,
        config_dir=str(_cfg_dir(req.config_dir)) if req.config_dir else None,
    )
    release = _content_release_enabled()
    exit_code, raw_result = _invoke(_cli().cmd_run, args)
    response_field = _extract_response(raw_result, release)
    result = _strip_content(raw_result)
    result.update(response_field)
    return JSONResponse(content=result, status_code=_http_status(exit_code))


# ---------------------------------------------------------------------------
# Routes: POST /runbook
# ---------------------------------------------------------------------------

@app.post("/runbook")
def api_runbook(req: RunbookRequest) -> JSONResponse:
    """
    Execute a runbook.  Transport adapter for cmd_runbook (ADR-025 §2).

    Fires RUNBOOK_COMPLETE webhook on completion (M9.3).
    """
    args = Namespace(
        json_file=req.json_file,
        audit=req.audit,
        config_dir=str(_cfg_dir(req.config_dir)) if req.config_dir else None,
    )
    exit_code, result = _invoke(_cli().cmd_runbook, args)
    result = _strip_content(result)

    # M9.3: webhook on RUNBOOK_COMPLETE
    runtime_cfg = _runtime_cfg()
    webhook_url = webhooks.get_webhook_url(runtime_cfg)
    webhooks.dispatch(webhook_url, "RUNBOOK_COMPLETE", {
        "runbook_id": result.get("runbook_id"),
        "status": result.get("status"),
        "steps_completed": result.get("steps_completed"),
    })

    return JSONResponse(content=result, status_code=_http_status(exit_code))


# ---------------------------------------------------------------------------
# Routes: POST /session/start
# ---------------------------------------------------------------------------

@app.post("/session/start")
def api_session_start(req: SessionStartRequest) -> JSONResponse:
    """
    Start a new dialogue session.  Transport adapter for cmd_session_start.
    """
    args = Namespace(
        mode=req.mode,
        persona_mode=req.persona_mode,
        prompt=req.prompt,
        audit=req.audit,
        config_dir=str(_cfg_dir(req.config_dir)) if req.config_dir else None,
    )
    exit_code, result = _invoke(_cli().cmd_session_start, args)
    result = _strip_content(result)

    # Publish initial session_state event so SSE subscribers see it immediately.
    session_id = result.get("session_id")
    if session_id:
        bus.publish(session_id, "session_state", {
            "session_id": session_id,
            "status": result.get("status") or result.get("session_status"),
            "turn_count": result.get("turn_count", 0),
            "session_mode": result.get("session_mode"),
        })

    return JSONResponse(content=result, status_code=_http_status(exit_code))


# ---------------------------------------------------------------------------
# Routes: POST /session/{id}/turn
# ---------------------------------------------------------------------------

@app.post("/session/{session_id}/turn")
def api_session_turn(session_id: str, req: SessionTurnRequest) -> JSONResponse:
    """
    Execute one turn on an existing session.

    Transport adapter for cmd_session_continue.  Publishes content-safe events
    to the SSE bus before and after execution (M9.2).  Fires webhooks on
    STEWARD_GATE_TRIGGERED and SESSION_COMPLETE (M9.3).
    """
    args = Namespace(
        session_id=session_id,
        prompt=req.prompt,
        persona_mode=req.persona_mode,
        audit=req.audit,
        action=req.action,
        config_dir=str(_cfg_dir(req.config_dir)) if req.config_dir else None,
        file_ref=req.file_ref,
    )

    # Publish turn_started before execution.
    bus.publish(session_id, "turn_started", {
        "session_id": session_id,
        "ts": time.time(),
    })

    release = _content_release_enabled()
    t0 = time.perf_counter()
    exit_code, raw_result = _invoke(_cli().cmd_session_continue, args)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    response_field = _extract_response(raw_result, release)
    result = _strip_content(raw_result)
    result.update(response_field)

    # Publish turn_completed.
    turn_payload: Dict[str, Any] = {
        "session_id": session_id,
        "turn_index": result.get("turn_index"),
        "status": result.get("status"),
        "latency_ms": result.get("latency_ms", latency_ms),
        "session_status": result.get("session_status"),
        "turn_count": result.get("turn_count"),
    }
    bus.publish(session_id, "turn_completed", turn_payload)

    # Derive session status from result to fire targeted webhooks (M9.3).
    session_status = result.get("session_status") or result.get("status")
    runtime_cfg = _runtime_cfg()
    webhook_url = webhooks.get_webhook_url(runtime_cfg)

    if session_status == "paused":
        pause_info = result.get("pause") or {}
        bus.publish(session_id, "steward_gate_triggered", {
            "session_id": session_id,
            "threshold_key": pause_info.get("threshold_key"),
            "step_index": pause_info.get("step_index"),
        })
        webhooks.dispatch(webhook_url, "STEWARD_GATE_TRIGGERED", {
            "session_id": session_id,
            "threshold_key": pause_info.get("threshold_key"),
        })

    if session_status in ("closed", "at_limit"):
        bus.publish(session_id, "session_closed", {
            "session_id": session_id,
            "session_status": session_status,
            "turn_count": result.get("turn_count"),
        })
        webhooks.dispatch(webhook_url, "SESSION_COMPLETE", {
            "session_id": session_id,
            "session_status": session_status,
            "turn_count": result.get("turn_count"),
        })

    return JSONResponse(content=result, status_code=_http_status(exit_code))


# ---------------------------------------------------------------------------
# Routes: GET /session/{id}/state
# ---------------------------------------------------------------------------

@app.get("/session/{session_id}/state")
def api_session_state(session_id: str, config_dir: Optional[str] = None) -> JSONResponse:
    """
    Return content-safe session status.  Transport adapter for cmd_session_status.
    """
    args = Namespace(
        session_id=session_id,
        config_dir=config_dir,
    )
    exit_code, result = _invoke(_cli().cmd_session_status, args)
    result = _strip_content(result)
    return JSONResponse(content=result, status_code=_http_status(exit_code))


# ---------------------------------------------------------------------------
# Routes: DELETE /session/{id}
# ---------------------------------------------------------------------------

@app.delete("/session/{session_id}")
def api_session_close(session_id: str, config_dir: Optional[str] = None) -> JSONResponse:
    """
    Close a session.  Transport adapter for cmd_session_close.

    Fires SESSION_COMPLETE webhook and publishes session_closed event (M9.3).
    """
    args = Namespace(
        session_id=session_id,
        config_dir=config_dir,
    )
    exit_code, result = _invoke(_cli().cmd_session_close, args)
    result = _strip_content(result)
    # ADR-033 §6: clean up in-memory file store on session close.
    from io_iii.core.file_store import delete as _fs_delete
    _fs_delete(session_id)

    if exit_code == 0:
        bus.publish(session_id, "session_closed", {
            "session_id": session_id,
            "session_status": result.get("status"),
            "turn_count": result.get("turn_count"),
        })
        runtime_cfg = _runtime_cfg()
        webhook_url = webhooks.get_webhook_url(runtime_cfg)
        webhooks.dispatch(webhook_url, "SESSION_COMPLETE", {
            "session_id": session_id,
            "session_status": result.get("status"),
            "turn_count": result.get("turn_count"),
        })

    return JSONResponse(content=result, status_code=_http_status(exit_code))


# ---------------------------------------------------------------------------
# Routes: GET /session/{id}/stream  — SSE (M9.2)
# ---------------------------------------------------------------------------

_SSE_POLL_INTERVAL = 1.0   # seconds between polls (override in tests via monkeypatching)
_SSE_KEEPALIVE_EVERY = 30  # keepalive every N polls


@app.get("/session/{session_id}/stream")
async def api_session_stream(session_id: str) -> StreamingResponse:
    """
    Server-Sent Events stream for a session.  Content-safe events only (ADR-025 §4).

    Emits:
        session_state           — current state on connect
        turn_started            — before a turn runs
        turn_completed          — after a turn completes
        steward_gate_triggered  — on steward pause
        session_closed          — on session close / at_limit
        keepalive               — every 30 s of inactivity

    Event data fields are structural metadata only (ADR-003).
    No prompt text, model output, or memory values.
    """
    async def generate():
        cursor = 0
        idle_polls = 0

        # Emit current session state on connect.
        try:
            state_args = Namespace(session_id=session_id, config_dir=None)
            _, state_result = _invoke(_cli().cmd_session_status, state_args)
            state_result = _strip_content(state_result)
            yield _sse("session_state", state_result)
        except Exception:
            pass

        while True:
            await asyncio.sleep(_SSE_POLL_INTERVAL)
            events = bus.get_events_since(session_id, cursor)
            if events:
                idle_polls = 0
                for evt in events:
                    cursor += 1
                    # Sentinel: terminate generator cleanly (no yield).
                    if evt["event"] == bus.STREAM_CLOSE_EVENT:
                        return
                    yield _sse(evt["event"], evt["data"])
            else:
                idle_polls += 1
                if idle_polls >= _SSE_KEEPALIVE_EVERY:
                    idle_polls = 0
                    yield _sse("keepalive", {})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event_type: str, data: Dict[str, Any]) -> str:
    """Format a single SSE message."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Routes: GET /health
# ---------------------------------------------------------------------------

@app.get("/health")
def api_health() -> JSONResponse:
    """Liveness probe.  No execution; no content-plane access."""
    return JSONResponse({"status": "ok", "runtime": "io-iii"})


# ---------------------------------------------------------------------------
# Routes: POST /upload  — server-side file upload (ADR-029, M10.5)
# ---------------------------------------------------------------------------

def _extract_file_text(filename: str, data: bytes) -> str:
    """
    Extract plain text from uploaded file bytes.
    Raises ValueError with a structured error code on failure.
    Content-safe: never logs extracted text.
    """
    ext = _Path(filename).suffix.lower()
    if ext in {".txt", ".md", ".csv", ".json", ".yaml", ".py"}:
        return data.decode("utf-8", errors="replace")
    if ext == ".pdf":
        import pypdf
        reader = pypdf.PdfReader(_io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if not text.strip():
            raise ValueError("FILE_NO_EXTRACTABLE_TEXT")
        return text
    if ext == ".docx":
        import docx
        doc = docx.Document(_io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text)
    raise ValueError("UNSUPPORTED_FILE_TYPE")


@app.post("/upload")
async def api_upload(
    file: UploadFile,
    session_id: str = Form(...),
) -> JSONResponse:
    """
    Accept a multipart file upload, extract text, store session-scoped.
    Returns {file_ref, filename, chars} on success.
    Content-safe: extracted text is never logged (ADR-029 §4, ADR-033 §3).
    """
    from io_iii.core import file_store

    data = await file.read()

    if len(data) > _UPLOAD_MAX_BYTES:
        return JSONResponse(
            {"error": {"code": "FILE_TOO_LARGE", "message": "File exceeds 2 MB limit."}},
            status_code=422,
        )

    filename = file.filename or "upload"
    ext = _Path(filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        return JSONResponse(
            {
                "error": {
                    "code": "UNSUPPORTED_FILE_TYPE",
                    "message": f"File type '{ext}' is not supported. "
                    f"Accepted: .txt .md .csv .json .yaml .py .pdf .docx",
                }
            },
            status_code=422,
        )

    try:
        text = _extract_file_text(filename, data)
    except ValueError as exc:
        code = str(exc)
        return JSONResponse(
            {"error": {"code": code, "message": "Could not extract text from file."}},
            status_code=422,
        )

    file_ref = file_store.store(session_id, text, filename)
    # Return structural metadata only — never the extracted text.
    return JSONResponse({"file_ref": file_ref, "filename": filename, "chars": len(text)})


# ---------------------------------------------------------------------------
# Routes: GET /  — static web UI (M9.5)
# ---------------------------------------------------------------------------

_STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", response_class=HTMLResponse)
def api_ui() -> HTMLResponse:
    """Serve the self-hosted web UI (M9.5)."""
    index = _STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="UI not found")
    return HTMLResponse(content=index.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Content-safety strip (ADR-003)
# ---------------------------------------------------------------------------

# Keys that may contain raw content and must never appear in API responses.
_UNSAFE_KEYS = frozenset({
    "message",         # model response text
    "prompt",          # user prompt text
    "persona_content", # persona system prompt
    "value",           # memory values
    "logging_policy",  # internal logging config (not content, but internal)
})


def _strip_content(obj: Any) -> Any:
    """
    Recursively remove content-unsafe keys from a dict (ADR-003).

    The ``message`` field from engine results contains model output.
    ``prompt`` would expose user input.  Both are stripped at the API boundary.
    Nested dicts are also cleaned.
    """
    if isinstance(obj, dict):
        return {
            k: _strip_content(v)
            for k, v in obj.items()
            if k not in _UNSAFE_KEYS
        }
    if isinstance(obj, list):
        return [_strip_content(item) for item in obj]
    return obj
