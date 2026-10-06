from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import users, warmup
from odoo.tools import mute_logger

from odoo.addons.sms.tests import common as sms_common
from odoo.addons.test_mail.tests.test_performance import BaseMailPerformance


@tagged("mail_performance", "post_install", "-at_install")
class TestSMSPerformance(BaseMailPerformance, sms_common.SMSCase):
    def setUp(self):
        super().setUp()

        self.test_record = (
            self.env["mail.test.sms"]
            .with_context(self._test_context)
            .create(
                {
                    "name": "Test",
                    "customer_id": self.customer.id,
                    "phone_nbr_ids": [
                        Command.create({"number": "0456999999", "type": "landline"})
                    ],
                }
            )
        )

        # prepare recipients to test for more realistic workload
        Partners = self.env["res.partner"].with_context(self._test_context)
        self.partners = self.env["res.partner"]
        for x in range(10):
            self.partners |= Partners.create(
                {
                    "name": "Test %s" % x,
                    "email": "test%s@example.com" % x,
                    "phone_ids": [
                        Command.create(
                            {"number": "0456%s%s0000" % (x, x), "type": "landline"}
                        )
                    ],
                    "country_id": self.env.ref("base.be").id,
                }
            )

    @mute_logger("odoo.addons.sms.models.sms_sms")
    @users("employee")
    @warmup
    def test_message_sms_record_1_partner(self):
        record = self.test_record.with_user(self.env.user)
        pids = self.customer.ids
        with (
            self.subTest("QueryCount"),
            self.mockSMSGateway(),
            # +2 mail.config, +3 the company's integration_twilio_config looked up and created on first send
            self.assertQueryCount(employee=37),
        ):  # tme: 31
            messages = record._message_sms(
                body="Performance Test",
                partner_ids=pids,
            )

        self.assertEqual(record.message_ids[0].body, "<p>Performance Test</p>")
        self.assertSMSNotification(
            [{"partner": self.customer}], "Performance Test", messages
        )
