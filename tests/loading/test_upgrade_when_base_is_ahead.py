from __future__ import annotations

import subprocess
import sys
import uuid

import pytest

from odoo.modules.module import Manifest, adapt_version

from .._pg import dropdb_path, pg_reachable, psql_path, repo_root

REPO_ROOT = repo_root()
PROBE = "base_ahead_probe"
MARKER = "base's code is ahead of the database"

requires_pg = pytest.mark.requires_pg
requires_psql = pytest.mark.requires_psql


def _write_probe(root, version: str) -> None:
    pkg = root / PROBE
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "__manifest__.py").write_text(
        repr(
            {
                "name": PROBE,
                "version": version,
                "depends": ["base"],
                "license": "LGPL-3",
            }
        ),
        encoding="utf-8",
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


def _versions(db: str) -> str:
    return _run_psql(
        db,
        "SELECT string_agg(name || ' ' || db_version, ', ' ORDER BY name) "
        f"FROM ir_module_module WHERE name IN ('base', '{PROBE}')",
    )


def _one_version_back(version: str) -> str:
    *head, last = version.split(".")
    return ".".join([*head, str(int(last) - 1)])


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    if not pg_reachable():
        pytest.skip("no reachable PostgreSQL")
    if dropdb_path() is None or psql_path() is None:
        pytest.skip("psql/dropdb not on PATH")

    extra = tmp_path_factory.mktemp("base_ahead_addons")
    addons = f"{REPO_ROOT / 'odoo' / 'addons'},{REPO_ROOT / 'addons'},{extra}"
    db = f"odoo_base_ahead_{uuid.uuid4().hex[:12]}"
    code = adapt_version(Manifest.for_addon("base")["version"])
    behind = _one_version_back(code)
    out: dict[str, object] = {"code": code, "behind": behind}
    try:
        _write_probe(extra, "1.0")
        installed = _run_odoo_bin(db, addons, "-i", f"base,{PROBE}")
        if installed.returncode != 0:
            pytest.fail(
                "could not install the probe:\n"
                f"{installed.stdout[-4000:]}\n{installed.stderr[-4000:]}"
            )
        _run_psql(
            db,
            f"UPDATE ir_module_module SET db_version = '{behind}' WHERE name = 'base'",
        )
        _write_probe(extra, "1.1")
        out["upgrade_probe"] = _run_odoo_bin(db, addons, "-u", PROBE)
        out["after"] = _versions(db)
        _write_probe(extra, "1.2")
        out["upgrade_probe_again"] = _run_odoo_bin(db, addons, "-u", PROBE)
        yield out
    finally:
        subprocess.run(
            [dropdb_path(), "--if-exists", "--force", db],
            check=False,
            capture_output=True,
        )


@requires_pg
@requires_psql
class TestAnUpgradeWhenBaseIsAhead:
    def test_an_upgrade_of_another_module_upgrades_base_first(self, runs):
        run = runs["upgrade_probe"]
        assert run.returncode == 0, run.stdout[-4000:] + run.stderr[-4000:]
        assert runs["after"] == (f"base {runs['code']}, {PROBE} {adapt_version('1.1')}")

    def test_the_run_says_why_and_from_which_version(self, runs):
        output = runs["upgrade_probe"].stdout + runs["upgrade_probe"].stderr
        assert f"{MARKER} ({runs['behind']} < {runs['code']})" in output, output[-4000:]

    def test_with_base_current_nothing_is_added(self, runs):
        run = runs["upgrade_probe_again"]
        assert run.returncode == 0, run.stdout[-4000:] + run.stderr[-4000:]
        assert MARKER not in run.stdout + run.stderr
