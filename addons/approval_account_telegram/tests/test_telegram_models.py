from psycopg import IntegrityError

from odoo.tools import mute_logger

from .common import PaymentApprovalTelegramTestCase


class TestTelegramIntakeCategory(PaymentApprovalTelegramTestCase):
    def test_a_company_s_own_category_comes_before_one_of_no_company(self):
        shared = self.env["approval.category"].create(
            {
                "name": "Shared Payments",
                "sequence_code": "TGSHARED",
                "company_id": False,
            }
        )
        categories = self.env["approval.category"]
        self.approval_category.telegram_intake = False
        shared.telegram_intake = "payment"
        self.assertEqual(
            categories._get_telegram_intake_category("payment", self.company), shared
        )

        self.approval_category.telegram_intake = "payment"
        self.assertEqual(
            categories._get_telegram_intake_category("payment", self.company),
            self.approval_category,
        )

    def test_a_company_has_one_category_per_command(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.db.cursor"):
            self.env["approval.category"].create(
                {
                    "name": "Second Payments",
                    "sequence_code": "TGSECOND",
                    "company_id": self.company.id,
                    "telegram_intake": "payment",
                }
            )


class TestPaymentFlow(PaymentApprovalTelegramTestCase):
    def _handler(self):
        return self.env["telegram.handler.approval_account"]

    def test_the_flow_is_named_by_what_is_being_recorded(self):
        handler = self._handler()
        handler._flow_start(self.test_chat, "payment_proof")
        self.assertEqual(
            handler._telegram_flow_label(self.test_bot, self.test_chat),
            "a payment record",
        )
        handler._flow_start(self.test_chat, "especie_proof")
        self.assertEqual(
            handler._telegram_flow_label(self.test_bot, self.test_chat),
            "a payment in kind",
        )

    def test_the_flow_keeps_the_validated_details(self):
        data = {
            "partner_fx_id": 1,
            "partner_fx_name": "Test Partner",
            "amount": 1500.50,
        }

        self._handler()._flow_start(self.test_chat, "payment_proof", data)

        self.assertEqual(self._handler()._flow_data(self.test_chat), data)

    def test_ending_the_flow_as_internal_user_clears_its_data(self):
        self._handler()._flow_start(self.test_chat, "payment_confirm", {"amount": 1000})

        self._handler().with_user(self.test_user)._flow_end(
            self.test_chat.with_user(self.test_user)
        )

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)
        self.assertFalse(self.test_chat.flow_data)

    def test_a_new_chat_has_no_flow(self):
        chat = self.env["telegram.chat"].create(
            {
                "chat_id": "99999",
                "bot_id": self.test_bot.id,
            }
        )

        self.assertFalse(chat.flow_owner)
        self.assertFalse(chat.flow_data)
