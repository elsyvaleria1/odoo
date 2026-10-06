from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from odoo.addons.account_collection_sale.tests import test_cash_sale


@tagged("post_install", "-at_install")
class TestHandOverOutsideTrips(test_cash_sale.TestCashSale):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        warehouse.out_type_id.write(
            {
                "dispatch_management": True,
                "dispatch_batch_required": True,
                "delivery_proof_required": True,
                "delivery_proof_since": fields.Datetime.now() - timedelta(days=30),
            }
        )

    def test_handed_over_goods_leave_in_no_trip(self):
        order = self._storable_order(stock=10)

        self._collect(order, hand_over=True)

        picking = order.picking_ids
        self.assertEqual(picking.state, "done")
        self.assertFalse(picking.batch_id)
        self.assertFalse(picking._requires_trip())
        self.assertFalse(picking._requires_delivery_proof())
