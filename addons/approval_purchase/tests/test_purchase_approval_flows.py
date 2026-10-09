from unittest.mock import patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval.tests.common import (
    add_category_approver,
    pool_step,
    record_approval,
)
from odoo.addons.approval_product.models import (
    mixin_approval_document as approval_document_module,
)


@tagged("post_install", "-at_install")
class TestPurchaseApprovalFlows(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        existing_categories = cls.env["approval.category"].search(
            [
                ("approval_type", "=", "purchase"),
                ("target_model", "=", False),
            ]
        )
        existing_categories.write({"active": False})

        cls.company = cls.env.ref("base.main_company")
        cls.company.write(
            {
                "po_validation_level": "manager_amount",
                "po_validation_amount": 1000.0,
            }
        )

        cls.purchase_user = cls.env["res.users"].create(
            {
                "name": "Purchase User",
                "login": "purchase_user",
                "email": "purchase@test.com",
                "group_ids": [
                    Command.set([cls.env.ref("purchase.group_purchase_user").id])
                ],
            },
        )

        cls.approver_user = cls.env["res.users"].create(
            {
                "name": "Approver User",
                "login": "approver_user",
                "email": "approver@test.com",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("purchase.group_purchase_manager").id,
                            cls.env.ref("base.group_user").id,
                        ],
                    ),
                ],
            },
        )

        cls.vendor = cls.env["res.partner"].create(
            {
                "name": "Test Vendor",
                "supplier_rank": 1,
            },
        )

        cls.product = cls.env["product.product"].create(
            {
                "name": "Test Product",
                "type": "consu",
                "list_price": 100.0,
                "standard_price": 75.0,
                "seller_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.vendor.id,
                            "min_qty": 1.0,
                            "price": 75.0,
                        },
                    ),
                ],
            },
        )

        cls.category_mixin = cls.env["approval.category"].create(
            {
                "name": "PO Approval (Mixin)",
                "approval_type": "purchase",
                "target_model": False,
                "approval_minimum": 1,
                "order_approval_mode": "amount",
                "order_amount_min": 1000.0,
                "order_amount_max": 10000.0,
                "has_amount": "required",
                "has_partner": "required",
            },
        )

        cls.category_creation = cls.env["approval.category"].create(
            {
                "name": "Purchase Request (Creation)",
                "approval_type": "purchase",
                "target_model": "purchase.order",
                "approval_minimum": 1,
                "has_product": "required",
                "has_amount": "optional",
                "has_partner": "optional",
            },
        )

        for category in [cls.category_mixin, cls.category_creation]:
            add_category_approver(category, cls.approver_user, required=True)

    def test_mixin_flow_po_to_approval(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 50.0,
                            "price_unit": 75.0,
                        },
                    ),
                ],
            },
        )

        self.assertTrue(
            po.approval_required,
            "PO should require approval (amount = 3750)",
        )
        self.assertFalse(po.approval_request_id, "No approval request yet")

        po.action_confirm()

        self.assertTrue(po.approval_request_id, "Approval request should be created")
        approval = po.approval_request_id
        self.assertEqual(approval.approval_type, "purchase")
        self.assertFalse(
            approval.target_model,
            "Mixin flow approval has no target_model",
        )
        self.assertEqual(approval.state, "pending", "Approval is pending")
        self.assertEqual(po.state, "draft", "PO still in draft")

        approval.with_user(self.approver_user).action_approve()

        self.assertEqual(approval.state, "approved")
        self.assertIn(
            po.state,
            ("purchase", "done"),
            "PO should be confirmed after approval",
        )

    def test_mixin_flow_stat_button_opens_the_source_order(self):
        """The button counts the source order, so it must be able to open it.

        A mixin-flow request has no ``target_model``, so the target-only helper
        resolves to an empty model and hands the client an act_window it cannot
        execute.
        """
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 50.0,
                            "price_unit": 75.0,
                        },
                    ),
                ],
            },
        )
        po.action_confirm()
        approval = po.approval_request_id

        self.assertFalse(approval.target_model, "this must be the mixin flow")
        self.assertEqual(
            approval.count_purchase_order,
            1,
            "the button is visible because the count is not zero",
        )

        action = approval.action_view_purchase_order()

        self.assertEqual(action["res_model"], "purchase.order")
        self.assertEqual(action["domain"], [("id", "in", po.ids)])
        self.assertTrue(action["name"], "an empty action name renders a blank title")
        self.assertIn(po, self.env["purchase.order"].search(action["domain"]))

    def test_target_flow_stat_button_still_uses_the_target_helper(self):
        approval = self.env["approval.request"].create(
            {
                "name": "Stat Button Target Request",
                "category_id": self.category_creation.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 75.0,
                            "product_uom_id": self.product.uom_id.id,
                            "description": self.product.name,
                        },
                    ),
                ],
            },
        )
        approval.action_confirm()
        approval.with_user(self.approver_user).action_approve()
        approval.action_create_purchase_orders()

        created = approval.line_ids.purchase_order_line_id.order_id
        action = approval.action_view_purchase_order()

        self.assertEqual(action["res_model"], "purchase.order")
        self.assertIn(created, self.env["purchase.order"].search(action["domain"]))

    def test_the_count_follows_an_order_that_links_itself(self):
        """An order created from a purchase request counts toward it the moment it
        links itself. The request must produce orders (`target_model`): an order's
        own approval request is about that order and cannot cover a second one."""
        approval = self.env["approval.request"].create(
            {
                "name": "Count Source",
                "category_id": self.category_creation.id,
                "partner_id": self.vendor.id,
                "line_ids": [
                    Command.create({"product_id": self.product.id, "quantity": 1.0})
                ],
            }
        )
        first = self.env["purchase.order"].create({"partner_id": self.vendor.id})
        approval._link_produced_documents(first)
        self.assertEqual(approval.count_purchase_order, 1)

        second = self.env["purchase.order"].create({"partner_id": self.vendor.id})
        approval._link_produced_documents(second)
        self.assertEqual(
            approval.count_purchase_order,
            2,
            "the count must not be served stale after an order links itself",
        )
        self.assertIn(second, approval.purchase_order_ids)

        own = self.env["purchase.order"].create(
            {
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
            }
        )
        own.action_confirm()
        with self.assertRaises(ValidationError):
            first.write({"approval_request_id": own.approval_request_id.id})

    def test_creation_flow_approval_to_po(self):
        approval = self.env["approval.request"].create(
            {
                "name": "Test Purchase Request",
                "category_id": self.category_creation.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 20.0,
                            "price_unit": 75.0,
                            "product_uom_id": self.product.uom_id.id,
                            "description": "Test Product Line",
                        },
                    ),
                ],
            },
        )

        self.assertEqual(approval.approval_type, "purchase")
        self.assertEqual(approval.target_model, "purchase.order")
        self.assertEqual(approval.state, "new")

        approval.action_confirm()
        self.assertEqual(approval.state, "pending")

        approval.with_user(self.approver_user).action_approve()
        self.assertEqual(approval.state, "approved")

        approval.action_create_purchase_orders()

        self.assertTrue(approval.line_ids.purchase_order_line_id, "PO lines created")
        po = approval.line_ids.purchase_order_line_id.order_id

        self.assertTrue(po, "Purchase order created")
        self.assertEqual(po.partner_id, self.vendor, "Vendor set correctly")
        self.assertEqual(len(po.line_ids), 1, "One PO line created")
        self.assertEqual(po.line_ids.product_id, self.product)
        self.assertEqual(po.line_ids.product_qty, 20.0)

        self.assertEqual(po.approval_request_id, approval, "PO linked to approval")
        self.assertFalse(
            po.approval_required,
            "PO should NOT require approval (already approved via creation flow)",
        )

        po.action_confirm()
        self.assertEqual(po.state, "done", "PO confirmed without re-approval")

    def test_no_redundant_approval_for_creation_flow_po(self):
        approval = self.env["approval.request"].create(
            {
                "name": "Test Purchase Request",
                "category_id": self.category_creation.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 100.0,
                            "price_unit": 75.0,
                            "product_uom_id": self.product.uom_id.id,
                            "description": "Large Order",
                        },
                    ),
                ],
            },
        )

        approval.action_confirm()
        approval.with_user(self.approver_user).action_approve()

        approval.action_create_purchase_orders()
        po = approval.line_ids.purchase_order_line_id.order_id

        self.assertGreaterEqual(
            po.amount_total, 7500.0, "Amount should be at least 7500"
        )
        self.assertLessEqual(
            po.amount_total, 10000.0, "Amount should be within mixin range"
        )
        self.assertFalse(
            po.approval_required,
            "PO from approved request should not require re-approval",
        )

        with self.assertRaises(UserError) as cm:
            po.action_create_approval_request()

        self.assertIn(
            "created from an approval request",
            str(cm.exception),
            "Error message should explain why approval not needed",
        )

    def test_mixin_flow_category_matching(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 50.0,
                            "price_unit": 75.0,
                        },
                    ),
                ],
            },
        )

        category = po._get_approval_category()

        self.assertTrue(category, "Should return a category")
        self.assertFalse(category.target_model, "Mixin category has no target_model")
        self.assertEqual(category.approval_type, "purchase")

    def test_creation_flow_validation_requires_product_lines(self):
        approval = self.env["approval.request"].create(
            {
                "name": "Empty Purchase Request",
                "category_id": self.category_creation.id,
            },
        )

        with self.assertRaises(UserError) as cm:
            approval.action_confirm()

        self.assertIn("empty purchase request", str(cm.exception).lower())

    def test_approve_checks_the_decision_right_before_the_contents(self):
        approval = self.env["approval.request"].create(
            {
                "name": "Empty Purchase Request",
                "category_id": self.category_creation.id,
            },
        )

        with self.assertRaises(AccessError):
            approval.with_user(self.purchase_user).action_approve()

    def test_a_line_swapped_at_the_same_amount_is_not_what_was_approved(self):
        self.company.po_auto_confirm_on_approval = False
        po = self.env["purchase.order"].create(
            {
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
            },
        )
        po.action_confirm()
        po.approval_request_id.with_user(self.approver_user).action_approve()
        self.assertEqual(po.state, "draft")
        other = self.env["product.product"].create(
            {"name": "Swapped Product", "type": "consu"}
        )

        po.line_ids.write({"product_id": other.id, "price_unit": 75.0})
        self.assertEqual(po.amount_total, po.approval_request_id.amount)

        with self.assertRaisesRegex(UserError, "no longer what is there"):
            po.action_confirm()

    def test_an_order_approved_at_zero_does_not_confirm_at_another_amount(self):
        po = self.env["purchase.order"].create(
            {
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
            },
        )
        po.action_confirm()
        approval = po.approval_request_id
        approval.with_user(self.approver_user).action_approve()
        # what a request raised while the order totalled zero carries
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE approval_request SET amount = 0 WHERE id = %s", [approval.id]
        )
        approval.invalidate_recordset(["amount"])
        po.action_unlock()
        with self.assertRaisesRegex(UserError, "amount has changed"):
            po.action_confirm()

    def test_mixin_flow_no_approval_for_low_amount(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 5.0,
                            "price_unit": 75.0,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(
            po.approval_required,
            "Low amount PO should not require approval",
        )

        po.action_confirm()
        self.assertEqual(po.state, "done", "Low amount PO confirmed directly")
        self.assertFalse(po.approval_request_id, "No approval request created")

    def test_draft_after_refusal_allows_new_approval(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 50.0,
                            "price_unit": 75.0,
                        },
                    ),
                ],
            },
        )

        po.action_confirm()
        old_approval = po.approval_request_id
        self.assertTrue(old_approval, "Mixin approval created on confirm")

        approver = old_approval.approver_ids.filtered(
            lambda a: a.user_id == self.approver_user,
        )
        old_approval.action_refuse(approver)
        self.assertEqual(po.approval_state, "refused")

        po.action_draft()
        self.assertFalse(
            po.approval_request_id,
            "Refused approval link should be cleared on draft",
        )
        self.assertFalse(po.approval_state)
        self.assertFalse(po.date_approval_requested)
        self.assertFalse(po.date_approval_granted)

        po.action_confirm()
        self.assertTrue(po.approval_request_id, "A new approval is requested")
        self.assertNotEqual(
            po.approval_request_id,
            old_approval,
            "Re-confirmation must create a fresh approval, not reuse the refused one",
        )
        self.assertEqual(po.approval_state, "pending")

    def test_draft_keeps_approved_link(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 50.0,
                            "price_unit": 75.0,
                        },
                    ),
                ],
            },
        )
        po.action_confirm()
        approval = po.approval_request_id
        approver = approval.approver_ids.filtered(
            lambda a: a.user_id == self.approver_user,
        )
        approval.action_approve(approver)
        self.assertEqual(po.approval_state, "approved")

        if po.locked:
            po.action_unlock()
        if po.state == "done":
            po.action_cancel()
        po.action_draft()

        self.assertEqual(
            po.approval_request_id,
            approval,
            "Approved approval link must survive a reset to draft",
        )

    def test_action_confirm_approved_confirms_order(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 50.0,
                            "price_unit": 75.0,
                        },
                    ),
                ],
            },
        )

        self.assertTrue(po.approval_required)

        approval = self.env["approval.request"].create(
            {
                "name": "Test Approval",
                "category_id": self.category_mixin.id,
                "request_owner_id": self.env.user.id,
                "amount": po.amount_total,
                "res_model": po._name,
                "res_id": po.id,
            },
        )
        record_approval(approval.approver_ids)
        po.approval_request_id = approval

        self.assertEqual(po.approval_state, "approved")

        result = po.action_confirm()

        self.assertEqual(
            po.state,
            "done",
            f"PO was not confirmed. State is '{po.state}' instead of 'done'",
        )
        self.assertTrue(
            result is True
            or result == {}
            or result.get("type") != "ir.actions.act_window",
            "Order was sent for re-approval instead of being confirmed",
        )

    def test_amount_check_blocks_modified_approved_po(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 50.0,
                            "price_unit": 75.0,
                        },
                    ),
                ],
            },
        )

        po.action_confirm()
        approval = po.approval_request_id
        self.assertTrue(approval, "Approval request created")

        approval.with_user(self.approver_user).action_approve()
        self.assertEqual(po.approval_state, "approved")

        po.action_unlock()
        po.line_ids.price_unit = 150.0

        with self.assertRaises(UserError) as cm:
            po.action_confirm()

        self.assertIn(
            "amount has changed",
            str(cm.exception).lower(),
            "Error should mention amount change",
        )

    def test_approval_reason_includes_vendor_notes(self):
        self.vendor.po_approval_notes = (
            "NEW VENDOR - verify credentials before approving"
        )

        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 50.0,
                            "price_unit": 75.0,
                        },
                    ),
                ],
            },
        )

        reason_html = po._get_approval_reason_html()

        self.assertIn(
            "NEW VENDOR",
            reason_html,
            "Vendor approval notes should appear in reason HTML",
        )
        self.assertIn(
            "Notes for approvers",
            reason_html,
            "the approver notes label should appear in reason HTML",
        )

    def test_approval_notes_survive_above_the_line_cap(self):
        self.vendor.po_approval_notes = "NEW VENDOR - verify credentials"
        self.product.po_approval_notes = "Controlled chemical - verify safety"
        self.product.categ_id = self.env["product.category"].create(
            {
                "name": "Cap Category",
                "po_approval_notes": "Category needs a safety sheet",
            },
        )

        def reason_for(line_count):
            order = self.env["purchase.order"].create(
                {
                    "partner_id": self.vendor.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": self.product.id,
                                "product_qty": 1.0,
                                "price_unit": 75.0,
                            },
                        )
                        for _ in range(line_count)
                    ],
                },
            )
            with patch.object(approval_document_module, "MAX_DETAIL_LINES", 5):
                return order._get_approval_reason_html()

        under_cap = reason_for(5)
        over_cap = reason_for(6)

        for reason, label in ((under_cap, "5 lines"), (over_cap, "6 lines")):
            self.assertIn("NEW VENDOR", reason, f"vendor note missing at {label}")
            self.assertIn(
                "Controlled chemical",
                reason,
                f"product note missing at {label}: it is exactly the text that "
                f"tells the approver why this order is risky",
            )
            self.assertIn(
                "Category needs a safety sheet",
                reason,
                f"category note missing at {label}",
            )
        self.assertIn(
            "<ul>",
            over_cap,
            "above the cap the list is truncated, not dropped",
        )
        self.assertEqual(
            over_cap.count("<li>"),
            5,
            "above the cap only MAX_DETAIL_LINES products are listed",
        )
        self.assertIn(
            "and 1 more lines",
            over_cap,
            "the approver must be told the list was truncated",
        )
        self.assertEqual(
            under_cap.count("<li>"),
            5,
            "at the cap every product is still listed",
        )
        self.assertNotIn("more lines", under_cap)

    def test_section_and_note_lines_do_not_hide_the_products(self):
        """The cap must count products, not every line.

        An order with two products and four text lines is under the product cap
        and must still render both products, with a count that describes
        products rather than text lines.
        """
        order = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 1.0,
                            "price_unit": 75.0,
                        },
                    ),
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 2.0,
                            "price_unit": 75.0,
                        },
                    ),
                    Command.create({"display_type": "line_section", "name": "Phase 1"}),
                    Command.create({"display_type": "line_note", "name": "note one"}),
                    Command.create({"display_type": "line_note", "name": "note two"}),
                    Command.create({"display_type": "line_note", "name": "note three"}),
                ],
            },
        )

        self.assertEqual(len(order.line_ids), 6, "six lines, but only two products")

        reason = order._get_approval_reason_html()

        self.assertIn("<strong>Products:</strong>", reason)
        self.assertEqual(
            reason.count("<li>"),
            2,
            "both products must be listed even though the order has six lines",
        )
        self.assertNotIn(
            "more lines",
            reason,
            "two products are under the cap, so nothing was truncated",
        )
        self.assertNotIn(
            "Phase 1",
            reason,
            "a section is not a product and must not be listed as one",
        )

    def test_approval_reason_includes_product_notes(self):
        self.product.po_approval_notes = "Controlled chemical - verify safety"

        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 5.0,
                            "price_unit": 75.0,
                        },
                    ),
                ],
            },
        )

        reason_html = po._get_approval_reason_html()

        self.assertIn(
            "Controlled chemical",
            reason_html,
            "Product approval notes should appear in reason HTML",
        )


@tagged("post_install", "-at_install")
class TestPurchaseApprovalWithdrawGuard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.vendor = cls.env["res.partner"].create(
            {"name": "PO Withdraw Vendor", "supplier_rank": 1},
        )
        cls.product = cls.env["product.product"].create(
            {"name": "PO Withdraw Product", "type": "consu", "standard_price": 50.0},
        )
        cls.env["approval.category"].search(
            [("approval_type", "=", "purchase"), ("active", "=", True)],
        ).write({"active": False})
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Purchase Withdraw Guard",
                "company_id": cls.company.id,
                "approval_type": "purchase",
                "approval_minimum": 1,
                "allow_self_approval": True,
                "target_model": "purchase.order",
                "has_product": "required",
                "step_ids": pool_step([(cls.env.user.id, True, 10)], minimum=1),
            }
        )

    def _approved_request(self):
        request = self.env["approval.request"].create(
            {
                "name": "Purchase Withdraw Test",
                "category_id": self.category.id,
                "company_id": self.company.id,
                "request_owner_id": self.env.user.id,
                "line_ids": [
                    Command.create({"product_id": self.product.id, "quantity": 1.0})
                ],
            }
        )
        request.action_confirm()
        request.approver_ids[0].with_context(skip_wizard=True).action_approve()
        self.assertEqual(request.state, "approved")
        return request

    def test_withdraw_allowed_without_descendant(self):
        request = self._approved_request()
        request._check_withdraw_allowed()

    def test_withdraw_blocked_with_active_purchase_order(self):
        request = self._approved_request()
        order = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "company_id": self.company.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 1,
                            "price_unit": 50.0,
                        },
                    ),
                ],
            }
        )
        request._link_produced_documents(order)
        with self.assertRaises(UserError):
            request._check_withdraw_allowed()

    def test_withdraw_unblocks_when_po_cancelled(self):
        request = self._approved_request()
        order = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "company_id": self.company.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 1,
                            "price_unit": 50.0,
                        },
                    ),
                ],
            }
        )
        request._link_produced_documents(order)
        order.action_cancel()
        self.assertEqual(order.state, "cancel")
        request._check_withdraw_allowed()


@tagged("post_install", "-at_install")
class TestPurchaseOrderApprovalRateLimit(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.company.write(
            {
                "po_validation_level": "manager_amount",
                "po_validation_amount": 1000.0,
                "po_rate_limit_enabled": True,
                "po_rate_limit_hours": 24,
                "po_rate_limit_count": 3,
                "po_rate_limit_amount": 2000.0,
            },
        )
        cls.env.user.group_ids = [
            Command.link(cls.env.ref("purchase.group_purchase_manager").id),
        ]
        cls.vendor = cls.env["res.partner"].create(
            {
                "name": "Test Vendor",
                "supplier_rank": 1,
                "company_id": cls.company.id,
            },
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Test Product",
                "type": "consu",
                "list_price": 100.0,
            },
        )

    def _create_purchase_order(self, amount):
        return self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "company_id": self.company.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 1,
                            "price_unit": amount,
                            "tax_ids": [Command.clear()],
                        },
                    ),
                ],
            },
        )

    def test_rate_limit_is_pinned_to_creator_not_viewer(self):
        for _i in range(3):
            self._create_purchase_order(100)
        order = self._create_purchase_order(100)
        self.assertTrue(order._check_rate_limit_exceeded())
        order.invalidate_recordset(["approval_required"])
        self.assertTrue(order.approval_required)

        other_manager = self.env["res.users"].create(
            {
                "name": "Other Purchase Manager",
                "login": "other_purchase_manager_rate",
                "email": "other.manager.rate@test.com",
                "company_id": self.company.id,
                "company_ids": [Command.link(self.company.id)],
                "group_ids": [
                    Command.link(
                        self.env.ref("purchase.group_purchase_manager").id,
                    ),
                    Command.link(self.env.ref("base.group_user").id),
                ],
            },
        )
        order_as_other = order.with_user(other_manager)
        self.assertTrue(order_as_other._check_rate_limit_exceeded())
        order_as_other.invalidate_recordset(["approval_required"])
        self.assertTrue(
            order_as_other.approval_required,
            "the rate-limit verdict must follow the creator, not the viewer",
        )
