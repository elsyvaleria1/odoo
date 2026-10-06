from __future__ import annotations

import subprocess
import sys
import uuid

import pytest

from .._pg import dropdb_path, pg_reachable, psql_path, repo_root

REPO_ROOT = repo_root()
ADDONS = f"{REPO_ROOT / 'odoo' / 'addons'},{REPO_ROOT / 'addons'}"
IMPORTED = "probe_imported"

IMPORT_SCRIPT = f"""
import io, zipfile
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("{IMPORTED}/__manifest__.py", repr({{
        "name": "{IMPORTED}", "version": "1.0", "depends": ["base"],
        "data": ["data.xml"], "license": "LGPL-3"}}))
    z.writestr("{IMPORTED}/data.xml", '<odoo><record id="partner" model="res.partner">'
               '<field name="name">Imported probe partner</field></record></odoo>')
env["ir.module.module"]._import_zipfile(io.BytesIO(buf.getvalue()))
env.cr.commit()
"""


def _run(db: str, data_dir, *args: str, subcommand: str = "", stdin: str = ""):
    command = [sys.executable, str(REPO_ROOT / "odoo-bin")]
    if subcommand:
        command.append(subcommand)
    command += [
        "--addons-path",
        ADDONS,
        "-d",
        db,
        "--max-cron-threads",
        "0",
        "--db_maxconn",
        "8",
        "--no-http",
        "--data-dir",
        str(data_dir),
        "--log-level",
        "info",
        *args,
    ]
    if not subcommand:
        command.append("--stop-after-init")
    done = subprocess.run(
        command,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=900,
        check=False,
    )
    assert done.returncode == 0, done.stdout[-4000:]
    return done.stdout


def _get_rows(db: str, query: str) -> set[str]:
    out = subprocess.run(
        [psql_path(), "-d", db, "-tAc", query],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    ).stdout
    return {line for line in out.splitlines() if line}


@pytest.fixture
def imported_db(tmp_path_factory):
    if not pg_reachable():
        pytest.skip("no reachable PostgreSQL")
    if dropdb_path() is None or psql_path() is None:
        pytest.skip("psql/dropdb not on PATH")
    data_dir = tmp_path_factory.mktemp("imported_probe_data")
    db = f"odoo_importprobe_{uuid.uuid4().hex[:12]}"
    try:
        _run(db, data_dir, "-i", "base_import_module")
        _run(db, data_dir, subcommand="shell", stdin=IMPORT_SCRIPT)
        assert _get_rows(
            db, f"SELECT state FROM ir_module_module WHERE name = '{IMPORTED}'"
        ) == {"installed"}
        yield db, data_dir
    finally:
        subprocess.run(
            [dropdb_path(), "--if-exists", "--force", db], check=False, timeout=60
        )


@pytest.mark.requires_pg
@pytest.mark.requires_psql
@pytest.mark.parametrize(
    ("upgraded", "left_pending"),
    [("base", False), ("all", False), ("base", True)],
    ids=["base", "all", "left-pending-by-an-earlier-upgrade"],
)
def test_an_imported_module_stays_installed_when_base_is_upgraded(
    imported_db, upgraded, left_pending
):
    db, data_dir = imported_db
    if left_pending:
        _get_rows(
            db,
            "UPDATE ir_module_module SET state = 'to upgrade'"
            f" WHERE name = '{IMPORTED}' RETURNING name",
        )
    out = _run(db, data_dir, "-u", upgraded)

    assert _get_rows(
        db, f"SELECT state FROM ir_module_module WHERE name = '{IMPORTED}'"
    ) == {"installed"}, (
        "an imported module has no code on disk to reload; left 'to upgrade' it "
        "keeps every job and cron off the database"
    )
    assert "inconsistent states" not in out
    assert not _get_rows(
        db,
        "SELECT value FROM ir_config_parameter"
        " WHERE key = 'base.partially_updated_database'",
    )
    assert _get_rows(
        db,
        "SELECT name FROM res_partner WHERE id = (SELECT res_id FROM"
        f" ir_model_data WHERE module = '{IMPORTED}' AND name = 'partner')",
    ) == {"Imported probe partner"}
