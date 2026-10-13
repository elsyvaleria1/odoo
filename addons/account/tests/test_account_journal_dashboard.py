from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo import Command
from odoo.tests import tagged
from odoo.tools.misc import format_amount

from odoo.addons.account.tests.test_account_journal_dashboard_common import (
    TestAccountJournalDashboardCommon,
)


@tagged("post_install", "-at_install")
class TestAccountJournalDashboard(TestAccountJournalDashboardCommon):
    @freeze_time("2019-01-22")
    def test_customer_invoice_dashboard(self):
        if (
            self.env["ir.module.module"]
            .search([("name", "=", "account_3way_match")])
            .state
            == "installed"
        ):
            self.skipTest("This test won't work if account_3way_match is installed")

        journal = self.company_data["default_journal_sale"]

        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "journal_id": journal.id,
                "partner_id": self.partner_a.id,
                "invoice_date": "2019-01-21",
                "date": "2019-01-21",
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_a.id,
                            "quantity": 40.0,
                            "name": "product test 1",
                            "discount": 10.00,
                            "price_unit": 2.27,
                            "tax_ids": [],
                        },
                    )
                ],
            }
        )
        refund = self.env["account.move"].create(
            {
                "move_type": "out_refund",
                "journal_id": journal.id,
                "partner_id": self.partner_a.id,
                "invoice_date": "2019-01-21",
                "date": "2019-01-21",
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_a.id,
                            "quantity": 1.0,
                            "name": "product test 1",
                            "price_unit": 13.3,
                            "tax_ids": [],
                        },
                    )
                ],
            }
        )

        dashboard_data = journal._get_journal_dashboard_data_batched()[journal.id]

        self.assertEqual(dashboard_data["number_draft"], 2)
        self.assertIn("68.42", dashboard_data["sum_draft"])

        self.assertEqual(dashboard_data["number_waiting"], 0)
        self.assertIn("0.00", dashboard_data["sum_waiting"])

        invoice.action_post()

        dashboard_data = journal._get_journal_dashboard_data_batched()[journal.id]
        self.assertEqual(dashboard_data["number_draft"], 1)
        self.assertIn(
            "-\N{ZERO WIDTH NO-BREAK SPACE}13.30", dashboard_data["sum_draft"]
        )

        self.assertEqual(dashboard_data["number_waiting"], 1)
        self.assertIn("81.72", dashboard_data["sum_waiting"])

        partial_payment = self.env["account.payment"].create(
            {
                "amount": 13.3,
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner_a.id,
            }
        )
        partial_payment.action_post()

        (invoice + partial_payment.move_id).line_ids.filtered(
            lambda line: line.account_type == "asset_receivable"
        ).reconcile()

        dashboard_data = journal._get_journal_dashboard_data_batched()[journal.id]
        self.assertEqual(dashboard_data["number_draft"], 1)
        self.assertIn("13.3", dashboard_data["sum_draft"])

        self.assertEqual(dashboard_data["number_waiting"], 1)
        self.assertIn("68.42", dashboard_data["sum_waiting"])

        refund.action_post()

        dashboard_data = journal._get_journal_dashboard_data_batched()[journal.id]
        self.assertEqual(dashboard_data["number_draft"], 0)
        self.assertIn("0.00", dashboard_data["sum_draft"])

        self.assertEqual(dashboard_data["number_waiting"], 2)
        self.assertIn("55.12", dashboard_data["sum_waiting"])

        payment = self.env["account.payment"].create(
            {
                "amount": 10.0,
                "payment_type": "outbound",
                "partner_type": "customer",
                "partner_id": self.partner_a.id,
            }
        )
        payment.action_post()

        (refund + payment.move_id).line_ids.filtered(
            lambda line: line.account_type == "asset_receivable"
        ).reconcile()

        dashboard_data = journal._get_journal_dashboard_data_batched()[journal.id]
        self.assertEqual(dashboard_data["number_draft"], 0)
        self.assertIn("0.00", dashboard_data["sum_draft"])

        self.assertEqual(dashboard_data["number_waiting"], 2)
        self.assertIn("65.12", dashboard_data["sum_waiting"])

        dashboard_data = journal._get_journal_dashboard_data_batched()[journal.id]
        self.assertEqual(dashboard_data["number_late"], 2)
        self.assertIn("65.12", dashboard_data["sum_late"])

    def test_sale_purchase_journal_for_purchase(self):
        if (
            self.env["ir.module.module"]
            .search([("name", "=", "account_3way_match")])
            .state
            == "installed"
        ):
            self.skipTest("This test won't work if account_3way_match is installed")

        foreign_currency = self.other_currency
        company_currency = self.company_data["currency"]

        setup_values = [
            [self.company_data["default_journal_purchase"], foreign_currency],
            [
                self.company_data["default_journal_purchase"].copy(
                    {
                        "currency_id": foreign_currency.id,
                        "default_account_id": self.company_data[
                            "default_account_expense"
                        ].id,
                    }
                ),
                foreign_currency,
            ],
            [
                self.company_data["default_journal_purchase"].copy(
                    {
                        "currency_id": foreign_currency.id,
                        "default_account_id": self.company_data[
                            "default_account_expense"
                        ].id,
                    }
                ),
                company_currency,
            ],
            [
                self.company_data["default_journal_purchase"].copy(
                    {
                        "currency_id": company_currency.id,
                        "default_account_id": self.company_data[
                            "default_account_expense"
                        ].id,
                    }
                ),
                company_currency,
            ],
            [
                self.company_data["default_journal_purchase"].copy(
                    {
                        "currency_id": company_currency.id,
                        "default_account_id": self.company_data[
                            "default_account_expense"
                        ].id,
                    }
                ),
                foreign_currency,
            ],
        ]

        expected_vals_list = [
            [1, 100, 1, 55, 1, 55, company_currency],
            [1, 200, 1, 110, 1, 110, foreign_currency],
            [1, 400, 1, 220, 1, 220, foreign_currency],
            [1, 200, 1, 110, 1, 110, company_currency],
            [1, 100, 1, 55, 1, 55, company_currency],
        ]

        for (purchase_journal, bill_currency), expected_vals in zip(
            setup_values, expected_vals_list, strict=True
        ):
            with self.subTest(
                purchase_journal_currency=purchase_journal.currency_id,
                bill_currency=bill_currency,
                expected_vals=expected_vals,
            ):
                bill = self.init_invoice(
                    "in_invoice",
                    invoice_date="2017-01-01",
                    post=True,
                    amounts=[200],
                    currency=bill_currency,
                    journal=purchase_journal,
                )
                _draft_bill = self.init_invoice(
                    "in_invoice",
                    invoice_date="2017-01-01",
                    post=False,
                    amounts=[200],
                    currency=bill_currency,
                    journal=purchase_journal,
                )

                payment = self.init_payment(
                    -90, post=True, date="2017-01-01", currency=bill_currency
                )
                (bill + payment.move_id).line_ids.filtered_domain(
                    [
                        (
                            "account_id",
                            "=",
                            self.company_data["default_account_payable"].id,
                        )
                    ]
                ).reconcile()

                self.assertDashboardPurchaseSaleData(purchase_journal, *expected_vals)

    def test_sale_purchase_journal_for_multi_currency_sale(self):
        if (
            self.env["ir.module.module"]
            .search([("name", "=", "account_3way_match")])
            .state
            == "installed"
        ):
            self.skipTest("This test won't work if account_3way_match is installed")

        currency = self.other_currency
        company_currency = self.company_data["currency"]

        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_date": "2017-01-01",
                "date": "2017-01-01",
                "partner_id": self.partner_a.id,
                "currency_id": currency.id,
                "invoice_line_ids": [(0, 0, {"name": "test", "price_unit": 200})],
            }
        )
        invoice.action_post()

        payment = self.env["account.payment"].create(
            {
                "amount": 90.0,
                "date": "2016-01-01",
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner_a.id,
                "currency_id": currency.id,
            }
        )
        payment.action_post()

        (invoice + payment.move_id).line_ids.filtered_domain(
            [("account_id", "=", self.company_data["default_account_receivable"].id)]
        ).reconcile()

        default_journal_sale = self.company_data["default_journal_sale"]
        dashboard_data = default_journal_sale._get_journal_dashboard_data_batched()[
            default_journal_sale.id
        ]
        self.assertEqual(
            format_amount(self.env, 55, company_currency), dashboard_data["sum_waiting"]
        )
        self.assertEqual(
            format_amount(self.env, 55, company_currency), dashboard_data["sum_late"]
        )

    @freeze_time("2023-03-15")
    def test_purchase_journal_numbers_and_sums(self):
        if (
            self.env["ir.module.module"]
            .search([("name", "=", "account_3way_match")])
            .state
            == "installed"
        ):
            self.skipTest("This test won't work if account_3way_match is installed")

        company_currency = self.company_data["currency"]
        journal = self.company_data["default_journal_purchase"]

        self._create_test_vendor_bills(journal)
        dashboard_data = journal._get_journal_dashboard_data_batched()[journal.id]
        self.assertEqual(3, dashboard_data["number_waiting"])
        self.assertEqual(
            format_amount(self.env, 4440, company_currency),
            dashboard_data["sum_waiting"],
        )
        self.assertEqual(1, dashboard_data["number_late"])
        self.assertEqual(
            format_amount(self.env, 40, company_currency), dashboard_data["sum_late"]
        )

    def test_gap_in_sequence_warning(self):
        journal = self.company_data["default_journal_sale"]
        self.assertFalse(journal._query_has_sequence_holes())
        moves = (
            self.env["account.move"]
            .create(
                [
                    {
                        "move_type": "out_invoice",
                        "journal_id": journal.id,
                        "partner_id": self.partner_a.id,
                        "invoice_date": f"1900-01-{i + 1:02d}",
                        "date": f"2019-01-{i + 1:02d}",
                        "invoice_line_ids": [
                            Command.create(
                                {
                                    "product_id": self.product_a.id,
                                    "quantity": 40.0,
                                    "name": "product test 1",
                                    "price_unit": 2.27,
                                    "tax_ids": [],
                                }
                            )
                        ],
                    }
                    for i in range(10)
                ]
            )
            .sorted("date")
        )
        gap_date = moves[3].date

        moves[:8].action_post()
        self.assertFalse(journal._query_has_sequence_holes())

        moves[2:4].action_draft()
        self.assertTrue(journal._query_has_sequence_holes())
        moves[3].unlink()
        self.assertTrue(journal._query_has_sequence_holes())

        moves[2].action_post()
        self.company_data["company"].account_config_id.write(
            {"fiscalyear_lock_date": gap_date + relativedelta(days=1)}
        )
        self.assertFalse(journal._query_has_sequence_holes())

        moves[6].action_draft()
        moves[6].action_cancel()
        self.assertTrue(journal._query_has_sequence_holes())

    def test_bank_journal_with_default_account_as_outstanding_account_payments(self):
        bank_journal = self.company_data["default_journal_bank"].copy()
        bank_journal.outbound_payment_channel_ids[
            0
        ].payment_account_id = bank_journal.default_account_id
        bank_journal.inbound_payment_channel_ids[
            0
        ].payment_account_id = bank_journal.default_account_id
        payment = self.env["account.payment"].create(
            {
                "amount": 100,
                "payment_type": "inbound",
                "partner_type": "customer",
                "journal_id": bank_journal.id,
            }
        )
        payment.action_post()

        dashboard_data = bank_journal._get_journal_dashboard_data_batched()[
            bank_journal.id
        ]
        self.assertEqual(dashboard_data["nb_misc_operations"], 0)
        self.assertEqual(
            dashboard_data["account_balance"],
            (bank_journal.currency_id or self.env.company.currency_id).format(100),
        )

    def test_outstanding_payments_count_is_per_payment_not_per_currency(self):
        bank_journal = self.company_data["default_journal_bank"]
        for amount in (10.0, 20.0, 30.0):
            payment = self.env["account.payment"].create(
                {
                    "amount": amount,
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "journal_id": bank_journal.id,
                }
            )
            payment.action_post()

        dashboard_data = bank_journal._get_journal_dashboard_data_batched()[
            bank_journal.id
        ]
        self.assertEqual(
            dashboard_data["nb_lines_outstanding_pay_account_balance"],
            3,
            "3 same-currency outstanding payments must be counted as 3, not 1.",
        )

    def test_bank_journal_different_currency(self):
        foreign_currency = self.other_currency
        bank_journal = self.company_data["default_journal_bank"].copy(
            {"currency_id": foreign_currency.id}
        )

        self.assertNotEqual(
            bank_journal.currency_id, bank_journal.company_id.currency_id
        )

        move = self.env["account.move"].create(
            {
                "journal_id": self.company_data["default_journal_misc"].id,
                "line_ids": [
                    Command.create(
                        {
                            "account_id": bank_journal.default_account_id.id,
                            "currency_id": foreign_currency.id,
                            "amount_currency": 100,
                        }
                    ),
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_account_assets"
                            ].id,
                            "currency_id": foreign_currency.id,
                            "amount_currency": -100,
                        }
                    ),
                ],
            }
        )
        move.action_post()

        dashboard_data = bank_journal._get_journal_dashboard_data_batched()[
            bank_journal.id
        ]
        self.assertEqual(
            dashboard_data.get("misc_operations_balance", 0),
            foreign_currency.format(100),
        )

        bank_journal.default_account_id.currency_id = False
        company_currency_move = self.env["account.move"].create(
            {
                "journal_id": self.company_data["default_journal_misc"].id,
                "line_ids": [
                    Command.create(
                        {
                            "account_id": bank_journal.default_account_id.id,
                            "debit": 100,
                        }
                    ),
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_account_assets"
                            ].id,
                            "credit": 100,
                        }
                    ),
                ],
            }
        )
        company_currency_move.action_post()
        dashboard_data = bank_journal._get_journal_dashboard_data_batched()[
            bank_journal.id
        ]

        self.assertEqual(dashboard_data.get("misc_operations_balance", 0), None)
        self.assertEqual(dashboard_data.get("misc_class", ""), "text-warning")

    def test_to_check_posted(self):
        journal = self.env["account.journal"].create(
            {
                "name": "Test Foreign Currency Journal",
                "type": "sale",
                "code": "TEST",
                "currency_id": self.currency.id,
                "company_id": self.env.company.id,
            }
        )
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "journal_id": journal.id,
                "partner_id": self.partner_a.id,
                "checked": False,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "quantity": 1,
                            "price_unit": 100,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )

        dashboard_data = journal._get_journal_dashboard_data_batched()[journal.id]
        self.assertEqual(
            dashboard_data["to_check_balance"], journal.currency_id.format(0)
        )

        move.action_post()
        move.checked = False

        dashboard_data = journal._get_journal_dashboard_data_batched()[journal.id]
        self.assertEqual(
            dashboard_data["to_check_balance"], journal.currency_id.format(100)
        )

    def test_to_check_amount_different_currency(self):
        self.env.ref("base.CHF").write({"active": True})
        self.env["res.currency.rate"].create(
            {
                "currency_id": self.env.ref("base.EUR").id,
                "name": "2024-12-01",
                "rate": 2.0,
            }
        )
        self.env["res.currency.rate"].create(
            {
                "currency_id": self.env.ref("base.CHF").id,
                "name": "2024-12-01",
                "rate": 4.0,
            }
        )
        journal = self.env["account.journal"].create(
            {
                "name": "Test Foreign Currency Journal",
                "type": "sale",
                "code": "TEST",
                "currency_id": self.env.ref("base.EUR").id,
                "company_id": self.env.company.id,
            }
        )
        moves = self.env["account.move"].create(
            [
                {
                    "move_type": "out_invoice",
                    "journal_id": journal.id,
                    "partner_id": self.partner_a.id,
                    "currency_id": currency.id,
                    "checked": False,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.product_a.id,
                                "quantity": 1,
                                "price_unit": 100,
                                "tax_ids": [],
                            }
                        )
                    ],
                }
                for currency in (self.env.ref("base.EUR"), self.env.ref("base.CHF"))
            ]
        )
        moves.action_post()
        moves.checked = False

        dashboard_data = journal._get_journal_dashboard_data_batched()[journal.id]
        self.assertEqual(
            dashboard_data["to_check_balance"], journal.currency_id.format(150)
        )

    @freeze_time("2023-06-15")
    def test_misc_operations_shared_default_account_windows(self):
        windowed = self.company_data["default_journal_bank"]
        shared_account = windowed.default_account_id
        open_journal = windowed.copy({"name": "Shared-Account Bank", "code": "SHBNK"})
        open_journal.default_account_id = shared_account
        self.assertEqual(open_journal.default_account_id, shared_account)

        self.env["account.bank.statement"].create(
            {
                "name": "Seed statement",
                "line_ids": [
                    Command.create(
                        {
                            "journal_id": windowed.id,
                            "date": "2023-05-01",
                            "payment_ref": "seed",
                            "amount": 10.0,
                        }
                    )
                ],
            }
        )
        self.assertEqual(windowed.last_statement_id.date.isoformat(), "2023-05-01")
        self.assertFalse(open_journal.last_statement_id)

        self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.company_data["default_journal_misc"].id,
                "date": "2023-03-15",
                "line_ids": [
                    Command.create(
                        {
                            "account_id": shared_account.id,
                            "debit": 100.0,
                            "credit": 0.0,
                            "name": "misc on shared account",
                        }
                    ),
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_account_expense"
                            ].id,
                            "debit": 0.0,
                            "credit": 100.0,
                            "name": "counterpart",
                        }
                    ),
                ],
            }
        ).action_post()

        data = (windowed | open_journal)._get_journal_dashboard_data_batched()
        self.assertEqual(data[windowed.id]["nb_misc_operations"], 0)
        self.assertEqual(data[open_journal.id]["nb_misc_operations"], 1)


@tagged("post_install", "-at_install")
class TestAccountJournalDashboardSigns(TestAccountJournalDashboardCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.par_currency = cls.setup_other_currency("GBP", rates=[("1900-01-01", 1.0)])

    def _journal_in(self, jtype, code, currency):
        return self.env["account.journal"].create(
            {
                "name": code,
                "code": code,
                "type": jtype,
                "company_id": self.env.company.id,
                "currency_id": currency.id if currency else False,
            }
        )

    def _post(self, journal, move_type, amount, currency):
        account = self.company_data[
            "default_account_revenue"
            if move_type.startswith("out")
            else "default_account_expense"
        ]
        move = self.env["account.move"].create(
            {
                "move_type": move_type,
                "journal_id": journal.id,
                "partner_id": self.partner_a.id,
                "currency_id": currency.id,
                "invoice_date": "2019-01-01",
                "date": "2019-01-01",
                "invoice_date_due": "2019-01-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "l",
                            "quantity": 1,
                            "price_unit": amount,
                            "account_id": account.id,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        move.action_post()
        return move

    def _sums(self, journal):
        data = journal._get_journal_dashboard_data_batched()[journal.id]
        return data["sum_waiting"], data["sum_late"]

    @freeze_time("2019-06-01")
    def test_credit_note_subtracts_in_a_foreign_currency_journal(self):
        expected = format_amount(self.env, 700, self.par_currency)

        journal = self._journal_in("sale", "FXS1", self.par_currency)
        self._post(journal, "out_invoice", 1000, self.par_currency)
        self._post(journal, "out_refund", 300, self.par_currency)
        self.assertEqual(self._sums(journal), (expected, expected))

    @freeze_time("2019-06-01")
    def test_credit_note_agrees_across_both_currency_branches(self):
        company_currency = self.company_data["currency"]
        control = self._journal_in("sale", "FXS2", None)
        self._post(control, "out_invoice", 1000, company_currency)
        self._post(control, "out_refund", 300, company_currency)

        foreign = self._journal_in("sale", "FXS3", self.par_currency)
        self._post(foreign, "out_invoice", 1000, self.par_currency)
        self._post(foreign, "out_refund", 300, self.par_currency)

        _waiting, control_late = self._sums(control)
        _waiting, foreign_late = self._sums(foreign)
        self.assertEqual(control_late, format_amount(self.env, 700, company_currency))
        self.assertEqual(foreign_late, format_amount(self.env, 700, self.par_currency))

    @freeze_time("2019-06-01")
    def test_vendor_receipt_adds_in_a_foreign_currency_journal(self):
        expected = format_amount(self.env, 1400, self.par_currency)

        journal = self._journal_in("purchase", "FXP1", self.par_currency)
        self._post(journal, "in_invoice", 1000, self.par_currency)
        self._post(journal, "in_receipt", 400, self.par_currency)
        self.assertEqual(self._sums(journal), (expected, expected))

    @freeze_time("2019-06-01")
    def test_every_invoice_type_keeps_its_residual_sign(self):
        cases = [
            ("sale", "out_invoice", 100),
            ("sale", "out_refund", -100),
            ("sale", "out_receipt", 100),
            ("purchase", "in_invoice", -100),
            ("purchase", "in_refund", 100),
            ("purchase", "in_receipt", -100),
        ]
        for index, (jtype, move_type, signed) in enumerate(cases):
            with self.subTest(move_type=move_type):
                journal = self._journal_in(jtype, f"FX{index}", self.par_currency)
                self._post(journal, move_type, 100, self.par_currency)
                display = signed if jtype == "sale" else -signed
                self.assertEqual(
                    self._sums(journal)[1],
                    format_amount(self.env, display, self.par_currency),
                )

    @freeze_time("2019-06-01")
    def test_bills_to_review_carry_the_sign_of_the_bills_to_pay(self):
        for code, currency in (("FXR1", None), ("FXR2", self.par_currency)):
            with self.subTest(currency=currency):
                journal = self._journal_in("purchase", code, currency)
                bill = self._post(
                    journal,
                    "in_invoice",
                    1000,
                    currency or self.company_data["currency"],
                )
                bill.checked = False
                data = journal._get_journal_dashboard_data_batched()[journal.id]
                self.assertEqual(data["number_to_check"], 1)
                self.assertEqual(data["to_check_balance"], data["sum_waiting"])
                self.assertEqual(
                    data["to_check_balance"],
                    format_amount(
                        self.env, 1000, currency or self.company_data["currency"]
                    ),
                )

    @freeze_time("2019-06-01")
    def test_due_graph_of_a_foreign_currency_journal_is_in_the_journal_currency(self):
        quarter = self.setup_other_currency("CHF", rates=[("1900-01-01", 4.0)])
        for jtype, move_type, code in (
            ("sale", "out_invoice", "FXG1"),
            ("purchase", "in_invoice", "FXG2"),
        ):
            with self.subTest(journal_type=jtype):
                journal = self._journal_in(jtype, code, quarter)
                self._post(journal, move_type, 1000, quarter)

                graph = journal._prepare_sale_purchase_graph_data()[journal.id][0]
                self.assertFalse(graph["is_sample_data"])
                self.assertEqual(graph["values"][0]["value"], 1000)
                self.assertEqual(
                    self._sums(journal)[1], format_amount(self.env, 1000, quarter)
                )

    def test_the_negative_residual_set_is_the_outbound_set(self):
        self.assertEqual(
            sorted(self.env["account.move"].get_outbound_types()),
            ["in_invoice", "in_receipt", "out_refund"],
        )


@tagged("post_install", "-at_install")
class TestAccountJournalToCheckValue(TestAccountJournalDashboardCommon):
    def setUp(self):
        super().setUp()
        self.journal = self.env["account.journal"].create(
            {
                "name": "TCV",
                "code": "TCV",
                "type": "sale",
                "company_id": self.env.company.id,
            }
        )

    def _post_unreviewed(self, amount):
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "journal_id": self.journal.id,
                "partner_id": self.partner_a.id,
                "invoice_date": "2019-01-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "l",
                            "quantity": 1,
                            "price_unit": amount,
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        move.action_post()
        move.checked = False
        return move

    def _to_check(self):
        self.journal.invalidate_recordset()
        data = self.journal._get_journal_dashboard_data_batched()[self.journal.id]
        return data["number_to_check"], data["to_check_balance"]

    def _pay_in_full(self, move):
        payment = self.env["account.payment"].create(
            {
                "journal_id": self.company_data["default_journal_bank"].id,
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner_a.id,
                "amount": move.amount_total,
                "currency_id": move.currency_id.id,
                "date": "2019-01-02",
            }
        )
        payment.action_post()
        (move + payment.move_id).line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        ).reconcile()
        move.checked = False

    def test_a_paid_but_unreviewed_invoice_still_has_a_value(self):
        currency = self.company_data["currency"]
        unpaid = self._post_unreviewed(500)
        paid = self._post_unreviewed(800)
        self._pay_in_full(paid)

        self.assertEqual(
            paid.payment_state,
            "in_payment" if paid._has_full_accounting() else "paid",
        )
        self.assertEqual(paid.amount_residual, 0.0)
        self.assertEqual(unpaid.amount_total + paid.amount_total, 1300)
        self.assertEqual(self._to_check(), (2, format_amount(self.env, 1300, currency)))

    def test_a_misc_entry_in_a_sale_journal_carries_its_total(self):
        currency = self.company_data["currency"]
        self._post_unreviewed(500)
        entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.journal.id,
                "date": "2019-01-01",
                "line_ids": [
                    Command.create(
                        {
                            "name": "d",
                            "debit": 70,
                            "credit": 0,
                            "account_id": self.company_data[
                                "default_account_receivable"
                            ].id,
                        }
                    ),
                    Command.create(
                        {
                            "name": "c",
                            "debit": 0,
                            "credit": 70,
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                        }
                    ),
                ],
            }
        )
        entry.action_post()
        entry.checked = False

        self.assertEqual(entry.amount_residual_signed, 0.0)
        self.assertEqual(self._to_check(), (2, format_amount(self.env, 570, currency)))


@tagged("post_install", "-at_install")
class TestAccountJournalEntryPresence(TestAccountJournalDashboardCommon):
    def _journal(self, code):
        return self.env["account.journal"].create(
            {
                "name": code,
                "code": code,
                "type": "sale",
                "company_id": self.env.company.id,
            }
        )

    def _invoice(self, journal):
        return self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "journal_id": journal.id,
                "partner_id": self.partner_a.id,
                "invoice_date": "2019-01-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "l",
                            "quantity": 1,
                            "price_unit": 100,
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )

    def test_entry_presence_distinguishes_draft_from_posted(self):
        empty, drafted, posted = (self._journal(c) for c in ("EP1", "EP2", "EP3"))
        self._invoice(drafted)
        self._invoice(posted).action_post()

        (empty + drafted + posted).invalidate_recordset()
        self.assertEqual(
            [(j.has_entries, j.has_posted_entries) for j in (empty, drafted, posted)],
            [(False, False), (True, False), (True, True)],
        )

    def test_entry_presence_on_an_empty_recordset(self):
        self.assertEqual(self.env["account.journal"].browse().mapped("has_entries"), [])


@tagged("post_install", "-at_install")
class TestAccountJournalBankGraph(TestAccountJournalDashboardCommon):
    @freeze_time("2019-01-22")
    def test_the_bank_graph_ignores_cancelled_and_future_lines(self):
        journal = self.company_data["default_journal_bank"]
        Line = self.env["account.bank.statement.line"]
        Line.create(
            {
                "journal_id": journal.id,
                "date": "2019-01-17",
                "payment_ref": "kept",
                "amount": 100.0,
            }
        )
        cancelled = Line.create(
            {
                "journal_id": journal.id,
                "date": "2019-01-20",
                "payment_ref": "cancelled",
                "amount": 1000.0,
            }
        )
        cancelled.move_id.action_draft()
        cancelled.move_id.action_cancel()
        Line.create(
            {
                "journal_id": journal.id,
                "date": "2019-01-25",
                "payment_ref": "future",
                "amount": 50.0,
            }
        )
        journal.invalidate_recordset()

        self.assertEqual(journal.amount_statement_balance_today, 100.0)
        self.assertEqual(journal.amount_upcoming, 50.0)
        self.assertEqual(journal.count_upcoming, 1)
        graph = journal._prepare_bank_cash_graph_data()[journal.id][0]
        self.assertEqual(
            [(point["name"], point["y"]) for point in graph["values"]],
            [
                ("23 December 2018", 0.0),
                ("17 January 2019", 100.0),
                ("22 January 2019", 100.0),
            ],
        )

    def test_the_bank_position_is_read_once_for_all_its_fields(self):
        journals = self.env["account.journal"].search(
            [("company_id", "=", self.env.company.id)]
        )
        Journal = type(self.env["account.journal"])
        original = Journal._get_bank_positions
        calls = []

        def counted(records):
            calls.append(records)
            return original(records)

        journals.invalidate_recordset()
        with patch.object(Journal, "_get_bank_positions", counted):
            journals.read(
                [
                    "amount_balance_today",
                    "amount_statement_balance_today",
                    "amount_upcoming",
                    "count_upcoming",
                    "has_statement_lines",
                    "has_direct_bank_payments",
                    "last_statement_id",
                ]
            )
        self.assertEqual(len(calls), 1)

    @freeze_time("2019-01-22")
    def test_the_bank_position_ignores_a_cancellation_not_yet_flushed(self):
        journal = self.company_data["default_journal_bank"]
        Line = self.env["account.bank.statement.line"]
        Line.create(
            {
                "journal_id": journal.id,
                "date": "2019-01-17",
                "payment_ref": "kept",
                "amount": 100.0,
            }
        )
        cancelled = Line.create(
            {
                "journal_id": journal.id,
                "date": "2019-01-20",
                "payment_ref": "cancelled",
                "amount": 1000.0,
            }
        )
        self.env.flush_all()
        cancelled.move_id.state = "cancel"
        journal.invalidate_recordset()

        self.assertEqual(journal.amount_statement_balance_today, 100.0)
        graph = journal._prepare_bank_cash_graph_data()[journal.id][0]
        self.assertEqual(graph["values"][0]["y"], 0.0)

    @freeze_time("2019-01-22")
    def test_the_bank_graph_reads_a_cancellation_not_yet_flushed(self):
        journal = self.company_data["default_journal_bank"]
        Line = self.env["account.bank.statement.line"]
        Line.create(
            {
                "journal_id": journal.id,
                "date": "2019-01-17",
                "payment_ref": "kept",
                "amount": 100.0,
            }
        )
        cancelled = Line.create(
            {
                "journal_id": journal.id,
                "date": "2019-01-20",
                "payment_ref": "cancelled",
                "amount": 1000.0,
            }
        )
        self.env.flush_all()
        cancelled.move_id.state = "cancel"
        journal.invalidate_recordset()

        graph = journal._prepare_bank_cash_graph_data()[journal.id][0]
        self.assertEqual(
            [(point["name"], point["y"]) for point in graph["values"]],
            [
                ("23 December 2018", 0.0),
                ("17 January 2019", 100.0),
                ("22 January 2019", 100.0),
            ],
        )


@tagged("post_install", "-at_install")
class TestAccountJournalBankCard(TestAccountJournalDashboardCommon):
    def _create_st_lines(self, journal, *date_amounts):
        return self.env["account.bank.statement.line"].create(
            [
                {
                    "journal_id": journal.id,
                    "date": line_date,
                    "payment_ref": f"line {line_date}",
                    "amount": amount,
                }
                for line_date, amount in date_amounts
            ]
        )

    def _direct_payment_journal(self, currency=None):
        journal = self.company_data["default_journal_bank"].copy(
            {"currency_id": currency.id} if currency else {}
        )
        (
            journal.inbound_payment_channel_ids[:1]
            | journal.outbound_payment_channel_ids[:1]
        ).payment_account_id = journal.default_account_id
        return journal

    def _create_direct_payments(self, journal, *date_amounts, post=True):
        payments = self.env["account.payment"].create(
            [
                {
                    "amount": abs(amount),
                    "date": payment_date,
                    "payment_type": "inbound" if amount > 0 else "outbound",
                    "partner_type": "customer" if amount > 0 else "supplier",
                    "partner_id": self.partner_a.id,
                    "journal_id": journal.id,
                }
                for payment_date, amount in date_amounts
            ]
        )
        if post:
            payments.action_post()
        return payments

    def _card_and_graph(self, journal):
        journal.invalidate_recordset()
        card = journal._get_journal_dashboard_data_batched()[journal.id]
        graph = journal._prepare_bank_cash_graph_data()[journal.id][0]["values"]
        return card, graph

    @freeze_time("2019-01-22")
    def test_the_card_balance_is_the_graph_last_point_with_future_lines(self):
        journal = self.company_data["default_journal_bank"]
        currency = journal._dashboard_currency()
        self._create_st_lines(
            journal,
            ("2019-01-17", 100.0),
            ("2019-01-22", 5.0),
            ("2019-01-25", 50.0),
            ("2019-02-10", 20.0),
        )

        card, graph = self._card_and_graph(journal)

        self.assertEqual(graph[-1]["name"], "22 January 2019")
        self.assertEqual(graph[-1]["y"], 105.0)
        self.assertEqual(card["account_balance"], currency.format(105.0))
        self.assertEqual(card["nb_upcoming"], 2)
        self.assertEqual(card["upcoming_balance"], currency.format(70.0))
        self.assertEqual(
            journal.get_total_journal_amount()["balance_amount"],
            format_amount(self.env, 105.0, currency),
        )

    @freeze_time("2019-01-22")
    def test_the_upcoming_action_lists_future_lines_and_direct_payments(self):
        journal = self._direct_payment_journal()
        lines = self._create_st_lines(
            journal,
            ("2019-01-17", 100.0),
            ("2019-01-25", 50.0),
            ("2019-02-10", 20.0),
        )
        cancelled = self._create_st_lines(journal, ("2019-01-26", 1000.0))
        cancelled.move_id.action_draft()
        cancelled.move_id.action_cancel()
        payments = self._create_direct_payments(
            journal,
            ("2019-01-15", 300.0),
            ("2019-01-28", 40.0),
            ("2019-02-05", -15.0),
        )
        self._create_direct_payments(journal, ("2019-01-29", 7.0), post=False)
        journal.invalidate_recordset()

        action = journal.open_upcoming_transactions_action()
        items = self.env["account.move.line"].search(action["domain"])

        self.assertEqual(action["res_model"], "account.move.line")
        self.assertEqual(action["display_name"], "Upcoming Transactions")
        self.assertEqual(items.move_id, lines[1:].move_id | payments[1:].move_id)
        self.assertEqual(len(items), journal.count_upcoming)
        self.assertEqual(sum(items.mapped("balance")), journal.amount_upcoming)
        self.assertEqual(journal.count_upcoming, 4)
        self.assertEqual(journal.amount_upcoming, 95.0)

    @freeze_time("2019-01-22 23:30:00")
    def test_today_is_the_user_timezone_date_for_balance_and_graph(self):
        journal = self.company_data["default_journal_bank"]
        currency = journal._dashboard_currency()
        self._create_st_lines(journal, ("2019-01-17", 100.0), ("2019-01-23", 7.0))

        for tz, balance, upcoming_count, last_point in (
            ("UTC", 100.0, 1, "22 January 2019"),
            ("Pacific/Auckland", 107.0, 0, "23 January 2019"),
        ):
            with self.subTest(tz=tz):
                card, graph = self._card_and_graph(journal.with_context(tz=tz))
                self.assertEqual(card["account_balance"], currency.format(balance))
                self.assertEqual(card["nb_upcoming"], upcoming_count)
                self.assertEqual(graph[-1]["name"], last_point)
                self.assertEqual(graph[-1]["y"], balance)

    @freeze_time("2019-01-22")
    def test_a_foreign_currency_journal_reads_in_its_own_currency(self):
        journal = self.company_data["default_journal_bank"].copy(
            {"currency_id": self.other_currency.id}
        )
        self._create_st_lines(journal, ("2019-01-17", 100.0), ("2019-01-30", 30.0))

        card, graph = self._card_and_graph(journal)

        self.assertEqual(graph[-1]["y"], 100.0)
        self.assertEqual(card["account_balance"], self.other_currency.format(100.0))
        self.assertEqual(card["upcoming_balance"], self.other_currency.format(30.0))
        self.assertEqual(card["nb_upcoming"], 1)

    @freeze_time("2019-01-22")
    def test_direct_bank_payments_are_dated_in_card_and_graph(self):
        journal = self._direct_payment_journal()
        currency = journal._dashboard_currency()
        self._create_direct_payments(
            journal,
            ("2018-12-01", 1000.0),
            ("2019-01-15", 100.0),
            ("2019-01-30", 40.0),
        )
        self._create_st_lines(journal, ("2019-01-17", 10.0))

        card, graph = self._card_and_graph(journal)

        self.assertEqual(card["account_balance"], currency.format(1110.0))
        self.assertEqual(card["nb_upcoming"], 1)
        self.assertEqual(card["upcoming_balance"], currency.format(40.0))
        self.assertEqual(
            [(point["name"], point["y"]) for point in graph],
            [
                ("23 December 2018", 1000.0),
                ("15 January 2019", 1100.0),
                ("17 January 2019", 1110.0),
                ("22 January 2019", 1110.0),
            ],
        )

    @freeze_time("2019-01-22")
    def test_balance_today_plus_upcoming_is_the_full_position(self):
        statement_lines = (
            ("2019-01-10", 100.0),
            ("2019-01-22", 5.0),
            ("2019-01-25", 50.0),
            ("2019-02-10", -20.0),
        )
        direct_payments = (
            ("2019-01-15", 300.0),
            ("2019-01-28", 40.0),
            ("2019-02-05", -15.0),
        )
        full_position = sum(
            amount for _date, amount in statement_lines + direct_payments
        )
        for currency in (self.env.company.currency_id, self.other_currency):
            with self.subTest(currency=currency.name):
                journal = self._direct_payment_journal(
                    currency if currency != self.env.company.currency_id else None
                )
                self._create_st_lines(journal, *statement_lines)
                self._create_direct_payments(journal, *direct_payments)

                card, graph = self._card_and_graph(journal)

                self.assertEqual(journal._dashboard_currency(), currency)
                self.assertEqual(
                    journal.amount_balance_today + journal.amount_upcoming,
                    full_position,
                )
                self.assertEqual(journal.amount_balance_today, 405.0)
                self.assertEqual(journal.amount_statement_balance_today, 105.0)
                self.assertEqual(journal.amount_upcoming, 55.0)
                self.assertEqual(journal.count_upcoming, 4)
                self.assertEqual(card["account_balance"], currency.format(405.0))
                self.assertEqual(card["upcoming_balance"], currency.format(55.0))
                self.assertEqual(card["nb_upcoming"], 4)
                self.assertEqual(graph[-1]["name"], "22 January 2019")
                self.assertEqual(graph[-1]["y"], 405.0)

    @freeze_time("2019-01-22")
    def test_only_old_direct_payments_still_draw_the_real_graph(self):
        journal = self._direct_payment_journal()
        self._create_direct_payments(journal, ("2018-11-01", 250.0))

        card, graph = self._card_and_graph(journal)

        self.assertTrue(card["nb_lines_bank_account_balance"])
        self.assertEqual(
            [(point["name"], point["y"]) for point in graph],
            [("23 December 2018", 250.0), ("22 January 2019", 250.0)],
        )

    @freeze_time("2019-01-22")
    def test_the_card_and_graph_of_six_journals_cost_no_more_queries(self):
        journals = self.env["account.journal"].concat(
            *(self._direct_payment_journal() for _i in range(6))
        )
        for journal in journals:
            self._create_st_lines(journal, ("2019-01-17", 100.0), ("2019-01-25", 50.0))
            self._create_direct_payments(
                journal, ("2019-01-15", 30.0), ("2019-01-28", 40.0)
            )
        self.env.flush_all()
        journals.invalidate_recordset()
        with self.assertQueryCount(default=20):
            journals.read(["kanban_dashboard", "kanban_dashboard_graph"])
