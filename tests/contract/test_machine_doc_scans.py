import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RPC_HARNESS = REPO / "addons/rpc/machine_doc_v1/factcheck.sh"


def test_rpc_harness_is_independent_of_working_directory(tmp_path):
    env = dict(os.environ, VENV_PY=sys.executable)
    result = subprocess.run(
        ["bash", str(RPC_HARNESS)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 failed" in result.stdout
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("argument_count", [3, 4, 5], ids=["routes", "client", "paths"])
def test_rpc_harness_propagates_a_failed_scan(tmp_path, argument_count):
    interpreter = tmp_path / "failing-python"
    interpreter.write_text(
        "#!/bin/sh\n"
        f'if [ "$1" = "-" ] && [ "$#" -eq {argument_count} ]; then\n'
        "    printf 'planted scan failure\\n' >&2\n"
        "    exit 23\n"
        "fi\n"
        f'exec {shlex.quote(sys.executable)} "$@"\n'
    )
    interpreter.chmod(0o755)
    env = dict(os.environ, VENV_PY=str(interpreter))
    result = subprocess.run(
        ["bash", str(RPC_HARNESS)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 23, result.stdout + result.stderr
    assert "planted scan failure" in result.stderr
    assert "0 failed" not in result.stdout
