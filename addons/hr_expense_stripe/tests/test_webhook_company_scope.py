from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.hr_expense.tests.common import TestExpenseCommon
from odoo.addons.hr_expense_stripe.controllers.main import StripeIssuingController


@tagged("post_install", "-at_install")
class TestWebhookCompanyScope(TestExpenseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.other_company = cls.company_data_2["company"]

    def _deliver(self, process, event):
        env = self.env(su=True, context={"allowed_company_ids": self.env.company.ids})
        return process(StripeIssuingController(), env, event)

    def _other_company_line(self, stripe_id):
        return self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.company_data_2["default_journal_bank"].id,
                "payment_ref": "Ajena",
                "amount": -10.0,
                "stripe_id": stripe_id,
            }
        )

    def test_a_transaction_update_leaves_another_company_s_line_alone(self):
        self._other_company_line("ipi_other")
        updated = []
        lines = type(self.env["account.bank.statement.line"])

        with patch.object(
            lines,
            "_update_from_stripe_transaction",
            lambda line, tr_object: updated.extend(line.ids),
        ):
            self._deliver(
                StripeIssuingController._process_transaction_event,
                {
                    "type": "issuing_transaction.updated",
                    "data": {
                        "object": {
                            "id": "ipi_other",
                            "authorization": None,
                            "type": "refund",
                        }
                    },
                },
            )

        self.assertEqual(updated, [])

    def test_another_company_s_top_up_does_not_stand_for_this_one(self):
        self._other_company_line("tu_other")
        created = []
        lines = type(self.env["account.bank.statement.line"])

        with patch.object(
            lines,
            "_create_from_stripe_topup",
            lambda model, tu_object: created.append(tu_object["id"]),
        ):
            self._deliver(
                StripeIssuingController._process_topup_event,
                {"data": {"object": {"id": "tu_other"}}},
            )

        self.assertEqual(created, ["tu_other"])

    def test_a_capture_leaves_another_company_s_expense_alone(self):
        employee = (
            self.env["hr.employee"]
            .sudo()
            .create({"name": "Empleado ajeno", "company_id": self.other_company.id})
        )
        self.env["hr.expense"].sudo().with_company(self.other_company).create(
            {
                "name": "Gasto ajeno",
                "employee_id": employee.id,
                "product_id": self.product_c.id,
                "total_amount_currency": 10.0,
                "stripe_transaction_id": "ipi_expense",
            }
        )
        updated, created = [], []
        expenses = type(self.env["hr.expense"])

        with (
            patch.object(
                expenses,
                "_update_from_stripe_transaction",
                lambda expense, tr_object: updated.extend(expense.ids),
            ),
            patch.object(
                expenses,
                "_create_from_stripe_transaction",
                lambda model, tr_object, split_id=False: created.append(
                    tr_object["id"]
                ),
            ),
        ):
            self._deliver(
                StripeIssuingController._process_transaction_event,
                {
                    "type": "issuing_transaction.captured",
                    "data": {
                        "object": {
                            "id": "ipi_expense",
                            "authorization": None,
                            "type": "capture",
                        }
                    },
                },
            )

        self.assertEqual((updated, created), ([], ["ipi_expense"]))
