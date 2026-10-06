from odoo.fields import Command
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPurchaseBillMatchTemplates(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.match = cls.env["purchase.bill.match"]
        cls.purchase_journal = cls.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", cls.company.id)],
            limit=1,
        )
        if not cls.purchase_journal:
            cls.purchase_journal = cls.env["account.journal"].create(
                {
                    "name": "Test Purchase Journal",
                    "code": "TPURJ",
                    "type": "purchase",
                    "company_id": cls.company.id,
                }
            )
        cls.expense_account = cls.env["account.account"].search(
            [("account_type", "=", "expense"), ("company_ids", "in", cls.company.id)],
            limit=1,
        )
        if not cls.expense_account:
            cls.expense_account = cls.env["account.account"].create(
                {
                    "name": "Test Expense Smoke",
                    "code": "TPBMEXP",
                    "account_type": "expense",
                    "company_ids": [Command.link(cls.company.id)],
                }
            )

    def _journal_code(self, journal_type):
        return (
            self.env["account.journal"]
            .search(
                [("type", "=", journal_type), ("company_id", "=", self.company.id)],
                limit=1,
            )
            .code
        )

    def _create_template(self, **kwargs):
        values = {
            "name": "Smoke Vendor Template",
            "journal_code": self.purchase_journal.code,
            "move_type": "in_invoice",
            "company_id": self.company.id,
            "line_ids": [
                Command.create(
                    {
                        "sequence": 10,
                        "name": "Smoke line",
                        "display_type": "product",
                        "account_code": self.expense_account.code,
                        "balance": 100.0,
                    }
                ),
            ],
        }
        values.update(kwargs)
        if values.get("is_payment"):
            values.pop("line_ids", None)
        return self.env["account.move.template"].create(values)

    def test_vendor_template_has_a_stable_source_id(self):
        template = self._create_template()
        match = self.match.search([("template_id", "=", template.id)])

        self.assertEqual(
            len(match), 1, "template should appear exactly once in the view"
        )
        self.assertEqual(match.id, 2**31 + template.id)
        bill = self.env["account.move"].create({"move_type": "in_invoice"})
        self.assertEqual(
            self.match.search([("template_id", "=", template.id)]).id, match.id
        )
        self.assertNotEqual(match.id, bill.id)
        self.assertIn(template.name, match.display_name)
        self.assertIn("Template", match.display_name)

    def test_payment_template_excluded(self):
        template = self._create_template(
            journal_code=self._journal_code("bank"),
            is_payment=True,
            payment_type="outbound",
            partner_type="supplier",
        )
        self.assertFalse(self.match.search([("template_id", "=", template.id)]))

    def test_archived_template_excluded(self):
        template = self._create_template(active=False)
        self.assertFalse(self.match.search([("template_id", "=", template.id)]))

    def test_customer_template_excluded(self):
        template = self._create_template(
            journal_code=self._journal_code("sale"),
            move_type="out_invoice",
        )
        self.assertFalse(self.match.search([("template_id", "=", template.id)]))

    def test_currency_fallback_to_env_company(self):
        template = self._create_template(company_id=False)
        match = self.match.search([("template_id", "=", template.id)])
        self.assertEqual(match.currency_id, self.env.company.currency_id)

    def test_display_name_includes_reference(self):
        template = self._create_template(ref="REF-001")
        match = self.match.search([("template_id", "=", template.id)])
        self.assertIn("REF-001", match.display_name)

    def test_hidden_when_user_lacks_invoice_group(self):
        template = self._create_template()
        restricted_user = self.env["res.users"].create(
            {
                "name": "No Invoice Group",
                "login": f"no-invoice-{template.id}@test",
                "group_ids": [
                    Command.set(
                        self.env.ref("base.group_user").ids
                        + self.env.ref("purchase.group_purchase_user").ids,
                    ),
                ],
            }
        )
        match = self.match.with_user(restricted_user).search(
            [("template_id", "=", template.id)]
        )
        self.assertFalse(
            match, "template must be hidden from users without invoice group"
        )

    def test_purchase_picker_loads_template_without_an_order_link(self):
        product = self.env["product.product"].create(
            {"name": "Purchase template product"}
        )
        vendor = self.env["res.partner"].create({"name": "Purchase template vendor"})
        template = self._create_template(
            partner_id=vendor.id,
            line_ids=[
                Command.create(
                    {
                        "name": "Purchase template line",
                        "account_code": self.expense_account.code,
                        "product_id": product.id,
                        "quantity": 3,
                        "price_unit": 24,
                    }
                )
            ],
        )
        source = self.match.search([("template_id", "=", template.id)])
        form = Form(
            self.env["account.move"].with_context(default_move_type="in_invoice")
        )
        form.purchase_vendor_bill_id = source
        move = form.save()
        self.assertEqual(move.partner_id, vendor)
        self.assertEqual(move.invoice_line_ids.product_id, product)
        product_lines = move.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        self.assertEqual(len(product_lines), 1)
        self.assertEqual(product_lines.quantity, 3)
        self.assertFalse(move.invoice_line_ids.purchase_line_ids)
