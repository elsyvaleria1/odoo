from datetime import date, datetime, timedelta
from unittest.mock import patch

from psycopg.errors import CheckViolation, UniqueViolation

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import SQL


@tagged("post_install", "-at_install")
class TestWallet(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.issuer = cls.env["res.partner"].create({"name": "Efectivale"})
        cls.prepaid = cls.env["account.account"].create(
            {
                "name": "Fuel cards prepaid",
                "code": "WAL.PREPAID",
                "account_type": "asset_prepayments",
                "company_ids": [(6, 0, cls.company.ids)],
            }
        )
        cls.expense = cls.env["account.account"].create(
            {
                "name": "Fuel expense",
                "code": "WAL.EXPENSE",
                "account_type": "expense",
                "company_ids": [(6, 0, cls.company.ids)],
            }
        )
        cls.account = cls.env["wallet.account"].create(
            {
                "name": "Efectivale fleet",
                "kind": "fuel",
                "issuer_id": cls.issuer.id,
                "account_id": cls.prepaid.id,
                "amount_threshold_low": 500.0,
            }
        )
        cls.card = cls.env["wallet.card"].create(
            {"number": "1234", "account_id": cls.account.id}
        )

    def _snapshot(self, amount, when=None, card=None):
        return self.env["wallet.balance"].create(
            {
                "card_id": (card or self.card).id,
                "amount_balance": amount,
                "date": when or fields.Datetime.now(),
            }
        )

    def test_a_card_reads_its_latest_snapshot(self):
        now = fields.Datetime.now()
        self._snapshot(900.0, now - timedelta(days=2))
        self._snapshot(300.0, now - timedelta(days=1))
        self._snapshot(700.0, now - timedelta(days=3))
        self.assertEqual(self.card.amount_balance, 300.0)
        self.assertEqual(self.card.date_balance, now - timedelta(days=1))
        self.assertTrue(self.card.is_low_balance)
        self.account.amount_threshold_low = 100.0
        self.assertFalse(self.card.is_low_balance)

    def test_a_card_never_read_is_not_low_until_its_first_balance(self):
        self.assertFalse(self.card.date_balance)
        self.assertFalse(self.card.is_low_balance)
        self._snapshot(120.0)
        self.assertTrue(self.card.is_low_balance)

    def test_the_account_sums_its_cards_and_counts_the_low_ones(self):
        other = self.env["wallet.card"].create(
            {"number": "5678", "account_id": self.account.id}
        )
        self._snapshot(1000.0)
        self._snapshot(100.0, card=other)
        self.account.invalidate_recordset()
        self.assertEqual(self.account.amount_balance, 1100.0)
        self.assertEqual(self.account.count_card_low, 1)

    def test_the_account_dates_its_newest_reading_and_flags_cards_behind(self):
        now = fields.Datetime.now()
        behind = self.env["wallet.card"].create(
            {"number": "5678", "account_id": self.account.id}
        )
        self.env["wallet.card"].create(
            {"number": "9012", "account_id": self.account.id}
        )
        archived = self.env["wallet.card"].create(
            {"number": "3456", "account_id": self.account.id, "active": False}
        )
        self._snapshot(800.0, now - timedelta(hours=1))
        # a card the issuer stopped reporting keeps its old reading
        self._snapshot(200.0, now - timedelta(days=3), card=behind)
        self._snapshot(50.0, now, card=archived)
        self.account.invalidate_recordset()
        self.assertEqual(self.account.date_balance, now - timedelta(hours=1))
        self.assertEqual(self.account.count_card_unread, 1)
        self.assertEqual(self.account.count_card_stale, 1)

    def test_a_card_read_within_the_margin_is_not_behind(self):
        now = fields.Datetime.now()
        other = self.env["wallet.card"].create(
            {"number": "5678", "account_id": self.account.id}
        )
        self._snapshot(800.0, now)
        self._snapshot(200.0, now - timedelta(hours=20), card=other)
        self.account.invalidate_recordset()
        self.assertEqual(self.account.count_card_stale, 0)

    def test_a_balance_summary_adds_only_the_cards_it_read(self):
        now = fields.Datetime.now()
        never_read = self.env["wallet.card"].create(
            {"number": "5678", "account_id": self.account.id}
        )
        behind = self.env["wallet.card"].create(
            {"number": "9012", "account_id": self.account.id}
        )
        # an old import left this card an amount with no reading behind it
        self.env.flush_all()
        self.env.cr.execute(
            SQL(
                "UPDATE wallet_card SET amount_balance = %s WHERE id = %s",
                3588.0,
                never_read.id,
            )
        )
        never_read.invalidate_recordset(["amount_balance"])
        self.assertEqual(never_read.amount_balance, 3588.0)
        self._snapshot(900.0, now - timedelta(hours=2))
        self._snapshot(1500.0, now - timedelta(days=5), card=behind)
        [row] = self.account._get_balance_summary(with_cards=True)
        self.assertEqual(row["account"], self.account)
        self.assertEqual(row["amount_balance"], 2400.0)
        self.assertEqual(row["date_balance"], now - timedelta(hours=2))
        self.assertEqual((row["count_card"], row["count_card_low"]), (3, 0))
        self.assertEqual(row["cards_unread"], never_read)
        self.assertEqual(row["cards_stale"], behind)
        self.assertEqual(row["cards"].ids, [behind.id, self.card.id, never_read.id])

    def test_a_balance_summary_of_an_account_never_read_has_no_date(self):
        tags = self.env["wallet.account"].create(
            {"name": "Toll tags", "kind": "toll", "issuer_id": self.issuer.id}
        )
        tag = self.env["wallet.card"].create({"number": "TAG-1", "account_id": tags.id})
        [row] = tags._get_balance_summary()
        self.assertIsNone(row["date_balance"])
        self.assertEqual(row["amount_balance"], 0.0)
        self.assertEqual(row["cards_unread"], tag)
        self.assertFalse(row["cards_stale"])
        self.assertNotIn("cards", row)

    def test_a_card_number_is_unique_per_account(self):
        with self.assertRaises(UniqueViolation), self.env.cr.savepoint():
            self.env["wallet.card"].create(
                {"number": "1234", "account_id": self.account.id}
            )
            self.env.flush_all()

    def test_a_transaction_reference_is_unique_per_account(self):
        vals = {
            "card_id": self.card.id,
            "amount": 50.0,
            "external_ref": "TX-1",
        }
        self.env["wallet.transaction"].create(vals)
        with self.assertRaises(UniqueViolation), self.env.cr.savepoint():
            self.env["wallet.transaction"].create(vals)
            self.env.flush_all()
        self.env["wallet.transaction"].create({**vals, "external_ref": False})
        self.env["wallet.transaction"].create({**vals, "external_ref": False})

    def test_a_card_sums_what_it_paid(self):
        for amount in (50.0, 25.0, -10.0):
            self.env["wallet.transaction"].create(
                {"card_id": self.card.id, "amount": amount, "place": "Station"}
            )
        self.assertEqual(self.card.amount_spent, 65.0)
        self.assertEqual(self.card.count_transaction, 3)
        transaction = self.card.transaction_ids.sorted("id")[0]
        self.assertTrue(transaction.name.startswith("Station - "))

    def test_a_transaction_is_dated_and_named_in_its_wallet_s_time_zone(self):
        self.account.tz = "America/Mexico_City"
        transaction = self.env["wallet.transaction"].create(
            {
                "card_id": self.card.id,
                "amount": 10.0,
                "place": "Station",
                "date_transaction": datetime(2026, 9, 1, 2, 0),
            }
        )
        self.assertEqual(transaction.date, date(2026, 8, 31))
        self.assertEqual(transaction.name, "Station - 2026-08-31 20:00")
        self.account.tz = "UTC"
        self.assertEqual(transaction.date, date(2026, 9, 1))
        self.assertEqual(transaction.name, "Station - 2026-09-01 02:00")

    def test_a_new_wallet_takes_its_company_s_time_zone(self):
        self.company.partner_id.tz = "America/Tijuana"
        account = self.env["wallet.account"].create(
            {"name": "Toll tags", "kind": "toll", "issuer_id": self.issuer.id}
        )
        self.assertEqual(account.tz, "America/Tijuana")

    def test_the_wallet_account_must_be_a_prepaid_asset(self):
        with self.assertRaises(ValidationError):
            self.account.account_id = self.expense

    def test_a_statement_cannot_end_before_it_starts(self):
        with self.assertRaises(CheckViolation), self.env.cr.savepoint():
            self.env["wallet.statement"].create(
                {
                    "account_id": self.account.id,
                    "date_start": "2026-02-01",
                    "date_end": "2026-01-01",
                }
            )
            self.env.flush_all()

    def test_old_snapshots_are_downsampled_to_one_a_day(self):
        old = fields.Datetime.now() - timedelta(days=120)
        for hour in (8, 12, 18):
            self._snapshot(100.0 + hour, old.replace(hour=hour, minute=0, second=0))
        recent = fields.Datetime.now() - timedelta(days=1)
        for hour in (8, 12):
            self._snapshot(50.0, recent.replace(hour=hour, minute=0, second=0))
        with patch.object(
            type(self.env["ir.cron"]), "_commit_progress", return_value=True
        ):
            removed = self.env["wallet.balance"]._cron_downsample_old_balances()
        self.assertEqual(removed, 2, "two of the three old ones go, the newest stays")
        kept = self.card.balance_ids.filtered(
            lambda b: b.date < old + timedelta(days=1)
        )
        self.assertEqual(kept.mapped("amount_balance"), [118.0])
        self.assertEqual(len(self.card.balance_ids), 3)

    def test_a_wallet_user_reads_and_does_not_write(self):
        user = self.env["res.users"].create(
            {
                "name": "Wallet reader",
                "login": "wallet_reader",
                "group_ids": [(4, self.env.ref("wallet.group_wallet_user").id)],
            }
        )
        self.assertEqual(self.card.with_user(user).number, "1234")
        with self.assertRaises(AccessError):
            self.card.with_user(user).write({"number": "9999"})

    def test_another_company_does_not_see_the_wallet(self):
        other_company = self.env["res.company"].create({"name": "Elsewhere"})
        user = self.env["res.users"].create(
            {
                "name": "Elsewhere manager",
                "login": "wallet_elsewhere",
                "company_id": other_company.id,
                "company_ids": [(6, 0, other_company.ids)],
                "group_ids": [(4, self.env.ref("wallet.group_wallet_manager").id)],
            }
        )
        self.assertFalse(
            self.env["wallet.card"].with_user(user).search([("id", "=", self.card.id)])
        )
