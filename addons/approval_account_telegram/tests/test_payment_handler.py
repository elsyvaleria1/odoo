from unittest.mock import patch

from odoo import Command

from .common import PaymentApprovalTelegramTestCase
from odoo.addons.approval.tests.common import pool_step


class TestPaymentCommand(PaymentApprovalTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.approval_account"]

    def test_pago_command_sets_awaiting_details_state(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response):
            self.handler._handle_payment_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=self.test_user,
            )

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "payment_details")

    def test_pago_command_sends_instructions(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._handle_payment_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=self.test_user,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("8 separate lines", text.lower())


class TestCancelPaymentCommand(PaymentApprovalTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.approval_account"]

    def test_cancel_from_awaiting_details(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "payment_details"
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.env["telegram.router"]._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/cancelar",
                [],
                self.test_partner,
                self.test_user,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("cancelled", text.lower())

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)

    def test_payment_details_from_an_unlinked_account_ends_the_flow(self):
        self.test_chat._flow_start("telegram.handler.approval_account", "payment_details")
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            text=self.get_payment_details_message(),
        )
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                False,
            )

            text = mock_post.call_args.kwargs.get("json", {}).get("text", "")
            self.assertIn("not linked to an internal user", text)

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)

    def test_cancel_from_awaiting_proof(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "payment_proof", {"amount": 1000}
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response):
            self.env["telegram.router"]._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/cancelar",
                [],
                self.test_partner,
                self.test_user,
            )

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)
        self.assertFalse(self.test_chat.flow_data)

    def test_cancel_from_awaiting_confirmation(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "payment_confirm"
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response):
            self.env["telegram.router"]._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/cancelar",
                [],
                self.test_partner,
                self.test_user,
            )

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)

    def test_cancel_when_no_operation(self):
        self.test_chat._flow_end()

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.env["telegram.router"]._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/cancelar",
                [],
                self.test_partner,
                self.test_user,
            )

            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("nothing in progress", text.lower())


class TestPaymentDetailsValidation(PaymentApprovalTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.approval_account"]

    def test_wrong_number_of_lines_rejected(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "payment_details"
        )

        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            text="Only\nThree\nLines",
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("8 lines were expected", text.lower())

    def test_invalid_partner_fx_rejected(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "payment_details"
        )

        details = self.get_payment_details_message(
            partner_fx="NonExistent Partner XYZ123"
        )
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            text=details,
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("no customer matched", text.lower())

    def test_a_typed_name_in_an_error_arrives_as_literal_text(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "payment_details"
        )
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            text=self.get_payment_details_message(partner_fx="Nadie_<x> & *co*"),
        )
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["parse_mode"], "HTML")
        self.assertIn("Nadie_&lt;x&gt; &amp; *co*", payload["text"])
        self.assertNotIn("<x>", payload["text"])

    def test_invalid_category_rejected(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "payment_details"
        )

        details = self.get_payment_details_message(category="InvalidCategory")
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            text=details,
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("product category", text.lower())

    def test_invalid_cfdi_rejected(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "payment_details"
        )

        details = self.get_payment_details_message(cfdi="InvalidCFDI")
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            text=details,
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("cfdi", text.lower())
            self.assertIn(
                "- Invalid CFDI use: 'InvalidCFDI'. "
                "Options: Adquisicion de mercancias (G01), Gastos en general (G03).",
                text,
            )

    def test_invalid_payment_method_rejected(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "payment_details"
        )

        details = self.get_payment_details_message(method="Bitcoin")
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            text=details,
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("payment method", text.lower())

    def test_invalid_date_format_rejected(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "payment_details"
        )

        details = self.get_payment_details_message(payment_date="15-01-2024")
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            text=details,
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("date format", text.lower())

    def test_invalid_amount_rejected(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "payment_details"
        )

        details = self.get_payment_details_message(amount="not-a-number")
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            text=details,
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("amount", text.lower())

    def test_valid_details_transition_to_proof(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "payment_details"
        )

        details = self.get_payment_details_message()
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            text=details,
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("payment receipt", text.lower())

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "payment_proof")
        self.assertTrue(self.test_chat.flow_data)

    def test_cheque_payment_method_accepted(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "payment_details"
        )

        details = self.get_payment_details_message(method="Cheque")
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            text=details,
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response):
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "payment_proof")
        self.assertEqual(self.test_chat.flow_data["payment_method"], "CHEQUE")

    def test_pasted_details_with_zero_width_characters_accepted(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "payment_details"
        )

        details = "\n".join(
            "\ufeff\ufeff\ufeff" + line
            for line in self.get_payment_details_message().split("\n")
        )
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            text=details,
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response):
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "payment_proof")
        self.assertEqual(self.test_chat.flow_data["product_category"], "AGROQUIMICOS")

    def test_trailing_invisible_line_does_not_inflate_the_count(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "payment_details"
        )

        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            text=self.get_payment_details_message() + "\n\ufeff\ufeff\ufeff",
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response):
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "payment_proof")


class TestPaymentProofHandling(PaymentApprovalTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.approval_account"]

        self.test_chat._flow_start("telegram.handler.approval_account", "payment_proof")
        self.test_chat._flow_update(
            {
                "partner_fx_id": self.partner_fx.id,
                "partner_fx_name": self.partner_fx.name,
                "product_category": "AGROQUIMICOS",
                "cfdi_use": "GASTOS EN GENERAL",
                "cfdi_use_code": "G03",
                "payment_method": "TRANSFERENCIA",
                "company": "LMMR",
                "partner_cn_id": self.partner_cn.id,
                "partner_cn_name": self.partner_cn.name,
                "date": "2024-06-15",
                "amount": 1500.50,
            }
        )

    def test_photo_accepted_transitions_to_confirmation(self):
        message = {
            "message_id": 1,
            "chat": {"id": self.test_chat.chat_id},
            "photo": [{"file_id": "photo_file_id", "width": 100, "height": 100}],
        }

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            with patch(
                "odoo.addons.telegram.models.telegram_bot.TelegramBot.get_file_content",
                return_value=b"fake_image_content",
            ):
                self.handler._on_message(
                    self.test_bot,
                    self.test_chat,
                    message,
                    self.test_partner,
                    self.test_user,
                )

                self.assertTrue(mock_post.called)
                payload = mock_post.call_args.kwargs.get("json", {})
                self.assertIn("reply_markup", payload)

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "payment_confirm")

    def test_partner_names_in_the_summary_arrive_as_literal_text(self):
        self.test_chat._flow_update({"partner_cn_name": "Ana_<Bold>*&co"})
        message = {
            "message_id": 1,
            "chat": {"id": self.test_chat.chat_id},
            "photo": [{"file_id": "photo_file_id", "width": 100, "height": 100}],
        }
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with (
            self.mock_api_gateway_post(mock_response) as mock_post,
            patch(
                "odoo.addons.telegram.models.telegram_bot.TelegramBot.get_file_content",
                return_value=b"fake_image_content",
            ),
        ):
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

        text = mock_post.call_args.kwargs["json"]["text"]
        self.assertIn("</b>: Ana_&lt;Bold&gt;*&amp;co", text)
        self.assertNotIn("<Bold>", text)

    def test_pdf_document_accepted(self):
        message = {
            "message_id": 1,
            "chat": {"id": self.test_chat.chat_id},
            "document": {
                "file_id": "pdf_file_id",
                "mime_type": "application/pdf",
                "file_name": "receipt.pdf",
            },
        }

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response):
            with patch(
                "odoo.addons.telegram.models.telegram_bot.TelegramBot.get_file_content",
                return_value=b"fake_pdf_content",
            ):
                self.handler._on_message(
                    self.test_bot,
                    self.test_chat,
                    message,
                    self.test_partner,
                    self.test_user,
                )

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "payment_confirm")

    def test_invalid_document_type_rejected(self):
        message = {
            "message_id": 1,
            "chat": {"id": self.test_chat.chat_id},
            "document": {
                "file_id": "doc_file_id",
                "mime_type": "application/msword",
                "file_name": "receipt.doc",
            },
        }

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("send an image", text.lower())

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "payment_proof")

    def test_text_message_rejected(self):
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            text="Just some text",
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("send an image", text.lower())


class TestConfirmationCallbacks(PaymentApprovalTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.approval_account"]

        self.test_chat._flow_start(
            "telegram.handler.approval_account", "payment_confirm"
        )
        self.test_chat._flow_update(
            {
                "partner_fx_id": self.partner_fx.id,
                "partner_fx_name": self.partner_fx.name,
                "product_category": "AGROQUIMICOS",
                "cfdi_use": "GASTOS EN GENERAL",
                "cfdi_use_code": "G03",
                "payment_method": "TRANSFERENCIA",
                "company": "LMMR",
                "partner_cn_id": self.partner_cn.id,
                "partner_cn_name": self.partner_cn.name,
                "date": "2024-06-15",
                "amount": 1500.50,
                "file_b64": "ZmFrZV9maWxlX2NvbnRlbnQ=",
                "file_mimetype": "image/jpeg",
            }
        )

    def test_cancel_callback_resets_state(self):
        callback = self.mock_telegram_callback_query(
            callback_data="payment_cancel",
            chat_id=self.test_chat.chat_id,
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._on_callback(
                self.test_bot,
                self.test_chat,
                callback,
                self.test_partner,
                self.test_user,
            )

            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("cancelled", text.lower())

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)

    def test_confirm_callback_creates_approval(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        initial_count = self.env["approval.request"].search_count([])

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._confirm_payment_approval(
                self.test_bot,
                self.test_chat,
                self.test_user,
            )

            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("done!", text.lower())

        final_count = self.env["approval.request"].search_count([])
        self.assertEqual(final_count, initial_count + 1)

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)

    def test_a_payment_approval_is_filed_in_the_bot_s_company(self):
        other_company = self.env["res.company"].create(
            {"name": "TG Payment Bot Company"}
        )
        (self.test_user | self.env.ref("base.user_admin")).company_ids = [
            Command.link(other_company.id)
        ]
        category = self.env["approval.category"].create(
            {
                "name": "Bot Company Payment Approval",
                "sequence_code": "TGPAYBOT",
                "has_bsl": "required",
                "has_date": "required",
                "company_id": other_company.id,
                "step_ids": pool_step(
                    [(self.env.ref("base.user_admin").id, True, 10)], minimum=1
                ),
            }
        )
        category.telegram_intake = "payment"
        self.test_bot.company_id = other_company

        with self.mock_api_gateway_post():
            self.handler._confirm_payment_approval(
                self.test_bot, self.test_chat, self.test_user
            )

        approval = self.env["approval.request"].search(
            [("category_id", "=", category.id)]
        )
        self.assertEqual(approval.company_id, other_company)

    def test_confirm_callback_populates_reason(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response):
            self.handler._confirm_payment_approval(
                self.test_bot,
                self.test_chat,
                self.test_user,
            )

        approval = self.env["approval.request"].search(
            [("category_id", "=", self.approval_category.id)],
            order="id desc",
            limit=1,
        )
        self.assertTrue(approval)
        self.assertTrue(approval.reason)
        self.assertIn("<ul>", approval.reason)
        self.assertIn(
            f"<li><strong>Apply Payment To:</strong> {self.partner_cn.name}</li>",
            approval.reason,
        )
        self.assertIn("<li><strong>Amount:</strong> $1,500.50</li>", approval.reason)

    def test_confirm_callback_creates_audit_log(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        initial_count = self.env["telegram.payment.report.log"].search_count([])

        with self.mock_api_gateway_post(mock_response):
            self.handler._confirm_payment_approval(
                self.test_bot,
                self.test_chat,
                self.test_user,
            )

        final_count = self.env["telegram.payment.report.log"].search_count([])
        self.assertEqual(
            final_count,
            initial_count + 1,
            "telegram.payment.report.log row not created on /pago confirm",
        )

        log = self.env["telegram.payment.report.log"].search(
            [], order="id desc", limit=1
        )
        self.assertEqual(log.user_id, self.test_user)
        self.assertEqual(log.telegram_chat_id, self.test_chat.chat_id)
        self.assertTrue(log.approval_request_id)
        self.assertEqual(log.amount, 1500.50)

    def test_confirm_without_category_shows_error(self):
        self.approval_category.telegram_intake = False

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._confirm_payment_approval(
                self.test_bot,
                self.test_chat,
                self.test_user,
            )

            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("has no approval category for payments", text)

    def test_pago_chatter_author_is_internal_user(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response):
            self.handler._confirm_payment_approval(
                self.test_bot,
                self.test_chat,
                self.test_user,
            )

        approval = self.env["approval.request"].search(
            [("category_id", "=", self.approval_category.id)],
            order="id desc",
            limit=1,
        )
        self.assertTrue(approval, "Approval was not created")

        public_partner = self.env.ref("base.public_partner")
        authors = approval.message_ids.mapped("author_id")

        self.assertNotIn(
            public_partner,
            authors,
            "Public user must NOT appear as author of any chatter message",
        )
        self.assertTrue(
            all(m.author_id == self.test_user.partner_id for m in approval.message_ids),
            "Every chatter message must be authored by the internal_user "
            f"partner ({self.test_user.partner_id.name}). "
            f"Got authors: {authors.mapped('name')}",
        )

        notification_authors = approval.message_ids.notification_ids.mapped("author_id")
        self.assertNotIn(
            public_partner,
            notification_authors,
            "Public user must NOT appear as author of any chatter notification",
        )


class TestValidationHelpers(PaymentApprovalTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.approval_account"]

    def test_normalize_string_removes_accents(self):
        self.assertEqual(self.handler._normalize_string("México"), "mexico")
        self.assertEqual(self.handler._normalize_string("Compañía"), "compañia")
        self.assertEqual(self.handler._normalize_string("ÁREA"), "area")

    def test_normalize_string_lowercases(self):
        self.assertEqual(self.handler._normalize_string("HELLO"), "hello")
        self.assertEqual(self.handler._normalize_string("MiXeD"), "mixed")

    def test_normalize_string_drops_invisible_characters(self):
        self.assertEqual(
            self.handler._normalize_string("\ufeffAgroquímicos "), "agroquimicos"
        )
        self.assertEqual(
            self.handler._normalize_string("Transferencia\u200b"), "transferencia"
        )

    def test_normalize_string_folds_no_break_space(self):
        self.assertEqual(
            self.handler._normalize_string("Gastos\u00a0en general"),
            "gastos en general",
        )

    def test_validate_choice_valid(self):
        result = self.handler._resolve_choice_error(
            "agroquimicos", ["agroquimicos", "papas"], "Error message"
        )
        self.assertIsNone(result)

    def test_validate_choice_invalid(self):
        result = self.handler._resolve_choice_error(
            "invalid", ["agroquimicos", "papas"], "Error: invalid option"
        )
        self.assertEqual(result, "Error: invalid option")

    def test_resolve_cfdi_use_by_code(self):
        name, code = self.handler._resolve_cfdi_use("g01")
        self.assertEqual(name, "adquisicion de mercancias")
        self.assertEqual(code, "g01")

    def test_resolve_cfdi_use_by_name(self):
        name, code = self.handler._resolve_cfdi_use("gastos en general")
        self.assertEqual(name, "gastos en general")
        self.assertEqual(code, "g03")

    def test_resolve_cfdi_use_invalid(self):
        name, code = self.handler._resolve_cfdi_use("invalid")
        self.assertIsNone(name)
        self.assertIsNone(code)

    def test_validate_date_valid(self):
        result, error = self.handler._get_date_or_error("2024-06-15", self.env)
        self.assertIsNotNone(result)
        self.assertIsNone(error)
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 6)
        self.assertEqual(result.day, 15)

    def test_validate_date_invalid_format(self):
        result, error = self.handler._get_date_or_error("15-06-2024", self.env)
        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertIn("date format", error.lower())

    def test_validate_amount_valid(self):
        result, error = self.handler._get_amount_or_error("1500.50", self.env)
        self.assertEqual(result, 1500.50)
        self.assertIsNone(error)

    def test_validate_amount_integer(self):
        result, error = self.handler._get_amount_or_error("1000", self.env)
        self.assertEqual(result, 1000.0)
        self.assertIsNone(error)

    def test_validate_amount_invalid(self):
        result, error = self.handler._get_amount_or_error("not-a-number", self.env)
        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertIn("amount", error.lower())

    def test_validate_amount_refuses_what_no_payment_can_carry(self):
        for amount_str in ("-500", "0", "-0.0", "nan", "NaN", "inf", "-inf", "1e400"):
            with self.subTest(amount=amount_str):
                result, error = self.handler._get_amount_or_error(amount_str, self.env)
                self.assertIsNone(result)
                self.assertIn("greater than zero", error)


class TestHelpSections(PaymentApprovalTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.approval_account"]

    def test_help_includes_payment_commands_for_internal_user(self):
        sections = self.handler._get_help_sections(
            self.test_bot,
            self.test_partner,
            self.test_user,
        )

        payment_section = None
        for title, cmds in sections:
            if "Payment Commands" in title:
                payment_section = cmds
                break

        self.assertIsNotNone(payment_section)
        section_text = " ".join(payment_section)
        self.assertIn("/pago", section_text)
        self.assertIn("/cancelar", section_text)

    def test_help_excludes_payment_for_non_internal_user(self):
        sections = self.handler._get_help_sections(
            self.test_bot,
            self.test_partner,
            False,
        )

        for title, _ in sections:
            self.assertNotIn("Payment", title)


class TestHandlerDeclarations(PaymentApprovalTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.approval_account"]

    def test_commands_require_internal_user(self):
        commands = self.handler._telegram_commands()

        self.assertEqual(
            {name: (spec.tier, spec.starts_flow) for name, spec in commands.items()},
            {
                "/pago": ("internal", True),
                "/especie": ("internal", True),
            },
        )

    def test_the_router_routes_the_commands_here(self):
        router = self.env["telegram.router"]
        for command in ("/pago", "/especie"):
            handler, _spec = router._command_owner(self.test_bot, command)
            self.assertEqual(handler._name, "telegram.handler.approval_account")

    def test_buttons_already_sent_keep_their_data(self):
        self.assertEqual(
            set(self.handler._telegram_callback_prefixes()),
            {"payment_confirm", "payment_cancel", "especie_confirm", "especie_cancel"},
        )
        router = self.env["telegram.router"]
        for data in self.handler._telegram_callback_prefixes():
            self.assertEqual(
                router._callback_owner(self.test_bot, data)._name,
                "telegram.handler.approval_account",
            )

    def test_it_takes_no_idle_message(self):
        self.assertFalse(self.handler._telegram_intakes())

    def test_the_generic_cancel_ends_a_payment_record(self):
        self.handler._flow_start(self.test_chat, "payment_proof", {"amount": 1})
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.env["telegram.router"]._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/cancelar",
                [],
                self.test_partner,
                self.test_user,
            )
            text = mock_post.call_args.kwargs.get("json", {}).get("text", "")

        self.assertEqual(text, "Done, I cancelled a payment record.")
        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)


class TestRouting(PaymentApprovalTelegramTestCase):
    def test_pago_through_the_router_opens_the_flow(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response):
            self.env["telegram.router"]._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/pago",
                [],
                self.test_partner,
                self.test_user,
            )

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "payment_details")

    def test_pago_is_refused_to_a_partner_without_user(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.env["telegram.router"]._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/pago",
                [],
                self.test_partner,
                False,
            )
            text = mock_post.call_args.kwargs.get("json", {}).get("text", "")
            self.assertIn("permission", text.lower())

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)

    def test_details_text_goes_to_the_flow_owner(self):
        self.env["telegram.handler.approval_account"]._flow_start(
            self.test_chat, "payment_details"
        )
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            text=self.get_payment_details_message(),
        )
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response):
            self.env["telegram.router"]._dispatch_free_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "payment_proof")

    def test_cancel_button_through_the_router(self):
        self.env["telegram.handler.approval_account"]._flow_start(
            self.test_chat, "payment_confirm", {"amount": 1}
        )
        callback = self.mock_telegram_callback_query(
            callback_data="payment_cancel",
            chat_id=self.test_chat.chat_id,
        )
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.env["telegram.router"]._dispatch_callback_query(
                self.test_bot, callback
            )
            texts = [
                call.kwargs.get("json", {}).get("text", "")
                for call in mock_post.call_args_list
            ]
            self.assertTrue(any("cancelled" in t.lower() for t in texts), texts)

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)

    def test_confirm_button_outside_its_state_is_not_handled(self):
        callback = self.mock_telegram_callback_query(
            callback_data="payment_confirm",
            chat_id=self.test_chat.chat_id,
        )

        self.assertFalse(
            self.env["telegram.handler.approval_account"]._on_callback(
                self.test_bot,
                self.test_chat,
                callback,
                self.test_partner,
                self.test_user,
            )
        )
