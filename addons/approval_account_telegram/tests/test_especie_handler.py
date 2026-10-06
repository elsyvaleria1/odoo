from unittest.mock import patch

from .common import PaymentApprovalTelegramTestCase


class TestEspecieCommand(PaymentApprovalTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.approval_account"]

    def test_especie_command_sets_state(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response):
            self.handler._handle_especie_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=self.test_user,
            )

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "especie_details")


class TestEspecieDetailsValidation(PaymentApprovalTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.approval_account"]

    def test_especie_valid_6_lines(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "especie_details"
        )

        details = self.get_especie_details_message()
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
            self.assertIn("as evidence", text.lower())

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "especie_proof")
        self.assertTrue(self.test_chat.flow_data)

    def test_especie_pasted_details_with_zero_width_characters_accepted(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "especie_details"
        )

        details = "\n".join(
            "\ufeff\ufeff\ufeff" + line
            for line in self.get_especie_details_message().split("\n")
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
        self.assertEqual(self.test_chat.flow_step, "especie_proof")

    def test_especie_wrong_line_count(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "especie_details"
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
            self.assertIn("6 lines were expected", text.lower())

    def test_especie_invalid_partner(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "especie_details"
        )

        details = self.get_especie_details_message(
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

    def test_especie_invalid_category(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "especie_details"
        )

        details = self.get_especie_details_message(category="Maquinaria")
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

    def test_especie_invalid_date(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "especie_details"
        )

        details = self.get_especie_details_message(especie_date="15-01-2024")
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

    def test_especie_invalid_amount(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_account", "especie_details"
        )

        details = self.get_especie_details_message(amount="not-a-number")
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


class TestEspecieProofHandling(PaymentApprovalTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.approval_account"]

        self.test_chat._flow_start("telegram.handler.approval_account", "especie_proof")
        self.test_chat._flow_update(
            {
                "partner_fx_id": self.partner_fx.id,
                "partner_fx_name": self.partner_fx.name,
                "product_category": "VEHICULOS",
                "partner_cn_id": self.partner_cn.id,
                "partner_cn_name": self.partner_cn.name,
                "date": "2024-06-15",
                "amount": 1500.50,
                "product_reference": "174",
            }
        )

    def test_especie_photo_accepted(self):
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
        self.assertEqual(self.test_chat.flow_step, "especie_confirm")

    def test_especie_pdf_accepted(self):
        message = {
            "message_id": 1,
            "chat": {"id": self.test_chat.chat_id},
            "document": {
                "file_id": "pdf_file_id",
                "mime_type": "application/pdf",
                "file_name": "asset.pdf",
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
        self.assertEqual(self.test_chat.flow_step, "especie_confirm")


class TestEspecieConfirmation(PaymentApprovalTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.approval_account"]

        self.test_chat._flow_start(
            "telegram.handler.approval_account", "especie_confirm"
        )
        self.test_chat._flow_update(
            {
                "partner_fx_id": self.partner_fx.id,
                "partner_fx_name": self.partner_fx.name,
                "product_category": "VEHICULOS",
                "partner_cn_id": self.partner_cn.id,
                "partner_cn_name": self.partner_cn.name,
                "date": "2024-06-15",
                "amount": 1500.50,
                "product_reference": "174",
                "file_b64": "ZmFrZV9maWxlX2NvbnRlbnQ=",
                "file_mimetype": "image/jpeg",
            }
        )

    def test_especie_confirm_creates_approval(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        initial_count = self.env["approval.request"].search_count([])

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._confirm_especie_approval(
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

    def test_especie_confirm_telegram_data(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response):
            self.handler._confirm_especie_approval(
                self.test_bot,
                self.test_chat,
                self.test_user,
            )

        approval = self.env["approval.request"].search(
            [("category_id", "=", self.especie_approval_category.id)],
            order="id desc",
            limit=1,
        )
        self.assertTrue(approval)

        tdata = approval.telegram_data
        self.assertEqual(tdata["partner_fx_id"], self.partner_fx.id)
        self.assertEqual(tdata["partner_cn_id"], self.partner_cn.id)
        self.assertEqual(tdata["product_category"], "VEHICULOS")
        self.assertEqual(tdata["amount"], 1500.50)
        self.assertEqual(tdata["product_reference"], "174")
        self.assertNotIn("file_b64", tdata)

    def test_especie_confirm_populates_reason(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response):
            self.handler._confirm_especie_approval(
                self.test_bot,
                self.test_chat,
                self.test_user,
            )

        approval = self.env["approval.request"].search(
            [("category_id", "=", self.especie_approval_category.id)],
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
        self.assertIn(
            "<li><strong>Product Reference:</strong> 174</li>", approval.reason
        )
        self.assertIn("<li><strong>Amount:</strong> $1,500.50</li>", approval.reason)

    def test_especie_cancel_resets_state(self):
        callback = self.mock_telegram_callback_query(
            callback_data="especie_cancel",
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

    def test_especie_chatter_author_is_internal_user(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response):
            self.handler._confirm_especie_approval(
                self.test_bot,
                self.test_chat,
                self.test_user,
            )

        approval = self.env["approval.request"].search(
            [("category_id", "=", self.especie_approval_category.id)],
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


class TestEspecieHelpSection(PaymentApprovalTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.approval_account"]

    def test_especie_help_section(self):
        sections = self.handler._get_help_sections(
            self.test_bot,
            self.test_partner,
            self.test_user,
        )

        especie_section = None
        for title, cmds in sections:
            if "Payment in Kind" in title:
                especie_section = cmds
                break

        self.assertIsNotNone(especie_section)
        section_text = " ".join(especie_section)
        self.assertIn("/especie", section_text)
        self.assertIn("/cancelar", section_text)
