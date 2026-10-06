from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTransactionCurrency(TransactionCase):
    def test_currency_acquisition_restores_identity_and_uses_fallback(self):
        lines = self.env["account.bank.statement.line"]
        currency = self.env["res.currency"].create(
            {"name": "XSC", "symbol": "XSC", "rounding": 0.01, "active": False}
        )
        acquired = lines._acquire_active_currency("xsc", self.env.company.currency_id)
        self.assertEqual(acquired, currency)
        self.assertTrue(currency.active)
        currency.active = False
        self.assertEqual(
            lines._acquire_active_currency("not-a-currency", currency), currency
        )
        self.assertTrue(currency.active)
        self.assertFalse(
            lines._acquire_active_currency("not-a-currency", self.env["res.currency"])
        )

    def test_transaction_data_activates_merchant_currency(self):
        company = self.env.company
        company.country_id = self.env.ref("base.us")
        journal = self.env["account.journal"].new(
            {
                "name": "Card transactions",
                "type": "bank",
                "company_id": company.id,
                "currency_id": company.stripe_currency_id.id,
            }
        )
        card = self.env["hr.expense.stripe.card"].new(
            {"company_id": company.id, "journal_id": journal}
        )
        merchant_currency = self.env["res.currency"].create(
            {"name": "XSC", "symbol": "XSC", "rounding": 0.01, "active": False}
        )
        data = self.env["account.bank.statement.line"]._acquire_transaction_data(
            card, {"amount": 1234, "merchant_amount": 2345, "merchant_currency": "xsc"}
        )
        self.assertEqual(
            data, (12.34, 23.45, journal, company.stripe_currency_id, merchant_currency)
        )
        self.assertTrue(merchant_currency.active)
