import re

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.form import Form

from .common import ensure_publish_date_field
from odoo.addons.approval.tests.common import ApprovalCommon


@tagged("post_install", "-at_install")
class TestProductLines(ApprovalCommon):
    def _make_product(self, name="Test Product"):
        has_publish_date = ensure_publish_date_field(self.env)
        template_vals = {"name": name, "type": "consu"}
        if has_publish_date:
            template_vals["publish_date"] = fields.Datetime.now()
        template = self.env["product.template"].create(template_vals)
        return template.product_variant_ids[:1]

    def test_submit_with_products_skips_quantity_validation(self):
        product = self._make_product()

        category = self._make_category(
            has_quantity="required",
            has_product="required",
            approvers=[self.approver_1],
        )
        request = self.env["approval.request"].create(
            {
                "name": "Test Request with Products",
                "category_id": category.id,
                "request_owner_id": self.env.user.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "quantity": 5.0,
                            "price_unit": 10.0,
                        }
                    )
                ],
            }
        )
        request.action_confirm()
        self.assertEqual(
            request.state,
            "pending",
            "Product-based category must skip the header quantity check.",
        )

    def test_line_quantities_reach_the_routing_engine(self):
        product = self._make_product()
        category = self._make_category(
            has_product="required",
            approvers=[self.approver_1],
        )
        request = self.env["approval.request"].create(
            {
                "name": "Routed on its lines",
                "category_id": category.id,
                "request_owner_id": self.env.user.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "quantity": 50.0,
                            "price_unit": 10.0,
                        }
                    )
                ],
            }
        )
        self.assertEqual(request.quantity, 50.0)

        rule = self.env["approval.rule"].create(
            {
                "category_id": category.id,
                "name": "Bulk order",
                "condition_field": "quantity",
                "operator": "gte",
                "threshold": 10.0,
                "action_type": "condition",
            }
        )
        self.assertTrue(
            rule._evaluate(request),
            "A quantity rule must see the quantity the lines carry",
        )

        request.line_ids[0].quantity = 3.0
        self.assertEqual(request.quantity, 3.0)
        self.assertFalse(rule._evaluate(request))

    def test_a_hand_written_quantity_survives_without_lines(self):
        category = self._make_category(
            has_product="no",
            has_quantity="required",
            approvers=[self.approver_1],
        )
        request = self.env["approval.request"].create(
            {
                "name": "Hand written quantity",
                "category_id": category.id,
                "request_owner_id": self.env.user.id,
                "quantity": 7.0,
            }
        )
        self.assertEqual(request.quantity, 7.0)
        request.write({"quantity": 9.0})
        self.assertEqual(request.quantity, 9.0)

    def test_a_line_needs_a_contact_only_when_the_request_does(self):
        product = self._make_product()
        category = self._make_category(
            has_product="required",
            has_partner="no",
            approvers=[self.approver_1],
        )
        request_form = Form(self.env["approval.request"])
        request_form.category_id = category
        with request_form.line_ids.new() as line:
            line.product_id = product
            line.quantity = 3.0
        request = request_form.save()

        self.assertFalse(
            request.line_ids.partner_id,
            "A category that needs no contact must not demand one per line",
        )

    def test_the_printed_request_carries_the_money(self):
        product = self._make_product()
        category = self._make_category(
            has_product="required",
            approvers=[self.approver_1],
        )
        request = self.env["approval.request"].create(
            {
                "name": "Printed Request",
                "category_id": category.id,
                "request_owner_id": self.env.user.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "quantity": 7.0,
                            "price_unit": 250.0,
                        }
                    )
                ],
            }
        )
        line = request.line_ids[0]
        self.assertEqual(line.price_subtotal, 1750.0)

        html = str(
            self.env["ir.qweb"]._render(
                "approval.report_approval_request_document",
                {"doc": request, "o": request, "docs": request},
            )
        )
        headers = re.findall(r"<th[^>]*>([^<]+)</th>", html)
        for column in ("Unit Price", "Subtotal"):
            self.assertIn(column, headers)
        rendered = re.findall(r'<span class="oe_currency_value">([^<]+)</span>', html)
        self.assertIn(
            "250.00",
            rendered,
            "The approver must see the unit price they are signing off",
        )
        self.assertEqual(
            rendered.count("1,750.00"),
            2,
            "The subtotal must appear on the line and again in the total row",
        )
        self.assertIn(request.currency_id.symbol, html)

    def test_required_products_are_validated_at_submit(self):
        category = self._make_category(
            has_product="required",
            approvers=[self.approver_1],
        )
        request = self.env["approval.request"].create(
            {
                "name": "Request without Products",
                "category_id": category.id,
                "request_owner_id": self.env.user.id,
            }
        )
        with self.assertRaises(UserError) as capture:
            request.action_confirm()
        self.assertIn("Products", str(capture.exception))
        self.assertEqual(
            request.state,
            "new",
            "A Products-Required category must not confirm with zero lines.",
        )

    def test_optional_products_still_require_the_header_quantity(self):
        category = self._make_category(
            has_quantity="required",
            has_product="optional",
            approvers=[self.approver_1],
        )
        request = self.env["approval.request"].create(
            {
                "name": "Optional Products without Quantity",
                "category_id": category.id,
                "request_owner_id": self.env.user.id,
            }
        )
        with self.assertRaises(UserError) as capture:
            request.action_confirm()
        self.assertIn("Quantity", str(capture.exception))

    def test_required_products_without_lines_still_require_the_quantity(self):
        category = self._make_category(
            has_quantity="required",
            has_product="required",
            approvers=[self.approver_1],
        )
        request = self.env["approval.request"].create(
            {
                "name": "Required Products without Lines",
                "category_id": category.id,
                "request_owner_id": self.env.user.id,
            }
        )
        with self.assertRaises(UserError) as capture:
            request.action_confirm()
        message = str(capture.exception)
        self.assertIn("Products", message)
        self.assertIn("Quantity", message)

    def test_header_quantity_is_shown_when_no_line_can_supply_it(self):
        category = self._make_category(
            has_quantity="required",
            has_product="optional",
            approvers=[self.approver_1],
        )
        request = self.env["approval.request"].create(
            {
                "name": "Optional Products Form",
                "category_id": category.id,
                "request_owner_id": self.env.user.id,
            }
        )
        arch = request.get_view(
            self.env.ref("approval.view_approval_request_form").id, "form"
        )["arch"]
        node = re.search(r'<field[^>]*name="quantity"[^>]*/>', arch).group(0)
        self.assertIn("not line_ids", node)
        self.assertIn("has_product != 'no' and line_ids", node)

    def test_optional_products_are_not_validated_at_submit(self):
        category = self._make_category(
            has_product="optional",
            approvers=[self.approver_1],
        )
        request = self.env["approval.request"].create(
            {
                "name": "Request with Optional Products",
                "category_id": category.id,
                "request_owner_id": self.env.user.id,
            }
        )
        request.action_confirm()
        self.assertEqual(request.state, "pending")
