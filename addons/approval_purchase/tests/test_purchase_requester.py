from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestPurchaseDeclaredRequester(TransactionCase):
    """The buyer an order names does not approve it, whoever sends it.

    On production, nine orders a purchasing assistant sent for approval were
    approved by their own buyer: the engine excluded only whoever pressed
    Confirm. The order's buyer is its declared requester now, and only an access
    exception lets them decide it.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["approval.category"].search(
            [("approval_type", "=", "purchase"), ("target_model", "=", False)]
        ).write({"active": False})
        cls.assistant = new_test_user(
            cls.env,
            login="requester_assistant",
            groups="purchase.group_purchase_manager",
        )
        cls.buyer = new_test_user(
            cls.env,
            login="requester_buyer",
            groups="purchase.group_purchase_user,base.group_user",
        )
        cls.approver = new_test_user(
            cls.env, login="requester_approver", groups="base.group_user"
        )
        vendor = cls.env["res.partner"].create(
            {
                "name": "Requester Vendor",
                "supplier_rank": 1,
                "po_approval_required": True,
            }
        )
        product = cls.env["product.product"].create(
            {"name": "Requester Product", "type": "consu", "standard_price": 75.0}
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Requester PO Approval",
                "approval_type": "purchase",
                "approval_minimum": 1,
                "has_amount": "required",
                "has_partner": "required",
            }
        )
        cls.env["ir.access.exception"].create(
            {
                "user_id": cls.buyer.id,
                "kind": "sod",
                "res_model": "ir.access.sod.rule",
                "res_id": cls.env.ref("approval_purchase.sod_rule_buy_and_approve").id,
                "reason": "the buyer approves purchases, as one does on production",
                "date_to": fields.Datetime.now() + timedelta(days=30),
            }
        )
        add_category_approver(cls.category, cls.buyer, required=False)
        add_category_approver(cls.category, cls.approver, required=False)
        cls.order = (
            cls.env["purchase.order"]
            .with_user(cls.assistant)
            .create(
                {
                    "partner_id": vendor.id,
                    "user_id": cls.buyer.id,
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

    def _send(self):
        self.order.with_user(self.assistant).action_confirm()
        request = self.order.approval_request_id
        self.assertEqual(request.request_owner_id, self.assistant)
        self.assertEqual(request.requester_id, self.buyer)
        return request

    def test_the_buyer_is_not_asked_to_approve_their_own_order(self):
        request = self._send()
        self.assertNotIn(self.buyer, request.approver_ids.user_id)
        self.assertIn(self.approver, request.approver_ids.user_id)

    def test_an_exception_lets_the_buyer_approve_until_it_lapses(self):
        exception = (
            self.env["ir.access.exception"]
            .sudo()
            .create(
                {
                    "user_id": self.buyer.id,
                    "kind": "requester_exclusion",
                    "res_model": "approval.category",
                    "res_id": self.category.id,
                    "reason": "Approves the assistants' orders this quarter",
                    "reviewer_ids": [(6, 0, self.approver.ids)],
                    "date_to": fields.Datetime.now() + timedelta(days=30),
                }
            )
        )
        request = self._send()
        row = request.approver_ids.filtered(lambda r: r.user_id == self.buyer)
        self.assertTrue(row)
        exception.write(
            {
                "date_from": fields.Datetime.now() - timedelta(days=60),
                "date_to": fields.Datetime.now() - timedelta(days=1),
            }
        )
        with self.assertRaises(AccessError):
            request.with_user(self.buyer).action_approve(row)
