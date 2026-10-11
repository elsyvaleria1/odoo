from odoo.tests import tagged

from odoo.addons.hr_expense.tests.common import TestExpenseCommon


class StripeCardCase(TestExpenseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        company.stripe_id = "acct_test"
        cls.stripe_journal = cls.env["account.journal"].create(
            {
                "name": "Stripe Issuing",
                "code": "STRI",
                "type": "bank",
                "company_id": company.id,
                "currency_id": company.stripe_currency_id.id,
            }
        )
        cls.card = cls.env["hr.expense.stripe.card"].create(
            {
                "name": "Tarjeta",
                "stripe_id": "ic_test",
                "company_id": company.id,
                "employee_id": cls.expense_employee.id,
                "journal_id": cls.stripe_journal.id,
            }
        )

    def _authorization(self, status, amount, **values):
        currency = self.card.currency_id.name.lower()
        return {
            "id": "iauth_test",
            "card": {"id": self.card.stripe_id},
            "status": status,
            "amount": amount,
            "merchant_amount": amount,
            "merchant_currency": currency,
            "pending_request": None,
            "merchant_data": {"name": "Ferretería", "category_code": "hardware_stores"},
            "metadata": {},
            **values,
        }

    def _expenses(self):
        return self.env["hr.expense"].search(
            [("stripe_authorization_id", "=", "iauth_test")]
        )


@tagged("post_install", "-at_install")
class TestAuthorizationEvents(StripeCardCase):
    def _ingest(self, auth_object, refusal_reason=None):
        expenses = self.env["hr.expense"].with_env(
            self.env(su=True, context={"allowed_company_ids": self.env.company.ids})
        )
        return expenses._create_from_stripe_authorization(auth_object, refusal_reason)

    def test_a_pending_authorization_s_update_reaches_its_expense(self):
        expense = self._ingest(self._authorization("pending", 1000))
        self.assertEqual(expense.total_amount_currency, 10.0)

        updated = self._ingest(self._authorization("pending", 2500))

        self.assertEqual(expense.total_amount_currency, 25.0)
        self.assertEqual((updated, self._expenses()), (expense, expense))

    def test_a_declined_authorization_s_notice_keeps_its_refused_expense(self):
        declined = self._authorization(
            "closed", 0, pending_request={"amount": 4000, "merchant_currency": "usd"}
        )
        expense = self._ingest(declined, "Over the limit")
        self.assertEqual(
            (expense.state, expense.total_amount_currency), ("refused", 40.0)
        )

        again = self._ingest({**declined, "pending_request": None}, "Over the limit")

        self.assertEqual((again, self._expenses()), (expense, expense))
        self.assertEqual(
            (expense.state, expense.total_amount_currency), ("refused", 40.0)
        )
