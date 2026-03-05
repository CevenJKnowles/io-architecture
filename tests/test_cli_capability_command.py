import json
import subprocess
import sys


def test_cli_capability_command_echo_json():
    """CLI capability command should execute cap.echo_json successfully."""

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "io_iii",
            "capability",
            "cap.echo_json",
            '{"x":1}',
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    output = json.loads(result.stdout)

    assert output["result"]["meta"]["capability"]["capability_id"] == "cap.echo_json"
    assert output["result"]["meta"]["capability"]["ok"] is True