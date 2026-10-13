from __future__ import annotations

import subprocess
import sys
import uuid

import pytest

from .._pg import dropdb_path, pg_reachable, psql_path, repo_root

REPO_ROOT = repo_root()
PARENT, CHILD, LAST = "probe_ledger", "probe_ledger_tax", "probe_ledger_audit"

PARENT_MODELS = """
from odoo import fields, models
from odoo.db.schema import drop_view_if_exists
from odoo.tools import frozendict


class ProbeLedger(models.Model):
    _name = "probe.ledger"
    _description = "Rows the report reads"

    name = fields.Char()


class ProbeLedgerReport(models.Model):
    _name = "probe.ledger.report"
    _description = "A view the upgraded parent recreates"
    _auto = False
    _depends = frozendict({"probe.ledger": ["name"]})

    name = fields.Char(readonly=True)

    def _select(self):
        return "SELECT L.id AS id, L.name AS name"

    def init(self):
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            f"CREATE VIEW {self._table} AS ({self._select()} FROM probe_ledger L)"
        )
"""

CHILD_MODELS = """
from odoo import fields, models
from odoo.tools import frozendict


class ProbeLedger(models.Model):
    _inherit = "probe.ledger"

    tax = fields.Integer()


class ProbeLedgerReport(models.Model):
    _inherit = "probe.ledger.report"
    _depends = frozendict({"probe.ledger": ["tax"]})

    tax = fields.Integer(readonly=True)

    def _select(self):
        return super()._select() + ", L.tax AS tax"
"""

REPORT_TEST = """
from odoo.tests import TransactionCase


class TestReportReadsEveryColumn(TransactionCase):
    def test_report_reads_every_column(self):
        row = self.env["probe.ledger"].create({{"name": "{name}"}})
        self.env.flush_all()
        report = self.env["probe.ledger.report"].search([("id", "=", row.id)])
        self.assertEqual(report.mapped("name"), ["{name}"])
"""


def _write(root, name: str, depends: list[str], models: str | None) -> None:
    pkg = root / name
    (pkg / "tests").mkdir(parents=True, exist_ok=True)
    (pkg / "__manifest__.py").write_text(
        repr(
            {
                "name": name,
                "version": "1.0",
                "depends": depends,
                "installable": True,
                "license": "LGPL-3",
            }
        ),
        encoding="utf-8",
    )
    if models is None:
        (pkg / "__init__.py").write_text("", encoding="utf-8")
    else:
        (pkg / "models").mkdir(exist_ok=True)
        (pkg / "__init__.py").write_text("from . import models\n", encoding="utf-8")
        (pkg / "models" / "__init__.py").write_text(
            "from . import m\n", encoding="utf-8"
        )
        (pkg / "models" / "m.py").write_text(models, encoding="utf-8")
    (pkg / "tests" / "__init__.py").write_text(
        "from . import test_report\n", encoding="utf-8"
    )
    (pkg / "tests" / "test_report.py").write_text(
        REPORT_TEST.format(name=name), encoding="utf-8"
    )


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


@pytest.mark.requires_pg
@pytest.mark.requires_psql
def test_at_install_tests_read_a_view_an_unchanged_module_extends(tmp_path_factory):
    if not pg_reachable():
        pytest.skip("no reachable PostgreSQL")
    if dropdb_path() is None or psql_path() is None:
        pytest.skip("psql/dropdb not on PATH")

    extra = tmp_path_factory.mktemp("view_probe_addons")
    addons = f"{REPO_ROOT / 'odoo' / 'addons'},{REPO_ROOT / 'addons'},{extra}"
    data_dir = tmp_path_factory.mktemp("view_probe_data")
    db = f"odoo_viewprobe_{uuid.uuid4().hex[:12]}"
    try:
        _write(extra, PARENT, ["base"], PARENT_MODELS)
        _write(extra, CHILD, [PARENT], CHILD_MODELS)
        _write(extra, LAST, [CHILD], None)
        run = _run_odoo_bin(db, addons, data_dir, "-i", f"base,{PARENT},{CHILD},{LAST}")
        assert run.returncode == 0, run.stdout[-4000:]
        run = _run_odoo_bin(db, addons, data_dir, "-u", "base")
        assert run.returncode == 0, run.stdout[-4000:]

        run = _run_odoo_bin(
            db,
            addons,
            data_dir,
            "-u",
            f"{PARENT},{LAST}",
            "--test-enable",
            "--test-tags",
            f"/{PARENT},/{LAST}",
        )
        assert "unchanged modules left as installed" in run.stdout, (
            "the child must be left out of the upgrade for this test to mean anything"
        )
        assert f"Module {PARENT}: 1 at_install test(s) deferred" in run.stdout
        assert f"Module {LAST}: 1 at_install test(s) deferred" not in run.stdout
        assert "0 failed, 0 error(s) of 2 tests" in run.stdout, (
            "the upgraded parent recreated its view without the unchanged child's "
            "column, and the at_install tests read it before the child's extension "
            "was put back:\n" + run.stdout[-4000:]
        )
        assert run.returncode == 0, run.stdout[-4000:]
    finally:
        subprocess.run(
            [dropdb_path(), "--if-exists", "--force", db], check=False, timeout=60
        )
