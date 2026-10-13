import tempfile
from pathlib import Path
from unittest.mock import patch

from odoo.modules import neutralize
from odoo.modules.module import Manifest
from odoo.tests import tagged
from odoo.tests.common import BaseCase, TransactionCase

import odoo.addons


@tagged("post_install", "-at_install", "neutralize")
class TestNeutralize(TransactionCase):
    def test_10_neutralize(self):
        installed_modules = neutralize.get_installed_module_names(self.cr)
        queries = neutralize.get_neutralization_queries(installed_modules)
        for query in queries:
            self.cr.execute(query)

    def test_a_copy_gets_a_secret_it_can_open(self):
        """The source's sealed secret is replaced, not left for every request to fail on."""
        self.cr.execute(
            "UPDATE ir_config_parameter SET value = 'fernet:sealed-elsewhere'"
            " WHERE key = 'database.secret'"
        )
        for query in neutralize.get_neutralization_queries(["base"]):
            self.cr.execute(query)
        self.env.registry.clear_cache("stable")
        secret = self.env["ir.config_parameter"].sudo().get_param("database.secret")
        self.assertTrue(secret)
        self.assertFalse(secret.startswith("fernet:"))


class TestNeutralizeQueries(BaseCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="odoo_test_neutralize_")
        self.addCleanup(self._tmp.cleanup)
        p = patch.object(odoo.addons, "__path__", [self._tmp.name])
        p.start()
        self.addCleanup(p.stop)
        saved = dict(Manifest._parse_cache)
        Manifest.clear_caches()

        def _restore():
            Manifest._parse_cache.clear()
            Manifest._parse_cache.update(saved)

        self.addCleanup(_restore)

    def _create_module_directory(self, name, neutralize_sql=None):
        d = Path(self._tmp.name, name)
        (d / "data").mkdir(parents=True)
        (d / "__manifest__.py").write_text(
            "{'name': 'X', 'license': 'LGPL-3', 'author': 'x'}"
        )
        if neutralize_sql is not None:
            (d / "data" / "neutralize.sql").write_text(neutralize_sql)
        return name

    def test_empty_and_whitespace_files_are_skipped(self):
        modules = [
            self._create_module_directory("probe_empty", ""),
            self._create_module_directory("probe_blank", "  \n\t\n"),
            self._create_module_directory(
                "probe_real", "UPDATE res_users SET active = active;\n"
            ),
            self._create_module_directory("probe_none"),
        ]
        queries = list(neutralize.get_neutralization_queries(modules))
        self.assertEqual(queries, ["UPDATE res_users SET active = active;"])
