from unittest.mock import patch

import odoo
from odoo.exceptions import AccessError
from odoo.tests import new_test_user

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@odoo.tests.tagged("post_install", "-at_install")
class TestPosRestaurantOnboardingScenarios(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config

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

    def test_a_restaurant_scenario_needs_the_sample_data_grant(self):
        manager = new_test_user(
            self.env,
            login="pos_restaurant_onboarding_manager",
            groups="base.group_user,point_of_sale.group_pos_manager,account.group_account_manager",
            company_id=self.company.id,
        )
        Config = self.env["pos.config"].with_user(manager)
        for scenario in (
            "load_onboarding_restaurant_scenario",
            "load_onboarding_bar_scenario",
        ):
            with (
                self.subTest(scenario=scenario),
                self._patch_journal_creation() as create_journal,
                self.assertRaises(AccessError),
            ):
                getattr(Config, scenario)(False)
            create_journal.assert_not_called()

    def test_the_restaurant_scenario_survives_a_missing_main_company_reference(self):
        Config = self.env["pos.config"]
        self.env["ir.model.data"].search(
            [("module", "=", "base"), ("name", "=", "main_company")]
        ).unlink()
        self.env.registry.clear_cache()
        sessions_before = self.env["pos.session"].search([])
        with (
            self._patch_journal_creation(),
            patch.object(type(Config), "_load_restaurant_demo_data", autospec=True),
        ):
            result = Config.load_onboarding_restaurant_scenario(with_demo_data=True)
        config = Config.browse(result["config_id"])
        self.assertTrue(config.exists())
        self.assertFalse(config.session_ids)
        self.assertEqual(self.env["pos.session"].search([]), sessions_before)
