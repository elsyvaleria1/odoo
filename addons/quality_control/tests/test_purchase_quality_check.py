from odoo import fields
from odoo.tests import tagged, users

from .test_common import TestQualityCommon


@tagged("post_install", "-at_install")
class TestPurchaseQualityCheck(TestQualityCommon):
    def setUp(self):
        super().setUp()
        if "purchase.order" not in self.env:
            self.skipTest("`purchase` is not installed")

        self.buyer = self.env["res.users"].create(
            {
                "name": "Buyer",
                "login": "buyer",
                "email": "superbuyer@example.com",
                "group_ids": [
                    (4, self.ref("base.group_user")),
                    (4, self.ref("purchase.group_purchase_user")),
                ],
            }
        )

        self.quality_point_test = self.env["quality.point"].create(
            {
                "product_ids": [(4, self.product.id)],
                "picking_type_ids": [(4, self.picking_type_id)],
            }
        )

    @users("buyer")
    def test_purchase_quality_check(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": self.product.name,
                            "product_id": self.product.id,
                            "product_qty": 1.0,
                            "product_uom_id": self.product.uom_id.id,
                            "price_unit": 1.0,
                            "date_commitment": fields.Datetime.now(),
                        },
                    )
                ],
            }
        )
        po.action_confirm()

        po_sudo = po.sudo()
        self.assertTrue(po_sudo.picking_ids, "Incoming shipment not created.")

        self.assertEqual(len(po_sudo.picking_ids.check_ids), 1)
        self.assertEqual(po_sudo.picking_ids.check_ids.quality_state, "none")

        self.env["stock.move.line"].invalidate_model()
        po.action_cancel()

        self.assertEqual(
            po_sudo.picking_ids.state,
            "cancel",
            "The picking should be canceled after the PO cancellation",
        )
        self.assertFalse(
            po_sudo.picking_ids.check_ids,
            "The quality check should be removed after the picking cancellation",
        )
