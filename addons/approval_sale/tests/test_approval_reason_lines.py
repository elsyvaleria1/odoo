from unittest.mock import patch

from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval_product.models import (
    mixin_approval_document as approval_document_module,
)


@tagged("post_install", "-at_install")
class TestApprovalReasonLines(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.customer = cls.env["res.partner"].create(
            {
                "name": "Reason Lines Customer",
                "company_id": cls.company.id,
            },
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Reason Lines Product",
                "type": "consu",
                "list_price": 10.0,
            },
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Reason Lines Category",
                "company_id": cls.company.id,
                "sequence_code": "REASONLINES",
            },
        )

    def _create_order(self, products=2, sections=0, notes=0):
        commands = [
            Command.create(
                {
                    "product_id": self.product.id,
                    "product_qty": index + 1,
                    "price_unit": 10.0,
                },
            )
            for index in range(products)
        ]
        commands += [
            Command.create(
                {
                    "display_type": "line_section",
                    "name": f"Section {index}",
                },
            )
            for index in range(sections)
        ]
        commands += [
            Command.create(
                {
                    "display_type": "line_note",
                    "name": f"Note {index}",
                },
            )
            for index in range(notes)
        ]
        return self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "company_id": self.company.id,
                "line_ids": commands,
            },
        )

    def _create_request(self):
        return self.env["approval.request"].create(
            {
                "name": "Reason Lines Request",
                "category_id": self.category.id,
                "company_id": self.company.id,
                "request_owner_id": self.env.user.id,
            },
        )

    def test_the_reason_carries_the_notes_left_for_approvers(self):
        self.product.categ_id = self.env["product.category"].create(
            {"name": "Reason Lines Category Of Products"},
        )
        self.customer.so_approval_notes = "Verify the credit limit first"
        self.product.so_approval_notes = "High value item"
        self.product.categ_id.so_approval_notes = "Check payment terms"

        reason = self._create_order(products=2)._get_approval_reason_html()

        self.assertIn("Notes for approvers", reason)
        self.assertIn("Verify the credit limit first", reason)
        self.assertIn("High value item", reason)
        self.assertIn("Check payment terms", reason)

    def test_a_repeated_product_contributes_its_note_once(self):
        self.product.so_approval_notes = "High value item"

        reason = self._create_order(products=3)._get_approval_reason_html()

        self.assertEqual(reason.count("High value item"), 1)

    def test_the_notes_are_escaped(self):
        self.customer.so_approval_notes = "<script>alert(1)</script>"

        reason = self._create_order(products=1)._get_approval_reason_html()

        self.assertNotIn("<script>", reason)
        self.assertIn("&lt;script&gt;", reason)

    def test_no_notes_adds_no_section(self):
        reason = self._create_order(products=2)._get_approval_reason_html()

        self.assertNotIn("Notes for approvers", reason)

    def test_reason_lists_every_product_line(self):
        order = self._create_order(products=17)

        reason = order._get_approval_reason_html()

        self.assertEqual(reason.count("<li>"), 17)
        self.assertNotIn("Number of Products", reason)

    def test_reason_small_order_unchanged(self):
        order = self._create_order(products=2)

        reason = order._get_approval_reason_html()

        self.assertIn("<p><strong>Products:</strong></p><ul>", reason)
        self.assertEqual(reason.count("<li>"), 2)
        self.assertIn("Qty: 1.0", reason)

    def test_reason_counts_products_not_sections(self):
        order = self._create_order(products=4, sections=2, notes=1)

        with patch.object(approval_document_module, "MAX_DETAIL_LINES", 5):
            reason = order._get_approval_reason_html()

        self.assertEqual(reason.count("<li>"), 4)
        self.assertNotIn("Section 0", reason)
        self.assertNotIn("Note 0", reason)
        self.assertNotIn("more lines", reason)

    def test_reason_overflow_lists_then_announces_remainder(self):
        order = self._create_order(products=5)

        with patch.object(approval_document_module, "MAX_DETAIL_LINES", 3):
            reason = order._get_approval_reason_html()

        self.assertEqual(reason.count("<li>"), 3)
        self.assertIn("and 2 more lines", reason)
        self.assertNotIn("Number of Products", reason)

    def test_display_lines_from_order_that_requested_approval(self):
        order = self._create_order(products=3, sections=1)
        approval = self._create_request()
        order.approval_request_id = approval.id

        self.assertFalse(approval.line_ids)

        lines, omitted = approval._get_sale_display_lines()

        self.assertEqual(omitted, 0)
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0]["product"], self.product.display_name)
        self.assertEqual(lines[0]["quantity"], 1.0)
        self.assertEqual(lines[0]["uom"], order.line_ids[0].product_uom_id.name)
        self.assertEqual(lines[0]["subtotal"], order.line_ids[0].price_subtotal)
        self.assertEqual(lines[0]["currency"], order.currency_id.symbol)
        self.assertEqual(lines[0]["order"], order.name)

    def test_display_lines_limit_reports_omitted(self):
        order = self._create_order(products=5)
        approval = self._create_request()
        order.approval_request_id = approval.id

        lines, omitted = approval._get_sale_display_lines(limit=2)

        self.assertEqual(len(lines), 2)
        self.assertEqual(omitted, 3)

    def test_display_lines_without_any_sale_order(self):
        approval = self._create_request()

        self.assertEqual(approval._get_sale_display_lines(), ([], 0))
