from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestPurchaseApprovalAbsence(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.company.po_validation_level = "module_approval"
        cls.categories = cls.env["approval.category"].search(
            [("approval_type", "=", "purchase"), ("target_model", "=", False)]
        )
        cls.categories.active = False
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Purchases from 1000",
                "approval_type": "purchase",
                "order_approval_mode": "amount",
                "order_amount_min": 1000.0,
                "has_amount": "required",
                "has_partner": "required",
            }
        )
        cls.approver = new_test_user(
            cls.env,
            login="purchase_absence_approver",
            groups="purchase.group_purchase_manager",
            company_id=cls.company.id,
        )
        add_category_approver(cls.category, cls.approver, required=True)
        cls.vendor = cls.env["res.partner"].create({"name": "Absence Vendor"})
        cls.product = cls.env["product.product"].create(
            {"name": "Absence Supply", "type": "consu", "standard_price": 100.0}
        )

    def _create_order(self, qty):
        return self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": qty,
                            "price_unit": 100.0,
                        }
                    )
                ],
            }
        )

    def test_a_configured_category_that_does_not_apply_still_refuses(self):
        order = self._create_order(1)
        self.assertTrue(order.approval_required)
        with self.assertRaisesRegex(UserError, "No approval category matches"):
            order.action_confirm()

    def test_no_category_configured_asks_no_approval(self):
        self.category.active = False
        order = self._create_order(20)
        self.assertFalse(order.approval_required)
        order.action_confirm()
        self.assertIn(order.state, ("purchase", "done"))

    def test_a_category_that_applies_still_gates(self):
        order = self._create_order(20)
        self.assertTrue(order.approval_required)
        order.action_confirm()
        self.assertEqual(order.state, "draft")
        self.assertEqual(order.approval_state, "pending")
