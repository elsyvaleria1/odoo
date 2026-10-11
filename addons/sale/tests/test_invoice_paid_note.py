from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.sale.tests.common import TestSaleCommon


@tagged("post_install", "-at_install")
class TestInvoicePaidNote(TestSaleCommon):
    def test_paid_invoices_note_their_orders_in_one_insert(self):
        orders = self.env["sale.order"].create(
            [
                {
                    "partner_id": partner.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": self.company_data[
                                    "product_service_order"
                                ].id,
                                "product_qty": 1.0,
                            }
                        )
                    ],
                }
                for partner in (self.partner_a, self.partner_b, self.partner_a)
            ]
        )
        orders.action_confirm()
        invoices = self.env["account.move"].concat(
            *(order._create_invoices() for order in orders)
        )
        invoices.action_post()
        noted_before = orders.message_ids

        with self.capturedQueries() as queries:
            invoices._invoice_paid_hook()

        self.assertEqual(
            sum(1 for query in queries if 'INSERT INTO "mail_message"' in query), 1
        )
        for order, invoice in zip(orders, invoices, strict=True):
            [note] = order.message_ids - noted_before
            self.assertIn(f"Invoice {invoice.name} paid", str(note.body))
            self.assertEqual(note.subtype_id, self.env.ref("mail.mt_note"))
            self.assertEqual(note.message_type, "notification")
