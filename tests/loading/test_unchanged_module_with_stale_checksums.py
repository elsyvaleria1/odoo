from __future__ import annotations

import subprocess
import uuid

import pytest

from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads

from .._pg import dropdb_path, pg_reachable, psql_path
from .test_unchanged_module_follows_a_recreated_reference import (
    ACTION,
    MENU,
    OWNER,
    REPO_ROOT,
    USER,
    _get_action_id,
    _get_rows,
    _run_odoo_bin,
    _write,
)


def _get_menu_action(db: str) -> set[str]:
    return _get_rows(
        db,
        "SELECT action FROM ir_ui_menu WHERE id = (SELECT res_id FROM"
        f" ir_model_data WHERE module = '{USER}' AND name = 'menu_x')",
    )


def _set_checksums_as_version_3_left_them(db: str) -> None:
    # version 3 recorded no reference a <menuitem action=> resolves, which is
    # why version 4 discards its entries
    [stored] = _get_rows(
        db, f"SELECT data_file_checksums FROM ir_module_module WHERE name = '{USER}'"
    )
    stored = json_loads(stored)
    assert stored["files"]["data/menu.xml"]["refs"], (
        "version 4 records the menu's action, the reference version 3 missed"
    )
    stored["v"] = 3
    for entry in stored["files"].values():
        entry.pop("refs", None)
    subprocess.run(
        [
            psql_path(),
            "-d",
            db,
            "-v",
            "ON_ERROR_STOP=1",
            "-v",
            f"stored={json_dumps(stored)}",
        ],
        input="UPDATE ir_module_module SET data_file_checksums = :'stored'::jsonb"
        f" WHERE name = '{USER}';",
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )


@pytest.fixture
def probe(tmp_path_factory):
    if not pg_reachable():
        pytest.skip("no reachable PostgreSQL")
    if dropdb_path() is None or psql_path() is None:
        pytest.skip("psql/dropdb not on PATH")
    extra = tmp_path_factory.mktemp("stale_probe_addons")
    addons = f"{REPO_ROOT / 'odoo' / 'addons'},{REPO_ROOT / 'addons'},{extra}"
    data_dir = tmp_path_factory.mktemp("stale_probe_data")
    db = f"odoo_staleprobe_{uuid.uuid4().hex[:12]}"

    def run(*args: str) -> str:
        done = _run_odoo_bin(db, addons, data_dir, *args)
        assert done.returncode == 0, done.stdout[-4000:]
        return done.stdout

    _write(extra, OWNER, ["base"], {"action.xml": ACTION})
    _write(extra, USER, [OWNER], {"menu.xml": MENU.format(owner=OWNER)})
    run.db = db
    try:
        run("-i", f"base,{OWNER},{USER}")
        run("-u", OWNER)
        yield run
    finally:
        subprocess.run(
            [dropdb_path(), "--if-exists", "--force", db], check=False, timeout=60
        )


@pytest.mark.requires_pg
@pytest.mark.requires_psql
def test_an_unchanged_module_stamped_by_an_older_checksum_version_is_reapplied(probe):
    db = probe.db
    _set_checksums_as_version_3_left_them(db)
    _get_rows(
        db,
        "DELETE FROM ir_act_window WHERE id = ("
        f" SELECT res_id FROM ir_model_data WHERE module = '{OWNER}'"
        " AND name = 'action_x')",
    )
    _get_rows(
        db,
        f"DELETE FROM ir_model_data WHERE module = '{OWNER}' AND name = 'action_x'",
    )

    probe("-u", OWNER)

    assert _get_menu_action(db) == {f"ir.actions.act_window,{_get_action_id(db)}"}, (
        "an entry of an older version is no evidence the module's data still "
        "resolves to what it did: the menu keeps the deleted action's id"
    )
    assert _get_rows(
        db,
        f"SELECT data_file_checksums->>'v' FROM ir_module_module WHERE name = '{USER}'",
    ) == {"4"}
