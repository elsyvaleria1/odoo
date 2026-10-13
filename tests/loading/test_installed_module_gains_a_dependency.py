from __future__ import annotations

import subprocess
import sys
import uuid

import psycopg
import pytest

import odoo.db
from odoo.modules.registry import Registry

from .._pg import dropdb_path
from .conftest import REPO_ROOT, requires_pg

pytestmark = requires_pg

CONSUMER, DEPENDENCY, UNRELATED = "gain_dep_consumer", "gain_dep_new", "gain_dep_other"


def _write(root, name: str, depends: list[str], model: str) -> None:
    package = root / name
    (package / "models").mkdir(parents=True, exist_ok=True)
    (package / "__manifest__.py").write_text(
        repr(
            {
                "name": name,
                "version": "1.0",
                "author": "test",
                "depends": depends,
                "license": "LGPL-3",
            }
        )
    )
    (package / "__init__.py").write_text("from . import models\n")
    (package / "models" / "__init__.py").write_text("from . import probe\n")
    (package / "models" / "probe.py").write_text(
        "from odoo import fields, models\n\n\n"
        "class Probe(models.Model):\n"
        f"    _name = {model!r}\n"
        '    _description = "Probe"\n\n'
        "    name = fields.Char()\n"
    )


def _run(addons: str, data_dir, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "odoo-bin"),
            *args,
            "--stop-after-init",
            "--no-http",
            "--max-cron-threads",
            "0",
            "--addons-path",
            addons,
            "--data-dir",
            str(data_dir),
            "--log-level",
            "info",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=900,
        check=False,
    )


def _run_module_upgrade(addons: str, data_dir, db: str, *args: str):
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "odoo-bin"),
            "--addons-path",
            addons,
            "module",
            "upgrade",
            "-d",
            db,
            "-D",
            str(data_dir),
            *args,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=900,
        check=False,
    )


def _clone(template: str) -> str:
    db = f"odoo_gain_dep_{uuid.uuid4().hex[:12]}"
    Registry.remove(template)
    odoo.db.close_db(template)
    with psycopg.connect(dbname="postgres", autocommit=True) as connection:
        connection.execute(f'CREATE DATABASE "{db}" TEMPLATE "{template}"')
    return db


def _drop(db: str) -> None:
    subprocess.run(
        [dropdb_path(), "--if-exists", "--force", db], check=False, capture_output=True
    )


def _get_states(db: str) -> dict[str, str]:
    with psycopg.connect(dbname=db) as connection:
        rows = connection.execute(
            "SELECT name, state FROM ir_module_module WHERE name = ANY(%s)",
            [[CONSUMER, DEPENDENCY, UNRELATED]],
        ).fetchall()
    return dict(rows)


@pytest.fixture(scope="module")
def consumer_gained_a_dependency(base_db, tmp_path_factory):
    if dropdb_path() is None:
        pytest.skip("dropdb not on PATH")
    extra = tmp_path_factory.mktemp("gain_dep_addons")
    addons = f"{REPO_ROOT / 'odoo' / 'addons'},{REPO_ROOT / 'addons'},{extra}"
    data_dir = tmp_path_factory.mktemp("gain_dep_data")
    _write(extra, CONSUMER, ["base"], "gain.dep.consumer")
    _write(extra, DEPENDENCY, ["base"], "gain.dep.new")
    _write(extra, UNRELATED, ["base"], "gain.dep.other")
    template = _clone(base_db)
    try:
        installed = _run(
            addons, data_dir, "-d", template, "-i", f"{CONSUMER},{UNRELATED}"
        )
        assert installed.returncode == 0, installed.stdout[-4000:]
        assert _get_states(template) == {
            CONSUMER: "installed",
            DEPENDENCY: "uninstalled",
            UNRELATED: "installed",
        }
        _write(extra, CONSUMER, ["base", DEPENDENCY], "gain.dep.consumer")
        yield template, addons, data_dir
    finally:
        _drop(template)


@pytest.fixture
def db(consumer_gained_a_dependency):
    template, addons, data_dir = consumer_gained_a_dependency
    db = _clone(template)
    try:
        yield db, addons, data_dir
    finally:
        _drop(db)


def _assert_consumer_loads(db: str, addons: str, data_dir) -> None:
    assert _get_states(db) == {
        CONSUMER: "installed",
        DEPENDENCY: "installed",
        UNRELATED: "installed",
    }
    start = _run(addons, data_dir, "-d", db)
    assert start.returncode == 0, start.stdout[-4000:]
    assert "some depends are not loaded" not in start.stdout, start.stdout[-4000:]
    assert " ERROR " not in start.stdout, start.stdout[-4000:]


def test_updating_an_unrelated_module_installs_the_new_dependency(db):
    name, addons, data_dir = db
    run = _run(addons, data_dir, "-d", name, "-u", UNRELATED)
    assert run.returncode == 0, run.stdout[-4000:]
    assert f"{CONSUMER} is installed but" not in run.stdout, (
        "the installed consumer was dropped from the update's graph instead of "
        "its new dependency being installed"
    )
    _assert_consumer_loads(name, addons, data_dir)


def test_module_upgrade_outdated_installs_the_new_dependency(db):
    name, addons, data_dir = db
    run = _run_module_upgrade(addons, data_dir, name, "all", "--outdated")
    assert run.returncode == 0, run.stdout[-4000:]
    assert "every module is up to date" not in run.stdout, run.stdout[-4000:]
    _assert_consumer_loads(name, addons, data_dir)


def test_a_plain_start_names_the_unloaded_module_and_the_fix(db):
    name, addons, data_dir = db
    start = _run(addons, data_dir, "-d", name)
    assert start.returncode == 0, start.stdout[-4000:]
    unloaded = [
        line
        for line in start.stdout.splitlines()
        if f"{CONSUMER} is installed but" in line
    ]
    assert len(unloaded) == 1, start.stdout[-4000:]
    assert " ERROR " in unloaded[0]
    assert f"depends on {DEPENDENCY}, not loaded" in unloaded[0]
    assert f"-u {CONSUMER}" in unloaded[0]
    assert _get_states(name)[DEPENDENCY] == "uninstalled"


def test_a_dependency_missing_from_the_addons_path_is_named(db, tmp_path):
    name, addons, data_dir = db
    _write(tmp_path, CONSUMER, ["base", "gain_dep_nowhere"], "gain.dep.consumer")
    shadowed = f"{tmp_path},{addons}"
    run = _run(shadowed, data_dir, "-d", name, "-u", UNRELATED)
    assert run.returncode == 0, run.stdout[-4000:]
    assert (
        f"Some modules are not loaded: {CONSUMER} is installed but depends on "
        "gain_dep_nowhere, not on the addons path"
    ) in run.stdout, run.stdout[-4000:]
