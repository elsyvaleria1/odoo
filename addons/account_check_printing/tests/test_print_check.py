import math

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools.misc import NON_BREAKING_SPACE

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.account_check_printing.models.account_payment import INV_LINES_PER_STUB


@tagged("post_install", "-at_install")
class TestPrintCheck(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.other_currency = cls.setup_other_currency("EUR")

        bank_journal = cls.company_data["default_journal_bank"]

        cls.payment_channel_check = bank_journal.outbound_payment_channel_ids.filtered(
            lambda l: l.code == "check_printing"
        )
        cls.payment_channel_check.payment_account_id = (
            cls.inbound_payment_channel.payment_account_id
        )

    def test_in_invoice_check_manual_sequencing(self):
        nb_invoices_to_test = INV_LINES_PER_STUB + 1

        self.company_data["default_journal_bank"].write(
            {
                "check_manual_sequencing": True,
                "check_next_number": "00042",
            }
        )

        in_invoices = self.env["account.move"].create(
            [
                {
                    "move_type": "in_invoice",
                    "partner_id": self.partner_a.id,
                    "date": "2017-01-01",
                    "invoice_date": "2017-01-01",
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.product_a.id,
                                "price_unit": 100.0,
                                "tax_ids": [],
                            }
                        )
                    ],
                }
                for i in range(nb_invoices_to_test)
            ]
        )
        in_invoices.action_post()

        payment = (
            self.env["wizard.account.move.line.pay"]
            .with_context(active_model="account.move", active_ids=in_invoices.ids)
            .create(
                {
                    "group_payment": True,
                    "payment_channel_id": self.payment_channel_check.id,
                }
            )
            ._create_payments()
        )

        self.assertRecordValues(
            payment,
            [
                {
                    "payment_channel_id": self.payment_channel_check.id,
                    "check_amount_in_words": payment.currency_id.amount_to_text(
                        100.0 * nb_invoices_to_test
                    ),
                    "check_number": "00042",
                }
            ],
        )

        self.company_data[
            "company"
        ].account_config_id.account_check_printing_multi_stub = True
        report_pages = payment._prepare_check_pages()
        self.assertEqual(
            len(report_pages), math.ceil(len(in_invoices) / INV_LINES_PER_STUB)
        )

        self.company_data[
            "company"
        ].account_config_id.account_check_printing_multi_stub = False
        report_pages = payment._prepare_check_pages()
        self.assertEqual(len(report_pages), 1)

    def test_out_refund_check_manual_sequencing(self):
        nb_invoices_to_test = INV_LINES_PER_STUB + 1

        self.company_data["default_journal_bank"].write(
            {
                "check_manual_sequencing": True,
                "check_next_number": "00042",
            }
        )

        out_refunds = self.env["account.move"].create(
            [
                {
                    "move_type": "out_refund",
                    "partner_id": self.partner_a.id,
                    "date": "2017-01-01",
                    "invoice_date": "2017-01-01",
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.product_a.id,
                                "price_unit": 100.0,
                                "tax_ids": [],
                            }
                        )
                    ],
                }
                for i in range(nb_invoices_to_test)
            ]
        )
        out_refunds.action_post()

        payment = (
            self.env["wizard.account.move.line.pay"]
            .with_context(active_model="account.move", active_ids=out_refunds.ids)
            .create(
                {
                    "group_payment": True,
                    "payment_channel_id": self.payment_channel_check.id,
                }
            )
            ._create_payments()
        )

        self.assertRecordValues(
            payment,
            [
                {
                    "payment_channel_id": self.payment_channel_check.id,
                    "check_amount_in_words": payment.currency_id.amount_to_text(
                        100.0 * nb_invoices_to_test
                    ),
                    "check_number": "00042",
                }
            ],
        )

        self.company_data[
            "company"
        ].account_config_id.account_check_printing_multi_stub = True
        report_pages = payment._prepare_check_pages()
        self.assertEqual(
            len(report_pages), math.ceil(len(out_refunds) / INV_LINES_PER_STUB)
        )

        self.company_data[
            "company"
        ].account_config_id.account_check_printing_multi_stub = False
        report_pages = payment._prepare_check_pages()
        self.assertEqual(len(report_pages), 1)

    def test_multi_currency_stub_lines(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "date": "2016-01-01",
                "invoice_date": "2016-01-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "price_unit": 150.0,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        invoice.action_post()

        payment = (
            self.env["wizard.account.move.line.pay"]
            .with_context(active_model="account.move", active_ids=invoice.ids)
            .create(
                {
                    "payment_channel_id": self.payment_channel_check.id,
                    "currency_id": self.other_currency.id,
                    "amount": 150.0,
                    "payment_date": "2017-01-01",
                }
            )
            ._create_payments()
        )

        stub_pages = payment._prepare_check_stub_pages()

        self.assertEqual(
            stub_pages,
            [
                [
                    {
                        "due_date": "01/01/2016",
                        "number": invoice.name,
                        "amount_total": f"${NON_BREAKING_SPACE}150.00",
                        "amount_residual": f"${NON_BREAKING_SPACE}75.00",
                        "amount_paid": f"150.00{NON_BREAKING_SPACE}€",
                        "currency": invoice.currency_id,
                    }
                ]
            ],
        )

    def test_in_invoice_check_manual_sequencing_with_multiple_payments(self):
        nb_invoices_to_test = INV_LINES_PER_STUB + 1

        self.company_data["default_journal_bank"].write(
            {
                "check_manual_sequencing": True,
                "check_next_number": "11111",
            }
        )

        in_invoices = self.env["account.move"].create(
            [
                {
                    "move_type": "in_invoice",
                    "partner_id": self.partner_a.id,
                    "date": "2017-01-01",
                    "invoice_date": "2017-01-01",
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.product_a.id,
                                "price_unit": 100.0,
                                "tax_ids": [],
                            }
                        )
                    ],
                }
                for i in range(nb_invoices_to_test)
            ]
        )
        in_invoices.action_post()

        payments = (
            self.env["wizard.account.move.line.pay"]
            .with_context(active_model="account.move", active_ids=in_invoices.ids)
            .create(
                {
                    "group_payment": False,
                    "payment_channel_id": self.payment_channel_check.id,
                }
            )
            ._create_payments()
        )

        self.assertEqual(
            set(payments.mapped("check_number")),
            {str(x) for x in range(11111, 11111 + nb_invoices_to_test)},
        )

    def test_check_label(self):
        payment = self.env["account.payment"].create(
            {
                "check_number": "2147483647",
                "payment_type": "outbound",
                "partner_type": "supplier",
                "amount": 100.0,
                "journal_id": self.company_data["default_journal_bank"].id,
                "payment_channel_id": self.payment_channel_check.id,
            }
        )
        payment.action_post()

        for move in payment.move_id:
            self.assertRecordValues(
                move.line_ids, [{"name": "Checks - 2147483647"}] * len(move.line_ids)
            )

    def test_print_great_pre_number_check(self):
        vals = {
            "payment_type": "outbound",
            "partner_type": "supplier",
            "amount": 100.0,
            "journal_id": self.company_data["default_journal_bank"].id,
            "payment_channel_id": self.payment_channel_check.id,
        }
        payment = self.env["account.payment"].create(vals)
        payment.action_post()
        self.assertTrue(payment.write({"check_number": "2147483647"}))
        self.assertTrue(payment.write({"check_number": "2147483648"}))

        payment_2 = self.env["account.payment"].create(vals)
        payment_2.action_post()
        action_window = payment_2.print_checks()
        self.assertEqual(
            action_window["context"]["default_next_check_number"],
            "2147483649",
            "Check number should have been incremented without error.",
        )

    def test_print_check_with_branch(self):
        company = self.env.company
        branch = self.env["res.company"].create(
            {
                "name": "Branch",
                "parent_id": company.id,
            }
        )
        self.cr.precommit.run()
        self.env.user.write(
            {"company_id": company.id, "company_ids": [Command.set(company.ids)]}
        )

        vals = {
            "payment_type": "outbound",
            "partner_type": "supplier",
            "amount": 100.0,
            "journal_id": self.company_data["default_journal_bank"].id,
            "payment_channel_id": self.payment_channel_check.id,
        }
        payment = self.env["account.payment"].create(vals)
        payment.action_post()
        self.assertTrue(payment.write({"check_number": "00001"}))
        payment.invalidate_recordset(["check_number"])

        self.env.user.write(
            {"company_id": branch.id, "company_ids": [Command.set(branch.ids)]}
        )

        payment_2 = self.env["account.payment"].create(vals)
        payment_2.action_post()

        action_window = payment_2.print_checks()
        self.assertTrue(action_window)

    def test_draft_invoice_payment_check_printing(self):
        nb_invoices_to_test = INV_LINES_PER_STUB + 1

        accounting_installed = (
            self.env["account.move"]._get_invoice_in_payment_state() == "in_payment"
        )
        if not accounting_installed:
            self.skipTest("Accounting not installed")

        self.company_data["default_journal_bank"].write(
            {
                "check_manual_sequencing": True,
                "check_next_number": "00042",
            }
        )
        self.payment_channel_check.payment_account_id = None

        in_invoices = self.env["account.move"].create(
            [
                {
                    "move_type": "in_invoice",
                    "partner_id": self.partner_a.id,
                    "date": "2017-01-01",
                    "invoice_date": "2017-01-01",
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.product_a.id,
                                "price_unit": 100.0,
                                "tax_ids": [],
                            }
                        )
                    ],
                }
                for _ in range(nb_invoices_to_test)
            ]
        )
        payment = (
            self.env["wizard.account.move.line.pay"]
            .with_context(active_model="account.move", active_ids=in_invoices.ids)
            .create(
                {
                    "group_payment": True,
                    "payment_channel_id": self.payment_channel_check.id,
                }
            )
            ._create_payments()
        )
        self.assertRecordValues(
            payment,
            [
                {
                    "payment_channel_id": self.payment_channel_check.id,
                    "check_amount_in_words": payment.currency_id.amount_to_text(
                        100.0 * nb_invoices_to_test
                    ),
                    "check_number": "00042",
                }
            ],
        )

        report_pages = payment._prepare_check_pages()
        self.assertEqual(len(report_pages), 1)

    def test_multiple_payments_check_number_uniqueness(self):
        self.company_data["default_journal_bank"].write(
            {
                "check_manual_sequencing": True,
                "check_next_number": "10001",
            }
        )

        in_invoices = self.env["account.move"].create(
            [
                {
                    "move_type": "in_invoice",
                    "partner_id": self.partner_a.id,
                    "date": "2023-01-01",
                    "invoice_date": "2023-01-01",
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.product_a.id,
                                "price_unit": 100.0,
                                "tax_ids": [],
                            }
                        )
                    ],
                },
                {
                    "move_type": "in_invoice",
                    "partner_id": self.partner_a.id,
                    "date": "2023-01-01",
                    "invoice_date": "2023-01-01",
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.product_a.id,
                                "price_unit": 200.0,
                                "tax_ids": [],
                            }
                        )
                    ],
                },
                {
                    "move_type": "in_invoice",
                    "partner_id": self.partner_b.id,
                    "date": "2023-01-01",
                    "invoice_date": "2023-01-01",
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.product_a.id,
                                "price_unit": 200.0,
                                "tax_ids": [],
                            }
                        )
                    ],
                },
            ]
        )
        in_invoices.action_post()

        payments = (
            self.env["wizard.account.move.line.pay"]
            .with_context(active_model="account.move", active_ids=in_invoices.ids)
            .create(
                {
                    "group_payment": True,
                    "payment_channel_id": self.payment_channel_check.id,
                }
            )
            ._create_payments()
        )

        check_numbers = payments.mapped("check_number")
        self.assertEqual(
            len(check_numbers), 2, "Both payments should have a check number"
        )
        self.assertEqual(
            set(check_numbers), {"10001", "10002"}, "Check numbers should be sequential"
        )

        move_names = payments.move_id.line_ids.mapped("name")
        self.assertIn(f"Checks - 10001: {payments[0].memo}", move_names)
        self.assertIn(f"Checks - 10002: {payments[1].memo}", move_names)

    def test_number_exceeds_int32_limit(self):
        self.journal = self.env["account.journal"].create(
            {
                "name": "Test Bank Journal",
                "type": "bank",
                "code": "TBJ",
                "bank_statements_source": "manual",
                "check_manual_sequencing": True,
            }
        )

        check_number_too_big = str(2_147_483_648)
        check_number_normal = str(2_147_483_647)
        with self.assertRaisesRegex(
            ValidationError,
            "The check number you entered .* exceeds the maximum allowed value",
        ):
            self.journal.check_next_number = check_number_too_big
        self.journal.check_next_number = check_number_normal
        self.assertEqual(
            self.journal.check_sequence_id.number_next_actual,
            int(check_number_normal),
            "The check sequence should be updated correctly",
        )
