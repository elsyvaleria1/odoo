from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestSaleApprovalAbsence(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.company.so_validation_level = "module_approval"
        cls.categories = cls.env["approval.category"].search(
            [("approval_type", "=", "sale"), ("target_model", "=", False)]
        )
        cls.approver = new_test_user(
            cls.env,
            login="sale_absence_approver",
            groups="sale.group_sale_manager",
            company_id=cls.company.id,
        )
        for category in cls.categories:
            add_category_approver(category, cls.approver, required=True)
        cls.partner = cls.env["res.partner"].create({"name": "Absence Customer"})
        cls.product = cls.env["product.product"].create(
            {"name": "Absence Product", "type": "consu", "list_price": 100.0}
        )

    def _create_order(self):
        return self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "company_id": self.company.id,
                "line_ids": [
                    Command.create({"product_id": self.product.id, "product_qty": 1})
                ],
            }
        )

    def test_no_category_configured_asks_no_approval(self):
        self.categories.active = False
        order = self._create_order()
        self.assertFalse(order.approval_required)
        order.action_confirm()
        self.assertIn(order.state, ("sale", "done"))
        self.assertFalse(order.approval_request_id)

    def test_a_configured_category_that_does_not_apply_still_refuses(self):
        someone_else = self.env["res.partner"].create({"name": "Someone Else"})
        self.categories.order_partner_ids = [Command.set(someone_else.ids)]
        order = self._create_order()
        self.assertTrue(order.approval_required)
        with self.assertRaisesRegex(UserError, "No approval category matches"):
            order.action_confirm()

    def test_a_category_that_applies_still_gates(self):
        self.assertTrue(self.categories)
        order = self._create_order()
        self.assertTrue(order.approval_required)
        order.action_confirm()
        self.assertEqual(order.state, "draft")
        self.assertEqual(order.approval_state, "pending")
