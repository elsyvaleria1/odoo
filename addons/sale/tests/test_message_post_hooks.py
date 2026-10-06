from odoo.tests import tagged

from odoo.addons.mail.tests.common import MailCase
from odoo.addons.sale.tests.common import SaleCommon


@tagged("post_install", "-at_install", "mail_post")
class TestSaleMessagePostBatch(SaleCommon, MailCase):
    def test_mass_comment_marks_every_draft_order_as_sent(self):
        orders = self.empty_order | self.sale_order
        self.assertEqual(set(orders.mapped("state")), {"draft"})
        composer = (
            self.env["wizard.mail.message.send"]
            .with_context(mark_so_as_sent=True)
            .create(
                {
                    "body": "<p>Your quotation</p>",
                    "composition_mode": "comment",
                    "model": orders._name,
                    "res_ids": orders.ids,
                }
            )
        )
        with self.mock_mail_gateway():
            composer._action_send_mail()
        self.assertEqual(orders.mapped("sent"), [True, True])
