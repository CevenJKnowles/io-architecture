import argparse
import json

from io_iii.cli import cmd_capabilities


def test_cli_capabilities_text_output(capsys):
    rc = cmd_capabilities(argparse.Namespace(json=False))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Registered capabilities" in out
    # At least one builtin should exist in Phase 3 (e.g., cap.echo_json)
    assert "cap." in out


def test_cli_capabilities_json_output(capsys):
    rc = cmd_capabilities(argparse.Namespace(json=True))
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert "capabilities" in payload
    assert isinstance(payload["capabilities"], list)
    assert all("id" in c and "bounds" in c for c in payload["capabilities"])
