from datetime import timedelta

from odoo import Command, fields
from odoo.tests import tagged
from odoo.tools import SQL

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.account.tools.aging import AgingBucket, AgingLadder

LADDER = AgingLadder(
    (
        AgingBucket("current", "Not due", None, 0),
        AgingBucket("b1_30", "1-30", 1, 30),
        AgingBucket("b31_90", "31-90", 31, 90),
        AgingBucket("b91_plus", "91+", 91, None),
    )
)


@tagged("post_install", "-at_install")
class TestAgingLadder(AccountTestInvoicingCommon):
    def test_every_day_falls_in_exactly_one_bucket(self):
        self.assertEqual(LADDER.classify(-5), "current")
        self.assertEqual(LADDER.classify(0), "current")
        self.assertEqual(LADDER.classify(1), "b1_30")
        self.assertEqual(LADDER.classify(30), "b1_30")
        self.assertEqual(LADDER.classify(31), "b31_90")
        self.assertEqual(LADDER.classify(91), "b91_plus")
        self.assertEqual(LADDER.classify(10_000), "b91_plus")

    def test_the_sql_ladder_classifies_as_the_python_one(self):
        for days in (-3, 0, 1, 30, 31, 90, 91, 400):
            [(bucket,)] = self.env.execute_query(
                SQL("SELECT %s", LADDER.case_sql(SQL("%s::int", days)))
            )
            self.assertEqual(bucket, LADDER.classify(days), days)

    def test_a_ladder_with_a_gap_is_refused(self):
        with self.assertRaises(ValueError):
            AgingLadder(
                (
                    AgingBucket("current", "Not due", None, 0),
                    AgingBucket("b2_30", "2-30", 2, None),
                )
            )


@tagged("post_install", "-at_install")
class TestReceivablePosition(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_data_2 = cls.setup_other_company()
        cls.today = fields.Date.today()
        cls.receivable = cls.company_data["default_account_receivable"]
        cls.revenue = cls.company_data["default_account_revenue"]
        cls.contact = cls.env["res.partner"].create(
            {"name": "Buyer", "parent_id": cls.partner_a.id, "type": "contact"}
        )
        cls.key = (cls.partner_a.id, cls.env.company.id)

    def _invoice(self, amount, days_ago, partner=None):
        return self.init_invoice(
            "out_invoice",
            partner=partner or self.partner_a,
            invoice_date=self.today - timedelta(days=days_ago),
            amounts=[amount],
            taxes=[],
            post=True,
        )

    def _entry(self, amount, days_ago, partner, maturity=None):
        date = self.today - timedelta(days=days_ago)
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": date,
                "journal_id": self.company_data["default_journal_misc"].id,
                "line_ids": [
                    Command.create(
                        {
                            "account_id": self.receivable.id,
                            "partner_id": partner.id,
                            "balance": amount,
                            "date_maturity": maturity,
                        }
                    ),
                    Command.create({"account_id": self.revenue.id, "balance": -amount}),
                ],
            }
        )
        move.action_post()
        return move

    def _pay(self, invoice, days_ago):
        receipt = self._entry(-invoice.amount_total, days_ago, self.partner_a)
        (invoice.line_ids | receipt.line_ids).filtered(
            lambda line: line.account_id == self.receivable
        ).reconcile()

    def _position(self, **kwargs):
        positions = self.env["account.move.line"]._read_receivable_position(
            self.partner_a, self.env.company, ladder=LADDER, **kwargs
        )
        return positions.get(self.key)

    def test_the_position_splits_open_into_buckets_overdue_and_unapplied(self):
        self._invoice(1000.0, 45)
        self._invoice(400.0, 0)
        self._entry(-300.0, 5, self.partner_a)

        position = self._position()

        self.assertAlmostEqual(position.open, 1100.0)
        self.assertAlmostEqual(position.unapplied, -300.0)
        self.assertAlmostEqual(position.outstanding, 1400.0)
        self.assertAlmostEqual(position.overdue, 1000.0)
        self.assertEqual(position.oldest_due, self.today - timedelta(days=45))
        self.assertEqual(position.overdue_days(self.today), 45)
        self.assertEqual(position.by_bucket, {"b31_90": 1000.0, "current": 400.0})

    def test_a_contact_owes_through_its_commercial_partner(self):
        self._entry(250.0, 10, self.contact)

        positions = self.env["account.move.line"]._read_receivable_position(
            self.contact, self.env.company
        )

        self.assertEqual(list(positions), [self.key])
        self.assertAlmostEqual(positions[self.key].open, 250.0)

    def test_a_line_without_maturity_is_due_on_its_date(self):
        self._entry(500.0, 100, self.partner_a, maturity=False)

        position = self._position()

        self.assertAlmostEqual(position.overdue, 500.0)
        self.assertEqual(position.by_bucket, {"b91_plus": 500.0})

    def test_as_of_a_past_date_the_position_is_what_was_open_then(self):
        paid = self._invoice(700.0, 60)
        self._pay(paid, 20)
        self._invoice(200.0, 10)
        as_of = self.today - timedelta(days=30)

        self.assertAlmostEqual(self._position().open, 200.0)
        then = self._position(as_of=as_of)
        self.assertAlmostEqual(then.open, 700.0, msg="paid after, invoiced before")
        self.assertAlmostEqual(then.overdue, 700.0)
        self.assertEqual(then.by_bucket, {"b1_30": 700.0})

    def test_another_company_owes_apart(self):
        self.init_invoice(
            "out_invoice",
            partner=self.partner_a,
            invoice_date=self.today,
            amounts=[90.0],
            taxes=[],
            company=self.company_data_2["company"],
            post=True,
        )
        self._invoice(10.0, 0)

        positions = self.env["account.move.line"]._read_receivable_position(
            self.partner_a,
            self.env.company | self.company_data_2["company"],
        )

        self.assertAlmostEqual(positions[self.key].open, 10.0)
        self.assertAlmostEqual(
            positions[self.partner_a.id, self.company_data_2["company"].id].open,
            90.0,
        )

    def test_a_domain_narrows_the_lines(self):
        kept = self._invoice(100.0, 0)
        self._invoice(50.0, 0)

        position = self.env["account.move.line"]._read_receivable_position(
            self.partner_a, self.env.company, domain=[("move_id", "=", kept.id)]
        )[self.key]

        self.assertAlmostEqual(position.open, 100.0)

    def test_a_contact_reads_and_finds_its_company_balance(self):
        self._entry(250.0, 10, self.contact)
        self._invoice(100.0, 0)

        self.assertAlmostEqual(self.partner_a.credit, 350.0)
        self.assertAlmostEqual(self.contact.credit, 350.0)
        found = self.env["res.partner"].search(
            [("credit", ">", 300.0), ("id", "in", (self.partner_a | self.contact).ids)]
        )
        self.assertEqual(found, self.partner_a | self.contact)
        self.assertFalse(
            self.env["res.partner"].search(
                [("credit", ">", 400.0), ("id", "=", self.partner_a.id)]
            )
        )
        self.assertIn(
            self.partner_b,
            self.env["res.partner"].search(
                [("credit", "=", 0.0), ("id", "=", self.partner_b.id)]
            ),
        )
