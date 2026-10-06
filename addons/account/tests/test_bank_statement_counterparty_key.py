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

    def test_a_match_awaiting_review_teaches_nothing(self):
        for index in range(2):
            self._settled_line(
                "UNREVIEWED %04d" % index, self.partner_a
            ).move_id.checked = False

        st_line = self._create_st_line(100.0, payment_ref="UNREVIEWED 0009")

        self.assertFalse(st_line.partner_id)

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
