from dateutil.relativedelta import relativedelta
from lxml import etree

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install", "loan_audit")
class TestLoanAuditFindings(AccountTestInvoicingCommon):
    """Each test asserts the CORRECT behaviour and therefore fails at HEAD.

    Written 2026-08-23 alongside
    agromarin-knowledge/research/2026-08-23-account-loans-audit.md.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.loan_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "general")], limit=1
        )
        cls.lt = cls._acc("liability_non_current")
        cls.st = cls._acc("liability_current")
        cls.ex = cls._acc("expense")

    @classmethod
    def _acc(cls, account_type):
        return cls.env["account.account"].search(
            [("company_ids", "=", cls.company.id), ("account_type", "=", account_type)],
            limit=1,
        )

    def _accounts(self):
        return {
            "journal_id": self.loan_journal.id,
            "long_term_account_id": self.lt.id,
            "short_term_account_id": self.st.id,
            "expense_account_id": self.ex.id,
        }

    def _loan(self, name, start, count, principal, interest, step_months=1, **kw):
        start = fields.Date.to_date(start)
        return self.env["account.loan"].create(
            {
                "name": name,
                "date": start,
                "duration": count,
                "amount_borrowed": principal * count,
                "interest": interest * count,
                **self._accounts(),
                "line_ids": [
                    Command.create(
                        {
                            "date": start + relativedelta(months=step_months * i),
                            "principal": principal,
                            "interest": interest,
                        }
                    )
                    for i in range(count)
                ],
                **kw,
            }
        )

    def test_short_term_window_is_twelve_months_not_twelve_lines(self):
        loan = self._loan("Quarterly", "2020-01-31", 20, 1000.0, 100.0, step_months=3)
        first = loan.line_ids[0]
        horizon = first.date + relativedelta(years=1)
        due_within_a_year = sum(
            line.principal
            for line in loan.line_ids
            if first.date < line.date <= horizon
        )
        self.assertEqual(
            due_within_a_year, 4000.0, "sanity: 4 quarters follow the first line"
        )
        self.assertEqual(
            first.short_term_theoretical_balance,
            due_within_a_year,
            "short-term balance must cover 12 months, not 12 schedule lines",
        )

    def test_reclassification_entry_covers_twelve_months(self):
        loan = self._loan(
            "QuarterlyPost", "2020-01-31", 20, 1000.0, 100.0, step_months=3
        )
        loan.action_confirm()
        reclass = loan.line_ids[0].generated_move_ids.filtered(
            lambda m: not m.is_loan_payment_move and not m.reversed_entry_id
        )
        moved = sum(
            reclass.line_ids.filtered(lambda l: l.account_id == self.st).mapped(
                "credit"
            )
        )
        self.assertEqual(
            moved, 4000.0, "reclassified amount must be the next 12 months of principal"
        )

    def test_outstanding_balance_of_a_repaid_loan_is_zero(self):
        loan = self._loan("Repaid", "2020-01-01", 12, 1000.0, 100.0)
        loan.action_confirm()
        self.assertEqual(loan.state, "closed", "sanity: a wholly past loan closes")
        self.assertTrue(all(l.is_payment_move_posted for l in loan.line_ids))
        self.assertEqual(
            loan.outstanding_balance,
            0.0,
            "a fully repaid loan owes nothing; the list view sums this field",
        )

    def test_confirming_a_running_loan_is_refused(self):
        loan = self._loan(
            "Reconfirm",
            str(fields.Date.today() - relativedelta(months=6)),
            12,
            1000.0,
            100.0,
        )
        loan.action_confirm()
        self.assertEqual(loan.state, "running")
        before = len(loan.line_ids.generated_move_ids)
        with self.assertRaises(
            UserError, msg="confirming twice must not duplicate the ledger"
        ):
            loan.action_confirm()
        self.assertEqual(len(loan.line_ids.generated_move_ids), before)

    def test_deleting_a_loan_with_posted_entries_is_refused(self):
        loan = self._loan("Deletable", "2020-01-01", 6, 1000.0, 100.0)
        loan.action_confirm()
        posted = loan.line_ids.generated_move_ids.filtered(
            lambda m: m.state == "posted"
        )
        self.assertTrue(posted, "sanity: entries were posted")
        with self.assertRaises(
            UserError, msg="cannot delete a loan linked to posted entries"
        ):
            loan.unlink()

    def test_audit_trail_survives_loan_deletion(self):
        self.company.account_config_id.restrictive_audit_trail = True
        loan = self._loan("Audited", "2020-01-01", 6, 1000.0, 100.0)
        loan.action_confirm()
        move_ids = loan.line_ids.generated_move_ids.ids
        loan.action_cancel()
        self.assertEqual(
            len(self.env["account.move"].browse(move_ids).exists()), len(move_ids)
        )
        try:
            loan.unlink()
        except UserError:
            return
        self.assertEqual(
            len(self.env["account.move"].browse(move_ids).exists()),
            len(move_ids),
            "the FK cascade must not destroy audit-trail-protected entries",
        )

    def test_computed_schedule_is_always_confirmable(self):
        cases = [
            (10000.0, 0.0, 1),
            (1000.0, 1.0, 15),
            (1000.0, 7.0, 20),
            (777.77, 12.0, 15),
        ]
        for amount, rate, term in cases:
            with self.subTest(amount=amount, rate=rate, term=term):
                loan = self.env["account.loan"].create(
                    {"name": f"W{amount}-{rate}-{term}", **self._accounts()}
                )
                self.env["wizard.account.loan.create.schedule"].create(
                    {
                        "loan_id": loan.id,
                        "loan_amount": amount,
                        "interest_rate": rate,
                        "loan_term": term,
                        "start_date": fields.Date.to_date("2024-01-01"),
                        "first_payment_date": fields.Date.to_date("2024-02-01"),
                    }
                ).action_save()
                self.assertEqual(
                    loan.amount_borrowed_difference,
                    0.0,
                    f"principals sum to {sum(loan.line_ids.mapped('principal'))}, not {amount}",
                )

    def test_recomputing_a_schedule_replaces_it(self):
        loan = self.env["account.loan"].create({"name": "Twice", **self._accounts()})
        for _ in range(2):
            self.env["wizard.account.loan.create.schedule"].create(
                {
                    "loan_id": loan.id,
                    "loan_amount": 12000.0,
                    "interest_rate": 5.0,
                    "loan_term": 1,
                    "start_date": fields.Date.to_date("2024-01-01"),
                    "first_payment_date": fields.Date.to_date("2024-02-01"),
                }
            ).action_save()
        self.assertEqual(len(loan.line_ids), 12, "recomputing must replace, not append")
        self.assertEqual(loan.duration, 12)

    def test_zero_header_interest_still_checked_against_lines(self):
        loan = self._loan("NoHeaderInterest", "2020-01-01", 12, 1000.0, 100.0)
        loan.interest = 0.0
        with self.assertRaises(
            UserError, msg="lines carry 1200 of interest; the header says 0"
        ):
            loan.action_confirm()

    def test_is_wrong_date_tracks_line_dates(self):
        loan = self._loan("DateDrift", "2024-06-01", 1, 100.0, 0.0)
        loan.line_ids[0].date = fields.Date.to_date("2024-07-01")
        self.assertFalse(loan.is_wrong_date)
        loan.line_ids[0].date = fields.Date.to_date("2024-01-01")
        self.assertTrue(
            loan.is_wrong_date,
            "moving a line before the loan date must invalidate is_wrong_date",
        )

    def test_preview_computes_over_a_recordset(self):
        loan = self.env["account.loan"].create({"name": "Multi", **self._accounts()})
        wizards = self.env["wizard.account.loan.create.schedule"].create(
            [
                {
                    "loan_id": loan.id,
                    "loan_amount": 1000.0,
                    "interest_rate": 5.0,
                    "loan_term": 1,
                    "start_date": fields.Date.to_date("2024-01-01"),
                    "first_payment_date": fields.Date.to_date("2024-02-01"),
                },
                {
                    "loan_id": loan.id,
                    "loan_amount": 9999.0,
                    "interest_rate": 3.0,
                    "loan_term": 2,
                    "start_date": fields.Date.to_date("2025-01-01"),
                    "first_payment_date": fields.Date.to_date("2025-02-01"),
                },
            ]
        )
        wizards.invalidate_recordset(["preview_line_ids"])
        previews = [w.preview_line_ids.mapped("principal") for w in wizards]
        self.assertNotEqual(
            previews[0], previews[1], "each wizard must preview its own schedule"
        )

    def test_new_loan_inherits_the_most_recent_configuration(self):
        self.env["account.loan"].search([]).unlink()
        other_expense = self.env["account.account"].search(
            [
                ("company_ids", "=", self.company.id),
                ("account_type", "=", "expense"),
                ("id", "!=", self.ex.id),
            ],
            limit=1,
        )
        self._loan("Older", "2019-01-01", 1, 100.0, 0.0)
        newer = self._loan("Newer", "2025-01-01", 1, 100.0, 0.0)
        newer.expense_account_id = other_expense
        defaults = self.env["account.loan"].default_get(["expense_account_id"])
        self.assertEqual(
            defaults["expense_account_id"],
            other_expense.id,
            "defaults must come from the most recent loan, not the oldest",
        )

    def test_sequence_is_unique_and_one_based(self):
        loan = self.env["account.loan"].create(
            {
                "name": "SameDates",
                "date": fields.Date.to_date("2024-01-01"),
                "line_ids": [
                    Command.create(
                        {
                            "date": fields.Date.to_date(d),
                            "principal": p,
                            "interest": 0.0,
                        }
                    )
                    for d, p in [
                        ("2024-01-31", 100.0),
                        ("2024-01-31", 200.0),
                        ("2024-02-29", 300.0),
                    ]
                ],
            }
        )
        sequences = loan.line_ids.mapped("period_number")
        self.assertEqual(
            sorted(sequences), [1, 2, 3], "row numbers must be unique and start at 1"
        )

    def test_interest_rate_precision_is_not_silently_truncated(self):
        loan = self.env["account.loan"].create({"name": "Rate", **self._accounts()})

        def total_interest(rate):
            wizard = self.env["wizard.account.loan.create.schedule"].create(
                {
                    "loan_id": loan.id,
                    "loan_amount": 100000.0,
                    "interest_rate": rate,
                    "loan_term": 20,
                    "start_date": fields.Date.to_date("2024-01-01"),
                    "first_payment_date": fields.Date.to_date("2024-02-01"),
                }
            )
            return sum(float(p.interest) for p in wizard._get_loan_payment_schedule())

        self.assertNotEqual(total_interest(4.5), total_interest(4.57))
        self.assertNotEqual(
            total_interest(4.567),
            total_interest(4.57),
            "4.567% is silently quantized into 4.57%",
        )

    def test_preview_dates_match_the_saved_schedule(self):
        loan = self.env["account.loan"].create({"name": "Tz", **self._accounts()})
        wizard = (
            self.env["wizard.account.loan.create.schedule"]
            .with_context(tz="America/Mexico_City")
            .create(
                {
                    "loan_id": loan.id,
                    "loan_amount": 12000.0,
                    "interest_rate": 5.0,
                    "loan_term": 1,
                    "start_date": fields.Date.to_date("2024-01-15"),
                    "first_payment_date": fields.Date.to_date("2024-02-01"),
                }
            )
        )
        previewed = wizard.preview_line_ids[0].date
        wizard.action_save()
        stored = loan.line_ids[0].date
        self.assertEqual(
            previewed,
            stored,
            f"preview shows {previewed} but {stored} is what gets saved",
        )

    def test_buttons_are_offered_only_to_groups_that_can_use_them(self):
        form = self.env.ref("account_loans.account_loan_form_view")
        arch = etree.fromstring(form.arch)
        buttons = arch.xpath("//header//button[@name and @groups]")
        self.assertTrue(buttons, "sanity: the header has grouped buttons")
        for button in buttons:
            group = self.env.ref(button.get("groups"))
            user = self.env["res.users"].create(
                {
                    "name": group.name,
                    "login": f"probe_{button.get('name')}",
                    "group_ids": [Command.link(group.id)],
                }
            )
            with self.subTest(button=button.get("name"), group=group.name):
                self.assertTrue(
                    self.env["account.loan"].with_user(user).has_access("write"),
                    f"{button.get('name')} is offered to {group.name}, "
                    f"which cannot write account.loan",
                )
