import importlib.util
from datetime import datetime
from pathlib import Path

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestUpgradeToEngineFloors(TransactionCase):
    def setUp(self):
        super().setUp()
        Users = self.env["res.users"].with_context(no_reset_password=True)
        self.accounts = {}
        for name, values in (
            ("reset", {"insert_since": datetime(2026, 6, 1), "sync_token": "t"}),
            ("synced", {"sync_token": "t"}),
            ("never", {}),
        ):
            user = Users.create({"name": name, "login": f"upgrade_floor_{name}"})
            account = self.env["calendar.sync.account"].create(
                {"user_id": user.id, "provider": "microsoft"}
            )
            account.write({"insert_since": False, **values})
            self.accounts[name] = account

    def _migrate(self, first):
        icp = self.env["ir.config_parameter"].sudo()
        key = "calendar_microsoft.sync.first_synchronization_date"
        icp.set_param(key, first or "")
        path = Path(__file__).parents[1] / "migrations" / "1.7" / "post-migrate.py"
        spec = importlib.util.spec_from_file_location("microsoft_1_7", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.migrate(self.env.cr, "1.6")
        self.env.invalidate_all()
        self.assertFalse(icp.get_param(key))

    def test_the_database_date_becomes_the_floor_of_accounts_without_one(self):
        self._migrate("2025-01-01 00:00:00")
        self.assertEqual(
            {name: account.insert_since for name, account in self.accounts.items()},
            {
                "reset": datetime(2026, 6, 1),
                "synced": datetime(2025, 1, 1),
                "never": datetime(2025, 1, 1),
            },
        )

    def test_without_a_date_an_account_that_never_synchronized_starts_now(self):
        self._migrate(False)
        self.assertEqual(self.accounts["reset"].insert_since, datetime(2026, 6, 1))
        self.assertFalse(self.accounts["synced"].insert_since)
        self.assertTrue(self.accounts["never"].insert_since)

    def test_a_new_account_sends_what_was_created_since_the_first_synchronization(self):
        self._migrate("2025-01-01 00:00:00")
        user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create({"name": "late", "login": "upgrade_floor_late"})
        )
        account = self.env["calendar.sync.account"].create(
            {"user_id": user.id, "provider": "microsoft"}
        )
        self.assertEqual(account.insert_since, datetime(2025, 1, 1))
