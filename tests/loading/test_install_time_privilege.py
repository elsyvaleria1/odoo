from __future__ import annotations

import subprocess
import uuid

import psycopg
import pytest

import odoo.db
from odoo.modules.registry import Registry

from .._pg import dropdb_path, psql_path
from .conftest import REPO_ROOT, requires_pg, requires_psql
from .test_unchanged_module_follows_a_recreated_reference import (
    _get_rows,
    _run_odoo_bin,
)

HOLDER = "probe_install_privilege"
PRIVILEGE = f"{HOLDER}.privilege_read_partner"
HOLDER_MODELS = f"""from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    probe_privileged_name = fields.Char(
        compute="_compute_probe_privileged_name", store=True
    )
    probe_privileged_count = fields.Integer(
        default=lambda self: self.with_privilege(
            "{PRIVILEGE}", reason="a probe column default"
        ).search_count([("id", "=", self.env.user.partner_id.id)])
    )

    @api.depends("name")
    def _compute_probe_privileged_name(self):
        for partner in self:
            partner.probe_privileged_name = partner.with_privilege(
                "{PRIVILEGE}", reason="a probe stored compute"
            ).name
"""
HOLDER_SECURITY = """<odoo>
    <record id="privilege_read_partner" model="res.groups">
        <field name="name">Privilege: probe read a partner</field>
        <field name="is_privilege" eval="True"/>
    </record>
</odoo>
"""
LATE = "probe_late_privilege"
LATE_HOOK = f"""def post_init_hook(env):
    env["res.partner"].with_privilege("{LATE}.privilege_never_declared")
"""


def _write_holder(root) -> None:
    pkg = root / HOLDER
    (pkg / "security").mkdir(parents=True)
    (pkg / "__manifest__.py").write_text(
        repr(
            {
                "name": HOLDER,
                "version": "1.0",
                "depends": ["base"],
                "data": ["security/security.xml"],
                "installable": True,
                "license": "LGPL-3",
            }
        ),
        encoding="utf-8",
    )
    (pkg / "__init__.py").write_text("from . import models\n", encoding="utf-8")
    (pkg / "models.py").write_text(HOLDER_MODELS, encoding="utf-8")
    (pkg / "security" / "security.xml").write_text(HOLDER_SECURITY, encoding="utf-8")


def _write_late(root) -> None:
    pkg = root / LATE
    pkg.mkdir()
    (pkg / "__manifest__.py").write_text(
        repr(
            {
                "name": LATE,
                "version": "1.0",
                "depends": ["base"],
                "post_init_hook": "post_init_hook",
                "installable": True,
                "license": "LGPL-3",
            }
        ),
        encoding="utf-8",
    )
    (pkg / "__init__.py").write_text(LATE_HOOK, encoding="utf-8")


@pytest.fixture
def populated_db(base_db, tmp_path_factory):
    if dropdb_path() is None or psql_path() is None:
        pytest.skip("psql/dropdb not on PATH")
    extra = tmp_path_factory.mktemp("install_privilege_addons")
    _write_holder(extra)
    _write_late(extra)
    addons = f"{REPO_ROOT / 'odoo' / 'addons'},{REPO_ROOT / 'addons'},{extra}"
    data_dir = tmp_path_factory.mktemp("install_privilege_data")
    db = f"odoo_install_privilege_{uuid.uuid4().hex[:12]}"
    Registry.remove(base_db)
    odoo.db.close_db(base_db)
    with psycopg.connect(dbname="postgres", autocommit=True) as connection:
        connection.execute(f'CREATE DATABASE "{db}" TEMPLATE "{base_db}"')
    try:
        yield lambda *args: _run_odoo_bin(db, addons, data_dir, *args), db
    finally:
        subprocess.run(
            [dropdb_path(), "--if-exists", "--force", db],
            check=False,
            capture_output=True,
        )


@requires_pg
@requires_psql
def test_a_module_elevates_to_its_own_privilege_on_rows_that_predate_it(
    populated_db,
):
    run, db = populated_db
    assert _get_rows(db, "SELECT count(*) FROM res_partner") != {"0"}

    installed = run("-i", HOLDER)

    assert installed.returncode == 0, installed.stdout[-4000:]
    assert "names no privilege" not in installed.stdout
    assert _get_rows(
        db,
        "SELECT count(*) FROM res_partner"
        " WHERE probe_privileged_name IS DISTINCT FROM name"
        " OR probe_privileged_count IS NULL",
    ) == {"0"}
    upgraded = run("-u", HOLDER)
    assert upgraded.returncode == 0, upgraded.stdout[-4000:]


@requires_pg
@requires_psql
def test_a_privilege_its_module_never_declares_is_refused_once_its_data_loaded(
    populated_db,
):
    run, _db = populated_db

    installed = run("-i", LATE)

    assert installed.returncode != 0
    assert f"'{LATE}.privilege_never_declared' names no privilege" in installed.stdout
