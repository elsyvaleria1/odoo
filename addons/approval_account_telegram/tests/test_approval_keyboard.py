from datetime import date

from .common import PaymentApprovalTelegramTestCase


class TestApprovalKeyboard(PaymentApprovalTelegramTestCase):
    def _submitted(self):
        request = self.create_approval_request({"amount": 500.0})
        request.action_confirm()
        return request, request.approver_ids[:1]

    def _callbacks(self, request, approver):
        markup = self.env["telegram.approval.notifier"]._prepare_keyboard(
            approver, request, self.test_bot
        )
        return {
            button.get("callback_data")
            for row in markup["inline_keyboard"]
            for button in row
        }

    def test_a_request_waiting_for_its_bank_line_is_not_approved_from_telegram(self):
        request, approver = self._submitted()

        callbacks = self._callbacks(request, approver)
        review = self.env["telegram.approval.notifier"]._summary_review_lines(
            request, self.env
        )

        self.assertNotIn(f"ar:a:{approver.id}", callbacks)
        self.assertIn(f"ar:r:{approver.id}", callbacks)
        self.assertTrue(any("bank transaction" in line for line in review))

    def test_a_request_with_its_bank_line_is_approved_from_telegram(self):
        request, approver = self._submitted()
        request.bank_statement_line_id = self.create_statement_line(date.today(), 500.0)

        self.assertIn(f"ar:a:{approver.id}", self._callbacks(request, approver))
