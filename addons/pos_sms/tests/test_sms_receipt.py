from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install")
class TestSmsReceiptNumber(TestPoSCommon):
    def test_a_receipt_number_is_keyed_in_the_customers_country(self):
        self.config = self.basic_config
        self.config.write(
            {
                "module_pos_sms": True,
                "sms_receipt_template_id": self.env.ref(
                    "pos_sms.sms_template_data_point_of_sale"
                ).id,
            }
        )
        self.open_new_session()
        belgium = self.env.ref("base.be")
        self.env.company.country_id = self.env.ref("base.fr")
        french_line = self.env["phone.number"].create({"number": "+33 4 78 12 34 56"})
        self.env["res.partner"].create(
            {"name": "Lyon shop", "phone_ids": [Command.link(french_line.id)]}
        )
        customer = self.env["res.partner"].create(
            {"name": "Tourist", "country_id": belgium.id}
        )
        order = self.env["pos.order"].create(
            {
                "session_id": self.pos_session.id,
                "partner_id": customer.id,
                "amount_tax": 0,
                "amount_total": 0,
                "amount_paid": 0,
                "amount_return": 0,
            }
        )
        Composer = self.env.registry["wizard.sms.sms.send"]

        with patch.object(Composer, "action_send_sms", lambda composer: None):
            order.action_sent_message_on_sms("0478 12 34 56", None)

        self.assertEqual(order.phone_ids.sanitized, "+32478123456")
        self.assertNotIn(french_line, customer.phone_ids)
