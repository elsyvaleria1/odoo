from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestPurchaseApproverReach(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["approval.category"].search(
            [("approval_type", "=", "purchase"), ("target_model", "=", False)]
        ).write({"active": False})
        cls.buyer = new_test_user(
            cls.env, login="reach_buyer", groups="purchase.group_purchase_user"
        )
        cls.approver = new_test_user(
            cls.env, login="reach_approver", groups="base.group_user"
        )
        category = cls.env["approval.category"].create(
            {
                "name": "Reach PO Approval",
                "approval_type": "purchase",
                "approval_minimum": 1,
                "has_amount": "required",
                "has_partner": "required",
            }
        )
        add_category_approver(category, cls.approver, required=True)
        cls.env.cr.flush()
        vendor = cls.env["res.partner"].create(
            {"name": "Reach Vendor", "supplier_rank": 1, "po_approval_required": True}
        )
        product = cls.env["product.product"].create(
            {"name": "Reach Product", "type": "consu", "standard_price": 75.0}
        )
        cls.order = (
            cls.env["purchase.order"]
            .with_user(cls.buyer)
            .create(
                {
                    "partner_id": vendor.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": product.id,
                                "product_qty": 50.0,
                                "price_unit": 75.0,
                            }
                        )
                    ],
                }
            )
        )

    def test_nobody_outside_a_pool_gains_model_access(self):
        bystander = new_test_user(
            self.env, login="reach_bystander", groups="base.group_user"
        )
        self.order.with_user(self.buyer).action_confirm()
        self.assertFalse(
            self.env["purchase.order"].with_user(bystander).has_access("read")
        )
        self.assertTrue(
            self.approver.has_group("approval.group_approval_decider"),
            "a step member holds the Decider group",
        )
        self.assertTrue(
            self.env["purchase.order"].with_user(self.approver).has_access("read")
        )

    def test_the_approver_reads_the_order_while_they_decide(self):
        order = self.order.with_user(self.approver)
        with self.assertRaises(AccessError):
            order.check_access("read")
        self.order.with_user(self.buyer).action_confirm()
        request = self.order.approval_request_id
        self.assertEqual(request.state, "pending")
        order.check_access("read")
        self.assertEqual(
            request.with_user(self.approver).res_name, self.order.display_name
        )
        request.with_user(self.approver).action_approve()
        self.env.invalidate_all()
        with self.assertRaises(AccessError):
            order.check_access("read")
