from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestPurchaseApprovalDoors(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["approval.category"].search(
            [("approval_type", "=", "purchase"), ("target_model", "=", False)]
        ).write({"active": False})
        cls.buyer = new_test_user(
            cls.env, login="doors_buyer", groups="purchase.group_purchase_user"
        )
        cls.approver = new_test_user(
            cls.env, login="doors_approver", groups="base.group_user"
        )
        cls.purchase_manager = new_test_user(
            cls.env,
            login="doors_purchase_manager",
            groups="purchase.group_purchase_manager",
        )
        cls.vendor = cls.env["res.partner"].create(
            {"name": "Doors Vendor", "supplier_rank": 1, "po_approval_required": True}
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Doors Product", "type": "consu", "standard_price": 75.0}
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Doors PO Approval",
                "approval_type": "purchase",
                "approval_minimum": 1,
                "order_approval_mode": "amount",
                "order_amount_min": 1000.0,
                "has_amount": "required",
                "has_partner": "required",
            }
        )
        add_category_approver(cls.category, cls.approver, required=True)
        cls.env.cr.flush()
        cls.obligation = cls.env.ref("approval_purchase.obligation_order_confirm")

    def _values(self, **values):
        return {
            "partner_id": self.vendor.id,
            "line_ids": [
                Command.create(
                    {
                        "product_id": self.product.id,
                        "product_qty": 50.0,
                        "price_unit": 75.0,
                    }
                )
            ],
            **values,
        }

    def _order(self, **values):
        order = (
            self.env["purchase.order"]
            .with_user(self.buyer)
            .create(self._values(**values))
        )
        self.assertTrue(order.approval_required)
        return order

    def test_writing_the_confirmed_state_needs_the_grant(self):
        self.assertEqual(self.obligation.verb, "confirm")
        self.assertEqual(
            self.obligation.mode, "request", "and it enforces from the start"
        )
        order = self._order()
        with self.assertRaises(UserError):
            order.write({"state": "done"})
        with self.assertRaises(UserError):
            self._order(state="done")
        self.assertEqual(order.state, "draft")

    def test_a_watching_gate_records_the_confirmation_that_skipped_it(self):
        self.obligation.mode = "advise"
        order = self._order()
        order.write({"state": "done"})
        self.assertTrue(
            self.env["approval.observation"].search(
                [
                    ("model_name", "=", "purchase.order"),
                    ("operation", "=", "confirm"),
                    ("res_id", "=", order.id),
                ]
            ),
        )

    def test_the_grant_confirms_as_the_buyer_when_the_approver_is_no_buyer(self):
        self.obligation.mode = "request"
        order = self._order()
        order.action_confirm()
        request = order.approval_request_id
        self.assertEqual(request.request_owner_id, self.buyer)
        self.assertFalse(self.approver.has_group("purchase.group_purchase_user"))
        order.with_user(self.approver).read(["state"])
        request.with_user(self.approver).action_approve()
        with self.assertRaises(AccessError):
            order.with_user(self.approver).read(["state"])
        self.assertEqual(request.state, "approved")
        self.assertEqual(order.state, "done")
        self.assertEqual(order.write_uid, self.buyer)

    def test_a_buyer_confirms_against_a_debit_limit_they_cannot_read(self):
        self.category.write(
            {
                "order_approval_mode": "debit",
                "check_debit_limit": True,
                "debit_limit_threshold": 1.0,
            }
        )
        order = self._order()
        with self.assertRaises(AccessError):
            self.vendor.with_user(self.buyer).read(["debit"])
        order.action_confirm()
        self.assertEqual(order.approval_request_id.category_id, self.category)

    def test_a_purchase_manager_writes_only_purchase_categories(self):
        general = self.env["approval.category"].create(
            {"name": "Doors General", "approval_type": "general"}
        )
        manager = self.purchase_manager
        with self.assertRaises(AccessError):
            general.with_user(manager).write({"allow_self_approval": True})
        with self.assertRaises(AccessError):
            general.with_user(manager).action_archive()
        self.category.with_user(manager).write({"order_amount_min": 500.0})
        self.assertEqual(self.category.order_amount_min, 500.0)

    def test_an_approval_manager_who_buys_keeps_every_category(self):
        general = self.env["approval.category"].create(
            {"name": "Doors General", "approval_type": "general"}
        )
        self.purchase_manager.group_ids |= self.env.ref(
            "approval.group_approval_manager"
        )
        general.with_user(self.purchase_manager).write({"allow_self_approval": True})
        self.assertTrue(general.allow_self_approval)
