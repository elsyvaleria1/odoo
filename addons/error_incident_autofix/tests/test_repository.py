import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.error_incident_autofix.models import (
    error_incident_autofix_repository as repository,
)


def _git(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@x", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@tagged("post_install", "-at_install")
class TestRepositoryOfAModule(TransactionCase):
    def setUp(self):
        super().setUp()
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.Repository = self.env["error.incident.autofix.repository"]

    def _clone(self, directory, url=None):
        checkout = self.root / directory
        (checkout / "addons" / "stock_x").mkdir(parents=True)
        _git(checkout, "init", "-q")
        if url:
            _git(checkout, "remote", "add", "origin", url)
        return checkout

    def _for(self, checkout):
        module_path = checkout / "addons" / "stock_x"
        with patch.object(repository, "get_module_path", return_value=str(module_path)):
            return self.Repository._for_module("stock_x")

    def _ref(self, name):
        return self.env.ref(f"error_incident_autofix.repository_{name}")

    def test_a_checkout_is_known_by_its_remote_not_its_directory(self):
        checkout = self._clone("odoo-19-prod", "https://github.com/Agro-Marin/odoo.git")
        self.assertEqual(self._for(checkout), self._ref("odoo"))

    def test_an_ssh_remote_and_a_host_alias_name_their_repository_too(self):
        self.assertEqual(
            self._for(self._clone("a", "git@github.com:Agro-Marin/agromarin.git")),
            self._ref("agromarin"),
        )
        self.assertEqual(
            self._for(self._clone("b", "git@github.com-l10n:Agro-Marin/l10n.git")),
            self._ref("l10n"),
        )

    def test_a_worktree_reads_the_remote_of_its_repository(self):
        main = self._clone("l10n-main", "https://github.com/Agro-Marin/l10n")
        _git(main, "commit", "-q", "--allow-empty", "-m", "seed")
        worktree = self.root / "wh"
        _git(main, "worktree", "add", "-q", "--detach", str(worktree))
        (worktree / "addons" / "stock_x").mkdir(parents=True)
        self.assertEqual(self._for(worktree), self._ref("l10n"))

    def test_git_resolves_what_a_config_written_by_hand_says(self):
        checkout = self._clone("hand")
        with (checkout / ".git" / "config").open("a") as config:
            config.write(
                '[url "https://github.com/Agro-Marin/"]\n'
                "insteadOf = am:  ; a shorthand\n"
                '[remote "origin"]\n'
                'URL = "am:odoo"  # quoted, upper-cased, commented\n'
            )
        self.assertEqual(self._for(checkout), self._ref("odoo"))

    def test_without_an_origin_the_directory_name_decides(self):
        self.assertEqual(self._for(self._clone("agromarin")), self._ref("agromarin"))

    def test_an_origin_that_is_no_mapped_github_repository_is_no_ones(self):
        for name, url in (
            ("odoo", "https://github.com/someone/odoo.git"),
            ("agromarin", "https://notgithub.com/Agro-Marin/agromarin.git"),
            ("l10n", "https://gitlab.example/Agro-Marin/l10n.git"),
        ):
            self.assertFalse(self._for(self._clone(name, url)), url)
            shutil.rmtree(self.root / name)

    def test_a_module_outside_any_checkout_has_no_repository(self):
        (self.root / "loose" / "addons" / "stock_x").mkdir(parents=True)
        self.assertFalse(self._for(self.root / "loose"))

    def test_an_incident_of_no_module_has_no_repository(self):
        self.assertFalse(self.Repository._for_module(""))

    def test_an_origin_git_cannot_read_is_no_repositorys(self):
        checkout = self._clone("odoo")
        self.assertEqual(self._for(checkout), self._ref("odoo"))
        with patch.dict(repository.os.environ, {"PATH": str(self.root)}):
            self.assertFalse(self._for(checkout))

    def test_a_github_host_is_known_whatever_its_case(self):
        checkout = self._clone("somewhere", "https://GitHub.com/Agro-Marin/odoo.git")
        self.assertEqual(self._for(checkout), self._ref("odoo"))

    def test_a_look_alike_host_is_not_github(self):
        for url in (
            "https://g\u0131thub.com/Agro-Marin/odoo.git",
            "git@G\u0130THUB.COM:Agro-Marin/odoo",
        ):
            self.assertIsNone(repository.github_repository_of(url), url)
