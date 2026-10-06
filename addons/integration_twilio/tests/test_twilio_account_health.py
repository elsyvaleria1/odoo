from odoo.tests import tagged

from odoo.addons.integration_twilio.tests.common import MockSmsTwilio


@tagged("post_install", "-at_install", "twilio")
class TestTwilioAccountHealth(MockSmsTwilio):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_sms_twilio(cls.company_admin)
        cls.config = cls.company_admin.integration_twilio_config_id.sudo()

    def _alerts(self):
        return self.config.activity_ids.activity_type_id.mapped("name")

    def test_hourly_probe_reads_status_and_balance(self):
        result = self.config.credential_id._probe_health()

        self.assertTrue(result["success"])
        self.assertRecordValues(
            self.config,
            [
                {
                    "twilio_account_status": "active",
                    "twilio_account_type": "Full",
                    "twilio_currency_id": self.env.ref("base.USD").id,
                    "amount_twilio_balance": 12.5,
                }
            ],
        )
        self.assertTrue(self.config.date_twilio_checked)
        self.assertFalse(self._alerts())

    def test_low_balance_raises_one_activity_and_clears_it(self):
        self.config.amount_twilio_balance_alert = 20
        self.config._refresh_account_state()
        self.config._refresh_account_state()
        self.assertEqual(self._alerts(), ["Twilio Balance Low"])

        self.patch(
            type(self), "balance_json", {**self.balance_json, "balance": "50.00"}
        )
        self.config._refresh_account_state()
        self.assertFalse(self._alerts())

    def test_suspended_account_raises_an_activity(self):
        self.patch(
            type(self), "account_json", {**self.account_json, "status": "suspended"}
        )
        self.config._refresh_account_state()
        self.assertEqual(self._alerts(), ["Twilio Account Stopped"])
        self.assertEqual(
            self.config.activity_ids.user_id, self.env.ref("base.user_admin")
        )

    def test_alerts_go_to_the_chosen_user_whoever_ran_the_check(self):
        manager = self.env["res.users"].create(
            {
                "name": "Twilio manager",
                "login": "twilio_manager",
                "group_ids": [(6, 0, self.env.ref("base.group_system").ids)],
            }
        )
        self.config.write(
            {"twilio_alert_user_id": manager.id, "amount_twilio_balance_alert": 20}
        )
        self.config.with_user(self.env.ref("base.user_root"))._refresh_account_state()
        self.assertEqual(self.config.activity_ids.user_id, manager)
