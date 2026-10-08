import importlib.util
from pathlib import Path

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestUpgrade(TransactionCase):
    def test_the_upgrade_keeps_each_websites_key(self):
        website = self.env["website"].get_current_website()
        website._set_held_secrets({"google_places_api_key": "OLD"})
        path = Path(__file__).parents[1] / "migrations" / "1.2" / "post-migrate.py"
        spec = importlib.util.spec_from_file_location("checkout_1_2", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        migration.migrate(self.env.cr, "1.1")

        website.invalidate_recordset(["address_autocomplete_key"])
        self.assertEqual(website.address_autocomplete_key, "OLD")
        self.assertFalse(website._get_held_secret("google_places_api_key"))
