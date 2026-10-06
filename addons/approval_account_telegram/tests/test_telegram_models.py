from .common import PaymentApprovalTelegramTestCase


class TestTelegramBotPaymentFields(PaymentApprovalTelegramTestCase):
    def test_payment_approval_category_field_exists(self):
        self.assertTrue(hasattr(self.test_bot, "payment_approval_category_id"))

    def test_payment_approval_category_assigned(self):
        self.assertEqual(
            self.test_bot.payment_approval_category_id, self.approval_category
        )

    def test_has_pago_command_true_when_enabled(self):
        self.assertTrue(self.test_bot.has_pago_command)

    def test_has_pago_command_false_when_disabled(self):
        self.test_bot.write({"command_ids": [(3, self.pago_command.id)]})

        self.assertFalse(self.test_bot.has_pago_command)

    def test_has_pago_command_recomputes_on_change(self):
        self.assertTrue(self.test_bot.has_pago_command)

        self.test_bot.write({"command_ids": [(3, self.pago_command.id)]})
        self.assertFalse(self.test_bot.has_pago_command)

        self.test_bot.write({"command_ids": [(4, self.pago_command.id)]})
        self.assertTrue(self.test_bot.has_pago_command)


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
