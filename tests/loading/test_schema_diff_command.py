from __future__ import annotations

import subprocess
import sys
import uuid

import psycopg
import pytest

from .._pg import dropdb_path
from .conftest import REPO_ROOT, requires_pg

pytestmark = requires_pg


def _get_installed_modules(db: str) -> set[str]:
    with psycopg.connect(dbname=db) as connection:
        rows = connection.execute(
            "SELECT name FROM ir_module_module WHERE state = 'installed'"
        ).fetchall()
    return {name for (name,) in rows}


def _get_tables(db: str) -> set[str]:
    with psycopg.connect(dbname=db) as connection:
        rows = connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        ).fetchall()
    return {name for (name,) in rows}


def test_schema_diff_previews_an_install_and_commits_nothing(base_db):
    before_modules, before_tables = (
        _get_installed_modules(base_db),
        _get_tables(base_db),
    )
    assert "uom" not in before_modules
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "odoo-bin"),
            "schema_diff",
            "--addons-path",
            f"{REPO_ROOT / 'odoo' / 'addons'},{REPO_ROOT / 'addons'}",
            "-d",
            base_db,
            "-i",
            "uom",
            "--log-level",
            "warn",
        ],
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert "DDL statements that would run:" in proc.stdout
    assert "CREATE TABLE" in proc.stdout
    assert "uom" in proc.stdout
    assert _get_installed_modules(base_db) == before_modules
    assert _get_tables(base_db) == before_tables


def test_schema_diff_does_not_publish_postcommit_effects(base_db, tmp_path):
    module = tmp_path / "preview_callback"
    module.mkdir()
    marker = tmp_path / "published.txt"
    (module / "__manifest__.py").write_text(
        repr(
            {
                "name": "Preview callback",
                "version": "1.0",
                "depends": ["base"],
                "license": "LGPL-3",
                "post_init_hook": "initialize",
            }
        )
    )
    (module / "__init__.py").write_text(
        "from pathlib import Path\n\n"
        "def initialize(env):\n"
        "    env.cr.execute('CREATE TABLE preview_callback_probe (value integer)')\n"
        f"    env.cr.postcommit.add(lambda: Path({str(marker)!r}).write_text('published'))\n"
    )
    before_modules, before_tables = (
        _get_installed_modules(base_db),
        _get_tables(base_db),
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "odoo-bin"),
            "schema_diff",
            "--addons-path",
            f"{REPO_ROOT / 'odoo' / 'addons'},{REPO_ROOT / 'addons'},{tmp_path}",
            "-d",
            base_db,
            "-i",
            "preview_callback",
            "--log-level",
            "warn",
        ],
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert "preview_callback_probe" in proc.stdout
    assert not marker.exists(), "a rolled-back preview published a postcommit effect"
    assert _get_installed_modules(base_db) == before_modules
    assert _get_tables(base_db) == before_tables


PROBE = "schema_diff_probe"


def _write_probe(root, version: str, *, ahead: bool) -> None:
    package = root / PROBE
    (package / "models").mkdir(parents=True, exist_ok=True)
    (package / "__manifest__.py").write_text(
        repr(
            {
                "name": "Schema diff probe",
                "version": version,
                "depends": ["base"],
                "license": "LGPL-3",
            }
        )
    )
    (package / "__init__.py").write_text("from . import models\n")
    (package / "models" / "__init__.py").write_text("from . import probe\n")
    (package / "models" / "probe.py").write_text(
        "from odoo import fields, models\n\n\n"
        "class SchemaDiffProbe(models.Model):\n"
        '    _name = "schema.diff.probe"\n'
        '    _description = "Schema diff probe"\n\n'
        "    kept = fields.Char()\n"
        + ("    added_at_1_1 = fields.Char()\n" if ahead else "")
    )
    if ahead:
        scripts = package / "migrations" / version
        scripts.mkdir(parents=True)
        (scripts / "pre-mark.py").write_text("def migrate(cr, version):\n    pass\n")


def _run_schema_diff(db: str, addons: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "odoo-bin"),
            "schema_diff",
            "--addons-path",
            addons,
            "-d",
            db,
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )


@pytest.fixture(scope="module")
def code_ahead_of_database(base_db, tmp_path_factory):
    if dropdb_path() is None:
        pytest.skip("dropdb not on PATH")
    extra = tmp_path_factory.mktemp("schema_diff_addons")
    addons = f"{REPO_ROOT / 'odoo' / 'addons'},{REPO_ROOT / 'addons'},{extra}"
    db = f"odoo_schema_diff_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(dbname="postgres", autocommit=True) as connection:
        connection.execute(f'CREATE DATABASE "{db}" TEMPLATE "{base_db}"')
    try:
        _write_probe(extra, "1.0", ahead=False)
        installed = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "odoo-bin"),
                "--addons-path",
                addons,
                "-d",
                db,
                "-i",
                PROBE,
                "--stop-after-init",
                "--log-level",
                "warn",
            ],
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        assert installed.returncode == 0, installed.stderr[-3000:]
        _write_probe(extra, "1.1", ahead=True)
        yield db, addons
    finally:
        subprocess.run(
            [dropdb_path(), "--if-exists", "--force", db],
            check=False,
            capture_output=True,
        )


def _get_preview(stdout: str) -> str:
    return stdout.partition("rows the catalog models would change:")[0]


def test_schema_diff_update_all_previews_what_update_base_does(
    code_ahead_of_database,
):
    db, addons = code_ahead_of_database
    by_all = _run_schema_diff(db, addons, "-u", "all", "--log-level", "warn")
    by_base = _run_schema_diff(db, addons, "-u", "base", "--log-level", "warn")
    assert by_all.returncode == 0, by_all.stderr[-3000:]
    assert by_base.returncode == 0, by_base.stderr[-3000:]
    assert f"{PROBE} [>1.1] pre-mark" in by_all.stdout
    assert "schema_diff_probe ADD COLUMN" in by_all.stdout.replace('"', "")
    assert _get_preview(by_all.stdout) == _get_preview(by_base.stdout)


def test_schema_diff_logs_under_the_database_name(code_ahead_of_database):
    db, addons = code_ahead_of_database
    proc = _run_schema_diff(db, addons, "-u", PROBE, "--log-level", "info")
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert f" {db} rid:" in proc.stderr + proc.stdout


def test_schema_diff_install_all_names_no_module(base_db):
    proc = _run_schema_diff(
        base_db,
        f"{REPO_ROOT / 'odoo' / 'addons'},{REPO_ROOT / 'addons'}",
        "-i",
        "all",
    )
    assert proc.returncode == 2
    assert "only supported by --update" in proc.stderr
    assert "name at least one module" in proc.stderr
