from odoo.fields import Command
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestSaleTemplateAutocomplete(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.journal = cls.env["account.journal"].search(
            [
                ("type", "=", "sale"),
                ("company_id", "=", cls.company.id),
            ],
            limit=1,
        )
        cls.account = cls.env["account.account"].search(
            [
                ("account_type", "=", "income"),
                ("company_ids", "in", cls.company.id),
            ],
            limit=1,
        )
        cls.partner = cls.env["res.partner"].create({"name": "Autocomplete customer"})
        cls.product = cls.env["product.product"].create(
            {"name": "Sales template product"}
        )
        cls.template = cls.env["account.move.template"].create(
            {
                "name": "Sales invoice template",
                "move_type": "out_invoice",
                "journal_code": cls.journal.code,
                "partner_id": cls.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "name": "Sales template line",
                            "account_code": cls.account.code,
                            "product_id": cls.product.id,
                            "quantity": 2,
                            "price_unit": 50,
                            "discount": 5,
                        }
                    )
                ],
            }
        )

    def test_selector_cache_respects_company_scoped_trade_role(self):
        other = self.env["res.company"].create({"name": "Selector other company"})
        user = new_test_user(
            self.env,
            login="scoped-autocomplete-sales",
            groups="account.group_account_user,sale.group_sale_salesman",
            company_ids=[Command.set((self.company | other).ids)],
        )
        group = self.env.ref("sale.group_sale_salesman")
        self.env["res.users.grant"].search(
            [
                ("user_id", "=", user.id),
                ("group_id", "=", group.id),
            ]
        ).write({"company_ids": [Command.set(self.company.ids)]})
        move = (
            self.env["account.move"]
            .create(
                {
                    "move_type": "out_invoice",
                    "journal_id": self.journal.id,
                }
            )
            .with_user(user)
        )
        scoped = move.with_context(allowed_company_ids=self.company.ids)
        other_scope = move.with_context(allowed_company_ids=other.ids)
        self.assertTrue(scoped.env.user.has_group("sale.group_sale_salesman"))
        self.assertFalse(other_scope.env.user.has_group("sale.group_sale_salesman"))
        self.assertEqual(scoped.invoice_autocomplete_field, "sale_customer_invoice_id")
        self.assertEqual(other_scope.invoice_autocomplete_field, "invoice_source_id")

    def test_sales_picker_loads_template_and_resets_selection(self):
        source = self.env["sale.invoice.match"].search(
            [("template_id", "=", self.template.id)]
        )
        self.assertEqual(source.id, 2**31 + self.template.id)
        self.assertIn("Template", source.display_name)
        with Form(
            self.env["account.move"].with_context(default_move_type="out_invoice")
        ) as form:
            form.sale_customer_invoice_id = source
            self.assertEqual(form.partner_id, self.partner)
            self.assertFalse(form.sale_customer_invoice_id)
            with form.invoice_line_ids.edit(0) as line:
                self.assertEqual(line.product_id, self.product)
                self.assertEqual(
                    (line.quantity, line.price_unit, line.discount), (2, 50, 5)
                )
        self.assertEqual(len(form.record.invoice_line_ids), 1)
        self.assertFalse(form.record.invoice_line_ids.sale_line_ids)

    def test_sales_picker_excludes_vendor_templates_and_filters_credit_notes(self):
        purchase_journal = self.env["account.journal"].search(
            [("type", "=", "purchase")], limit=1
        )
        vendor = self.template.copy(
            {
                "name": "Vendor template",
                "move_type": "in_invoice",
                "journal_code": purchase_journal.code,
            }
        )
        refund = self.template.copy(
            {"name": "Customer credit template", "move_type": "out_refund"}
        )
        Source = self.env["sale.invoice.match"]
        self.assertFalse(Source.search([("template_id", "=", vendor.id)]))
        self.assertTrue(
            Source.search(
                [("template_id", "=", refund.id), ("move_type", "=", "out_refund")]
            )
        )
        self.assertFalse(
            Source.search(
                [("template_id", "=", refund.id), ("move_type", "=", "out_invoice")]
            )
        )

    def test_template_visibility_follows_template_read_permission(self):
        salesman = new_test_user(
            self.env, login="template-sales-only", groups="sale.group_sale_salesman"
        )
        Source = self.env["sale.invoice.match"].with_user(salesman)
        self.assertFalse(Source.search([("template_id", "=", self.template.id)]))
        salesman.group_ids += self.env.ref("account.group_account_user")
        self.assertEqual(
            Source.search([("template_id", "=", self.template.id)]).template_id,
            self.template,
        )

    def test_sales_order_still_appends_lines_and_keeps_its_link(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 3,
                            "price_unit": 25,
                        }
                    )
                ],
            }
        )
        order.action_confirm()
        source = self.env["sale.invoice.match"].search([("order_id", "=", order.id)])
        move = self.env["account.move"].new(
            {"move_type": "out_invoice", "company_id": self.company.id}
        )
        move.sale_customer_invoice_id = source
        move._onchange_sale_auto_complete()
        self.assertEqual(move.invoice_line_ids.sale_line_ids._origin, order.line_ids)
        self.assertEqual(move.invoice_line_ids.quantity, 3)
        self.assertEqual(move.invoice_origin, order.name)
        move.sale_customer_invoice_id = source
        move._onchange_sale_auto_complete()
        self.assertEqual(len(move.invoice_line_ids), 1)

    def test_previous_invoice_still_appends_its_lines(self):
        previous = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "invoice_line_ids": [
                    Command.create(
                        {"product_id": self.product.id, "quantity": 4, "price_unit": 30}
                    )
                ],
            }
        )
        previous.action_post()
        source = self.env["sale.invoice.match"].search([("move_id", "=", previous.id)])
        move = self.env["account.move"].new(
            {"move_type": "out_invoice", "company_id": self.company.id}
        )
        move.sale_customer_invoice_id = source
        move._onchange_sale_auto_complete()
        self.assertEqual(move.invoice_line_ids.product_id, self.product)
        self.assertEqual(move.invoice_line_ids.quantity, 4)
        self.assertEqual(move.currency_id, previous.currency_id)
