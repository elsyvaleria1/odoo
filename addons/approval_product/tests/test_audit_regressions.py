import unittest

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools.misc import format_datetime, formatLang

from .common import create_test_product
from odoo.addons.approval.tests.common import ApprovalCommon


@tagged("post_install", "-at_install")
class TestAuditRegressions(ApprovalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "sale.order" not in cls.env:
            raise unittest.SkipTest(
                "these regressions are driven through sale.order; "
                "approval_product alone does not depend on sale"
            )
        cls.env.company.so_auto_confirm_on_approval = False
        cls.product = create_test_product(cls.env, type="consu", list_price=100.0)
        cls.vendor = cls.env["res.partner"].create({"name": "Audit Vendor"})
        cls.company_currency = cls.env.company.currency_id
        other = cls.env.ref("base.EUR")
        if other == cls.company_currency:
            other = cls.env.ref("base.USD")
        other.active = True
        cls.other_currency = other
        cls.env["res.currency.rate"].create(
            {
                "name": "2026-06-01",
                "currency_id": other.id,
                "rate": 2.0,
                "company_id": cls.env.company.id,
            },
        )
        cls.other_pricelist = cls.env["product.pricelist"].create(
            {
                "name": "Audit Other Currency",
                "currency_id": other.id,
                "company_id": cls.env.company.id,
            },
        )

    def _make_order(self, currency=None, quantity=1.0, price=100.0, product=None):
        values = {
            "partner_id": self.vendor.id,
            "line_ids": [
                (
                    0,
                    0,
                    {
                        "product_id": (product or self.product).id,
                        "product_qty": quantity,
                    },
                ),
            ],
        }
        if currency:
            values["currency_id"] = currency.id
        order = self.env["sale.order"].create(values)
        order.line_ids.write({"price_unit": price, "tax_ids": [(5, 0, 0)]})
        order.invalidate_recordset()
        return order

    def test_amount_criteria_convert_from_the_threshold_currency(self):
        category = self._make_category(
            name="Audit Amount",
            approvers=[self.approver_1],
        )
        category.write({"order_amount_min": 1000.0})
        self.assertEqual(
            category.order_amount_currency_id,
            self.company_currency,
            "A company-bound category's thresholds are in its company currency",
        )

        order = self._make_order(currency=self.other_currency, quantity=12.0)
        self.assertEqual(order.currency_id, self.other_currency)
        self.assertEqual(order.amount_total, 1200.0)
        self.assertFalse(
            category._is_matching_amount(order),
            "A 1,200 foreign-currency order is 600 in company currency and must "
            "not clear a 1,000 company-currency floor",
        )

        self.assertTrue(
            category._is_matching_amount(self._make_order(quantity=12.0)),
        )

    def test_global_category_thresholds_carry_a_currency(self):
        category = self._make_category(
            name="Audit Global",
            approvers=[self.approver_1],
        )
        category.sudo().write({"company_id": False, "order_amount_min": 1000.0})
        self.assertFalse(category.company_id)
        self.assertEqual(
            category.order_amount_currency_id,
            self.company_currency,
            "A global category falls back to the active company's currency "
            "instead of leaving the thresholds currency-less",
        )

    def test_product_category_match_follows_the_hierarchy(self):
        parent = self.env["product.category"].create({"name": "Audit Parent"})
        child = self.env["product.category"].create(
            {"name": "Audit Child", "parent_id": parent.id},
        )
        product = create_test_product(self.env, type="consu", categ_id=child.id)
        order = self._make_order(product=product)

        on_parent = self._make_category(
            name="Audit Categ Parent",
            approvers=[self.approver_1],
        )
        on_parent.write({"product_categ_ids": [(6, 0, [parent.id])]})
        self.assertTrue(
            on_parent._is_matching_product_category(order),
            "A category set on the parent must match a product filed under a child",
        )

        on_child = self._make_category(
            name="Audit Categ Child",
            approvers=[self.approver_1],
        )
        on_child.write({"product_categ_ids": [(6, 0, [child.id])]})
        self.assertTrue(on_child._is_matching_product_category(order))

        unrelated = self.env["product.category"].create({"name": "Audit Other"})
        on_other = self._make_category(
            name="Audit Categ Other",
            approvers=[self.approver_1],
        )
        on_other.write({"product_categ_ids": [(6, 0, [unrelated.id])]})
        self.assertFalse(
            on_other._is_matching_product_category(order),
            "An unrelated category must still not match",
        )

    def test_reason_header_localises_the_expected_delivery(self):
        order = self._make_order(quantity=1.0, price=100.0)
        order.write({"date_commitment": "2026-12-31 23:30:00"})
        order.invalidate_recordset()

        header = "".join(order._get_approval_reason_header())
        self.assertIn(
            format_datetime(self.env, order.date_commitment),
            header,
            "The approvers must read the deadline in their own locale",
        )
        self.assertNotIn("2026-12-31 23:30:00", header)

    def test_request_values_keep_what_base_already_maps(self):
        category = self._make_category(
            name="Audit Prepare Values",
            approvers=[self.approver_1],
        )
        order = self._make_order(quantity=2.0, price=50.0)
        values = order._prepare_approval_request_values(category)

        self.assertEqual(values["partner_id"], order.partner_id.id)
        self.assertEqual(values["amount"], order.amount_total)
        self.assertEqual(values["date"], order.date_order)
        self.assertEqual(values["currency_id"], order.currency_id.id)
        self.assertEqual(
            values["reference"], order._get_approval_reference() or order.origin
        )
        self.assertEqual(
            values["date_deadline"],
            order._get_approval_deadline_date(),
        )

    def test_approved_amount_error_names_the_approved_currency(self):
        category = self._make_category(
            name="Audit Currency",
            approvers=[self.approver_1],
        )
        order = self._make_order(quantity=1.0, price=100.0)
        request = self.env["approval.request"].create(
            {
                "name": "Audit currency request",
                "category_id": category.id,
                "request_owner_id": self.env.uid,
                "amount": order.amount_total,
                "currency_id": order.currency_id.id,
            },
        )
        order.approval_request_id = request.id
        request.action_confirm()
        request.with_user(self.approver_1).action_approve()

        order.write({"currency_id": self.other_currency.id})
        order.line_ids.write({"price_unit": 500.0})
        order.invalidate_recordset()

        with self.assertRaises(UserError) as caught:
            order._check_approved_amount()
        message = str(caught.exception)
        self.assertIn(
            formatLang(self.env, 100.0, currency_obj=request.currency_id),
            message,
            "The approved figure must carry the currency it was approved in",
        )
        self.assertIn(
            formatLang(self.env, 500.0, currency_obj=order.currency_id),
            message,
        )

    def test_approved_amount_is_converted_before_it_is_compared(self):
        category = self._make_category(
            name="Audit Currency Swap",
            approvers=[self.approver_1],
        )
        order = self._make_order(quantity=1.0, price=100.0)
        request = self.env["approval.request"].create(
            {
                "name": "Audit currency swap request",
                "category_id": category.id,
                "request_owner_id": self.env.uid,
                "amount": order.amount_total,
                "currency_id": order.currency_id.id,
            },
        )
        order.approval_request_id = request.id
        request.action_confirm()
        request.with_user(self.approver_1).action_approve()

        order.write({"pricelist_id": self.other_pricelist.id})
        order.invalidate_recordset()
        self.assertEqual(order.currency_id, self.other_currency)
        self.assertEqual(
            order.amount_total,
            100.0,
            "The swap must leave the figure untouched, only its currency",
        )

        with self.assertRaises(UserError):
            order._check_approved_amount()

    def test_approved_amount_accepts_an_equivalent_currency(self):
        category = self._make_category(
            name="Audit Currency Equivalent",
            approvers=[self.approver_1],
        )
        order = self._make_order(quantity=1.0, price=100.0)
        request = self.env["approval.request"].create(
            {
                "name": "Audit currency equivalent request",
                "category_id": category.id,
                "request_owner_id": self.env.uid,
                "amount": order.amount_total,
                "currency_id": order.currency_id.id,
            },
        )
        order.approval_request_id = request.id
        request.action_confirm()
        request.with_user(self.approver_1).action_approve()

        order.write({"currency_id": self.other_currency.id})
        order.line_ids.write({"price_unit": 200.0})
        order.invalidate_recordset()

        order._check_approved_amount()

    def _approved_creation_request(self, category, quantity):
        request = self.env["approval.request"].create(
            {
                "name": "Audit rollback",
                "category_id": category.id,
                "request_owner_id": self.env.uid,
                "partner_id": self.vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": quantity,
                            "price_unit": 10.0,
                            "product_uom_id": self.product.uom_id.id,
                            "description": "audit",
                        },
                    ),
                ],
            },
        )
        request.action_confirm()
        request.with_user(self.approver_1).action_approve()
        request.action_create_target_documents()
        return request

    def _creation_category(self, name):
        category = self._make_category(name=name, approvers=[self.approver_1])
        category.write(
            {
                "has_product": "required",
                "approval_type": "sale",
                "target_model": "sale.order",
            },
        )
        return category

    def test_refusal_never_leaves_a_negative_quantity(self):
        request = self._approved_creation_request(
            self._creation_category("Audit Rollback Partial"),
            quantity=10.0,
        )
        order = request._get_target_documents()
        document_line = order.line_ids[0]
        self.assertEqual(document_line.product_qty, 10.0)

        document_line.write({"product_qty": 4.0})
        request._refuse_approval_request()

        self.assertFalse(
            document_line.exists(),
            "A line the approval fully covers is removed, not driven negative",
        )
        self.assertFalse(order.exists())

    def test_refusal_decrements_a_line_it_only_partly_covers(self):
        request = self._approved_creation_request(
            self._creation_category("Audit Rollback Decrement"),
            quantity=3.0,
        )
        order = request._get_target_documents()
        document_line = order.line_ids[0]

        document_line.write({"product_qty": 10.0})
        request._refuse_approval_request()

        self.assertTrue(document_line.exists())
        self.assertEqual(document_line.product_qty, 7.0)
        self.assertTrue(order.exists())

    def test_refusal_removes_an_untouched_document(self):
        request = self._approved_creation_request(
            self._creation_category("Audit Rollback Full"),
            quantity=7.0,
        )
        order = request._get_target_documents()
        self.assertEqual(order.line_ids[0].product_qty, 7.0)

        request._refuse_approval_request()

        self.assertFalse(
            order.exists(),
            "An untouched document is removed whole when the approval is refused",
        )

    def test_refusal_notice_keeps_its_markup_and_escapes_the_request_name(self):
        request = self._approved_creation_request(
            self._creation_category("Audit Refusal Notice"),
            quantity=2.0,
        )
        request.name = "<b>Rush</b>"
        order = request._get_target_documents()

        request._log_target_refusal_to_document_chatter(
            [{"document": order, "source_lines": request.line_ids}],
        )

        body = order.message_ids[:1].body
        self.assertIn("<strong>Warning: Approval Request Refused</strong>", body)
        self.assertIn("&lt;b&gt;Rush&lt;/b&gt;", body)
        self.assertIn("<li>2.0 x ", body)

    def test_product_category_forcing_follows_the_hierarchy(self):
        """A flag on a parent category has to reach products filed below it.

        The mirror of test_product_category_match_follows_the_hierarchy: the
        matcher reads the tree with child_of, and the master-data flag that
        forces approval outright has to scope the same way. It used to read
        the product's own category and nothing above it, so flagging a parent
        protected none of its branch.
        """
        parent = self.env["product.category"].create({"name": "Forced Parent"})
        child = self.env["product.category"].create(
            {"name": "Forced Child", "parent_id": parent.id},
        )
        product = create_test_product(self.env, type="consu", categ_id=child.id)
        order = self._make_order(product=product)
        flag = f"{order._get_approval_field_prefix()}_approval_required"

        self.assertFalse(
            order._is_approval_forced_by_product_category(),
            "precondition: nothing is flagged yet",
        )

        parent.sudo()[flag] = True
        self.assertTrue(
            order._is_approval_forced_by_product_category(),
            "a flag on the parent category did not reach a product in its child",
        )

    def test_product_category_forcing_still_reads_the_own_category(self):
        parent = self.env["product.category"].create({"name": "Own Parent"})
        child = self.env["product.category"].create(
            {"name": "Own Child", "parent_id": parent.id},
        )
        product = create_test_product(self.env, type="consu", categ_id=child.id)
        order = self._make_order(product=product)
        flag = f"{order._get_approval_field_prefix()}_approval_required"

        child.sudo()[flag] = True
        self.assertTrue(
            order._is_approval_forced_by_product_category(),
            "the product's own category must still force approval",
        )

    def test_product_category_forcing_ignores_an_unrelated_branch(self):
        flagged = self.env["product.category"].create({"name": "Unrelated Flagged"})
        other = self.env["product.category"].create({"name": "Unrelated Other"})
        product = create_test_product(self.env, type="consu", categ_id=other.id)
        order = self._make_order(product=product)
        flag = f"{order._get_approval_field_prefix()}_approval_required"

        flagged.sudo()[flag] = True
        self.assertFalse(
            order._is_approval_forced_by_product_category(),
            "a flag on an unrelated category must not force approval",
        )

    def _requests_with_orders(self, count, prefix):
        category = self._creation_category(f"{prefix} category")
        requests = self.env["approval.request"]
        for index in range(count):
            # _approved_creation_request already creates the target documents.
            requests |= self._approved_creation_request(category, quantity=1.0 + index)
        return requests

    def test_documents_by_request_agrees_with_the_singleton_helper(self):
        requests = self._requests_with_orders(3, "Batch agree")
        batched = requests._documents_of_model_by_request(
            "sale.order",
            "sale_order_line_id",
            "order_id",
        )
        for request in requests:
            self.assertEqual(
                batched[request.id],
                request._get_target_documents(),
                f"batched lookup disagrees with the singleton form for {request.name}",
            )

    def test_documents_by_request_costs_the_same_whatever_the_selection(self):
        """The batched form exists to stop the cost growing per request.

        _get_documents_of_model is check_singleton() and searches once per
        record; consumers holding many requests paid that per record.
        """
        small = self._requests_with_orders(2, "Batch small")
        large = self._requests_with_orders(6, "Batch large")
        args = ("sale.order", "sale_order_line_id", "order_id")

        self.env.invalidate_all()
        before = self.env.cr.sql_statement_count
        small._documents_of_model_by_request(*args)
        small_cost = self.env.cr.sql_statement_count - before

        self.env.invalidate_all()
        before = self.env.cr.sql_statement_count
        large._documents_of_model_by_request(*args)
        large_cost = self.env.cr.sql_statement_count - before

        self.assertEqual(
            small_cost,
            large_cost,
            f"the batched lookup scales with the selection: {small_cost} "
            f"queries for 2 requests, {large_cost} for 6",
        )

    def test_documents_by_request_is_empty_without_documents(self):
        # Never approved, so nothing was ever created from it.
        request = self.env["approval.request"].create(
            {
                "name": "Batch empty",
                "category_id": self._creation_category("Batch empty").id,
                "request_owner_id": self.env.uid,
                "partner_id": self.vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 10.0,
                            "product_uom_id": self.product.uom_id.id,
                            "description": "audit",
                        },
                    ),
                ],
            },
        )
        batched = request._documents_of_model_by_request(
            "sale.order",
            "sale_order_line_id",
            "order_id",
        )
        self.assertFalse(batched[request.id])
