from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestPaymentLineRoles(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.receivable = cls.company_data["default_account_receivable"]

    def _payment(self, post=True, **vals):
        payment = self.env["account.payment"].create(
            {
                "amount": 100.0,
                "date": "2026-08-01",
                "partner_id": self.partner_a.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "journal_id": self.bank_journal.id,
                **vals,
            }
        )
        if post:
            payment.action_post()
        return payment

    def _roles(self, payment):
        return sorted(
            (line.payment_role, line.account_id.id, line.balance)
            for line in payment.move_id.line_ids
        )

    def test_generated_lines_carry_their_role(self):
        payment = self._payment()

        self.assertEqual(
            self._roles(payment),
            [
                ("counterpart", self.receivable.id, -100.0),
                ("liquidity", payment.outstanding_account_id.id, 100.0),
            ],
        )
        liquidity, counterpart, other = payment._seek_for_lines()
        self.assertEqual(liquidity.payment_role, "liquidity")
        self.assertEqual(counterpart.payment_role, "counterpart")
        self.assertFalse(other)

    def test_write_off_on_a_receivable_account_stays_a_write_off(self):
        second_receivable = self.copy_account(self.receivable)
        payment = self.env["account.payment"].create(
            {
                "amount": 90.0,
                "date": "2026-08-01",
                "partner_id": self.partner_a.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "journal_id": self.bank_journal.id,
                "write_off_line_vals": [
                    {
                        "name": "discount",
                        "account_id": second_receivable.id,
                        "partner_id": self.partner_a.id,
                        "currency_id": self.company_data["currency"].id,
                        "amount_currency": 10.0,
                        "balance": 10.0,
                    }
                ],
            }
        )

        payment.date = "2026-08-02"

        self.assertEqual(
            sorted(
                (line.account_id.id, line.balance) for line in payment.move_id.line_ids
            ),
            sorted(
                [
                    (self.receivable.id, -100.0),
                    (payment.outstanding_account_id.id, 90.0),
                    (second_receivable.id, 10.0),
                ]
            ),
        )
