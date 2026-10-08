from unittest.mock import patch

import odoo
from odoo.exceptions import AccessError
from odoo.tests import new_test_user

from odoo.addons.point_of_sale.tests.common import TestPoSCommon

SCENARIOS = (
    "load_onboarding_clothes_scenario",
    "load_onboarding_bakery_scenario",
    "load_onboarding_furniture_scenario",
    "load_onboarding_retail_scenario",
)


@odoo.tests.tagged("post_install", "-at_install")
class TestPosOnboardingScenarios(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.accounting_manager = new_test_user(
            cls.env,
            login="pos_onboarding_accounting_manager",
            groups="base.group_user,point_of_sale.group_pos_manager,account.group_account_manager",
            company_id=cls.company.id,
        )
        cls.admin = new_test_user(
            cls.env,
            login="pos_onboarding_admin",
            groups="base.group_user,base.group_system,point_of_sale.group_pos_manager,account.group_account_manager",
            company_id=cls.company.id,
        )

    def _patch_journal_creation(self):
        non_cash = self.config.payment_method_ids.filtered(
            lambda method: not method.is_cash_count
        )
        return patch.object(
            type(self.env["pos.config"]),
            "_create_journal_and_payment_methods",
            autospec=True,
            return_value=(self.config.journal_id, non_cash.ids),
        )

    def test_a_scenario_needs_the_sample_data_grant(self):
        Config = self.env["pos.config"].with_user(self.accounting_manager)
        for scenario in SCENARIOS:
            with (
                self.subTest(scenario=scenario),
                self._patch_journal_creation() as create_journal,
                self.assertRaises(AccessError),
            ):
                getattr(Config, scenario)(False)
            create_journal.assert_not_called()

    def test_an_administrator_loads_a_scenario(self):
        Config = self.env["pos.config"].with_user(self.admin)
        with self._patch_journal_creation():
            result = Config.load_onboarding_retail_scenario(False)
        self.assertTrue(Config.browse(result["config_id"]).exists())
