from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common_reconcile import TestBankRecWidgetCommon


@tagged("post_install", "-at_install")
class TestBankStatementCounterpartyKey(TestBankRecWidgetCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_data_2 = cls.setup_other_company()

    def _settled_line(self, payment_ref, partner, amount=100.0, **kwargs):
        st_line = self._create_st_line(
            amount, payment_ref=payment_ref, partner_id=partner.id, **kwargs
        )
        _liquidity, suspense, _other = st_line._seek_for_lines()
        st_line.set_account_bank_statement_line(
            suspense.id, self.company_data["default_account_revenue"].id
        )
        self.assertTrue(st_line.is_reconciled)
        return st_line

    def test_key_blanks_the_numbers_and_the_spacing_of_the_label(self):
        cases = [
            (
                "SPEI ENVIADO STP/0000509773  646 0030926TAG",
                "SPEI ENVIADO STP/# # #TAG",
            ),
            (
                "spei enviado stp/0000611200  646 0041026tag",
                "SPEI ENVIADO STP/# # #TAG",
            ),
            ("  NETFLIX  ", "NETFLIX"),
            ("20260930", "#"),
        ]
        for label, expected in cases:
            with self.subTest(label=label):
                st_line = self._create_st_line(-10.0, payment_ref=label)
                self.assertEqual(st_line.counterparty_key, expected)

    def test_key_follows_the_label(self):
        st_line = self._create_st_line(-10.0, payment_ref="ACME 001")
        st_line.payment_ref = "GLOBEX 002"
        self.assertEqual(st_line.counterparty_key, "GLOBEX #")

    def test_two_agreeing_precedents_name_the_partner(self):
        self._settled_line("CARD ACME*SUBSCRIPTION 0001", self.partner_a)
        self._settled_line("CARD ACME*SUBSCRIPTION 0002", self.partner_a)

        st_line = self._create_st_line(100.0, payment_ref="CARD ACME*SUBSCRIPTION 0003")

        self.assertEqual(st_line.partner_id, self.partner_a)

    def test_one_precedent_is_not_enough(self):
        self._settled_line("CARD ACME*SUBSCRIPTION 0001", self.partner_a)

        st_line = self._create_st_line(100.0, payment_ref="CARD ACME*SUBSCRIPTION 0002")

        self.assertFalse(st_line.partner_id)

    def test_disagreeing_precedents_name_nobody(self):
        self._settled_line("TRANSFER 0001 PAYMENT", self.partner_a)
        self._settled_line("TRANSFER 0002 PAYMENT", self.partner_a)
        self._settled_line("TRANSFER 0003 PAYMENT", self.partner_b)

        st_line = self._create_st_line(100.0, payment_ref="TRANSFER 0004 PAYMENT")

        self.assertFalse(
            st_line.partner_id,
            "a label two parties share identifies neither of them",
        )

    def test_only_the_latest_precedents_are_read(self):
        self._settled_line("RENT 0001", self.partner_b)
        for index in range(2, 5):
            self._settled_line("RENT %04d" % index, self.partner_a)

        st_line = self._create_st_line(100.0, payment_ref="RENT 0005")

        self.assertEqual(
            st_line.partner_id,
            self.partner_a,
            "the counterparty behind a label may change; the recent ones decide",
        )

    def test_an_open_precedent_teaches_nothing(self):
        for index in range(2):
            self._create_st_line(
                100.0, payment_ref="OPEN %04d" % index, partner_id=self.partner_a.id
            )

        st_line = self._create_st_line(100.0, payment_ref="OPEN 0009")

        self.assertFalse(
            st_line.partner_id,
            "a partner nobody confirmed by settling the transaction is a guess",
        )
        self.assertSuggestion(st_line, self.env["res.partner"], False)

    def _unreviewed_line(self, payment_ref, partner, **kwargs):
        st_line = self._settled_line(payment_ref, partner, **kwargs)
        st_line.move_id.checked = False
        return st_line

    def assertSuggestion(self, st_line, partner, source):
        self.assertEqual(
            (st_line.suggested_partner_id, st_line.partner_suggestion_source),
            (partner, source),
        )

    def test_a_match_awaiting_review_only_suggests_its_partner(self):
        for index in range(2):
            self._unreviewed_line("UNREVIEWED %04d" % index, self.partner_a)

        st_line = self._create_st_line(100.0, payment_ref="UNREVIEWED 0009")

        self.assertFalse(st_line.partner_id)
        self.assertSuggestion(st_line, self.partner_a, "counterparty_unreviewed")

    def test_an_unreviewed_precedent_by_name_only_suggests_its_partner(self):
        self._unreviewed_line("ANYTHING 1", self.partner_b, partner_name="QQX NAMED CO")

        st_line = self._create_st_line(
            100.0, payment_ref="OTHER 2", partner_name="QQX NAMED CO"
        )

        self.assertFalse(st_line.partner_id)
        self.assertSuggestion(st_line, self.partner_b, "name_precedent_unreviewed")

    def test_reviewed_precedents_apply_the_partner_and_suggest_nothing(self):
        self._settled_line("REVIEWED 0001", self.partner_a)
        self._settled_line("REVIEWED 0002", self.partner_a)

        st_line = self._create_st_line(100.0, payment_ref="REVIEWED 0003")

        self.assertEqual(st_line.partner_id, self.partner_a)
        self.assertSuggestion(st_line, self.env["res.partner"], False)

    def test_one_unreviewed_precedent_suggests_nothing_by_label(self):
        self._unreviewed_line("LONE GUESS 0001", self.partner_a)

        st_line = self._create_st_line(100.0, payment_ref="LONE GUESS 0002")

        self.assertSuggestion(st_line, self.env["res.partner"], False)

    def test_a_suggestion_is_never_matched(self):
        invoice_line = self._create_invoice_line(
            "out_invoice",
            partner_id=self.partner_a.id,
            invoice_line_ids=[{"price_unit": 432.10}],
        )
        partner_model = self._create_reconcile_model(
            trigger="auto_reconcile",
            match_partner_ids=[Command.set(self.partner_b.ids)],
            line_ids=[{}],
        )
        for index in range(2):
            self._unreviewed_line("CUSTOMER WIRE %04d" % index, self.partner_a)
            self._unreviewed_line("SUPPLIER REFUND %04d" % index, self.partner_b)

        by_amount = self._create_st_line(432.10, payment_ref="CUSTOMER WIRE 0009")
        by_model = self._create_st_line(55.0, payment_ref="SUPPLIER REFUND 0009")
        (by_amount + by_model)._try_auto_reconcile_statement_lines()

        self.assertSuggestion(by_amount, self.partner_a, "counterparty_unreviewed")
        self.assertSuggestion(by_model, self.partner_b, "counterparty_unreviewed")
        self.assertFalse((by_amount + by_model).partner_id)
        self.assertFalse(by_amount.is_reconciled)
        self.assertFalse(by_model.is_reconciled)
        self.assertFalse(invoice_line.reconciled)
        self.assertFalse(by_model.line_ids.reconcile_model_id)

        (by_amount + by_model).action_accept_partner_suggestion()

        self.assertEqual(by_amount.partner_id, self.partner_a)
        self.assertEqual(by_model.partner_id, self.partner_b)
        self.assertSuggestion(by_amount, self.env["res.partner"], False)
        self.assertSuggestion(by_model, self.env["res.partner"], False)
        self.assertTrue(invoice_line.reconciled)
        self.assertTrue(by_amount.is_reconciled)
        self.assertEqual(by_model.line_ids.reconcile_model_id, partner_model)

    def test_setting_a_partner_clears_the_suggestion(self):
        for index in range(2):
            self._unreviewed_line("CLEAR ME %04d" % index, self.partner_a)
        typed, picked = (
            self._create_st_line(100.0, payment_ref="CLEAR ME 0008"),
            self._create_st_line(100.0, payment_ref="CLEAR ME 0009"),
        )
        self.assertSuggestion(typed, self.partner_a, "counterparty_unreviewed")
        self.assertSuggestion(picked, self.partner_a, "counterparty_unreviewed")

        typed.partner_id = self.partner_b
        picked.set_partner_bank_statement_line(self.partner_b.id)

        self.assertEqual((typed + picked).partner_id, self.partner_b)
        self.assertSuggestion(typed, self.env["res.partner"], False)
        self.assertSuggestion(picked, self.env["res.partner"], False)

    def test_a_suggestion_follows_the_precedents(self):
        precedents = self._unreviewed_line("MOVING 0001", self.partner_a)
        precedents += self._unreviewed_line("MOVING 0002", self.partner_a)
        st_line = self._create_st_line(100.0, payment_ref="MOVING 0009")
        self.assertSuggestion(st_line, self.partner_a, "counterparty_unreviewed")

        self._unreviewed_line("MOVING 0003", self.partner_b)
        st_line._try_auto_reconcile_statement_lines()
        self.assertSuggestion(st_line, self.env["res.partner"], False)

        precedents.move_id.checked = True
        self._settled_line("MOVING 0004", self.partner_a)
        self._settled_line("MOVING 0005", self.partner_a)
        st_line._try_auto_reconcile_statement_lines()
        self.assertEqual(st_line.partner_id, self.partner_a)
        self.assertSuggestion(st_line, self.env["res.partner"], False)

    def test_accepting_without_a_suggestion_changes_nothing(self):
        st_line = self._create_st_line(100.0, payment_ref="NOTHING TO ACCEPT")

        st_line.action_accept_partner_suggestion()

        self.assertFalse(st_line.partner_id)

    def test_unreviewed_precedents_of_another_company_suggest_nothing(self):
        other = self.company_data_2
        for index in range(2):
            st_line = (
                self.env["account.bank.statement.line"]
                .with_company(other["company"])
                .create(
                    {
                        "journal_id": other["default_journal_bank"].id,
                        "date": "2019-01-01",
                        "payment_ref": "OTHER BOOKS %04d" % index,
                        "partner_name": "QQX ELSEWHERE",
                        "partner_id": self.partner_a.id,
                        "amount": 100.0,
                    }
                )
            )
            _liquidity, suspense, _other = st_line._seek_for_lines()
            st_line.set_account_bank_statement_line(
                suspense.id, other["default_account_revenue"].id
            )
            st_line.move_id.checked = False

        here = self._create_st_line(
            100.0, payment_ref="OTHER BOOKS 0009", partner_name="QQX ELSEWHERE"
        )
        there = (
            self.env["account.bank.statement.line"]
            .with_company(other["company"])
            .create(
                {
                    "journal_id": other["default_journal_bank"].id,
                    "date": "2019-01-01",
                    "payment_ref": "OTHER BOOKS 0009",
                    "partner_name": "QQX ELSEWHERE",
                    "amount": 100.0,
                }
            )
        )

        self.assertSuggestion(here, self.env["res.partner"], False)
        self.assertSuggestion(there, self.partner_a, "name_precedent_unreviewed")

    def test_precedents_of_another_company_are_not_read(self):
        other = self.company_data_2
        journal = other["default_journal_bank"]
        for index in range(2):
            st_line = (
                self.env["account.bank.statement.line"]
                .with_company(other["company"])
                .create(
                    {
                        "journal_id": journal.id,
                        "date": "2019-01-01",
                        "payment_ref": "SHARED LABEL %04d" % index,
                        "partner_id": self.partner_a.id,
                        "amount": 100.0,
                    }
                )
            )
            _liquidity, suspense, _other = st_line._seek_for_lines()
            st_line.set_account_bank_statement_line(
                suspense.id, other["default_account_revenue"].id
            )

        st_line = self._create_st_line(100.0, payment_ref="SHARED LABEL 0009")

        self.assertFalse(st_line.partner_id)

    def test_a_waiting_line_learns_its_partner_on_a_later_run(self):
        waiting = self._create_st_line(100.0, payment_ref="LATE LEARNER 0001")
        self.assertFalse(waiting.partner_id)
        self._settled_line("LATE LEARNER 0002", self.partner_a)
        self._settled_line("LATE LEARNER 0003", self.partner_a)

        waiting._try_auto_reconcile_statement_lines()

        self.assertEqual(waiting.partner_id, self.partner_a)

    def test_a_partner_already_set_is_kept(self):
        self._settled_line("KEEP MINE 0001", self.partner_a)
        self._settled_line("KEEP MINE 0002", self.partner_a)

        st_line = self._create_st_line(
            100.0, payment_ref="KEEP MINE 0003", partner_id=self.partner_b.id
        )
        st_line._try_auto_reconcile_statement_lines()

        self.assertEqual(st_line.partner_id, self.partner_b)

    def _open_line(self, payment_ref, partner, **kwargs):
        st_line = self._create_st_line(100.0, payment_ref=payment_ref, **kwargs)
        st_line.partner_id = partner
        self.assertTrue(st_line.is_partner_manual)
        self.assertFalse(st_line.is_reconciled)
        return st_line

    def test_an_open_line_partnered_by_hand_only_suggests_its_partner(self):
        invoice_line = self._create_invoice_line(
            "out_invoice",
            partner_id=self.partner_a.id,
            invoice_line_ids=[{"price_unit": 765.40}],
        )
        for index in range(2):
            self._open_line("HAND WIRE %04d" % index, self.partner_a)

        st_line = self._create_st_line(765.40, payment_ref="HAND WIRE 0009")
        st_line._try_auto_reconcile_statement_lines()

        self.assertFalse(st_line.partner_id)
        self.assertSuggestion(st_line, self.partner_a, "counterparty_open")
        self.assertFalse(st_line.is_reconciled)
        self.assertFalse(invoice_line.reconciled)

        st_line.action_accept_partner_suggestion()

        self.assertEqual(st_line.partner_id, self.partner_a)
        self.assertTrue(st_line.is_partner_manual)
        self.assertTrue(invoice_line.reconciled)

    def test_an_open_line_partnered_by_hand_suggests_by_name(self):
        self._open_line("ANYTHING 1", self.partner_b, partner_name="QQX HAND NAMED")

        st_line = self._create_st_line(
            100.0, payment_ref="OTHER 2", partner_name="QQX HAND NAMED"
        )

        self.assertFalse(st_line.partner_id)
        self.assertSuggestion(st_line, self.partner_b, "name_precedent_open")

    def test_one_open_line_suggests_nothing_by_label(self):
        self._open_line("LONE HAND 0001", self.partner_a)

        st_line = self._create_st_line(100.0, payment_ref="LONE HAND 0002")

        self.assertSuggestion(st_line, self.env["res.partner"], False)

    def test_open_lines_disagreeing_suggest_nobody(self):
        self._open_line("SPLIT HAND 0001", self.partner_a)
        self._open_line("SPLIT HAND 0002", self.partner_a)
        self._open_line("SPLIT HAND 0003", self.partner_b)

        st_line = self._create_st_line(100.0, payment_ref="SPLIT HAND 0009")

        self.assertSuggestion(st_line, self.env["res.partner"], False)

    def test_an_unreviewed_match_outranks_open_lines(self):
        for index in range(2):
            self._open_line("RANKED %04d" % index, self.partner_b)
            self._unreviewed_line("RANKED %04d" % (index + 2), self.partner_a)

        st_line = self._create_st_line(100.0, payment_ref="RANKED 0009")

        self.assertFalse(st_line.partner_id)
        self.assertSuggestion(st_line, self.partner_a, "counterparty_unreviewed")

    def test_a_reviewed_match_outranks_open_lines(self):
        for index in range(2):
            self._open_line("TRUSTED %04d" % index, self.partner_b)
            self._settled_line("TRUSTED %04d" % (index + 2), self.partner_a)

        st_line = self._create_st_line(100.0, payment_ref="TRUSTED 0009")

        self.assertEqual(st_line.partner_id, self.partner_a)
        self.assertSuggestion(st_line, self.env["res.partner"], False)

    def test_open_lines_of_another_company_suggest_nothing(self):
        other = self.company_data_2
        StatementLine = self.env["account.bank.statement.line"].with_company(
            other["company"]
        )
        for index in range(2):
            StatementLine.create(
                {
                    "journal_id": other["default_journal_bank"].id,
                    "date": "2019-01-01",
                    "payment_ref": "OTHER HANDS %04d" % index,
                    "amount": 100.0,
                }
            ).partner_id = self.partner_a

        here = self._create_st_line(100.0, payment_ref="OTHER HANDS 0009")
        there = StatementLine.create(
            {
                "journal_id": other["default_journal_bank"].id,
                "date": "2019-01-01",
                "payment_ref": "OTHER HANDS 0009",
                "amount": 100.0,
            }
        )

        self.assertSuggestion(here, self.env["res.partner"], False)
        self.assertSuggestion(there, self.partner_a, "counterparty_open")

    def test_a_batch_does_not_teach_itself(self):
        self.env["res.partner.bank.account"].create(
            {"acc_number": "QQX0042", "partner_id": self.partner_a.id}
        )
        batch = self.env["account.bank.statement.line"].create(
            [
                {
                    "journal_id": self.company_data["default_journal_bank"].id,
                    "date": "2019-01-01",
                    "payment_ref": "SAME FEED %04d" % index,
                    "amount": 100.0,
                    **extra,
                }
                for index, extra in enumerate(
                    [
                        {"account_number": "QQX0042"},
                        {"account_number": "QQX0042"},
                        {"partner_id": self.partner_a.id},
                        {"partner_id": self.partner_a.id},
                        {},
                    ]
                )
            ]
        )
        *partnered, asking = batch

        self.assertEqual(
            self.env["account.bank.statement.line"].union(*partnered).partner_id,
            self.partner_a,
        )
        self.assertFalse(batch.filtered("is_partner_manual"))
        self.assertFalse(asking.partner_id)
        self.assertSuggestion(asking, self.env["res.partner"], False)

    def test_a_partner_spread_by_name_is_not_set_by_hand(self):
        chosen, sibling = (
            self._create_st_line(
                100.0, payment_ref="SPREAD %04d" % index, partner_name="QQX SPREAD"
            )
            for index in range(2)
        )

        chosen.set_partner_bank_statement_line(self.partner_a.id)

        self.assertEqual(sibling.partner_id, self.partner_a)
        self.assertTrue(chosen.is_partner_manual)
        self.assertFalse(sibling.is_partner_manual)
        st_line = self._create_st_line(100.0, payment_ref="SPREAD 0009")
        self.assertSuggestion(st_line, self.env["res.partner"], False)

    def test_clearing_the_partner_unmarks_it(self):
        st_line = self._open_line("CLEARED 0001", self.partner_a)

        st_line.partner_id = False

        self.assertFalse(st_line.is_partner_manual)

    def test_a_partner_mapped_by_a_model_is_not_set_by_hand(self):
        mapping = self._create_reconcile_model(
            match_label="contains",
            match_label_param="QQXMAPPED",
            line_ids=[{"account_id": False, "partner_id": self.partner_a.id}],
        )
        mapped = self._create_st_line(100.0, payment_ref="QQXMAPPED 0001")
        mapped += self._create_st_line(100.0, payment_ref="QQXMAPPED 0002")
        mapped._try_auto_reconcile_statement_lines()
        self.assertEqual(mapped.partner_id, self.partner_a)
        self.assertFalse(mapped.filtered("is_partner_manual"))
        mapping.active = False

        st_line = self._create_st_line(100.0, payment_ref="QQXMAPPED 0009")

        self.assertSuggestion(st_line, self.env["res.partner"], False)
