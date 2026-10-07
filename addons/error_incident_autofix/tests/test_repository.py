import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.error_incident_autofix.models import (
    error_incident_autofix_repository as repository,
)

CONFIG = '[core]\n\tbare = false\n[remote "origin"]\n\turl = {url}\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n'


@tagged("post_install", "-at_install")
class TestRepositoryOfAModule(TransactionCase):
    def setUp(self):
        super().setUp()
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.Repository = self.env["error.incident.autofix.repository"]

    def _clone(self, directory, url):
        checkout = self.root / directory
        (checkout / ".git").mkdir(parents=True)
        (checkout / ".git" / "config").write_text(CONFIG.format(url=url))
        (checkout / "addons" / "stock_x").mkdir(parents=True)
        return checkout

    def _for(self, module_path):
        with patch.object(repository, "get_module_path", return_value=str(module_path)):
            return self.Repository._for_module("stock_x")

    def test_a_checkout_is_known_by_its_remote_not_its_directory(self):
        checkout = self._clone("odoo-19-prod", "https://github.com/Agro-Marin/odoo.git")
        self.assertEqual(
            self._for(checkout / "addons" / "stock_x"),
            self.env.ref("error_incident_autofix.repository_odoo"),
        )

    def test_an_ssh_remote_names_its_repository_too(self):
        checkout = self._clone("src", "git@github.com:Agro-Marin/agromarin.git")
        self.assertEqual(
            self._for(checkout / "addons" / "stock_x"),
            self.env.ref("error_incident_autofix.repository_agromarin"),
        )

    def test_a_worktree_reads_the_remote_of_its_repository(self):
        main = self._clone("l10n-main", "https://github.com/Agro-Marin/l10n")
        (main / ".git" / "worktrees" / "wh").mkdir(parents=True)
        (main / ".git" / "worktrees" / "wh" / "commondir").write_text("../..\n")
        worktree = self.root / "wh"
        (worktree / "addons" / "stock_x").mkdir(parents=True)
        (worktree / ".git").write_text(f"gitdir: {main}/.git/worktrees/wh\n")
        self.assertEqual(
            self._for(worktree / "addons" / "stock_x"),
            self.env.ref("error_incident_autofix.repository_l10n"),
        )

    def test_without_a_known_remote_the_directory_name_decides(self):
        checkout = self._clone("agromarin", "https://gitlab.example/someone/else.git")
        self.assertEqual(
            self._for(checkout / "addons" / "stock_x"),
            self.env.ref("error_incident_autofix.repository_agromarin"),
        )

    def test_a_module_outside_any_checkout_has_no_repository(self):
        (self.root / "loose" / "stock_x").mkdir(parents=True)
        self.assertFalse(self._for(self.root / "loose" / "stock_x"))
