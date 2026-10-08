from odoo.tests.common import HttpCase, tagged


@tagged("-at_install", "post_install")
class TestPurchaseOnboardingTour(HttpCase):
    def test_purchase_tour_ends_on_a_draft_bill_for_the_received_quantity(self):
        vendor = self.env["res.partner"].create(
            {"name": "Azure Interior", "email": "azure.interior@example.com"}
        )
        self.env["product.product"].create(
            {
                "name": "Office Desk",
                "default_code": "DESK0001",
                "is_storable": True,
                "purchase_ok": True,
            }
        )

        self.start_tour("/odoo", "purchase_tour", login="admin")

        order = self.env["purchase.order"].search([("partner_id", "=", vendor.id)])
        self.assertEqual(order.picking_ids.state, "done")
        self.assertEqual(order.invoice_ids.state, "draft")
        self.assertEqual(order.invoice_ids.invoice_line_ids.quantity, 12)
