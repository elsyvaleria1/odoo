from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestTemplateAutocomplete(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.account = cls.env["account.account"].create(
            {
                "name": "Autocomplete expense",
                "code": "AUTO001",
                "account_type": "expense",
                "company_ids": [Command.link(cls.company.id)],
            }
        )
        cls.journal = cls.env["account.journal"].search(
            [
                ("company_id", "=", cls.company.id),
                ("type", "=", "purchase"),
            ],
            limit=1,
        ) or cls.env["account.journal"].create(
            {
                "name": "Autocomplete purchases",
                "code": "AUTO",
                "type": "purchase",
                "company_id": cls.company.id,
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "Template vendor"})
        cls.product = cls.env["product.product"].create({"name": "Template product"})
        cls.template = cls.env["account.move.template"].create(
            {
                "name": "Autocomplete template",
                "ref": "TEMPLATE-REF",
                "move_type": "in_invoice",
                "journal_code": cls.journal.code,
                "partner_id": cls.partner.id,
                "invoice_payment_term_id": cls.env.ref(
                    "payment_term.account_payment_term_immediate"
                ).id,
                "line_ids": [
                    Command.create(
                        {
                            "display_type": "line_section",
                            "name": "Recurring costs",
                            "sequence": 10,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Monthly cost",
                            "account_code": cls.account.code,
                            "product_id": cls.product.id,
                            "quantity": 3,
                            "price_unit": 40,
                            "discount": 10,
                            "sequence": 20,
                        }
                    ),
                    Command.create(
                        {
                            "display_type": "line_note",
                            "name": "Review each month",
                            "sequence": 30,
                        }
                    ),
                ],
            }
        )

    def _move(self, **values):
        return self.env["account.move"].new(
            {
                "move_type": "in_invoice",
                "company_id": self.company.id,
                "journal_id": self.journal.id,
                **values,
            }
        )

    def test_base_picker_applies_template_without_trade_dependency(self):
        user = new_test_user(
            self.env,
            login="autocomplete-accountant",
            groups="account.group_account_user",
        )
        source = (
            self.env["account.move.match"]
            .with_user(user)
            .search(
                [
                    ("template_id", "=", self.template.id),
                ]
            )
        )
        with Form(
            self.env["account.move"]
            .with_user(user)
            .with_context(default_move_type="in_invoice")
        ) as form:
            form.invoice_source_id = source
            self.assertEqual(form.partner_id, self.partner)
            self.assertEqual(form.ref, "TEMPLATE-REF")
            self.assertEqual(len(form.invoice_line_ids), 3)
        self.assertEqual(len(form.record.invoice_line_ids), 3)
        self.assertEqual(
            form.record.invoice_line_ids.mapped("name"),
            ["Recurring costs", "Monthly cost", "Review each month"],
        )

    def test_template_preserves_sections_units_discounts_and_terms(self):
        move = self._move()
        move._load_template_data(self.template)
        self.assertEqual(
            move.invoice_line_ids.mapped("name"),
            ["Recurring costs", "Monthly cost", "Review each month"],
        )
        line = move.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        self.assertEqual(line.product_id, self.product)
        self.assertEqual(line.product_uom_id, self.product.uom_id)
        self.assertEqual((line.quantity, line.price_unit, line.discount), (3, 40, 10))
        self.assertEqual(line.account_id, self.account)
        self.assertEqual(
            move.invoice_payment_term_id, self.template.invoice_payment_term_id
        )

    def test_autocomplete_preserves_explicit_zero_price_and_empty_taxes(self):
        self.product.standard_price = 75
        tax = self.env["account.tax"].create(
            {
                "name": "Product default tax",
                "amount": 15,
                "type_tax_use": "purchase",
            }
        )
        self.product.supplier_taxes_id = [Command.set(tax.ids)]
        line = self.template.line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        line.write({"price_unit": 0, "tax_ids": [Command.clear()]})
        move = self._move()
        move._load_template_data(self.template)
        result = move.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        self.assertEqual(result.price_unit, 0)
        self.assertEqual(result.name, "Monthly cost")
        self.assertFalse(result.tax_ids)
        user = new_test_user(
            self.env,
            login="literal-template-accountant",
            groups="account.group_account_user",
        )
        source = (
            self.env["account.move.match"]
            .with_user(user)
            .search(
                [
                    ("template_id", "=", self.template.id),
                ]
            )
        )
        with Form(
            self.env["account.move"]
            .with_user(user)
            .with_context(
                default_move_type="in_invoice",
            )
        ) as form:
            form.invoice_source_id = source
        saved_line = form.record.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        self.assertEqual(saved_line.price_unit, 0)
        self.assertEqual(saved_line.name, "Monthly cost")
        self.assertFalse(saved_line.tax_ids)

    def test_template_replaces_lines_but_preserves_existing_partner_and_reference(self):
        partner = self.env["res.partner"].create({"name": "Chosen vendor"})
        move = self._move(
            partner_id=partner.id,
            ref="KEEP",
            invoice_line_ids=[
                Command.create(
                    {
                        "name": "Old line",
                        "display_type": "product",
                        "product_id": self.product.id,
                    }
                )
            ],
        )
        move._load_template_data(self.template)
        self.assertEqual(move.partner_id, partner)
        self.assertEqual(move.ref, "KEEP")
        self.assertNotIn("Old line", move.invoice_line_ids.mapped("name"))

    def test_incompatible_template_does_not_clear_existing_lines(self):
        move = self.env["account.move"].create(
            {
                "move_type": "in_refund",
                "partner_id": self.partner.id,
                "journal_id": self.journal.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Keep",
                            "product_id": self.product.id,
                            "account_id": self.account.id,
                            "quantity": 1,
                            "price_unit": 20,
                        }
                    )
                ],
            }
        )
        with self.assertRaises(UserError):
            move._load_template_data(self.template)
        self.assertEqual(move.invoice_line_ids.mapped("name"), ["Keep"])

    def test_archived_template_cannot_be_selected_or_loaded(self):
        self.template.active = False
        self.assertFalse(
            self.env["account.move.match"].search(
                [("template_id", "=", self.template.id)]
            )
        )
        with self.assertRaises(UserError):
            self._move()._load_template_data(self.template)

    def test_posted_destination_rejects_template(self):
        with self.assertRaises(UserError):
            self._move(state="posted")._load_template_data(self.template)

    def test_user_without_template_read_access_cannot_see_or_load_it(self):
        user = new_test_user(
            self.env,
            login="autocomplete-billing",
            groups="account.group_account_invoice",
        )
        self.assertFalse(
            self.env["account.move.match"]
            .with_user(user)
            .search([("template_id", "=", self.template.id)])
        )
        with self.assertRaises(AccessError):
            self._move().with_user(user)._load_template_data(
                self.template.with_user(user)
            )

    def test_global_template_uses_destination_company(self):
        self.template.company_id = False
        move = self._move()
        move._load_template_data(self.template)
        self.assertEqual(
            move.invoice_line_ids.filtered(
                lambda line: line.display_type == "product"
            ).account_id,
            self.account,
        )

    def test_company_guard_hides_other_company_templates(self):
        other = self.env["res.company"].create({"name": "Other autocomplete company"})
        self.env["account.account"].with_company(other).create(
            {
                "name": "Other expense",
                "code": "AUTO001",
                "account_type": "expense",
                "company_ids": [Command.link(other.id)],
            }
        )
        journal = self.env["account.journal"].create(
            {
                "name": "Other purchases",
                "code": "OAUTO",
                "type": "purchase",
                "company_id": other.id,
            }
        )
        template = self.template.with_company(other).copy(
            {
                "company_id": other.id,
                "journal_code": journal.code,
            }
        )
        user = new_test_user(
            self.env, login="autocomplete-company", groups="account.group_account_user"
        )
        self.assertFalse(
            self.env["account.move.match"]
            .with_user(user)
            .search([("template_id", "=", template.id)])
        )
        with self.assertRaises(UserError):
            self._move()._load_template_data(template)

    def test_account_resolution_prefers_exact_code_to_a_longer_prefix(self):
        self.env["account.account"].create(
            {
                "name": "Longer code",
                "code": "AUTO001X",
                "account_type": "expense",
                "company_ids": [Command.link(self.company.id)],
            }
        )
        self._move()._load_template_data(self.template)
        self.assertEqual(
            self.template.line_ids.filtered("account_code").account_id, self.account
        )
