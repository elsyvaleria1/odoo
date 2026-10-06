from unittest.mock import patch

from lxml import etree
from psycopg.errors import UniqueViolation

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAccountMoveTemplate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env["res.partner"].create({"name": "Template Partner"})
        cls.other_partner = cls.env["res.partner"].create(
            {"name": "Diff Partner"},
        )
        cls.debit_account = cls.env["account.account"].create(
            {
                "name": "Test Debit Account",
                "code": "TAMT001",
                "account_type": "expense",
                "company_ids": [Command.link(cls.company.id)],
            }
        )
        cls.credit_account = cls.env["account.account"].create(
            {
                "name": "Test Credit Account",
                "code": "TAMT002",
                "account_type": "liability_current",
                "company_ids": [Command.link(cls.company.id)],
            }
        )
        cls.prefix_account = cls.env["account.account"].create(
            {
                "name": "Test Prefix Account",
                "code": "TAMT9X",
                "account_type": "expense",
                "company_ids": [Command.link(cls.company.id)],
            }
        )
        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", cls.company.id)],
            limit=1,
        )
        if not cls.journal:
            cls.journal = cls.env["account.journal"].create(
                {
                    "name": "Test Misc Journal",
                    "code": "TAMTJ",
                    "type": "general",
                    "company_id": cls.company.id,
                }
            )
        cls.purchase_journal = cls.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", cls.company.id)],
            limit=1,
        )
        if not cls.purchase_journal:
            cls.purchase_journal = cls.env["account.journal"].create(
                {
                    "name": "Test Purchase Journal",
                    "code": "TAMTP",
                    "type": "purchase",
                    "company_id": cls.company.id,
                }
            )
        cls.bank_journal = cls.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", cls.company.id)],
            limit=1,
        )
        chart = cls.env["account.chart.template"]
        cls.bank_journal.inbound_payment_channel_ids.payment_account_id = chart.ref(
            "account_journal_payment_debit_account_id"
        )
        cls.bank_journal.outbound_payment_channel_ids.payment_account_id = chart.ref(
            "account_journal_payment_credit_account_id"
        )
        cls.purchase_tax = cls.env["account.tax"].create(
            {
                "name": "AMT Purchase 16",
                "amount": 16.0,
                "amount_type": "percent",
                "type_tax_use": "purchase",
                "company_ids": [Command.set(cls.company.ids)],
            }
        )
        if not cls.bank_journal:
            cls.bank_journal = cls.env["account.journal"].create(
                {
                    "name": "Test Bank Journal",
                    "code": "TAMTB",
                    "type": "bank",
                    "company_id": cls.company.id,
                }
            )
        cls._setup_second_company()

    @classmethod
    def _setup_second_company(cls):
        """A second company, so the multi-company paths are actually exercised.

        Everything else in this file is built in ``cls.env.company``, which is
        why a whole family of company-scoped defects stayed invisible until a
        two-company database was used.
        """
        cls.other_company = cls.env["res.company"].create({"name": "AMT Other Co"})
        cls.other_journal = cls.env["account.journal"].create(
            {
                "name": "AMT Other Purchase Journal",
                "code": "TAMTO",
                "type": "purchase",
                "company_id": cls.other_company.id,
            }
        )
        cls.other_purchase_tax = cls.env["account.tax"].create(
            {
                "name": "AMT Other Purchase 7",
                "amount": 7.0,
                "amount_type": "percent",
                "type_tax_use": "purchase",
                "company_ids": [Command.set(cls.other_company.ids)],
            }
        )

    def setUp(self):
        super().setUp()
        self.template = self.env["account.move.template"].create(
            {
                "name": "Test Journal Template",
                "journal_code": self.journal.code,
                "move_type": "entry",
                "company_id": self.company.id,
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 10,
                            "name": "Debit line",
                            "account_code": self.debit_account.code,
                            "balance": 100.0,
                        }
                    ),
                    Command.create(
                        {
                            "sequence": 20,
                            "name": "Credit line",
                            "account_code": self.credit_account.code,
                            "balance": -100.0,
                        }
                    ),
                ],
            }
        )

    def test_wizard_creates_balanced_move(self):
        action = self.template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        self.assertFalse(wizard.line_ids)

        move = wizard.create_move()
        self.assertEqual(len(wizard.line_ids), 2)
        self.assertEqual(move.move_type, "entry")
        self.assertEqual(move.journal_id, self.journal)
        self.assertEqual(len(move.line_ids), 2)
        self.assertEqual(sum(move.line_ids.mapped("balance")), 0.0)

    def test_use_template_button_returns_an_openable_action(self):
        action = self.template.action_move_template_run()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(
            action["res_model"], "wizard.account.move.template.create.move"
        )
        self.assertEqual(action["target"], "new")
        self.assertTrue(action["res_id"])

    def test_action_create_move_navigates_to_the_document(self):
        action = self.template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )

        result = wizard.action_create_move()
        self.assertEqual(result["type"], "ir.actions.act_window")
        self.assertEqual(result["res_model"], "account.move")
        self.assertTrue(self.env["account.move"].browse(result["res_id"]).exists())

    def test_create_move_still_returns_the_record_for_callers(self):
        action = self.template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )

        move = wizard.create_move()
        self.assertEqual(move._name, "account.move")

    def test_duplicating_a_template_carries_its_lines(self):
        duplicate = self.template.copy()
        self.assertEqual(len(duplicate.line_ids), len(self.template.line_ids))
        self.assertEqual(
            sorted(duplicate.line_ids.mapped("account_code")),
            sorted(self.template.line_ids.mapped("account_code")),
        )
        self.assertEqual(duplicate.name, "Test Journal Template (copy)")

    def test_duplicating_twice_gives_distinct_names(self):
        first = self.template.copy()
        second = self.template.copy()
        self.env.flush_all()
        self.assertNotEqual(first.name, second.name)
        self.assertEqual(second.name, "Test Journal Template (copy 2)")

    def test_duplicating_a_batch_of_templates(self):
        other = self.template.copy({"name": "Second Template"})
        duplicates = (self.template | other).copy()
        self.env.flush_all()
        self.assertEqual(len(duplicates), 2)

    def test_an_explicit_name_survives_the_copy(self):
        self.assertEqual(
            self.template.copy({"name": "Chosen Name"}).name, "Chosen Name"
        )

    def test_wizard_carries_no_document_level_line_fields(self):
        wizard_fields = self.env["wizard.account.move.template.create.move"]._fields
        for name in ("quantity", "price_unit", "discount", "balance"):
            self.assertNotIn(name, wizard_fields)

    def test_multi_line_entry_takes_each_balance_from_its_own_line(self):
        action = self.template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )

        move = wizard.create_move()
        self.assertEqual(sorted(move.line_ids.mapped("balance")), [-100.0, 100.0])

    def test_wizard_propagates_partner_from_template(self):
        action = self.template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        self.assertEqual(wizard.partner_id, self.partner)
        move = wizard.create_move()
        self.assertEqual(move.partner_id, self.partner)

    def test_third_party_does_not_override_partner_on_move(self):
        action = self.template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        wizard.third_party_id = self.other_partner
        move = wizard.create_move()
        self.assertEqual(move.partner_id, self.partner)

    def test_a_template_that_asks_for_it_is_issued_to_the_third_party(self):
        self.template.use_third_party = True
        wizard = self.env["wizard.account.move.template.create.move"].create(
            {
                "template_id": self.template.id,
                "partner_id": self.partner.id,
                "third_party_id": self.other_partner.id,
            }
        )
        wizard.load_lines()
        move = wizard.create_move()
        self.assertEqual(move.partner_id, self.other_partner)
        self.assertEqual(
            move.line_ids.mapped("partner_id"),
            self.other_partner,
        )

    def test_naming_the_third_party_after_loading_moves_the_lines_too(self):
        self.template.use_third_party = True
        action = self.template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        wizard.load_lines()
        self.assertFalse(wizard.line_ids.partner_id)

        with Form(wizard) as form:
            form.third_party_id = self.other_partner

        move = wizard.create_move()
        self.assertEqual(move.partner_id, self.other_partner)
        self.assertEqual(
            move.line_ids.mapped("partner_id"),
            self.other_partner,
        )

    def test_a_template_that_asks_for_it_falls_back_to_the_owner(self):
        self.template.use_third_party = True
        action = self.template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        self.assertFalse(wizard.third_party_id)
        move = wizard.create_move()
        self.assertEqual(move.partner_id, self.partner)

    def test_unknown_journal_code_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env["account.move.template"].create(
                {
                    "name": "Bad Journal Template",
                    "journal_code": "ZZZNOPE",
                    "move_type": "entry",
                    "company_id": self.company.id,
                    "line_ids": [
                        Command.create(
                            {
                                "sequence": 10,
                                "name": "x",
                                "account_code": self.debit_account.code,
                                "balance": 1.0,
                            }
                        ),
                        Command.create(
                            {
                                "sequence": 20,
                                "name": "y",
                                "account_code": self.credit_account.code,
                                "balance": -1.0,
                            }
                        ),
                    ],
                }
            )

    def test_unknown_account_code_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env["account.move.template"].create(
                {
                    "name": "Bad Account Template",
                    "journal_code": self.journal.code,
                    "move_type": "entry",
                    "company_id": self.company.id,
                    "line_ids": [
                        Command.create(
                            {
                                "sequence": 10,
                                "name": "x",
                                "account_code": "ZZZNOPE",
                                "balance": 1.0,
                            }
                        ),
                    ],
                }
            )

    def test_non_payment_template_without_product_lines_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env["account.move.template"].create(
                {
                    "name": "Empty Template",
                    "journal_code": self.journal.code,
                    "move_type": "entry",
                    "company_id": self.company.id,
                    "line_ids": [
                        Command.create(
                            {
                                "sequence": 10,
                                "name": "Section",
                                "display_type": "line_section",
                            }
                        ),
                    ],
                }
            )

    def test_section_line_does_not_require_account_code(self):
        self.template.write(
            {
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 5,
                            "display_type": "line_section",
                            "name": "Header section",
                        }
                    ),
                ],
            }
        )
        section = self.template.line_ids.filtered(
            lambda line: line.display_type == "line_section",
        )
        self.assertTrue(section)
        self.assertFalse(section.account_code)

    def test_duplicate_sequence_is_rejected(self):
        with self.assertRaises(UniqueViolation), self.cr.savepoint():
            self.template.write(
                {
                    "line_ids": [
                        Command.create(
                            {
                                "sequence": 10,
                                "name": "Dup",
                                "account_code": self.debit_account.code,
                                "balance": 1.0,
                            }
                        ),
                    ],
                }
            )
            self.template.flush_model()

    def test_invoice_move_type_sets_invoice_date(self):
        invoice_tmpl = self.env["account.move.template"].create(
            {
                "name": "Invoice Template",
                "journal_code": self.purchase_journal.code,
                "move_type": "in_invoice",
                "company_id": self.company.id,
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 10,
                            "name": "Bill line",
                            "account_code": self.debit_account.code,
                            "quantity": 1.0,
                            "price_unit": 100.0,
                        }
                    ),
                ],
            }
        )
        action = invoice_tmpl.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        move = wizard.create_move()
        self.assertEqual(move.move_type, "in_invoice")
        self.assertEqual(move.invoice_date, wizard.date)

    def test_account_code_prefix_match_resolves_wizard_line(self):
        prefix_tmpl = self.env["account.move.template"].create(
            {
                "name": "Prefix Template",
                "journal_code": self.journal.code,
                "move_type": "entry",
                "company_id": self.company.id,
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 10,
                            "name": "Prefix debit",
                            "account_code": "TAMT9",
                            "balance": 1.0,
                        }
                    ),
                    Command.create(
                        {
                            "sequence": 20,
                            "name": "Credit",
                            "account_code": self.credit_account.code,
                            "balance": -1.0,
                        }
                    ),
                ],
            }
        )
        action = prefix_tmpl.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        wizard.load_lines()
        self.assertEqual(wizard.line_ids[0].account_id, self.prefix_account)

    def test_payment_template_dispatches_to_create_payment(self):
        payment_tmpl = self.env["account.move.template"].create(
            {
                "name": "Payment Template",
                "journal_code": self.bank_journal.code,
                "move_type": "entry",
                "is_payment": True,
                "payment_type": "outbound",
                "partner_type": "supplier",
                "company_id": self.company.id,
                "partner_id": self.partner.id,
            }
        )
        action = payment_tmpl.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        wizard.amount = 50.0

        result = wizard.create_move()
        self.assertEqual(result._name, "account.payment")
        self.assertEqual(result.amount, 50.0)
        self.assertEqual(result.partner_id, self.partner)
        self.assertEqual(result.journal_id, self.bank_journal)

    def test_the_manifest_declares_what_the_module_uses(self):
        manifest = self.env["ir.module.module"].search(
            [("name", "=", "account_move_template")], limit=1
        )
        declared = set(manifest.dependencies_id.mapped("name"))
        self.assertEqual(declared, {"account", "analytic", "mail", "product", "uom"})

    def test_a_company_less_template_cannot_borrow_a_foreign_journal(self):
        other_company = self.env["res.company"].create({"name": "Foreign Co"})
        self.env["account.journal"].create(
            {
                "name": "Foreign Journal",
                "code": "AMTFJ",
                "type": "general",
                "company_id": other_company.id,
            }
        )

        template_model = self.env["account.move.template"].with_context(
            allowed_company_ids=[self.company.id]
        )
        with self.assertRaises(ValidationError):
            template_model.create(
                {
                    "name": "Borrowed Journal Template",
                    "journal_code": "AMTFJ",
                    "move_type": "entry",
                    "company_id": False,
                    "line_ids": [
                        Command.create(
                            {
                                "sequence": 10,
                                "account_code": self.debit_account.code,
                                "balance": 1.0,
                            }
                        )
                    ],
                }
            )

    def test_a_company_less_template_accepts_a_journal_it_can_reach(self):
        template = self.env["account.move.template"].create(
            {
                "name": "Reachable Journal Template",
                "journal_code": self.journal.code,
                "move_type": "entry",
                "company_id": False,
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 10,
                            "account_code": self.debit_account.code,
                            "balance": 1.0,
                        }
                    )
                ],
            }
        )
        self.assertTrue(template.id)

    def test_writing_a_bogus_account_code_on_a_line_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.template.line_ids.write({"account_code": "NOSUCHCODE"})

    def test_emptying_a_template_from_the_line_side_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.template.line_ids.unlink()

    def test_a_data_file_line_is_validated_too(self):
        template_model = self.env["account.move.template"].with_context(
            install_mode=True
        )
        template = template_model.create(
            {
                "name": "Install Mode Template",
                "journal_code": self.journal.code,
                "move_type": "entry",
                "company_id": self.company.id,
            }
        )
        with self.assertRaises(ValidationError):
            self.env["account.move.template.line"].with_context(
                install_mode=True
            ).create(
                {
                    "template_id": template.id,
                    "sequence": 10,
                    "account_code": "NOSUCHCODE",
                    "balance": 1.0,
                }
            )

    def test_the_account_code_check_costs_one_search_per_company(self):
        template = self.env["account.move.template"].create(
            {
                "name": "Wide Template",
                "journal_code": self.journal.code,
                "move_type": "entry",
                "company_id": self.company.id,
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 10 * (index + 1),
                            "name": f"Line {index}",
                            "account_code": self.debit_account.code,
                            "balance": 1.0,
                        }
                    )
                    for index in range(30)
                ],
            }
        )
        self.env.flush_all()
        self.env.invalidate_all()
        lines = template.line_ids
        lines.mapped("account_code")

        before = self.env.cr.sql_statement_count
        lines._check_account_code_exists()
        self.assertLess(self.env.cr.sql_statement_count - before, 5)

    def test_sections_and_notes_reach_the_generated_move(self):
        self.template.write(
            {
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 5,
                            "display_type": "line_section",
                            "name": "Header section",
                        }
                    ),
                    Command.create(
                        {
                            "sequence": 30,
                            "display_type": "line_note",
                            "name": "Trailing note",
                        }
                    ),
                ],
            }
        )
        action = self.template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        move = wizard.create_move()
        self.assertEqual(len(wizard.line_ids), 4)
        by_type = dict(
            zip(
                move.line_ids.mapped("display_type"),
                move.line_ids.mapped("name"),
                strict=True,
            )
        )
        self.assertEqual(by_type.get("line_section"), "Header section")
        self.assertEqual(by_type.get("line_note"), "Trailing note")
        self.assertEqual(sum(move.line_ids.mapped("balance")), 0.0)

    def test_a_section_does_not_take_a_share_of_the_amount(self):
        template = self._create_two_line_bill_template()
        template.write(
            {
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 5,
                            "display_type": "line_section",
                            "name": "Section",
                        }
                    ),
                ],
            }
        )
        wizard = self._run_with_amount(template, 250.0)

        self.assertEqual(len(wizard.line_ids), 3)
        product_lines = wizard.line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        self.assertEqual(sorted(product_lines.mapped("price_unit")), [125.0, 125.0])
        self.assertEqual(wizard.create_move().amount_untaxed, 250.0)

    def test_payment_term_is_no_longer_an_option(self):
        selection = dict(
            self.env["account.move.template.line"]._fields["display_type"].selection
        )
        self.assertNotIn("payment_term", selection)
        self.assertEqual(set(selection), {"product", "line_section", "line_note"})

    def test_creating_a_move_without_loading_the_lines_loads_them(self):
        wizard = self.env["wizard.account.move.template.create.move"].create(
            {
                "template_id": self.template.id,
                "partner_id": self.partner.id,
                "date": fields.Date.context_today(self.env["account.move"]),
            }
        )
        self.assertFalse(wizard.line_ids)

        move = wizard.create_move()
        self.assertEqual(len(move.line_ids), 2)
        self.assertEqual(sum(move.line_ids.mapped("balance")), 0.0)

    def test_an_emptied_customised_run_is_refused(self):
        action = self.template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        wizard.customize_lines = True
        wizard.line_ids.unlink()

        with self.assertRaises(UserError):
            wizard.create_move()

    def test_a_template_of_only_sections_cannot_be_saved(self):
        with self.assertRaises(ValidationError):
            self.env["account.move.template"].create(
                {
                    "name": "Sections Only Template",
                    "journal_code": self.journal.code,
                    "move_type": "entry",
                    "company_id": self.company.id,
                    "line_ids": [
                        Command.create(
                            {
                                "sequence": 10,
                                "display_type": "line_section",
                                "name": "Just a heading",
                            }
                        )
                    ],
                }
            )

    def test_the_journal_picker_shows_what_the_code_resolves_to(self):
        self.assertEqual(self.template.journal_id, self.journal)

    def test_picking_a_journal_fills_the_code(self):
        other = self.env["account.journal"].create(
            {
                "name": "Second Misc Journal",
                "code": "AMTJ2",
                "type": "general",
                "company_id": self.company.id,
            }
        )
        self.template.journal_id = other
        self.assertEqual(self.template.journal_code, "AMTJ2")
        self.assertEqual(self.template.journal_id, other)

    def test_templates_of_two_companies_resolve_a_shared_code_in_their_own(self):
        companies = self.company | self.env["res.company"].create(
            {"name": "Second Template Company"}
        )
        journals = self.env["account.journal"].create(
            [
                {
                    "name": f"Shared Code {company.name}",
                    "code": "AMTSH",
                    "type": "general",
                    "company_id": company.id,
                }
                for company in companies
            ]
        )
        for company in companies:
            self.env["account.account"].with_company(company).create(
                {
                    "name": f"Shared Code Account {company.name}",
                    "code": "AMTSH1",
                    "account_type": "expense",
                    "company_ids": [Command.link(company.id)],
                }
            )
        templates = self.env["account.move.template"].create(
            [
                {
                    "name": f"Shared Code Template {company.name}",
                    "journal_code": "AMTSH",
                    "company_id": company.id,
                    "line_ids": [
                        Command.create(
                            {"name": "Line", "account_code": "AMTSH1", "balance": 0.0}
                        )
                    ],
                }
                for company in companies
            ]
        )
        templates.invalidate_recordset(["journal_id"])
        self.assertEqual(templates.mapped("journal_id"), journals)
        for template, journal in zip(templates, journals, strict=True):
            self.assertEqual(template.journal_id, journal)

    def test_the_account_picker_shows_what_the_prefix_resolves_to(self):
        for line in self.template.line_ids:
            self.assertTrue(line.account_id)
            self.assertTrue(line.account_id.code.startswith(line.account_code))

    def test_picking_an_account_fills_the_prefix(self):
        line = self.template.line_ids[0]
        line.account_id = self.prefix_account
        self.assertEqual(line.account_code, self.prefix_account.code)
        self.assertEqual(line.account_id, self.prefix_account)

    def test_the_pickers_are_not_carried_by_copy_data(self):
        vals = self.template.copy_data()[0]
        self.assertNotIn("journal_id", vals)

    def test_the_account_picker_costs_one_search_for_the_whole_list(self):
        template = self.env["account.move.template"].create(
            {
                "name": "Picker Cost Template",
                "journal_code": self.journal.code,
                "move_type": "entry",
                "company_id": self.company.id,
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 10 * (index + 1),
                            "name": f"Line {index}",
                            "account_code": self.debit_account.code,
                            "balance": 1.0,
                        }
                    )
                    for index in range(30)
                ],
            }
        )
        self.env.flush_all()
        self.env.invalidate_all()
        lines = template.line_ids
        lines.mapped("account_code")

        before = self.env.cr.sql_statement_count
        lines.mapped("account_id")
        self.assertLess(self.env.cr.sql_statement_count - before, 5)

    def test_an_archived_template_keeps_its_name_reserved(self):
        self.template.active = False
        self.env.flush_all()

        with self.assertRaises(UniqueViolation), self.cr.savepoint():
            self.env["account.move.template"].create(
                {
                    "name": "Test Journal Template",
                    "journal_code": self.journal.code,
                    "move_type": "entry",
                    "company_id": self.company.id,
                    "line_ids": [
                        Command.create(
                            {
                                "sequence": 10,
                                "account_code": self.debit_account.code,
                                "balance": 1.0,
                            }
                        )
                    ],
                }
            )
            self.env.flush_all()

    def _create_payment_template(self, name="Payment Template"):
        return self.env["account.move.template"].create(
            {
                "name": name,
                "journal_code": self.bank_journal.code,
                "move_type": "entry",
                "is_payment": True,
                "payment_type": "outbound",
                "partner_type": "supplier",
                "company_id": self.company.id,
                "partner_id": self.partner.id,
            }
        )

    def test_a_payment_run_leaves_posting_to_its_caller(self):
        template = self._create_payment_template("Draft Payment Template")
        action = template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        wizard.amount = 50.0

        payment = wizard.create_move()
        self.assertEqual(payment._name, "account.payment")
        self.assertEqual(payment.state, "draft")
        self.assertFalse(payment.move_id, "no journal entry behind the caller's back")

        payment.action_post()
        self.assertEqual(payment.move_id.state, "posted")

    def test_a_payment_run_without_an_amount_is_refused(self):
        template = self._create_payment_template("Amountless Payment Template")
        action = template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        self.assertFalse(wizard.amount)

        with self.assertRaises(UserError):
            wizard.create_move()

    def _create_bill_template_with_split(self, price_unit=100.0):
        return self.env["account.move.template"].create(
            {
                "name": "Amount Split Template",
                "journal_code": self.purchase_journal.code,
                "move_type": "in_invoice",
                "company_id": self.company.id,
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 10,
                            "name": "Bill line",
                            "account_code": self.debit_account.code,
                            "distribution_method": "split",
                            "quantity": 1.0,
                            "price_unit": price_unit,
                        }
                    ),
                ],
            }
        )

    def _create_bill_template_with_collapse(self, price_unit=100.0):
        return self.env["account.move.template"].create(
            {
                "name": "Amount Collapse Template",
                "journal_code": self.purchase_journal.code,
                "move_type": "in_invoice",
                "company_id": self.company.id,
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 10,
                            "name": "Bill line",
                            "account_code": self.debit_account.code,
                            "quantity": 1.0,
                            "price_unit": price_unit,
                        }
                    ),
                ],
            }
        )

    def _create_two_line_bill_template(self, method="collapse", price_unit=100.0):
        return self.env["account.move.template"].create(
            {
                "name": f"Two Line Bill {method}",
                "journal_code": self.purchase_journal.code,
                "move_type": "in_invoice",
                "company_id": self.company.id,
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 10 + index * 10,
                            "name": f"Bill line {index}",
                            "account_code": self.debit_account.code,
                            "distribution_method": method,
                            "quantity": 1.0,
                            "price_unit": price_unit,
                        }
                    )
                    for index in range(2)
                ],
            }
        )

    def _run_with_amount(self, template, amount):
        action = template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        wizard.amount = amount
        wizard.load_lines()
        return wizard

    def test_amount_is_distributed_across_the_product_lines(self):
        wizard = self._run_with_amount(self._create_two_line_bill_template(), 250.0)

        self.assertEqual(len(wizard.line_ids), 2)
        self.assertEqual(sorted(wizard.line_ids.mapped("price_unit")), [125.0, 125.0])
        self.assertEqual(wizard.create_move().amount_untaxed, 250.0)

    def test_an_odd_amount_keeps_its_residue_on_one_line(self):
        wizard = self._run_with_amount(self._create_two_line_bill_template(), 100.01)

        self.assertEqual(len(wizard.line_ids), 2)
        self.assertEqual(sorted(wizard.line_ids.mapped("price_unit")), [50.0, 50.01])
        self.assertEqual(wizard.create_move().amount_untaxed, 100.01)

    def test_a_single_line_template_still_takes_the_whole_amount(self):
        wizard = self._run_with_amount(
            self._create_bill_template_with_collapse(price_unit=100.0), 250.0
        )

        self.assertEqual(len(wizard.line_ids), 1)
        self.assertEqual(wizard.create_move().amount_untaxed, 250.0)

    def test_the_split_adjustment_carries_the_taxes_of_its_units(self):
        template = self._create_bill_template_with_split(price_unit=100.0)
        template.line_ids.tax_ids = [Command.set(self.purchase_tax.ids)]
        wizard = self._run_with_amount(template, 250.0)

        main = wizard.line_ids.filtered(lambda line: line.quantity == 2)
        adjustment = wizard.line_ids - main
        self.assertEqual(adjustment.tax_ids, self.purchase_tax)

        move = wizard.create_move()
        self.assertEqual(move.amount_untaxed, 250.0)
        self.assertEqual(move.amount_tax, 40.0)

    def test_split_and_collapse_agree_on_the_tax_of_one_amount(self):
        totals = []
        for method in ("split", "collapse"):
            template = self.env["account.move.template"].create(
                {
                    "name": f"Tax Agreement {method}",
                    "journal_code": self.purchase_journal.code,
                    "move_type": "in_invoice",
                    "company_id": self.company.id,
                    "partner_id": self.partner.id,
                    "line_ids": [
                        Command.create(
                            {
                                "sequence": 10,
                                "name": "Bill line",
                                "account_code": self.debit_account.code,
                                "distribution_method": method,
                                "quantity": 1.0,
                                "price_unit": 100.0,
                                "tax_ids": [Command.set(self.purchase_tax.ids)],
                            }
                        )
                    ],
                }
            )
            move = self._run_with_amount(template, 250.0).create_move()
            totals.append((move.amount_untaxed, move.amount_tax))

        self.assertEqual(totals[0], totals[1])
        self.assertEqual(totals[0], (250.0, 40.0))

    def test_a_vendor_bill_is_not_priced_from_the_sale_price(self):
        product = self.env["product.product"].create(
            {"name": "Cost-less Product", "standard_price": 0.0, "list_price": 777.0}
        )
        template = self._create_bill_template_with_collapse(price_unit=0.0)
        template.line_ids.write({"product_id": product.id, "price_unit": 0.0})

        action = template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        wizard.load_lines()
        self.assertNotEqual(wizard.line_ids.price_unit, 777.0)
        self.assertEqual(wizard.line_ids.price_unit, 1.0)

    def test_split_amount_into_main_and_adjustment(self):
        template = self._create_bill_template_with_split(price_unit=100.0)
        action = template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        wizard.amount = 250.0
        wizard.load_lines()

        self.assertEqual(len(wizard.line_ids), 2)
        main = wizard.line_ids.filtered(lambda line: line.quantity == 2)
        adj = wizard.line_ids - main
        self.assertEqual(len(main), 1)
        self.assertEqual(main.price_unit, 100.0)
        self.assertEqual(adj.quantity, 1)
        self.assertEqual(adj.price_unit, 50.0)
        self.assertEqual(
            adj.tax_ids, main.tax_ids, "adjustment line follows the units it completes"
        )
        self.assertEqual(adj.name, main.name, "the CFDI shows the same concept")

    def test_split_amount_below_price_unit_creates_single_line(self):
        template = self._create_bill_template_with_split(price_unit=100.0)
        action = template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        wizard.amount = 30.0
        wizard.load_lines()

        self.assertEqual(len(wizard.line_ids), 1)
        self.assertEqual(wizard.line_ids.quantity, 1)
        self.assertEqual(wizard.line_ids.price_unit, 30.0)

    def test_split_amount_exact_multiple_has_no_adjustment(self):
        template = self._create_bill_template_with_split(price_unit=100.0)
        action = template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        wizard.amount = 200.0
        wizard.load_lines()

        self.assertEqual(len(wizard.line_ids), 1)
        self.assertEqual(wizard.line_ids.quantity, 2)

    def test_collapse_default_with_bug_repro_amounts(self):
        template = self._create_bill_template_with_collapse(price_unit=10.0)
        action = template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        wizard.amount = 100000.0
        wizard.load_lines()

        self.assertEqual(len(wizard.line_ids), 1)
        self.assertEqual(wizard.line_ids.quantity, 1)
        self.assertEqual(wizard.line_ids.price_unit, 100000.0)

    def test_collapse_with_amount_below_price_unit(self):
        template = self._create_bill_template_with_collapse(price_unit=100.0)
        action = template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        wizard.amount = 30.0
        wizard.load_lines()

        self.assertEqual(len(wizard.line_ids), 1)
        self.assertEqual(wizard.line_ids.quantity, 1)
        self.assertEqual(wizard.line_ids.price_unit, 30.0)

    def test_collapse_amount_equals_price_unit(self):
        template = self._create_bill_template_with_collapse(price_unit=200.0)
        action = template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        wizard.amount = 200.0
        wizard.load_lines()

        self.assertEqual(len(wizard.line_ids), 1)
        self.assertEqual(wizard.line_ids.quantity, 1)
        self.assertEqual(wizard.line_ids.price_unit, 200.0)

    def test_customize_lines_blocks_reload_on_amount_change(self):
        template = self._create_bill_template_with_collapse()
        action = template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        with Form(wizard) as form:
            form.customize_lines = True
            with form.line_ids.edit(0) as line:
                line.price_unit = 42.0
        self.assertEqual(wizard.line_ids.price_unit, 42.0)

        with Form(wizard) as form:
            form.amount = 999.0
        self.assertEqual(
            wizard.line_ids.price_unit,
            42.0,
            "customize_lines=True must preserve manually edited wizard lines",
        )
        self.assertEqual(wizard.create_move().amount_untaxed, 42.0)

    def test_a_foreign_company_template_resolves_its_own_accounts(self):
        account = (
            self.env["account.account"]
            .with_company(self.other_company)
            .create(
                {
                    "name": "AMT Other Expense",
                    "code": "TAMTX1",
                    "account_type": "expense",
                    "company_ids": [Command.link(self.other_company.id)],
                }
            )
        )
        # `code` is company-dependent: it does not exist in this company's
        # namespace at all, which is what used to make the template
        # unresolvable from here.
        self.assertFalse(account.with_company(self.company).code)
        self.assertEqual(account.with_company(self.other_company).code, "TAMTX1")

        template = self.env["account.move.template"].create(
            {
                "name": "Foreign Company Template",
                "journal_code": self.other_journal.code,
                "move_type": "in_invoice",
                "company_id": self.other_company.id,
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 10,
                            "name": "Bill line",
                            "account_code": "TAMTX1",
                            "quantity": 1.0,
                            "price_unit": 5.0,
                        }
                    )
                ],
            }
        )
        self.assertEqual(template.line_ids.account_id, account)

        wizard = self.env["wizard.account.move.template.create.move"].create(
            {
                "template_id": template.id,
                "date": fields.Date.context_today(self.env.user),
                "partner_id": self.partner.id,
            }
        )
        wizard.load_lines()
        self.assertEqual(wizard.line_ids.account_id, account)

    def test_the_tax_picker_is_scoped_to_the_templates_company(self):
        # `tax_ids` carries `check_company=True`, so a picker that offers
        # every tax of the right `type_tax_use` offers taxes the save
        # refuses with a company-crossover error.
        arch = etree.fromstring(
            self.env["account.move.template"].get_view(view_type="form")["arch"]
        )
        domains = [
            node.get("domain")
            for node in arch.iter("field")
            if node.get("name") == "tax_ids"
        ]
        self.assertTrue(domains)
        for domain in domains:
            self.assertIn("company_ids", domain or "")

    def test_a_foreign_tax_on_a_line_is_refused(self):
        with self.assertRaises(UserError):
            self.env["account.move.template"].create(
                {
                    "name": "Foreign Tax Template",
                    "journal_code": self.purchase_journal.code,
                    "move_type": "in_invoice",
                    "company_id": self.company.id,
                    "partner_id": self.partner.id,
                    "line_ids": [
                        Command.create(
                            {
                                "sequence": 10,
                                "account_code": self.debit_account.code,
                                "tax_ids": [Command.set(self.other_purchase_tax.ids)],
                            }
                        )
                    ],
                }
            )

    def test_lines_created_without_a_sequence_do_not_collide(self):
        template = self.env["account.move.template"].create(
            {
                "name": "Sequenceless Template",
                "journal_code": self.journal.code,
                "move_type": "entry",
                "company_id": self.company.id,
                "line_ids": [
                    Command.create(
                        {"account_code": self.debit_account.code, "balance": 100.0}
                    ),
                    Command.create(
                        {"account_code": self.credit_account.code, "balance": -100.0}
                    ),
                ],
            }
        )
        self.assertEqual(len(template.line_ids), 2)
        self.assertEqual(
            len(set(template.line_ids.mapped("sequence"))),
            2,
            "two lines created together must not share a sequence",
        )

    def test_an_explicit_sequence_is_still_honoured(self):
        self.assertEqual(self.template.line_ids.mapped("sequence"), [10, 20])
        added = self.env["account.move.template.line"].create(
            {
                "template_id": self.template.id,
                "account_code": self.debit_account.code,
                "sequence": 99,
                "balance": 0.0,
            }
        )
        self.assertEqual(added.sequence, 99)

    def test_a_line_added_later_continues_the_numbering(self):
        added = self.env["account.move.template.line"].create(
            {
                "template_id": self.template.id,
                "account_code": self.debit_account.code,
                "balance": 0.0,
            }
        )
        self.assertGreater(added.sequence, 20)

    def test_moving_a_template_to_a_company_revalidates_its_lines(self):
        # `company_id` is a stored related the code resolution keys on, so
        # a company switch has to re-run the check the codes were accepted
        # by -- otherwise the template silently keeps pointing at accounts
        # the new company does not have.
        self.env["account.journal"].create(
            {
                "name": "AMT Other Misc Journal",
                "code": "TAMTM",
                "type": "general",
                "company_id": self.other_company.id,
            }
        )
        with self.assertRaises(ValidationError):
            self.template.write(
                {"company_id": self.other_company.id, "journal_code": "TAMTM"}
            )

    def test_an_accounting_manager_can_run_a_template(self):
        # `group_account_manager` implies only `group_account_invoice`, so
        # it does not inherit the accountant's grant on the run wizard: a
        # user who can create and edit templates could not run one.
        manager = self.env["res.users"].create(
            {
                "name": "AMT Manager",
                "login": "amt_manager",
                "company_id": self.company.id,
                "company_ids": [Command.set(self.company.ids)],
                "group_ids": [
                    Command.set(
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("account.group_account_manager").id,
                        ]
                    )
                ],
            }
        )
        action = self.template.with_user(manager).action_move_template_run()
        wizard = (
            self.env["wizard.account.move.template.create.move"]
            .with_user(manager)
            .browse(action["res_id"])
        )
        self.assertEqual(len(wizard.create_move().line_ids), 2)

    def test_a_payment_run_keeps_the_reference_it_was_given(self):
        template = self.env["account.move.template"].create(
            {
                "name": "Referenced Payment Template",
                "journal_code": self.bank_journal.code,
                "move_type": "entry",
                "is_payment": True,
                "payment_type": "outbound",
                "partner_type": "supplier",
                "company_id": self.company.id,
                "partner_id": self.partner.id,
            }
        )
        wizard = self.env["wizard.account.move.template.create.move"].create(
            {
                "template_id": template.id,
                "date": fields.Date.context_today(self.env.user),
                "partner_id": self.partner.id,
                "amount": 50.0,
                "ref": "AMT-REF-11",
            }
        )
        payment = wizard.create_move()
        self.assertEqual(payment.memo, "AMT-REF-11")

    def test_the_payment_branch_has_an_extension_hook(self):
        # `_prepare_move_vals` is the move branch's override point and
        # downstream uses it; the payment branch needs the mirror, or a
        # downstream module has to re-implement `create_payment` whole.
        model = self.env["wizard.account.move.template.create.move"]
        self.assertTrue(hasattr(model, "_prepare_move_vals"))
        self.assertTrue(hasattr(model, "_prepare_payment_vals"))

    def test_a_template_lines_unit_of_measure_reaches_the_move(self):
        dozens = self.env.ref("uom.product_uom_dozen", raise_if_not_found=False)
        if not dozens:
            self.skipTest("uom.product_uom_dozen is not available")
        product = self.env["product.product"].create(
            {
                "name": "AMT UoM Product",
                "purchase_ok": True,
                "standard_price": 3.0,
                "supplier_taxes_id": [Command.set(self.purchase_tax.ids)],
            }
        )
        template = self.env["account.move.template"].create(
            {
                "name": "UoM Template",
                "journal_code": self.purchase_journal.code,
                "move_type": "in_invoice",
                "company_id": self.company.id,
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 10,
                            "name": "Bill line",
                            "account_code": self.debit_account.code,
                            "product_id": product.id,
                            "product_uom_id": dozens.id,
                            "quantity": 2.0,
                        }
                    )
                ],
            }
        )
        self.assertEqual(template.line_ids.product_uom_id, dozens)

        wizard = self.env["wizard.account.move.template.create.move"].create(
            {
                "template_id": template.id,
                "date": fields.Date.context_today(self.env.user),
                "partner_id": self.partner.id,
            }
        )
        wizard.load_lines()
        self.assertEqual(wizard.line_ids.product_uom_id, dozens)

        move = wizard.create_move()
        self.assertEqual(move.invoice_line_ids.product_uom_id, dozens)

    def test_a_wizard_line_without_a_unit_lets_the_move_compute_one(self):
        # The move line's `product_uom_id` is a stored, editable compute. Passing
        # the key as False on create suppresses it, so an unset wizard line must
        # omit the key rather than write an empty value.
        product = self.env["product.product"].create(
            {
                "name": "AMT Uomless Product",
                "purchase_ok": True,
                "standard_price": 5.0,
                "supplier_taxes_id": [Command.set(self.purchase_tax.ids)],
            }
        )
        template = self.env["account.move.template"].create(
            {
                "name": "Uomless Template",
                "journal_code": self.purchase_journal.code,
                "move_type": "in_invoice",
                "company_id": self.company.id,
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 10,
                            "name": "Bill line",
                            "account_code": self.debit_account.code,
                            "product_id": product.id,
                        }
                    )
                ],
            }
        )
        wizard = self.env["wizard.account.move.template.create.move"].create(
            {
                "template_id": template.id,
                "date": fields.Date.context_today(self.env.user),
                "partner_id": self.partner.id,
            }
        )
        wizard.load_lines()
        wizard.line_ids.product_uom_id = False

        move = wizard.create_move()
        self.assertEqual(move.invoice_line_ids.product_uom_id, product.uom_id)

    def test_an_entry_template_refuses_an_amount_it_would_ignore(self):
        action = self.template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        wizard.amount = 777.0
        wizard.load_lines()

        with self.assertRaises(UserError):
            wizard.create_move()

    def test_an_entry_template_still_runs_without_an_amount(self):
        action = self.template.action_move_template_run()
        wizard = self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )
        move = wizard.create_move()
        self.assertEqual(sum(move.line_ids.mapped("debit")), 100.0)

    def test_a_payment_template_needs_both_of_its_types(self):
        with self.assertRaises(ValidationError):
            self.env["account.move.template"].create(
                {
                    "name": "Typeless Payment Template",
                    "journal_code": self.bank_journal.code,
                    "move_type": "entry",
                    "is_payment": True,
                    "company_id": self.company.id,
                }
            )

    def test_the_journal_picker_follows_the_active_companies(self):
        both = [self.company.id, self.other_company.id]
        template = (
            self.env["account.move.template"]
            .with_context(allowed_company_ids=both)
            .create(
                {
                    "name": "Company-less Picker Template",
                    "journal_code": self.other_journal.code,
                    "move_type": "entry",
                    "company_id": False,
                    "line_ids": [
                        Command.create(
                            {
                                "sequence": 10,
                                "account_code": self.debit_account.code,
                                "balance": 1.0,
                            }
                        )
                    ],
                }
            )
        )
        wide = self.env["account.move.template"].with_context(allowed_company_ids=both)
        self.assertEqual(wide.browse(template.id).journal_id, self.other_journal)

        # The compute reads `env.companies`, so narrowing the active
        # companies has to produce a different answer -- not the one left
        # in the cache by the wider read.
        narrow = self.env["account.move.template"].with_context(
            allowed_company_ids=[self.company.id]
        )
        self.assertFalse(narrow.browse(template.id).journal_id)

    def test_a_bill_is_priced_with_the_target_company_cost(self):
        self.env["account.account"].with_company(self.other_company).create(
            {
                "name": "AMT Other Cost Expense",
                "code": "TAMTX2",
                "account_type": "expense",
                "company_ids": [Command.link(self.other_company.id)],
            }
        )
        product = self.env["product.product"].create(
            {"name": "AMT Cost Probe", "purchase_ok": True}
        )
        product.with_company(self.company).standard_price = 11.0
        product.with_company(self.other_company).standard_price = 99.0

        template = self.env["account.move.template"].create(
            {
                "name": "Foreign Company Cost Template",
                "journal_code": self.other_journal.code,
                "move_type": "in_invoice",
                "company_id": self.other_company.id,
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 10,
                            "name": "Bill line",
                            "account_code": "TAMTX2",
                            "product_id": product.id,
                            "quantity": 1.0,
                        }
                    )
                ],
            }
        )
        wizard = self.env["wizard.account.move.template.create.move"].create(
            {
                "template_id": template.id,
                "date": fields.Date.context_today(self.env.user),
                "partner_id": self.partner.id,
            }
        )
        wizard.load_lines()
        self.assertEqual(wizard.line_ids.price_unit, 99.0)

    def test_an_account_code_prefix_is_never_a_sql_wildcard(self):
        self.env["account.account"].create(
            {
                "name": "AMT Wildcard Account",
                "code": "TAMTW1Z",
                "account_type": "expense",
                "company_ids": [Command.link(self.company.id)],
            }
        )
        resolved = self.env["account.move.template.line"]._resolve_codes_in_company(
            ["TAMTW_Z"],
            self.company,
        )
        self.assertEqual(resolved, {})

    def test_a_products_foreign_taxes_never_reach_the_move(self):
        product = self.env["product.product"].create(
            {
                "name": "AMT Two-Company Product",
                "purchase_ok": True,
                "standard_price": 25.0,
                "supplier_taxes_id": [
                    Command.set((self.purchase_tax | self.other_purchase_tax).ids)
                ],
            }
        )
        template = self.env["account.move.template"].create(
            {
                "name": "Two-Company Tax Template",
                "journal_code": self.purchase_journal.code,
                "move_type": "in_invoice",
                "company_id": self.company.id,
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 10,
                            "name": "Bill line",
                            "account_code": self.debit_account.code,
                            "product_id": product.id,
                            "quantity": 1.0,
                        }
                    )
                ],
            }
        )
        wizard = self.env["wizard.account.move.template.create.move"].create(
            {
                "template_id": template.id,
                "date": fields.Date.context_today(self.env.user),
                "partner_id": self.partner.id,
            }
        )
        wizard.load_lines()
        self.assertEqual(wizard.line_ids.tax_ids, self.purchase_tax)

        move = wizard.create_move()
        self.assertEqual(move.invoice_line_ids.tax_ids, self.purchase_tax)

    def _open_run(self, template):
        action = template.action_move_template_run()
        return self.env["wizard.account.move.template.create.move"].browse(
            action["res_id"]
        )

    def test_a_partner_changed_in_the_dialog_reaches_every_line(self):
        wizard = self._open_run(self.template)
        wizard.partner_id = self.other_partner

        move = wizard.create_move()
        self.assertEqual(move.partner_id, self.other_partner)
        self.assertEqual(move.line_ids.partner_id, self.other_partner)

    def test_a_line_keeps_the_partner_its_template_line_names(self):
        self.template.line_ids[0].partner_id = self.other_partner
        wizard = self._open_run(self.template)

        move = wizard.create_move()
        debit, credit = move.line_ids.sorted("balance", reverse=True)
        self.assertEqual(debit.partner_id, self.other_partner)
        self.assertEqual(credit.partner_id, self.partner)

    def test_a_target_company_changed_in_the_dialog_rebooks_the_lines(self):
        template = self._create_bill_template_with_collapse()
        self.env["account.journal"].create(
            {
                "name": "AMT Other Same-Code Journal",
                "code": self.purchase_journal.code,
                "type": "purchase",
                "company_id": self.other_company.id,
            }
        )
        other_account = (
            self.env["account.account"]
            .with_company(self.other_company)
            .create(
                {
                    "name": "AMT Other Same-Code Expense",
                    "code": self.debit_account.code,
                    "account_type": "expense",
                    "company_ids": [Command.link(self.other_company.id)],
                }
            )
        )
        self.partner.with_company(self.other_company).property_account_payable_id = (
            self.env["account.account"]
            .with_company(self.other_company)
            .create(
                {
                    "name": "AMT Other Payable",
                    "code": "TAMTPAY",
                    "account_type": "liability_payable",
                    "reconcile": True,
                    "company_ids": [Command.link(self.other_company.id)],
                }
            )
        )
        wizard = self._open_run(template)
        wizard.load_lines()
        self.assertEqual(wizard.line_ids.account_id, self.debit_account)

        wizard.multicompany_id = self.other_company
        move = wizard.create_move()
        self.assertEqual(move.company_id, self.other_company)
        self.assertEqual(move.invoice_line_ids.account_id, other_account)

    def test_an_exact_multiple_of_the_price_is_split_without_adjustment(self):
        for price_unit, amount, units in ((23.1, 69.3, 3), (0.23, 1.15, 5)):
            with self.subTest(price_unit=price_unit, amount=amount):
                template = self._create_bill_template_with_split(price_unit)
                wizard = self._run_with_amount(template, amount)
                self.assertEqual(wizard.line_ids.mapped("quantity"), [units])
                self.assertEqual(wizard.line_ids.mapped("price_unit"), [price_unit])
                template.unlink()

    def test_a_split_remainder_is_rounded_to_the_currency(self):
        template = self._create_bill_template_with_split(23.1)
        wizard = self._run_with_amount(template, 70.0)
        self.assertEqual(wizard.line_ids.mapped("quantity"), [3, 1])
        self.assertEqual(wizard.line_ids.mapped("price_unit"), [23.1, 0.7])

    def test_a_negative_collapse_price_still_takes_the_amount(self):
        template = self._create_bill_template_with_collapse(price_unit=-10.0)
        wizard = self._run_with_amount(template, 500.0)
        self.assertEqual(wizard.line_ids.quantity, 1)
        self.assertEqual(wizard.line_ids.price_unit, 500.0)

    def test_the_created_document_carries_no_default_move_type(self):
        template = self._create_bill_template_with_collapse()
        move = self._open_run(template).create_move()
        self.assertNotIn("default_move_type", move.env.context)
        self.assertEqual(move.env.company, self.company)

    def test_turning_the_last_product_line_into_a_section_is_rejected(self):
        template = self._create_bill_template_with_collapse()
        with self.assertRaises(ValidationError):
            template.line_ids.display_type = "line_section"

    def test_moving_the_last_product_line_away_is_rejected(self):
        source = self._create_bill_template_with_collapse()
        target = self._create_two_line_bill_template()
        with self.assertRaises(ValidationError):
            source.line_ids.write({"template_id": target.id, "sequence": 99})

    def test_the_run_resolves_every_account_code_in_one_search(self):
        template = self._create_two_line_bill_template()
        template.line_ids[1].account_code = self.prefix_account.code
        wizard = self._open_run(template)

        line_model = self.env.registry["account.move.template.line"]
        resolve = line_model._resolve_codes_in_company
        with patch.object(
            line_model,
            "_resolve_codes_in_company",
            autospec=True,
            side_effect=resolve,
        ) as lookup:
            wizard.load_lines()
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(
            wizard.line_ids.account_id,
            self.debit_account | self.prefix_account,
        )

    def test_a_payment_template_shows_no_payment_terms(self):
        arch = etree.fromstring(
            self.env["account.move.template"].get_view(view_type="form")["arch"]
        )
        payment_group = arch.find(".//group[@name='payment_config']")
        names = {node.get("name") for node in payment_group.iter("field")}
        self.assertEqual(names, {"payment_type", "partner_type"})

    def test_a_template_on_the_wrong_kind_of_journal_is_refused(self):
        bill_line = Command.create(
            {
                "sequence": 10,
                "name": "Line",
                "account_code": self.debit_account.code,
                "price_unit": 10.0,
            }
        )
        cases = (
            ("out_invoice", False, self.purchase_journal),
            ("in_refund", False, self.journal),
            ("entry", True, self.purchase_journal),
        )
        for move_type, is_payment, journal in cases:
            with (
                self.subTest(move_type=move_type, is_payment=is_payment),
                self.assertRaises(ValidationError),
            ):
                self.env["account.move.template"].create(
                    {
                        "name": f"Wrong journal {move_type} {is_payment}",
                        "journal_code": journal.code,
                        "move_type": move_type,
                        "is_payment": is_payment,
                        "payment_type": "inbound",
                        "partner_type": "customer",
                        "company_id": self.company.id,
                        "line_ids": [bill_line],
                    }
                )

    def test_an_entry_may_use_any_kind_of_journal(self):
        template = self.env["account.move.template"].create(
            {
                "name": "Entry on a purchase journal",
                "journal_code": self.purchase_journal.code,
                "move_type": "entry",
                "company_id": self.company.id,
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 10,
                            "name": "Debit",
                            "account_code": self.debit_account.code,
                            "balance": 1.0,
                        }
                    ),
                    Command.create(
                        {
                            "sequence": 20,
                            "name": "Credit",
                            "account_code": self.credit_account.code,
                            "balance": -1.0,
                        }
                    ),
                ],
            }
        )
        self.assertEqual(
            self._open_run(template).create_move().journal_id,
            self.purchase_journal,
        )

    def test_changing_the_move_type_revalidates_the_journal(self):
        template = self._create_bill_template_with_collapse()
        with self.assertRaises(ValidationError):
            template.move_type = "out_invoice"

    def test_a_run_never_books_on_a_journal_of_the_wrong_kind(self):
        template = self._create_bill_template_with_collapse()
        template.company_id = False
        self.env["account.journal"].create(
            {
                "name": "AMT Same-Code Sale Journal",
                "code": self.purchase_journal.code,
                "type": "sale",
                "company_id": self.other_company.id,
            }
        )
        wizard = self._open_run(template)
        wizard.multicompany_id = self.other_company
        with self.assertRaisesRegex(UserError, self.purchase_journal.code):
            wizard.create_move()

    def test_the_only_product_line_can_be_replaced_in_one_save(self):
        new_line = {
            "sequence": 20,
            "name": "Replacement",
            "account_code": self.debit_account.code,
            "price_unit": 7.0,
        }
        for label, commands in (
            (
                "delete",
                lambda line: [Command.delete(line.id), Command.create(new_line)],
            ),
            (
                "section",
                lambda line: [
                    Command.update(line.id, {"display_type": "line_section"}),
                    Command.create(new_line),
                ],
            ),
        ):
            with self.subTest(label):
                template = self._create_bill_template_with_collapse()
                template.write({"line_ids": commands(template.line_ids)})
                self.assertEqual(
                    template.line_ids.filtered(
                        lambda line: line.display_type == "product"
                    ).name,
                    "Replacement",
                )
                template.unlink()

    def test_emptying_a_template_in_one_save_is_still_rejected(self):
        for label, commands in (
            ("delete", lambda line: [Command.delete(line.id)]),
            (
                "section",
                lambda line: [Command.update(line.id, {"display_type": "line_note"})],
            ),
        ):
            with self.subTest(label):
                template = self._create_bill_template_with_collapse()
                with self.assertRaises(ValidationError):
                    template.write({"line_ids": commands(template.line_ids)})
                template.unlink()

    def test_another_template_cannot_take_the_only_product_line(self):
        source = self._create_bill_template_with_collapse()
        target = self._create_two_line_bill_template()
        source.line_ids.sequence = 99
        with self.assertRaises(ValidationError):
            target.write({"line_ids": [Command.link(source.line_ids.id)]})

    def test_a_negative_or_undefined_amount_is_refused(self):
        template = self._create_bill_template_with_collapse()
        for amount in (-1.0, float("nan"), float("inf")):
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                self.env["wizard.account.move.template.create.move"].create(
                    {"template_id": template.id, "amount": amount},
                )

    def test_a_split_line_without_a_real_price_collapses(self):
        template = self._create_bill_template_with_split(price_unit=0.0)
        wizard = self._run_with_amount(template, 1500.0)
        self.assertEqual(wizard.line_ids.mapped("quantity"), [1])
        self.assertEqual(wizard.line_ids.mapped("price_unit"), [1500.0])

    def test_an_entry_carries_no_payment_term(self):
        self.template.invoice_payment_term_id = self.env["account.payment.term"].search(
            [], limit=1
        )
        self.assertTrue(self.template.invoice_payment_term_id)
        move = self._open_run(self.template).create_move()
        self.assertFalse(move.invoice_payment_term_id)

    def test_a_drawn_product_brings_its_own_unit_of_measure(self):
        # The template line's unit describes the product it pins. A product an
        # extension draws in its place carries its own unit, and an empty unit
        # sends an empty `ClaveUnidad` to the SAT (CFDI40165).
        dozens = self.env.ref("uom.product_uom_dozen")
        drawn = self.env["product.product"].create(
            {
                "name": "AMT Drawn Product",
                "purchase_ok": True,
                "standard_price": 4.0,
                "uom_id": dozens.id,
            }
        )
        template = self._create_bill_template_with_collapse()
        wizard_model = self.env.registry["wizard.account.move.template.create.move"]
        with patch.object(
            wizard_model,
            "_get_template_line_product",
            autospec=True,
            return_value=drawn,
        ):
            move = self._open_run(template).create_move()
        self.assertEqual(move.invoice_line_ids.product_id, drawn)
        self.assertEqual(move.invoice_line_ids.product_uom_id, dozens)
