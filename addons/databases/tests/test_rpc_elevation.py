from odoo import Command
from odoo.exceptions import AccessError
from odoo.service.model import call_kw
from odoo.tests import tagged

from .common import TestDatabasesCommon


@tagged("-at_install", "post_install")
class TestSynchronizationWizardRpcElevation(TestDatabasesCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.database = cls.env["project.project"].create(
            {
                "name": "Client",
                "database_hosting": "saas",
                "database_api_login": "login",
                "database_name": "db_name",
                "database_url": "http://client.doesnt.exist",
                "database_user_ids": [
                    Command.create({"login": "db_user@company.tld", "name": "User"})
                ],
            }
        )

    def _definition(self):
        return self.database.sudo().database_kpi_base_definition_id

    def test_a_database_user_forges_no_kpi(self):
        self.assertTrue(self.database.with_user(self.user_db_user).has_access("read"))
        self.assertFalse(self.database.with_user(self.user_db_user).has_access("write"))
        before = list(self._definition().properties_definition or [])
        wizards = self.env["wizard.project.project.synchronize.database"].with_user(self.user_db_user)
        wizard = wizards.create(
            {
                "database_ids": [Command.set(self.database.ids)],
                "property_definition": [
                    {"name": "forged", "string": "Forged", "type": "integer"}
                ],
                "new_properties": {"forged": {"label": "Forged", "checked": True}},
                "fetched_values": {str(self.database.id): {"forged": 999}},
            }
        )
        with self.assertRaises(AccessError):
            call_kw(wizards, "action_add_metrics_to_dashboard", [wizard.ids], {})
        self._definition().invalidate_recordset()
        self.assertEqual(list(self._definition().properties_definition or []), before)
