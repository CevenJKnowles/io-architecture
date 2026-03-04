import types

import io_iii.cli as cli


def test_cli_logs_capability_summary_fields_only(monkeypatch):
    # Arrange: local deterministic config + routing
    fake_cfg = types.SimpleNamespace(
        config_dir=".",
        providers={},
        routing={"routing_table": {}},
        logging={"schema": "test"},
    )

    monkeypatch.setattr(cli, "load_io3_config", lambda _d: fake_cfg)
    monkeypatch.setattr(cli, "default_config_dir", lambda: ".")

    fake_selection = types.SimpleNamespace(
        mode="executor",
        primary_target="local:qwen3:8b",
        secondary_target=None,
        selected_target="local:qwen3:8b",
        selected_provider="ollama",
        fallback_used=False,
        fallback_reason=None,
        boundaries={},
    )
    monkeypatch.setattr(cli, "resolve_route", lambda *a, **k: fake_selection)

    # Patch engine_run to return a deterministic result containing a capability meta payload.
    import io_iii.core.engine as engine

    def fake_engine_run(**kwargs):
        state2 = kwargs["session_state"]
        res = engine.ExecutionResult(
            message="ok",
            meta={
                "capability": {
                    "capability_id": "cap.echo_json",
                    "version": "1.0",
                    "ok": True,
                    "error_code": None,
                    "duration_ms": 3,
                    # This must never be written into metadata.jsonl.
                    "output": {"secret": "nope"},
                }
            },
            provider="ollama",
            model="qwen3:8b",
            route_id=state2.route_id,
            audit_meta=None,
            prompt_hash="hash",
        )
        return state2, res

    monkeypatch.setattr(cli, "engine_run", fake_engine_run)

    captured = {}

    def fake_append_metadata(_logging_cfg, record):
        captured.update(record)

    monkeypatch.setattr(cli, "append_metadata", fake_append_metadata)

    # Act
    args = types.SimpleNamespace(
        mode="executor",
        prompt="hi",
        audit=False,
        config_dir=None,
        capability_id="cap.echo_json",
        capability_payload_json='{"a": 1}',
    )
    rc = cli.cmd_run(args)
    assert rc == 0

    # Assert: summary fields are present
    assert captured.get("capability_id") == "cap.echo_json"
    assert captured.get("capability_ok") is True
    assert captured.get("capability_version") == "1.0"
    assert captured.get("capability_duration_ms") == 3
    assert captured.get("capability_error_code") is None

    # Assert: output is not logged
    assert "output" not in captured
