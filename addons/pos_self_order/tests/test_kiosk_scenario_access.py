from unittest.mock import patch

import odoo
from odoo.exceptions import AccessError
from odoo.tests import new_test_user

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@odoo.tests.tagged("post_install", "-at_install")
class TestKioskScenarioAccess(TestPoSCommon):
    def test_the_kiosk_scenario_needs_the_sample_data_grant(self):
        manager = new_test_user(
            self.env,
            login="pos_kiosk_scenario_manager",
            groups="base.group_user,point_of_sale.group_pos_manager,account.group_account_manager",
            company_id=self.company.id,
        )
        Config = self.env["pos.config"]
        with (
            patch.object(
                type(Config), "_create_journal_and_payment_methods", autospec=True
            ) as create_journal,
            self.assertRaises(AccessError),
        ):
            Config.with_user(manager).load_onboarding_kiosk_scenario()
        create_journal.assert_not_called()
