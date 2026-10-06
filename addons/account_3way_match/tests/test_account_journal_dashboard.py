import ast

from freezegun import freeze_time
from lxml import etree

from odoo.tests import tagged
from odoo.tools.misc import format_amount

from odoo.addons.account.tests.test_account_journal_dashboard_common import (
    TestAccountJournalDashboardCommon,
)
from odoo.addons.account_3way_match import uninstall_hook


@tagged("post_install", "-at_install")
class AccountJournalDashboard3WayWatchTest(TestAccountJournalDashboardCommon):
    @classmethod
    def init_invoice(
        cls,
        move_type,
        partner=None,
        invoice_date=None,
        post=False,
        products=None,
        amounts=None,
        taxes=None,
        company=False,
        currency=None,
        journal=None,
        invoice_date_due=None,
        release_to_pay=None,
    ):
        move = super().init_invoice(
            move_type,
            partner,
            invoice_date,
            False,
            products,
            amounts,
            taxes,
            company,
            currency,
            journal,
        )
        if invoice_date_due:
            move.invoice_date_due = invoice_date_due
        if release_to_pay:
            # Force the status the way the application does. Writing
            # release_to_pay directly reaches past its compute -- it is not a
            # gesture any user can make, and the value does not survive the
            # next recompute of the bill.
            move.write(
                {
                    "force_release_to_pay": True,
                    "release_to_pay_manual": release_to_pay,
                }
            )
        if post:
            move.action_post()
        return move

    def test_sale_purchase_journal_for_purchase(self):
        """
        Test different purchase journal setups with or without multicurrency:
            1) Journal with no currency, bills in foreign currency -> dashboard data should be displayed in company currency
            2) Journal in foreign currency, bills in foreign currency -> dashboard data should be displayed in foreign currency
            3) Journal in foreign currency, bills in company currency -> dashboard data should be displayed in foreign currency
            4) Journal in company currency, bills in company currency -> dashboard data should be displayed in company currency
            5) Journal in company currency, bills in foreign currency -> dashboard data should be displayed in company currency
        """
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
            # number_draft, sum_draft, number_waiting, sum_waiting, number_late, sum_late, currency
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
                # A draft bill counts on the dashboard once it is late, so its
                # due date is stated: through the form, the due date is derived
                # before any line exists and the onchange round-trip keeps
                # today's, which the ORM then saves as given.
                _draft_bill = self.init_invoice(
                    "in_invoice",
                    invoice_date="2017-01-01",
                    invoice_date_due="2017-01-01",
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

    @freeze_time("2023-03-15")
    def test_purchase_journal_numbers_and_sums(self):
        company_currency = self.company_data["currency"]
        journal = self.company_data["default_journal_purchase"]

        self._create_test_vendor_bills(journal)

        dashboard_data = journal._get_journal_dashboard_data_batched()[journal.id]
        # Expected behavior is to have three moves waiting for payment for a total amount of 4440$ one of which would be late
        # for a total amount of 40$ (second move has one of three lines late but that's not enough to make the move late)
        self.assertEqual(3, dashboard_data["number_waiting"])
        self.assertEqual(
            format_amount(self.env, 4440, company_currency),
            dashboard_data["sum_waiting"],
        )
        self.assertEqual(1, dashboard_data["number_late"])
        self.assertEqual(
            format_amount(self.env, 40, company_currency), dashboard_data["sum_late"]
        )

    @freeze_time("2019-01-22")
    def test_customer_invoice_dashboard(self):
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

        # Check Draft
        dashboard_data = journal._get_journal_dashboard_data_batched()[journal.id]

        self.assertEqual(dashboard_data["number_draft"], 2)
        self.assertIn("68.42", dashboard_data["sum_draft"])

        self.assertEqual(dashboard_data["number_waiting"], 0)
        self.assertIn("0.00", dashboard_data["sum_waiting"])

        # Check Both
        invoice.action_post()

        dashboard_data = journal._get_journal_dashboard_data_batched()[journal.id]
        self.assertEqual(dashboard_data["number_draft"], 1)
        self.assertIn(
            "-\N{ZERO WIDTH NO-BREAK SPACE}13.30", dashboard_data["sum_draft"]
        )

        self.assertEqual(dashboard_data["number_waiting"], 1)
        self.assertIn("81.72", dashboard_data["sum_waiting"])

        # Check partial on invoice
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

        # Check waiting payment
        refund.action_post()

        dashboard_data = journal._get_journal_dashboard_data_batched()[journal.id]
        self.assertEqual(dashboard_data["number_draft"], 0)
        self.assertIn("0.00", dashboard_data["sum_draft"])

        self.assertEqual(dashboard_data["number_waiting"], 2)
        self.assertIn("55.12", dashboard_data["sum_waiting"])

        # Check partial on refund
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

    def test_sale_purchase_journal_for_multi_currency_sale(self):
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
    def test_purchase_journal_numbers_and_sums_to_validate(self):
        company_currency = self.company_data["currency"]
        journal = self.company_data["default_journal_purchase"]

        datas = [
            {"invoice_date_due": "2023-04-30"},
            {"invoice_date_due": "2023-04-30", "release_to_pay": "yes"},
            {"invoice_date_due": "2023-04-30", "release_to_pay": "no"},
            {"invoice_date_due": "2023-03-01"},
            {"invoice_date_due": "2023-03-01", "release_to_pay": "yes"},
            {"invoice_date_due": "2023-03-01", "release_to_pay": "no"},
        ]

        for data in datas:
            self.init_invoice(
                "in_invoice",
                invoice_date="2023-03-01",
                post=False,
                amounts=[4000],
                invoice_date_due=data["invoice_date_due"],
                release_to_pay=data.get("release_to_pay"),
            )

        dashboard_data = journal._get_journal_dashboard_data_batched()[journal.id]
        # Four of the six draft bills reach the dashboard: the three already due
        # plus the future-dated one forced to release_to_pay 'yes' — 4 x 4000$.
        self.assertEqual(4, dashboard_data["number_draft"])
        self.assertEqual(
            format_amount(self.env, 16000, company_currency),
            dashboard_data["sum_draft"],
        )

    @freeze_time("2023-03-15")
    def test_draft_purchase_receipts_reach_the_dashboard(self):
        """A draft purchase receipt counts as a draft, as it does without us."""
        # Core counts receipts on both legs, via get_invoice_types(include_receipts=True).
        # This module replaced that query and asked the purchase leg for
        # get_purchase_types(include_receipts=False), so installing it made draft
        # purchase receipts disappear from the dashboard count and sum.
        journal = self.company_data["default_journal_purchase"]

        self.init_invoice(
            "in_receipt",
            invoice_date="2023-03-01",
            post=False,
            amounts=[4000],
            invoice_date_due="2023-03-01",
        )

        dashboard_data = journal._get_journal_dashboard_data_batched()[journal.id]
        self.assertEqual(1, dashboard_data["number_draft"])

    @freeze_time("2023-03-15")
    def test_bills_to_pay_tile_and_its_list_agree(self):
        """The tile's number and the list it opens must be one rule, not two.

        The SQL gate exempts credit notes on purpose -- a credit note is not
        paid, it offsets -- so it counts every posted unpaid refund. The search
        filter the tile links to carried no such exemption and dropped any
        refund whose verdict was 'no', so the number and the list disagreed.
        """
        journal = self.company_data["default_journal_purchase"]

        self.init_invoice(
            "in_invoice",
            invoice_date="2023-03-01",
            post=True,
            amounts=[4000],
            release_to_pay="yes",
        )
        refund = self.init_invoice(
            "in_refund",
            invoice_date="2023-03-01",
            post=True,
            amounts=[4000],
            release_to_pay="no",
        )

        dashboard_data = journal._get_journal_dashboard_data_batched()[journal.id]

        # Read the filter the tile actually opens rather than restating it, so
        # this test fails if the view and the SQL gate drift apart again.
        view = self.env.ref(
            "account_3way_match.account_invoice_filter_inherit_account_3way_match"
        )
        node = etree.fromstring(view.arch_db).xpath("//filter[@name='bills_to_pay']")[0]
        filter_domain = ast.literal_eval(node.get("domain"))
        action = self.env.ref("account.action_move_in_invoice_type")
        opened = self.env["account.move"].search(
            [
                *ast.literal_eval(action.domain),
                *filter_domain,
                ("journal_id", "=", journal.id),
            ]
        )

        self.assertEqual(dashboard_data["number_waiting"], len(opened))
        self.assertIn(refund, opened)

    def test_the_bill_action_still_carries_the_module_search_view(self):
        """open_action was deleted; the XML binding is what supplies the view.

        The override restated a search_view_id that account_invoice_view.xml
        already writes onto the same action record, so removing it must leave
        the binding untouched.
        """
        journal = self.company_data["default_journal_purchase"]
        action = journal.open_action()
        expected = self.env.ref(
            "account_3way_match.account_invoice_filter_inherit_account_3way_match"
        )
        self.assertEqual(action["search_view_id"][0], expected.id)

    def test_uninstall_gives_core_actions_their_search_view_back(self):
        """search_view_id declares no ondelete, so it defaults to `set null`.

        Uninstalling would drop this module's search view and leave both core
        actions with no search view at all, rather than reverting them to the
        one core shipped.
        """
        bill_filter = self.env.ref("account.view_account_bill_filter")
        actions = self.env.ref("account.action_move_in_invoice_type") | self.env.ref(
            "account.action_move_in_refund_type"
        )
        # The module's XML has pointed them at its own search view.
        self.assertNotIn(bill_filter, actions.search_view_id)

        uninstall_hook(self.env)

        for action in actions:
            self.assertEqual(action.search_view_id, bill_filter)

    def test_the_dashboard_gate_asks_the_refund_helper(self):
        """One definition of "which judged documents are refunds", not two.

        _release_to_pay_refund_types() exists so the quantity source, the
        line's own sign and this gate cannot drift. The gate kept its own copy
        of the literal, so widening the judged set would have left it behind --
        the exact drift the helper's docstring warns about. Patching the helper
        must move the gate.
        """
        journal = self.company_data["default_journal_purchase"]
        before = journal._get_to_pay_select()
        self.assertIn("in_invoice", before.params[0])
        self.assertNotIn("in_refund", before.params[0])

        AccountMove = type(self.env["account.move"])
        original = AccountMove._release_to_pay_refund_types
        AccountMove._release_to_pay_refund_types = lambda self: []
        try:
            after = journal._get_to_pay_select()
        finally:
            AccountMove._release_to_pay_refund_types = original

        self.assertIn("in_refund", after.params[0])

    @freeze_time("2023-03-15")
    def test_to_validate_tile_and_its_list_agree(self):
        """The other tile, and the same rule: one count, one list.

        _get_draft_sales_purchases_query gates on payment_state; the filter the
        tile opens did not. A draft bill whose payment is blocked -- and
        action_toggle_block_payment works on a draft -- was shown by the list
        and not counted by the tile.
        """
        journal = self.company_data["default_journal_purchase"]

        self.init_invoice(
            "in_invoice",
            invoice_date="2023-03-01",
            post=False,
            amounts=[4000],
            invoice_date_due="2023-03-01",
        )
        blocked = self.init_invoice(
            "in_invoice",
            invoice_date="2023-03-01",
            post=False,
            amounts=[4000],
            invoice_date_due="2023-03-01",
        )
        blocked.action_toggle_block_payment()
        self.assertEqual(blocked.state, "draft")
        self.assertEqual(blocked.payment_state, "blocked")

        dashboard_data = journal._get_journal_dashboard_data_batched()[journal.id]

        view = self.env.ref(
            "account_3way_match.account_invoice_filter_inherit_account_3way_match"
        )
        node = etree.fromstring(view.arch_db).xpath(
            "//filter[@name='bills_to_validate']"
        )[0]
        action = self.env.ref("account.action_move_in_invoice_type")
        opened = self.env["account.move"].search(
            [
                *ast.literal_eval(action.domain),
                *ast.literal_eval(node.get("domain")),
                ("journal_id", "=", journal.id),
            ]
        )

        self.assertEqual(dashboard_data["number_draft"], len(opened))
        self.assertNotIn(blocked, opened)
