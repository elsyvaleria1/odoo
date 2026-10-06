from __future__ import annotations

import subprocess
import sys
import textwrap
import uuid

import pytest

from odoo.modules.module import adapt_version

from .._pg import dropdb_path, pg_reachable, psql_path, repo_root

REPO_ROOT = repo_root()
PROBE = "oldest_upgradable_probe"
BYSTANDER = "oldest_upgradable_bystander"
NEWCOMER = "oldest_upgradable_newcomer"

requires_pg = pytest.mark.requires_pg
requires_psql = pytest.mark.requires_psql

MIGRATION = textwrap.dedent(
    """
    def migrate(cr, version):
        cr.execute(
            "INSERT INTO ir_config_parameter "
            "(key, value, create_uid, write_uid, create_date, write_date) "
            "VALUES (%s, %s, 1, 1, now(), now()) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            ("MODULE.migrated", version),
        )
    """
)


def _write_module(
    root, name: str, version: str, *, oldest: str = "", migration: str = ""
) -> None:
    pkg = root / name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    manifest = {
        "name": name,
        "version": version,
        "depends": ["base"],
        "license": "LGPL-3",
    }
    if oldest:
        manifest["oldest_upgradable_version"] = oldest
    (pkg / "__manifest__.py").write_text(repr(manifest), encoding="utf-8")
    if migration:
        versioned = pkg / "migrations" / migration
        versioned.mkdir(parents=True, exist_ok=True)
        (versioned / "pre-migrate.py").write_text(
            MIGRATION.replace("MODULE", name), encoding="utf-8"
        )


def _run_odoo_bin(db: str, addons: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "odoo-bin"),
            "--addons-path",
            addons,
            "-d",
            db,
            "--db_maxconn",
            "4",
            *args,
            "--stop-after-init",
            "--log-level",
            "warn",
        ],
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )


def _run_psql(db: str, statement: str) -> str:
    return subprocess.run(
        [psql_path(), "-d", db, "-tAc", statement],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


def _snapshot(db: str) -> dict[str, str]:
    return {
        "modules": _run_psql(
            db,
            "SELECT string_agg(name || ' ' || state || ' ' || db_version, ', ' "
            "ORDER BY name) FROM ir_module_module "
            f"WHERE name IN ('base', '{PROBE}', '{BYSTANDER}', '{NEWCOMER}')",
        ),
        "migrated": _run_psql(
            db,
            "SELECT string_agg(key || '=' || value, ', ' ORDER BY key) "
            "FROM ir_config_parameter WHERE key LIKE '%.migrated'",
        ),
    }


def _refusal(run: subprocess.CompletedProcess) -> str:
    return run.stdout + run.stderr


def _refused_modules(run: subprocess.CompletedProcess) -> str:
    marker = "cannot be updated by this code: "
    [line] = {
        line.split(marker, 1)[1].split(". The migrations")[0]
        for line in _refusal(run).splitlines()
        if marker in line
    }
    return line


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    if not pg_reachable():
        pytest.skip("no reachable PostgreSQL")
    if dropdb_path() is None or psql_path() is None:
        pytest.skip("psql/dropdb not on PATH")

    extra = tmp_path_factory.mktemp("oldest_upgradable_addons")
    addons = f"{REPO_ROOT / 'odoo' / 'addons'},{REPO_ROOT / 'addons'},{extra}"
    db = f"odoo_oldest_upgradable_{uuid.uuid4().hex[:12]}"
    out: dict[str, object] = {}
    try:
        _write_module(extra, PROBE, "1.0")
        _write_module(extra, BYSTANDER, "1.0")
        installed = _run_odoo_bin(db, addons, "-i", f"base,{PROBE},{BYSTANDER}")
        if installed.returncode != 0:
            pytest.fail(
                "could not install the probes at 1.0:\n"
                f"{installed.stdout[-4000:]}\n{installed.stderr[-4000:]}"
            )
        _write_module(extra, PROBE, "1.3", oldest="1.2", migration="1.3")
        _write_module(extra, BYSTANDER, "1.1", migration="1.1")
        _write_module(extra, NEWCOMER, "1.4", oldest="1.4")
        out["before"] = _snapshot(db)
        out["upgrade_all"] = _run_odoo_bin(db, addons, "-u", "all")
        out["after_upgrade_all"] = _snapshot(db)
        out["upgrade_bystander"] = _run_odoo_bin(db, addons, "-u", BYSTANDER)
        out["install_newcomer"] = _run_odoo_bin(db, addons, "-i", NEWCOMER)
        out["after_refusals"] = _snapshot(db)

        _run_psql(
            db,
            f"UPDATE ir_module_module SET db_version = '{adapt_version('1.2')}' "
            f"WHERE name = '{PROBE}'",
        )
        out["upgrade_at_floor"] = _run_odoo_bin(db, addons, "-u", PROBE)
        out["install_newcomer_after"] = _run_odoo_bin(db, addons, "-i", NEWCOMER)
        out["after_upgrade"] = _snapshot(db)

        _run_psql(
            db,
            f"UPDATE ir_module_module SET db_version = '{adapt_version('1.0')}' "
            f"WHERE name = '{PROBE}'",
        )
        _run_psql(
            db,
            "ALTER TABLE ir_module_module RENAME COLUMN db_version TO latest_version",
        )
        out["upgrade_before_rename"] = _run_odoo_bin(db, addons, "-u", "base")
        yield out
    finally:
        subprocess.run(
            [dropdb_path(), "--if-exists", "--force", db],
            check=False,
            capture_output=True,
        )


@requires_pg
@requires_psql
class TestAnUpgradeOfADatabaseOlderThanUpgradable:
    def test_an_upgrade_of_everything_is_refused_naming_the_module(self, runs):
        run = runs["upgrade_all"]
        assert run.returncode != 0, run.stdout[-4000:]
        assert "DatabaseOlderThanUpgradableError" in _refusal(run), run.stdout[-4000:]
        assert _refused_modules(run) == (
            f"{PROBE} {adapt_version('1.0')} is older than {adapt_version('1.2')}"
        )

    def test_the_refusal_comes_before_any_migration_or_state_change(self, runs):
        assert runs["after_upgrade_all"] == runs["before"]
        assert runs["before"]["migrated"] == ""

    def test_an_upgrade_of_another_module_is_refused_too(self, runs):
        run = runs["upgrade_bystander"]
        assert run.returncode != 0, run.stdout[-4000:]
        assert "DatabaseOlderThanUpgradableError" in _refusal(run)

    def test_an_install_on_that_database_is_refused_too(self, runs):
        run = runs["install_newcomer"]
        assert run.returncode != 0, run.stdout[-4000:]
        assert "DatabaseOlderThanUpgradableError" in _refusal(run)
        assert runs["after_refusals"] == runs["before"]

    def test_a_database_at_the_oldest_upgradable_version_upgrades(self, runs):
        run = runs["upgrade_at_floor"]
        assert run.returncode == 0, run.stdout[-4000:] + run.stderr[-4000:]
        after = runs["after_upgrade"]
        assert f"{PROBE} installed {adapt_version('1.3')}" in after["modules"]
        assert f"{PROBE}.migrated={adapt_version('1.2')}" in after["migrated"]

    def test_a_module_installed_fresh_has_nothing_to_be_older_than(self, runs):
        run = runs["install_newcomer_after"]
        assert run.returncode == 0, run.stdout[-4000:] + run.stderr[-4000:]
        assert (
            f"{NEWCOMER} installed {adapt_version('1.4')}"
            in runs["after_upgrade"]["modules"]
        )

    def test_a_database_from_before_the_column_rename_is_refused_by_name(self, runs):
        run = runs["upgrade_before_rename"]
        assert run.returncode != 0, run.stdout[-4000:]
        assert _refused_modules(run) == (
            f"{PROBE} {adapt_version('1.0')} is older than {adapt_version('1.2')}"
        ), _refusal(run)[-4000:]
