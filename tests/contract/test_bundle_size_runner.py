import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from odoo.libs.json import loads as json_loads

RUNNER = Path(__file__).resolve().parents[2] / "addons/web/tests/bundle_size.sh"


@pytest.fixture
def runner_env(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    commands = tmp_path / "commands.jsonl"
    for command in ("createdb", "dropdb"):
        script = bin_dir / command
        script.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "with open(os.environ['RUNNER_COMMANDS'], 'a') as output:\n"
            f"    output.write(json.dumps([{command!r}, *sys.argv[1:]]) + '\\n')\n"
            f"sys.exit(int(os.environ.get('{command.upper()}_STATUS', '0')))\n"
        )
        script.chmod(0o755)
    interpreter = bin_dir / "python"
    interpreter.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "-" ] && [ "${ROOTS_STATUS:-0}" -ne 0 ]; then\n'
        '    exit "$ROOTS_STATUS"\n'
        "fi\n"
        'case "$1" in */odoo-bin) exit "${SERVER_STATUS:-0}" ;; esac\n'
        f'exec {shlex.quote(sys.executable)} "$@"\n'
    )
    interpreter.chmod(0o755)
    return dict(
        os.environ,
        VIRTUAL_ENV=str(tmp_path),
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        TMPDIR=str(data_dir),
        RUNNER_COMMANDS=str(commands),
        ODOO_DB_TEMPLATE="owned_test_template",
    )


@pytest.mark.parametrize(
    ("create_status", "server_status", "drop_status", "expected_status"),
    [(23, 0, 0, 23), (0, 17, 0, 17), (0, 0, 0, 0), (0, 0, 29, 29), (0, 17, 29, 17)],
)
def test_cleanup_only_drops_a_created_database(
    runner_env, create_status, server_status, drop_status, expected_status
):
    runner_env.update(
        CREATEDB_STATUS=str(create_status),
        SERVER_STATUS=str(server_status),
        DROPDB_STATUS=str(drop_status),
    )
    result = subprocess.run(
        ["bash", str(RUNNER)],
        env=runner_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == expected_status, result.stdout + result.stderr
    commands = [
        json_loads(line)
        for line in Path(runner_env["RUNNER_COMMANDS"])
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    create = commands[0]
    assert create[:3] == ["createdb", "-T", "owned_test_template"]
    assert re.fullmatch(r"codex_bundle_[0-9a-f]{16}", create[3])
    assert commands[1:] == ([] if create_status else [["dropdb", create[3]]])
    assert not list(Path(runner_env["TMPDIR"]).iterdir())


def test_a_failed_calibration_scan_cleans_up_without_touching_databases(runner_env):
    runner_env["ROOTS_STATUS"] = "23"
    result = subprocess.run(
        ["bash", str(RUNNER)],
        env=runner_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 23
    assert not Path(runner_env["RUNNER_COMMANDS"]).exists()
    assert not list(Path(runner_env["TMPDIR"]).iterdir())


@pytest.mark.parametrize("create_status", [0, 23])
def test_keep_preserves_only_a_database_created_by_this_run(runner_env, create_status):
    runner_env["CREATEDB_STATUS"] = str(create_status)
    result = subprocess.run(
        ["bash", str(RUNNER), "--keep"],
        env=runner_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == create_status, result.stdout + result.stderr
    commands = (
        Path(runner_env["RUNNER_COMMANDS"]).read_text(encoding="utf-8").splitlines()
    )
    assert len(commands) == 1
    assert ("kept database" in result.stdout) == (create_status == 0)
    assert bool(list(Path(runner_env["TMPDIR"]).iterdir())) == (create_status == 0)
