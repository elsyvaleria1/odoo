from __future__ import annotations

import subprocess
import uuid

import pytest

from .._pg import dropdb_path, pg_reachable, psql_path
from .test_unchanged_module_follows_a_recreated_reference import (
    REPO_ROOT,
    _get_rows,
    _run_odoo_bin,
)

PROBE = "probe_activity_owner"
MODELS = f"""from odoo import models


class ProbeActivity(models.Model):
    _name = "{PROBE.replace("_", ".")}"
    _inherit = ["mixin.mail.activity"]
    _description = "Probe activity"
"""


def _get_activity_states(db: str) -> set[str]:
    return _get_rows(
        db,
        "SELECT s.value FROM ir_model_fields_selection s"
        " JOIN ir_model_fields f ON f.id = s.field_id"
        f" WHERE f.model = '{PROBE.replace('_', '.')}' AND f.name = 'activity_state'",
    )


@pytest.fixture
def probe(tmp_path_factory):
    if not pg_reachable():
        pytest.skip("no reachable PostgreSQL")
    if dropdb_path() is None or psql_path() is None:
        pytest.skip("psql/dropdb not on PATH")
    extra = tmp_path_factory.mktemp("selection_probe_addons")
    package = extra / PROBE
    package.mkdir()
    (package / "__manifest__.py").write_text(
        repr(
            {
                "name": PROBE,
                "version": "1.0",
                "depends": ["mail"],
                "installable": True,
                "license": "LGPL-3",
            }
        ),
        encoding="utf-8",
    )
    (package / "__init__.py").write_text("from . import models\n", encoding="utf-8")
    (package / "models.py").write_text(MODELS, encoding="utf-8")
    addons = f"{REPO_ROOT / 'odoo' / 'addons'},{REPO_ROOT / 'addons'},{extra}"
    data_dir = tmp_path_factory.mktemp("selection_probe_data")
    db = f"odoo_selprobe_{uuid.uuid4().hex[:12]}"

    def run(*args: str) -> str:
        done = _run_odoo_bin(db, addons, data_dir, *args)
        assert done.returncode == 0, done.stdout[-4000:]
        return done.stdout

    run.db = db
    try:
        run("-i", f"base,mail,{PROBE}")
        run("-u", PROBE)
        yield run
    finally:
        subprocess.run(
            [dropdb_path(), "--if-exists", "--force", db], check=False, timeout=60
        )


@pytest.mark.requires_pg
@pytest.mark.requires_psql
def test_a_module_left_unchanged_keeps_the_selection_values_its_mixin_reflects(probe):
    db = probe.db
    states = _get_activity_states(db)
    assert states == {"overdue", "today", "planned"}, states

    out = probe("-u", "mail")

    assert "unchanged modules left as installed" in out, (
        "the probe module must be skipped for this test to mean anything"
    )
    assert f"Loading module {PROBE} " not in out
    assert _get_activity_states(db) == states, (
        "mail's selection values on a model of a module this upgrade skipped are "
        "still declared; the stale-data sweep deleted them"
    )
