"""
io_iii.api.server — HTTP API server (Phase 9 M9.1, ADR-025).

Single-threaded HTTP/1.1 server using Python stdlib http.server.
No external framework dependency (ADR-025 §8).

Endpoints (ADR-025 §3):
    POST   /run                     — single-turn execution
    POST   /runbook                 — runbook execution
    POST   /session/start           — start a new dialogue session
    POST   /session/{id}/turn       — run one turn on an existing session
    GET    /session/{id}/state      — session status summary (content-safe)
    DELETE /session/{id}            — close a session
    GET    /session/{id}/stream     — SSE stream for one turn (M9.2)
    GET    /                        — self-hosted web UI (M9.5)

Start via CLI:
    python -m io_iii serve [--host 127.0.0.1] [--port 8080]

Default bind: 127.0.0.1:8080 (loopback only; ADR-025 §8).

Content policy (ADR-003 / ADR-025):
    All JSON responses from session endpoints are content-safe.
    POST /run and POST /runbook responses include model output (primary surface).
    SSE turn_output event carries model output (ADR-025 §5).
    Webhook payloads are strictly content-safe (ADR-025 §6).
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from io_iii.api._handlers import (
    handle_run,
    handle_runbook,
    handle_session_delete,
    handle_session_start,
    handle_session_state,
    handle_session_turn,
)
from io_iii.api._sse import stream_session_turn
from io_iii.api._webhooks import (
    WEBHOOK_RUNBOOK_COMPLETE,
    WEBHOOK_SESSION_COMPLETE,
    WEBHOOK_STEWARD_GATE_TRIGGERED,
    WebhookDispatcher,
)
from io_iii.config import load_io3_config, default_config_dir

# Path to bundled web UI static file (M9.5)
_STATIC_DIR: Path = Path(__file__).parent / "static"
_UI_PATH: Path = _STATIC_DIR / "index.html"


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

def _make_handler(cfg, dispatcher: WebhookDispatcher):
    """
    Factory that creates a request handler class with cfg and dispatcher injected.

    Returns a BaseHTTPRequestHandler subclass. Using a factory avoids the need
    for global state — each server instance gets its own handler class with the
    correct config bound in.
    """

    class _APIHandler(BaseHTTPRequestHandler):
        _cfg = cfg
        _dispatcher = dispatcher

        # ------------------------------------------------------------------
        # Logging — suppress default request log lines (use stderr only for errors)
        # ------------------------------------------------------------------

        def log_message(self, fmt: str, *args) -> None:  # type: ignore[override]
            # Suppress to keep stdout clean; errors go through log_error()
            pass

        def log_error(self, fmt: str, *args) -> None:  # type: ignore[override]
            print(f"API_ERROR: {fmt % args}", file=sys.stderr)

        # ------------------------------------------------------------------
        # Routing helpers
        # ------------------------------------------------------------------

        def _parse_path(self) -> Tuple[str, Dict[str, str]]:
            """Return (clean_path, query_params)."""
            parsed = urlparse(self.path)
            raw_qs = parse_qs(parsed.query, keep_blank_values=False)
            # Flatten single-value lists from parse_qs
            params = {k: v[0] for k, v in raw_qs.items() if v}
            return parsed.path.rstrip("/"), params

        def _read_json_body(self) -> Tuple[Optional[dict], Optional[str]]:
            """Read and decode request body as JSON. Returns (body, error_code)."""
            length_raw = self.headers.get("Content-Length", "0")
            try:
                length = int(length_raw)
            except (ValueError, TypeError):
                length = 0
            if length == 0:
                return {}, None
            raw = self.rfile.read(length)
            try:
                obj = json.loads(raw)
                if not isinstance(obj, dict):
                    return None, "INVALID_REQUEST_BODY"
                return obj, None
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None, "INVALID_REQUEST_BODY"

        # ------------------------------------------------------------------
        # Response helpers
        # ------------------------------------------------------------------

        def _send_json(self, status: int, body: dict) -> None:
            payload = json.dumps(body, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload)

        def _send_sse_headers(self) -> None:
            """Write SSE response headers and leave connection open."""
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

        def _send_cors_preflight(self) -> None:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        # ------------------------------------------------------------------
        # Session ID extraction from path
        # ------------------------------------------------------------------

        @staticmethod
        def _session_id_from_path(path: str, suffix: str) -> Optional[str]:
            """
            Extract session_id from /session/{id}/{suffix}.
            Returns None if path does not match.
            """
            # e.g. /session/abc123/turn -> ["", "session", "abc123", "turn"]
            parts = path.split("/")
            if len(parts) >= 4 and parts[1] == "session" and parts[3] == suffix:
                return parts[2] if parts[2] else None
            return None

        @staticmethod
        def _session_id_bare(path: str) -> Optional[str]:
            """
            Extract session_id from DELETE /session/{id}.
            Matches exactly /session/{id} with no trailing component.
            """
            parts = path.split("/")
            if len(parts) == 3 and parts[1] == "session" and parts[2]:
                return parts[2]
            return None

        # ------------------------------------------------------------------
        # CORS preflight
        # ------------------------------------------------------------------

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._send_cors_preflight()

        # ------------------------------------------------------------------
        # POST
        # ------------------------------------------------------------------

        def do_POST(self) -> None:  # noqa: N802
            path, _ = self._parse_path()
            body, err = self._read_json_body()
            if err:
                self._send_json(400, {"status": "error", "error_code": err})
                return

            if path == "/run":
                status, resp = handle_run(body, self._cfg)
                self._send_json(status, resp)

            elif path == "/runbook":
                status, resp = handle_runbook(body, self._cfg)
                self._send_json(status, resp)
                if status == 200 and resp.get("status") == "ok":
                    self._dispatcher.dispatch(WEBHOOK_RUNBOOK_COMPLETE, {
                        "runbook_id": resp.get("runbook_id"),
                        "steps_total": resp.get("steps_total"),
                        "steps_completed": resp.get("steps_completed"),
                        "failed_step_index": resp.get("failed_step_index"),
                    })

            elif path == "/session/start":
                status, resp = handle_session_start(body, self._cfg)
                self._send_json(status, resp)

            else:
                session_id = self._session_id_from_path(path, "turn")
                if session_id:
                    status, resp = handle_session_turn(session_id, body, self._cfg)
                    self._send_json(status, resp)
                    # Fire webhooks after response is sent
                    if resp.get("session_status") == "closed" or resp.get("status") == SESSION_STATUS_CLOSED:
                        self._dispatcher.dispatch(WEBHOOK_SESSION_COMPLETE, {
                            "session_id": session_id,
                            "turn_count": resp.get("turn_count"),
                        })
                    elif resp.get("pause"):
                        self._dispatcher.dispatch(WEBHOOK_STEWARD_GATE_TRIGGERED, {
                            "session_id": session_id,
                            "threshold_key": resp["pause"].get("threshold_key"),
                            "step_index": resp["pause"].get("step_index"),
                            "session_mode": resp["pause"].get("session_mode"),
                            "run_id": resp["pause"].get("run_id"),
                        })
                    return

                self._send_json(404, {"status": "error", "error_code": "NOT_FOUND"})

        # ------------------------------------------------------------------
        # GET
        # ------------------------------------------------------------------

        def do_GET(self) -> None:  # noqa: N802
            path, params = self._parse_path()

            # Web UI (M9.5)
            if path in ("", "/", "/index.html"):
                self._serve_ui()
                return

            # SSE session stream (M9.2)
            session_id = self._session_id_from_path(path, "stream")
            if session_id:
                prompt = params.get("prompt", "")
                if not prompt:
                    self._send_json(400, {
                        "status": "error",
                        "error_code": "PROMPT_REQUIRED",
                        "detail": "prompt query parameter is required",
                    })
                    return
                persona_mode = params.get("persona_mode", "executor")
                audit = params.get("audit", "false").lower() == "true"
                self._send_sse_headers()
                stream_session_turn(
                    session_id=session_id,
                    prompt=prompt,
                    cfg=self._cfg,
                    wfile=self.wfile,
                    persona_mode=persona_mode,
                    audit=audit,
                )
                return

            # Session state
            session_id = self._session_id_from_path(path, "state")
            if session_id:
                status, resp = handle_session_state(session_id, self._cfg)
                self._send_json(status, resp)
                return

            self._send_json(404, {"status": "error", "error_code": "NOT_FOUND"})

        # ------------------------------------------------------------------
        # DELETE
        # ------------------------------------------------------------------

        def do_DELETE(self) -> None:  # noqa: N802
            path, _ = self._parse_path()
            session_id = self._session_id_bare(path)
            if session_id:
                status, resp = handle_session_delete(session_id, self._cfg)
                self._send_json(status, resp)
                if status == 200:
                    self._dispatcher.dispatch(WEBHOOK_SESSION_COMPLETE, {
                        "session_id": session_id,
                        "turn_count": resp.get("turn_count"),
                    })
                return
            self._send_json(404, {"status": "error", "error_code": "NOT_FOUND"})

        # ------------------------------------------------------------------
        # Web UI (M9.5)
        # ------------------------------------------------------------------

        def _serve_ui(self) -> None:
            if not _UI_PATH.exists():
                self._send_json(503, {
                    "status": "error",
                    "error_code": "UI_NOT_AVAILABLE",
                })
                return
            content = _UI_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return _APIHandler


# Needed inside the handler for webhook dispatch comparison
from io_iii.core.dialogue_session import SESSION_STATUS_CLOSED  # noqa: E402


# ---------------------------------------------------------------------------
# Server entrypoint
# ---------------------------------------------------------------------------

def start_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    cfg_dir: Optional[Path] = None,
) -> None:
    """
    Start the IO-III HTTP API server (ADR-025 §8).

    Blocks until interrupted (Ctrl-C / SIGINT).

    Args:
        host:    bind address (default: 127.0.0.1 — loopback only)
        port:    listen port (default: 8080)
        cfg_dir: path to IO-III config directory (default: auto-detected)
    """
    if cfg_dir is None:
        cfg_dir = default_config_dir()

    cfg = load_io3_config(cfg_dir)
    dispatcher = WebhookDispatcher.from_runtime_config(cfg.runtime)
    handler_cls = _make_handler(cfg, dispatcher)

    server = HTTPServer((host, port), handler_cls)
    print(
        f"IO-III API server listening on http://{host}:{port}/ "
        f"(config: {cfg_dir})",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nIO-III API server stopped.", file=sys.stderr)
    finally:
        server.server_close()


# ---------------------------------------------------------------------------
# CLI serve command handler
# ---------------------------------------------------------------------------

def cmd_serve(args) -> int:
    """
    CLI handler for: python -m io_iii serve [--host H] [--port P]

    Phase 9 M9.1 (ADR-025 §8).
    """
    host = getattr(args, "host", "127.0.0.1") or "127.0.0.1"
    port = int(getattr(args, "port", 8080) or 8080)
    cfg_dir_raw = getattr(args, "config_dir", None)
    cfg_dir = Path(cfg_dir_raw) if cfg_dir_raw else None

    try:
        start_server(host=host, port=port, cfg_dir=cfg_dir)
    except OSError as e:
        print(f"API_SERVER_FAILED: {e}", file=sys.stderr)
        return 2  # configuration/binding error → exit code 2

    return 0
