from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import AccountApprovalCommon
from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestAccountMoveCreation(AccountApprovalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.vendor1 = cls.env["res.partner"].create(
            {
                "name": "Vendor 1",
                "supplier_rank": 1,
            },
        )

        cls.vendor2 = cls.env["res.partner"].create(
            {
                "name": "Vendor 2",
                "supplier_rank": 1,
            },
        )

        cls.customer = cls.env["res.partner"].create(
            {
                "name": "Customer 1",
                "customer_rank": 1,
            },
        )

        cls.product1 = cls.env["product.product"].create(
            {
                "name": "Product 1",
                "type": "consu",
                "list_price": 100.0,
                "standard_price": 75.0,
            },
        )

        cls.product2 = cls.env["product.product"].create(
            {
                "name": "Product 2",
                "type": "consu",
                "list_price": 50.0,
                "standard_price": 35.0,
            },
        )

        cls.category = cls.env["approval.category"].create(
            {
                "name": "Bill Request",
                "approval_type": "accounting",
                "target_model": "account.move",
                "approval_minimum": 1,
                "has_product": "required",
                "has_partner": "optional",
                "has_amount": "required",
            },
        )

        add_category_approver(cls.category, cls.approver, required=True)

    def test_create_single_bill_from_approval(self):
        approval = self.env["approval.request"].create(
            {
                "name": "Test Bill Request",
                "category_id": self.category.id,
                "partner_id": self.vendor1.id,
                "amount": 750.0,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product1.id,
                            "quantity": 10.0,
                            "price_unit": 75.0,
                            "product_uom_id": self.product1.uom_id.id,
                            "description": "Product 1 line",
                        },
                    ),
                ],
            },
        )

        approval.action_confirm()
        approval.with_user(self.approver).action_approve()
        approval.action_create_account_moves()

        self.assertEqual(approval.count_account_move, 1)
        bill = approval.line_ids.account_move_line_id.move_id

        self.assertEqual(bill.move_type, "in_invoice")
        self.assertEqual(bill.partner_id, self.vendor1)
        self.assertEqual(len(bill.invoice_line_ids), 1)

        line = bill.invoice_line_ids[0]
        self.assertEqual(line.product_id, self.product1)
        self.assertEqual(line.quantity, 10.0)
        self.assertEqual(line.price_unit, 75.0)
        self.assertEqual(line.name, "Product 1 line")

        approval_line = approval.line_ids[0]
        self.assertEqual(approval_line.account_move_line_id, line)
        self.assertEqual(line.approval_request_line_id, approval_line)

    def test_create_multiple_lines_single_bill(self):
        approval = self.env["approval.request"].create(
            {
                "name": "Multi-Line Bill",
                "category_id": self.category.id,
                "partner_id": self.vendor1.id,
                "amount": 1450.0,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product1.id,
                            "quantity": 10.0,
                            "price_unit": 75.0,
                            "product_uom_id": self.product1.uom_id.id,
                            "description": "Product 1",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "product_id": self.product2.id,
                            "quantity": 20.0,
                            "price_unit": 35.0,
                            "product_uom_id": self.product2.uom_id.id,
                            "description": "Product 2",
                        },
                    ),
                ],
            },
        )

        approval.action_confirm()
        approval.with_user(self.approver).action_approve()
        approval.action_create_account_moves()

        self.assertEqual(approval.count_account_move, 1)
        bill = approval.line_ids[0].account_move_line_id.move_id

        self.assertEqual(len(bill.invoice_line_ids), 2)
        self.assertEqual(bill.partner_id, self.vendor1)

        for approval_line in approval.line_ids:
            self.assertTrue(
                approval_line.account_move_line_id,
                "All approval lines should be linked",
            )

    def test_action_view_account_move(self):
        approval = self.env["approval.request"].create(
            {
                "name": "Test Request",
                "category_id": self.category.id,
                "partner_id": self.vendor1.id,
                "amount": 375.0,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product1.id,
                            "quantity": 5.0,
                            "price_unit": 75.0,
                            "product_uom_id": self.product1.uom_id.id,
                            "description": "Test",
                        },
                    ),
                ],
            },
        )

        approval.action_confirm()
        approval.with_user(self.approver).action_approve()
        approval.action_create_account_moves()

        action = approval.action_view_account_move()

        self.assertEqual(action["res_model"], "account.move")
        self.assertEqual(action["type"], "ir.actions.act_window")

        bill = approval.line_ids.account_move_line_id.move_id
        self.assertEqual(action["res_id"], bill.id)

    def test_move_not_created_if_already_exists(self):
        approval = self.env["approval.request"].create(
            {
                "name": "Test Request",
                "category_id": self.category.id,
                "partner_id": self.vendor1.id,
                "amount": 375.0,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product1.id,
                            "quantity": 5.0,
                            "price_unit": 75.0,
                            "product_uom_id": self.product1.uom_id.id,
                            "description": "Test",
                        },
                    ),
                ],
            },
        )

        approval.action_confirm()
        approval.with_user(self.approver).action_approve()
        approval.action_create_account_moves()

        self.assertEqual(approval.count_account_move, 1)
        first_bill = approval.line_ids.account_move_line_id.move_id

        approval.action_create_account_moves()

        self.assertEqual(approval.count_account_move, 1)
        second_bill = approval.line_ids.account_move_line_id.move_id
        self.assertEqual(first_bill, second_bill, "Should not create duplicate")

    def test_count_account_move_computed_correctly(self):
        approval = self.env["approval.request"].create(
            {
                "name": "Test Request",
                "category_id": self.category.id,
                "partner_id": self.vendor1.id,
                "amount": 925.0,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product1.id,
                            "quantity": 10.0,
                            "price_unit": 75.0,
                            "product_uom_id": self.product1.uom_id.id,
                            "description": "Line 1",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "product_id": self.product2.id,
                            "quantity": 5.0,
                            "price_unit": 35.0,
                            "product_uom_id": self.product2.uom_id.id,
                            "description": "Line 2",
                        },
                    ),
                ],
            },
        )

        self.assertEqual(approval.count_account_move, 0)

        approval.action_confirm()
        approval.with_user(self.approver).action_approve()
        approval.action_create_account_moves()

        self.assertEqual(approval.count_account_move, 1)

    def test_refuse_removes_approval_line_link(self):
        approval = self.env["approval.request"].create(
            {
                "name": "Test Request",
                "category_id": self.category.id,
                "partner_id": self.vendor1.id,
                "amount": 375.0,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product1.id,
                            "quantity": 5.0,
                            "price_unit": 75.0,
                            "product_uom_id": self.product1.uom_id.id,
                            "description": "Test",
                        },
                    ),
                ],
            },
        )

        approval.action_confirm()
        approval.with_user(self.approver).action_approve()
        approval.action_create_account_moves()

        approval_line = approval.line_ids[0]
        bill = approval_line.account_move_line_id.move_id
        self.assertTrue(approval_line.account_move_line_id, "Link should exist")
        self.assertEqual(bill.state, "draft", "Bill should be in draft")

        approval._refuse_approval_request()

        self.assertFalse(
            approval_line.account_move_line_id,
            "Link should be cleared on refusal",
        )
        self.assertFalse(
            bill.exists(),
            "Draft bill should be deleted on refusal",
        )

    def test_move_date_follows_the_user_timezone_not_utc(self):
        self.env.user.tz = "America/Mexico_City"
        approval = self.env["approval.request"].create(
            {
                "name": "Evening Bill Request",
                "category_id": self.category.id,
                "partner_id": self.vendor1.id,
                "amount": 75.0,
                "date": "2026-08-23 02:00:00",
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product1.id,
                            "quantity": 1.0,
                            "price_unit": 75.0,
                            "product_uom_id": self.product1.uom_id.id,
                            "description": "Evening line",
                        },
                    ),
                ],
            },
        )

        approval.action_confirm()
        approval.with_user(self.approver).action_approve()
        approval.action_create_account_moves()

        bill = approval.line_ids.account_move_line_id.move_id
        self.assertEqual(
            str(bill.invoice_date),
            "2026-08-22",
            "20:00 in Mexico City is still the 22nd; truncating the UTC "
            "datetime would book it on the 23rd",
        )
        self.assertEqual(str(bill.date), "2026-08-22")

    def _make_bill_request(self, name, vendor):
        return self.env["approval.request"].create(
            {
                "name": name,
                "category_id": self.category.id,
                "partner_id": vendor.id,
                "amount": 150.0,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product1.id,
                            "quantity": 2.0,
                            "price_unit": 75.0,
                            "product_uom_id": self.product1.uom_id.id,
                        },
                    ),
                ],
            },
        )

    def test_bulk_create_skips_ineligible_and_opens_created_bills(self):
        approved_1 = self._make_bill_request("Bulk 1", self.vendor1)
        approved_2 = self._make_bill_request("Bulk 2", self.vendor2)
        pending = self._make_bill_request("Bulk pending", self.vendor1)
        invoiced = self._make_bill_request("Bulk invoiced", self.vendor2)
        for request in approved_1 | approved_2 | invoiced:
            request.action_confirm()
            request.with_user(self.approver).action_approve()
        pending.action_confirm()
        invoiced.action_create_account_moves()
        existing_bill = invoiced.line_ids.account_move_line_id.move_id

        selection = approved_1 | approved_2 | pending | invoiced
        result = selection.action_create_account_moves_bulk()

        self.assertEqual(approved_1.count_account_move, 1)
        self.assertEqual(approved_2.count_account_move, 1)
        self.assertEqual(pending.count_account_move, 0)
        self.assertEqual(pending.state, "pending")
        self.assertEqual(invoiced.line_ids.account_move_line_id.move_id, existing_bill)

        created = (approved_1 | approved_2).line_ids.account_move_line_id.move_id
        self.assertEqual(len(created), 2)
        self.assertEqual(set(created.mapped("move_type")), {"in_invoice"})
        self.assertEqual(created.mapped("partner_id"), self.vendor1 | self.vendor2)

        self.assertEqual(result["tag"], "display_notification")
        self.assertTrue(result["params"]["sticky"])
        self.assertIn(
            "2 journal entries created from 2 requests", result["params"]["message"]
        )
        self.assertIn("2 selected requests were skipped", result["params"]["message"])
        next_action = result["params"]["next"]
        self.assertEqual(next_action["res_model"], "account.move")
        self.assertEqual(set(next_action["domain"][0][2]), set(created.ids))

    def test_bulk_create_single_bill_opens_form_and_is_not_sticky(self):
        approved = self._make_bill_request("Bulk single", self.vendor1)
        approved.action_confirm()
        approved.with_user(self.approver).action_approve()

        result = approved.action_create_account_moves_bulk()

        bill = approved.line_ids.account_move_line_id.move_id
        self.assertFalse(result["params"]["sticky"])
        self.assertEqual(result["params"]["next"]["res_id"], bill.id)
        self.assertEqual(result["params"]["next"]["view_mode"], "form")

    def test_bulk_create_raises_when_nothing_is_eligible(self):
        pending = self._make_bill_request("Bulk nothing", self.vendor1)
        pending.action_confirm()

        with self.assertRaises(UserError):
            pending.action_create_account_moves_bulk()

        self.assertEqual(pending.count_account_move, 0)

    def _make_invoiced_requests(self, count, prefix):
        requests = self.env["approval.request"]
        for index in range(count):
            request = self._make_bill_request(
                f"{prefix} {index}",
                self.vendor1 if index % 2 else self.vendor2,
            )
            request.action_confirm()
            request.with_user(self.approver).action_approve()
            request.action_create_account_moves()
            requests |= request
        return requests

    def test_moves_by_request_costs_the_same_whatever_the_selection(self):
        """The batched lookup must not grow a query per selected request.

        _get_documents_of_model is check_singleton() and searches once per
        record, which is why the bulk action used to pay one account.move
        search per request -- twice over.
        """
        small = self._make_invoiced_requests(2, "Cost small")
        large = self._make_invoiced_requests(6, "Cost large")

        self.env.invalidate_all()
        before = self.env.cr.sql_statement_count
        small._account_moves_by_request()
        small_cost = self.env.cr.sql_statement_count - before

        self.env.invalidate_all()
        before = self.env.cr.sql_statement_count
        large._account_moves_by_request()
        large_cost = self.env.cr.sql_statement_count - before

        self.assertEqual(
            small_cost,
            large_cost,
            f"the lookup scales with the selection: {small_cost} queries for 2 "
            f"requests, {large_cost} for 6",
        )

    def test_moves_by_request_agrees_with_the_singleton_helper(self):
        """Batched and per-record readings must return the same moves."""
        requests = self._make_invoiced_requests(3, "Agree")
        batched = requests._account_moves_by_request()
        for request in requests:
            self.assertEqual(
                batched[request.id],
                request._get_all_account_moves(),
                f"batched lookup disagrees with _get_all_account_moves for "
                f"{request.name}",
            )

    def test_moves_by_request_is_empty_for_a_request_without_moves(self):
        request = self._make_bill_request("No moves", self.vendor1)
        self.assertFalse(request._account_moves_by_request()[request.id])
