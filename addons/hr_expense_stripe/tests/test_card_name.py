from odoo.tests import tagged

from .test_authorization_events import StripeCardCase


@tagged("post_install", "-at_install")
class TestCardName(StripeCardCase):
    def _create_card(self, **values):
        return self.env["hr.expense.stripe.card"].create(
            {
                "company_id": self.env.company.id,
                "employee_id": self.expense_employee.id,
                "journal_id": self.stripe_journal.id,
                **values,
            }
        )

    def test_a_card_created_without_a_name_is_named_after_its_employee(self):
        card = self._create_card()
        self.assertEqual(card.name, self.expense_employee.name)

    def test_a_card_created_with_a_name_keeps_it(self):
        card = self._create_card(name="Viáticos")
        self.assertEqual(card.name, "Viáticos")
