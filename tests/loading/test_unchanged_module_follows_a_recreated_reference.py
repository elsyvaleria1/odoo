from __future__ import annotations

import subprocess
import sys
import uuid

import pytest

from .._pg import dropdb_path, pg_reachable, psql_path, repo_root

REPO_ROOT = repo_root()
OWNER, USER, OVERRIDER = "probe_ref_owner", "probe_ref_user", "probe_ref_overrider"

ACTION = """<odoo>
    <record id="action_x" model="ir.actions.act_window">
        <field name="name">Probe action</field>
        <field name="res_model">res.partner</field>
    </record>
</odoo>
"""
RECREATED_ACTION = """<odoo>
    <delete model="ir.actions.act_window" search="[('name', '=', 'Probe action')]"/>
    <record id="action_x" model="ir.actions.act_window">
        <field name="name">Probe action</field>
        <field name="res_model">res.partner</field>
    </record>
</odoo>
"""
MENU = """<odoo>
    <menuitem id="menu_x" name="Probe menu" action="{owner}.action_x"/>
</odoo>
"""
OVERRIDE = """<odoo>
    <record id="{user}.menu_x" model="ir.ui.menu">
        <field name="name">Overridden menu</field>
    </record>
</odoo>
"""
VIEW = """<odoo>
    <record id="{view}" model="ir.ui.view">
        <field name="name">{view}</field>
        <field name="model">res.partner</field>
        <field name="arch" type="xml">
            <form><button name="%({owner}.action_x)d" type="action" string="X"/></form>
        </field>
    </record>
</odoo>
"""


def _write(root, name: str, depends: list[str], files: dict[str, str]) -> None:
    pkg = root / name
    (pkg / "data").mkdir(parents=True, exist_ok=True)
    (pkg / "__manifest__.py").write_text(
        repr(
            {
                "name": name,
                "version": "1.0",
                "depends": depends,
                "data": [f"data/{filename}" for filename in files],
                "installable": True,
                "license": "LGPL-3",
            }
        ),
        encoding="utf-8",
    )
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    for filename, content in files.items():
        (pkg / "data" / filename).write_text(content, encoding="utf-8")


def _run_odoo_bin(
    db: str, addons: str, data_dir, *args: str
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "odoo-bin"),
            "--addons-path",
            addons,
            "-d",
            db,
            "--db-filter",
            f"^{db}$",
            "--max-cron-threads",
            "0",
            "--stream-workers",
            "0",
            "--db_maxconn",
            "8",
            "--no-http",
            "--data-dir",
            str(data_dir),
            *args,
            "--stop-after-init",
            "--log-level",
            "info",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=900,
        check=False,
    )


def _get_rows(db: str, query: str) -> set[str]:
    out = subprocess.run(
        [psql_path(), "-d", db, "-tAc", query],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    ).stdout
    return {line for line in out.splitlines() if line}


def _prepare_user_files() -> dict[str, str]:
    # the second view resolves the action from the first one's idref,
    # which is the resolution a skip must know about too
    return {
        "menu.xml": MENU.format(owner=OWNER),
        "view.xml": VIEW.format(owner=OWNER, view="view_one"),
        "view2.xml": VIEW.format(owner=OWNER, view="view_two"),
    }


def _get_action_id(db: str) -> str:
    [action] = _get_rows(
        db,
        "SELECT res_id FROM ir_model_data"
        f" WHERE module = '{OWNER}' AND name = 'action_x'",
    )
    return action


def _assert_the_user_points_at(db: str, action: str) -> None:
    assert _get_rows(
        db,
        "SELECT action FROM ir_ui_menu WHERE id = (SELECT res_id FROM"
        f" ir_model_data WHERE module = '{USER}' AND name = 'menu_x')",
    ) == {f"ir.actions.act_window,{action}"}
    assert _get_rows(
        db,
        "SELECT d.name FROM ir_ui_view v JOIN ir_model_data d"
        " ON d.model = 'ir.ui.view' AND d.res_id = v.id"
        f" WHERE d.module = '{USER}'"
        f" AND v.arch_db->>'en_US' LIKE '%name=\"{action}\"%'",
    ) == {"view_one", "view_two"}, (
        "a view still naming the deleted action's id opens nothing"
    )


@pytest.fixture
def probe(tmp_path_factory):
    if not pg_reachable():
        pytest.skip("no reachable PostgreSQL")
    if dropdb_path() is None or psql_path() is None:
        pytest.skip("psql/dropdb not on PATH")

    extra = tmp_path_factory.mktemp("ref_probe_addons")
    addons = f"{REPO_ROOT / 'odoo' / 'addons'},{REPO_ROOT / 'addons'},{extra}"
    data_dir = tmp_path_factory.mktemp("ref_probe_data")
    db = f"odoo_refprobe_{uuid.uuid4().hex[:12]}"

    def run(*args: str) -> str:
        done = _run_odoo_bin(db, addons, data_dir, *args)
        assert done.returncode == 0, done.stdout[-4000:]
        return done.stdout

    def install(action_xml: str, *more: str) -> None:
        _write(extra, OWNER, ["base"], {"action.xml": action_xml})
        _write(extra, USER, [OWNER], _prepare_user_files())
        _write(extra, OVERRIDER, [USER], {"override.xml": OVERRIDE.format(user=USER)})
        run("-i", ",".join(["base", OWNER, USER, *more]))
        # the first update stamps the data-file checksums the skips compare against
        run("-u", OWNER)

    run.db = db
    run.install = install
    try:
        yield run
    finally:
        subprocess.run(
            [dropdb_path(), "--if-exists", "--force", db], check=False, timeout=60
        )


@pytest.mark.requires_pg
@pytest.mark.requires_psql
def test_an_unchanged_dependent_follows_a_record_its_data_points_at(probe):
    probe.install(ACTION)
    db = probe.db

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
    out = probe("-u", OWNER)
    assert f"re-applying unchanged {OWNER}/data/action.xml" in out, (
        "the owner must recreate the action for this test to mean anything"
    )
    _assert_the_user_points_at(db, _get_action_id(db))

    out = probe("-u", OWNER)
    assert "1 unchanged modules left as installed" in out, (
        "once nothing moved, the dependent is skipped again"
    )
    assert f"Loading module {USER} " not in out
    _assert_the_user_points_at(db, _get_action_id(db))


@pytest.mark.requires_pg
@pytest.mark.requires_psql
def test_an_unchanged_dependent_follows_a_record_recreated_in_the_same_run(probe):
    probe.install(RECREATED_ACTION, OVERRIDER)
    db = probe.db
    before = _get_action_id(db)
    _assert_the_user_points_at(db, before)

    out = probe("-u", OWNER)
    assert "2 unchanged modules left as installed" in out, (
        "before the owner loads, nothing the dependent references has moved"
    )
    after = _get_action_id(db)
    assert after != before, (
        "the owner's own data must recreate the action for this test to mean anything"
    )
    _assert_the_user_points_at(db, after)
    assert _get_rows(
        db,
        "SELECT name->>'en_US' FROM ir_ui_menu WHERE id = (SELECT res_id FROM"
        f" ir_model_data WHERE module = '{USER}' AND name = 'menu_x')",
    ) == {"Overridden menu"}, (
        "re-applying the dependent's menu reverts what a module loaded after it "
        "wrote over that menu, unless that module is re-applied in order too"
    )
