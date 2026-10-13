from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from odoo import Command, fields
from odoo.tests import Form, tagged

from odoo.addons.approval.tests.common import pool_step
from odoo.addons.approval_telegram_ml.services.approval_assistant import (
    ApprovalAssistant,
)
from odoo.addons.integration_machine_learning.tests.common import connect
from odoo.addons.telegram.models.telegram_bot import TelegramBot
from odoo.addons.telegram.tests.common import TelegramBotTestCase


class SmartApprovalTestBase(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler = cls.env["telegram.handler.approval_ai"]
        cls.router = cls.env["telegram.router"]
        cls.company = cls.env.ref("base.main_company")
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Solicitud General",
                "sequence_code": "TGSOL",
                "company_id": cls.company.id,
                "step_ids": pool_step(
                    [(cls.env.ref("base.user_admin").id, False, 10)], minimum=1
                ),
            }
        )


class TestSmartApprovalData(SmartApprovalTestBase):
    def test_intake_commands_registered(self):
        command = self.env.ref(
            "approval_telegram_ml.command_solicitar", raise_if_not_found=False
        )
        self.assertTrue(command, "The /solicitar command record should exist.")
        self.assertEqual(command.name, "/solicitar")
        self.assertFalse(
            self.env["telegram.command"].search([("name", "=", "/cancelarsolicitud")]),
            "/cancelar cancels a request; it has no command of its own.",
        )

    def test_the_intake_is_named_in_the_busy_notice(self):
        self.assertEqual(
            self.handler._telegram_flow_label(self.test_bot, self.test_chat),
            "an approval request",
        )

    def test_bot_ai_config_fields(self):
        self.assertFalse(
            self.test_bot.smart_approval_ai_enabled,
            "AI must default to off so a bot opts in explicitly.",
        )
        self.assertEqual(
            self.test_bot.smart_approval_ai_provider_id,
            self.env.ref("integration_machine_learning.ai_provider_groq"),
            "Groq stays the default so existing bots keep working untouched.",
        )
        self.assertFalse(self.test_bot.smart_approval_ai_model_id)

    def test_has_solicitar_command_gates_page(self):
        self.assertFalse(self.test_bot.has_solicitar_command)
        command = self.env.ref("approval_telegram_ml.command_solicitar")
        self.test_bot.write({"command_ids": [(4, command.id)]})
        self.assertTrue(self.test_bot.has_solicitar_command)

    def test_ending_the_intake_clears_its_draft(self):
        self.handler._flow_start(
            self.test_chat, "request_text", {"raw_text": "necesito aprobar algo"}
        )
        self.handler._flow_end(self.test_chat)
        self.assertFalse(self.test_chat.flow_owner)
        self.assertFalse(self.test_chat.flow_data)


class TestApprovalAssistant(SmartApprovalTestBase):
    def test_unavailable_when_disabled(self):
        assistant = ApprovalAssistant(self.test_bot)
        self.assertFalse(assistant.available)
        self.assertIsNone(assistant.classify("texto", self.category))

    def test_required_fields_labels(self):
        category = self.env["approval.category"].create(
            {
                "name": "Con Monto",
                "sequence_code": "TGMON",
                "company_id": self.company.id,
                "has_amount": "required",
                "has_partner": "optional",
            }
        )
        labels = ApprovalAssistant._required_fields(category)
        self.assertIn("monto*", labels)
        self.assertIn("contacto", labels)
        self.assertNotIn("contacto*", labels)


class TestAiProvider(SmartApprovalTestBase):
    def _use(self, xmlid):
        self.test_bot.smart_approval_ai_provider_id = self.env.ref(xmlid)

    def test_voice_notes_follow_the_transcription_policy_not_the_chat_vendor(self):
        self.env["integration.ml.policy"].search(
            [("purpose_id.key", "=like", "speech.transcription%")]
        ).unlink()
        self._use("integration_machine_learning.ai_provider_groq")
        self.assertFalse(self.test_bot.voice_notes_heard)
        deepgram = self.env.ref("integration_machine_learning.ai_provider_deepgram")
        connect(self.env, deepgram)
        self.env["integration.ml.policy"].create(
            {
                "company_id": self.env.company.id,
                "purpose_id": self.env["integration.ml.purpose"]
                ._get_or_create_by_key("speech.transcription")
                .id,
                "provider_ids": [(6, 0, deepgram.ids)],
            }
        )
        self.test_bot.invalidate_recordset(["voice_notes_heard"])
        self.assertTrue(self.test_bot.voice_notes_heard)

    def test_the_assistant_uses_the_bots_provider_and_model(self):
        google = self.env.ref("integration_machine_learning.ai_provider_google")
        connect(self.env, google)
        model = self.env["integration.ml.model"].create(
            {
                "provider_id": google.id,
                "name": "Next",
                "code": "gemini-next",
                "kind": "chat",
            }
        )
        self.test_bot.write(
            {
                "smart_approval_ai_provider_id": google.id,
                "smart_approval_ai_model_id": model.id,
            }
        )
        assistant = ApprovalAssistant(self.test_bot)
        self.assertEqual(assistant._chat_model(), model)

    def test_a_requester_who_cannot_read_ai_providers_still_gets_the_model(self):
        google = self.env.ref("integration_machine_learning.ai_provider_google")
        connect(self.env, google)
        model = self.env["integration.ml.model"].create(
            {
                "provider_id": google.id,
                "name": "Next",
                "code": "gemini-next",
                "kind": "chat",
            }
        )
        self.test_bot.write(
            {
                "smart_approval_ai_enabled": True,
                "smart_approval_ai_provider_id": google.id,
                "smart_approval_ai_model_id": model.id,
            }
        )
        requester = self.test_user
        self.assertFalse(
            self.env["integration.ml.provider"].with_user(requester).has_access("read")
        )
        bot = self.test_bot.with_user(requester)
        assistant = ApprovalAssistant(bot)
        self.assertEqual(assistant._chat_model(), model)
        self.assertTrue(assistant.available)

    def test_the_assistant_chooses_its_model_in_the_bot_company(self):
        google = self.env.ref("integration_machine_learning.ai_provider_google")
        bot_company = self.env["res.company"].create({"name": "Bot Co"})
        connect(google.with_company(bot_company).env, google)
        model = self.env["integration.ml.model"].create(
            {
                "provider_id": google.id,
                "name": "Next",
                "code": "gemini-next",
                "kind": "chat",
            }
        )
        self.test_bot.write(
            {
                "smart_approval_ai_provider_id": google.id,
                "smart_approval_ai_model_id": model.id,
            }
        )
        self.assertFalse(
            ApprovalAssistant(self.test_bot)._chat_model(),
            "The bot's company holds no credential for the vendor.",
        )
        self.test_bot.company_id = bot_company
        self.assertEqual(ApprovalAssistant(self.test_bot)._chat_model(), model)

    def test_switching_provider_clears_a_model_of_another_vendor(self):
        groq = self.env.ref("integration_machine_learning.ai_provider_groq")
        self.test_bot.command_ids = [
            Command.link(self.env.ref("approval_telegram_ml.command_solicitar").id)
        ]
        with Form(self.test_bot) as form:
            form.smart_approval_ai_enabled = True
            form.smart_approval_ai_model_id = groq._service_for("chat").model_id
            form.smart_approval_ai_provider_id = self.env.ref(
                "integration_machine_learning.ai_provider_openai"
            )
            self.assertFalse(form.smart_approval_ai_model_id)


class TestSmartApprovalFlow(SmartApprovalTestBase):
    def setUp(self):
        super().setUp()
        self.controller = self.handler
        self.test_bot.write(
            {
                "command_ids": [
                    Command.link(
                        self.env.ref("approval_telegram_ml.command_solicitar").id
                    )
                ]
            }
        )
        self.mock_ok = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

    def test_solicitar_sets_awaiting_text_state(self):
        with self.mock_api_gateway_post(self.mock_ok):
            self.controller._handle_solicitar_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=self.test_user,
            )
        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "request_text")

    def test_text_ai_off_falls_back_to_picker(self):
        self.test_chat._flow_start("telegram.handler.approval_ai", "request_text")
        message = {"text": "necesito aprobar la compra de unas llantas"}
        with self.mock_api_gateway_post(self.mock_ok):
            self.router._dispatch_free_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )
        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "category_pick")

    def test_classify_high_confidence_shows_summary(self):
        self.test_bot.smart_approval_ai_enabled = True
        connect(self.env, self.test_bot.smart_approval_ai_provider_id)
        self.test_chat._flow_start("telegram.handler.approval_ai", "request_text")
        classification = {
            "category_id": self.category.id,
            "confidence": 0.95,
            "amount": 12000.0,
            "partner_name": None,
            "quantity": None,
            "reason": "compra de llantas",
        }
        with (
            self.mock_api_gateway_post(self.mock_ok),
            patch.object(ApprovalAssistant, "classify", return_value=classification),
        ):
            self.router._dispatch_free_message(
                self.test_bot,
                self.test_chat,
                {"text": "compra de 3 llantas, ~12 mil"},
                self.test_partner,
                self.test_user,
            )
        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "classification_confirm")
        self.assertEqual(self.test_chat.flow_data.get("category_id"), self.category.id)

    def test_stray_message_at_confirm_resends_summary(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_ai",
            "classification_confirm",
            {
                "raw_text": "necesito aprobar algo",
                "category_id": self.category.id,
                "reason": "compra de llantas",
            },
        )
        with self.mock_api_gateway_post(self.mock_ok) as mock_post:
            self.router._dispatch_free_message(
                self.test_bot,
                self.test_chat,
                {"text": "ya lo confirmé o no?"},
                self.test_partner,
                self.test_user,
            )

        texts = [
            call.kwargs.get("json", {}).get("text", "")
            for call in mock_post.call_args_list
        ]
        self.assertTrue(
            any("You are still on the request" in text for text in texts),
            f"Expected the nudge naming the pending request, got: {texts}",
        )
        self.assertTrue(
            any(
                "This is what I understood from your request" in text for text in texts
            ),
            f"Expected the draft summary to be re-sent, got: {texts}",
        )
        keyboards = [
            call.kwargs.get("json", {}).get("reply_markup")
            for call in mock_post.call_args_list
        ]
        self.assertTrue(
            any(keyboards),
            "The re-sent summary must carry the confirm/change/cancel keyboard",
        )
        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "classification_confirm")

    def test_stray_message_in_other_flow_state_uses_busy_notice(self):
        self.test_chat._flow_start("telegram.handler.approval_ai", "date_choice")
        with self.mock_api_gateway_post(self.mock_ok) as mock_post:
            self.router._dispatch_free_message(
                self.test_bot,
                self.test_chat,
                {"text": "hola?"},
                self.test_partner,
                self.test_user,
            )

        texts = [
            call.kwargs.get("json", {}).get("text", "")
            for call in mock_post.call_args_list
        ]
        self.assertTrue(
            any("an approval request" in text for text in texts),
            f"Expected the flow-busy notice naming the intake flow, got: {texts}",
        )
        self.assertFalse(
            any("Tap the button" in text for text in texts),
            f"A typed message must not be told to press a button: {texts}",
        )

    def test_confirm_creates_and_submits_request(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_ai",
            "classification_confirm",
            {
                "raw_text": "necesito aprobar algo",
                "category_id": self.category.id,
            },
        )
        with self.mock_api_gateway_post(self.mock_ok):
            self.controller._on_confirm(self.test_bot, self.test_chat, self.test_user)
            self.test_chat.invalidate_recordset()
            self.assertEqual(self.test_chat.flow_step, "evidence_question")
            self.controller._on_evidence_question(
                self.test_bot, self.test_chat, self.test_user, "sa_ev:no"
            )
        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)
        request = self.env["approval.request"].search(
            [
                ("request_owner_id", "=", self.test_user.id),
                ("category_id", "=", self.category.id),
            ],
            limit=1,
        )
        self.assertTrue(request, "An approval.request should have been created.")
        self.assertEqual(request.state, "pending")


class TestConversationReset(SmartApprovalTestBase):
    def test_an_expired_intake_is_over_and_collected(self):
        self.handler._flow_start(
            self.test_chat, "request_text", {"raw_text": "compra de llantas"}
        )
        self.test_chat.flow_expires_at = fields.Datetime.now() - timedelta(minutes=1)

        self.assertFalse(self.handler._owns_flow(self.test_chat))
        self.assertIsNone(self.router._flow_owner(self.test_chat))
        self.env["telegram.chat"]._gc_expired_flows()
        self.assertFalse(self.test_chat.flow_owner)
        self.assertFalse(self.test_chat.flow_data)

    def test_end_the_intake_as_internal_user(self):
        self.handler._flow_start(
            self.test_chat, "request_text", {"raw_text": "compra de llantas"}
        )

        self.handler.with_user(self.test_user)._flow_end(
            self.test_chat.with_user(self.test_user)
        )

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)
        self.assertFalse(self.test_chat.flow_data)


class TestCancelAsInternalUser(SmartApprovalTestBase):
    def setUp(self):
        super().setUp()
        self.mock_ok = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

    def _cancel(self):
        with self.mock_api_gateway_post(self.mock_ok) as mock_post:
            self.router._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/cancelar",
                [],
                self.test_partner,
                self.test_user,
            )
        return mock_post.call_args.kwargs["json"]["text"]

    def test_cancel_ends_the_request_as_internal_user(self):
        self.handler._flow_start(
            self.test_chat,
            "classification_confirm",
            {"raw_text": "compra de llantas"},
        )

        text = self._cancel()

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)
        self.assertFalse(self.test_chat.flow_data)
        self.assertEqual(text, "Done, I cancelled an approval request.")

    def test_cancel_on_an_idle_chat_changes_nothing(self):
        text = self._cancel()

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)
        self.assertEqual(text, "You have nothing in progress to cancel.")


class TestSolicitarFlowGuard(SmartApprovalTestBase):
    def setUp(self):
        super().setUp()
        self.controller = self.handler
        self.mock_ok = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )
        self.test_bot.write(
            {
                "command_ids": [
                    Command.link(
                        self.env.ref("approval_telegram_ml.command_solicitar").id
                    )
                ]
            }
        )

    def test_voice_ignored_when_bot_does_not_offer_solicitar(self):
        self.test_bot.write({"command_ids": [Command.clear()]})
        self.test_chat._flow_end()
        with (
            patch.object(type(self.handler), "_handle_voice_intake") as intake,
            patch.object(TelegramBot, "send_message"),
        ):
            self.router._dispatch_free_message(
                self.test_bot,
                self.test_chat,
                {"voice": {"file_id": "abc", "duration": 3}},
                self.test_partner,
                self.test_user,
            )
        intake.assert_not_called()
        self.assertFalse(
            self.test_chat.flow_owner,
            "The chat must stay idle so the bot that owns /nueva can answer.",
        )

    def test_voice_captured_when_bot_offers_solicitar(self):
        self.test_chat._flow_end()
        with patch.object(type(self.handler), "_handle_voice_intake") as intake:
            self.router._dispatch_free_message(
                self.test_bot,
                self.test_chat,
                {"voice": {"file_id": "abc", "duration": 3}},
                self.test_partner,
                self.test_user,
            )
        intake.assert_called_once()
        self.assertEqual(self.test_chat.flow_step, "request_text")

    def test_every_intake_step_is_its_flow(self):
        for step in ("request_text", "date_choice", "evidence_upload"):
            self.handler._flow_start(self.test_chat, step)
            self.assertEqual(self.router._flow_owner(self.test_chat), self.handler)

    def test_solicitar_is_registered_as_flow_starting(self):
        commands = self.handler._telegram_commands()
        self.assertEqual(set(commands), {"/solicitar"})
        self.assertTrue(commands["/solicitar"].starts_flow)
        self.assertEqual(
            {spec.tier for spec in commands.values()},
            {"internal"},
        )
        self.assertIn("/solicitar", self.router._flow_starting_commands())

    def test_handler_declarations(self):
        self.assertEqual(self.handler._telegram_intakes(), {"voice"})
        self.assertEqual(self.handler._telegram_intake_priority, 90)
        self.assertEqual(
            set(self.handler._telegram_callback_prefixes()),
            {
                "sa_confirm",
                "sa_changecat",
                "sa_cancel",
                "sa_cat:",
                "sa_date:",
                "sa_cal:",
                "sa_jrnl:",
                "sa_inv:",
                "sa_ev:",
            },
        )
        for data in ("sa_confirm", "sa_cat:1", "sa_cal:d:2026-01-01", "sa_ev:done"):
            self.assertEqual(
                self.router._callback_owner(self.test_bot, data), self.handler
            )

    def test_idle_voice_needs_an_internal_user(self):
        voice = {"voice": {"file_id": "abc", "duration": 3}}
        self.assertTrue(
            self.handler._accepts_idle(
                self.test_bot,
                self.test_chat,
                "voice",
                voice,
                self.test_partner,
                self.test_user,
            )
        )
        self.assertFalse(
            self.handler._accepts_idle(
                self.test_bot, self.test_chat, "voice", voice, self.test_partner, False
            )
        )
        self.assertTrue(
            self.handler._accepts_idle(
                self.test_bot,
                self.test_chat,
                "voice",
                {"audio": {"file_id": "abc", "file_name": "compra.m4a"}},
                self.test_partner,
                self.test_user,
            ),
            "The router routes an audio file as a voice message; it is heard too.",
        )

    @contextmanager
    def _hearing(self, transcript):
        Bot = type(self.test_bot)
        with (
            patch.object(
                ApprovalAssistant,
                "supports_audio",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch.object(Bot, "_hears_voice_notes", return_value=True),
            patch.object(TelegramBot, "get_file_content", return_value=b"audio"),
            patch.object(Bot, "_hear_voice_note", return_value=transcript) as hearing,
            patch.object(TelegramBot, "send_chat_action") as typing,
            patch.object(TelegramBot, "send_message") as sent,
            patch.object(type(self.handler), "_run_classification") as classify,
        ):
            yield SimpleNamespace(
                hearing=hearing, typing=typing, sent=sent, classify=classify
            )

    def test_an_audio_file_starts_a_request_from_its_transcript(self):
        self.test_chat._flow_end()
        with self._hearing("compra de 3 llantas") as heard:
            self.router._dispatch_free_message(
                self.test_bot,
                self.test_chat,
                {"audio": {"file_id": "abc", "file_name": "compra.m4a"}},
                self.test_partner,
                self.test_user,
            )
        self.assertEqual(heard.hearing.call_args.kwargs["filename"], "compra.m4a")
        heard.typing.assert_called_once_with(self.test_chat, "typing")
        self.assertEqual(heard.classify.call_args.args[3], "compra de 3 llantas")
        self.assertEqual(self.test_chat.flow_data["transcript"], "compra de 3 llantas")

    def test_a_note_without_a_transcript_asks_to_type(self):
        self.test_chat._flow_end()
        with self._hearing(None) as heard:
            self.router._dispatch_free_message(
                self.test_bot,
                self.test_chat,
                {"voice": {"file_id": "abc", "duration": 3}},
                self.test_partner,
                self.test_user,
            )
        heard.classify.assert_not_called()
        self.assertIn("could not transcribe", heard.sent.call_args.args[1])

    def test_cancel_button_on_the_summary_discards_the_draft(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_ai",
            "classification_confirm",
            {"raw_text": "compra de 3 llantas"},
        )
        with self.mock_api_gateway_post(self.mock_ok):
            self.router._dispatch_callback_query(
                self.test_bot, self.mock_telegram_callback_query("sa_cancel")
            )
        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)
        self.assertFalse(self.test_chat.flow_data)

    def test_solicitar_keeps_the_draft_it_used_to_wipe(self):
        draft = {"raw_text": "compra de 3 llantas"}
        self.test_chat._flow_start(
            "telegram.handler.approval_ai", "classification_confirm", draft
        )

        with patch.object(TelegramBot, "send_message") as mock_send:
            self.router._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/solicitar",
                [],
                self.test_partner,
                self.test_user,
            )

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "classification_confirm")
        self.assertEqual(self.test_chat.flow_data, draft)
        self.assertIn("/cancelar", mock_send.call_args.args[1])

    def test_solicitar_refused_while_another_module_owns_the_chat(self):
        self.test_chat._flow_start("telegram.handler.base", "other")

        with patch.object(TelegramBot, "send_message") as mock_send:
            self.router._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/solicitar",
                [],
                self.test_partner,
                self.test_user,
            )

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_owner, "telegram.handler.base")
        self.assertIn("in progress", mock_send.call_args.args[1])

    def test_solicitar_starts_normally_on_an_idle_chat(self):
        with self.mock_api_gateway_post(self.mock_ok):
            self.router._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/solicitar",
                [],
                self.test_partner,
                self.test_user,
            )

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "request_text")

    def test_restart_button_discards_and_starts_a_new_intake(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_ai",
            "classification_confirm",
            {"raw_text": "compra de 3 llantas"},
        )
        callback_query = {
            "id": "cb1",
            "data": "tg_busy:restart:/solicitar",
            "message": {"message_id": 42},
        }

        with self.mock_api_gateway_post(self.mock_ok):
            self.router._handle_flow_busy_callback(
                self.test_bot,
                self.test_chat,
                callback_query,
                self.test_partner,
                self.test_user,
            )

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "request_text")
        self.assertFalse(self.test_chat.flow_data)


class TestCalendarCallback(SmartApprovalTestBase):
    def setUp(self):
        super().setUp()
        self.controller = self.handler

    def test_forged_calendar_callbacks_are_ignored(self):
        self.handler._flow_start(self.test_chat, "date_calendar")
        self.controller._on_calendar(
            self.test_bot,
            self.test_chat,
            self.test_user,
            {"data": "sa_cal:p:notanumber", "message": {"message_id": 1}},
        )
        self.controller._on_calendar(
            self.test_bot,
            self.test_chat,
            self.test_user,
            {"data": "sa_cal:d:9999-99-99", "message": {"message_id": 1}},
        )
        self.test_chat.invalidate_recordset()
        self.assertFalse((self.test_chat.flow_data or {}).get("date"))


class TestSummaryEscaping(SmartApprovalTestBase):
    def test_ai_output_in_the_summary_arrives_as_literal_text(self):
        data = {
            "category_id": self.category.id,
            "partner_name": "Llantera_<Bajío> & *Hijos*",
            "reason": "compra <urgente> & rápida",
            "items": [
                {"description": "llanta <R15> & rin_", "quantity": 2, "price_unit": 5}
            ],
            "payment": {"bank": "Banco <MX>"},
        }
        with patch.object(TelegramBot, "send_message") as mock_send:
            self.handler._send_classification_summary(
                self.test_bot, self.test_chat, data
            )

        text = mock_send.call_args.args[1]
        self.assertNotIn("parse_mode", mock_send.call_args.kwargs)
        for escaped in (
            "Llantera_&lt;Bajío&gt; &amp; *Hijos*",
            "compra &lt;urgente&gt; &amp; rápida",
            "llanta &lt;R15&gt; &amp; rin_",
            "Banco &lt;MX&gt;",
        ):
            self.assertIn(escaped, text)
        self.assertNotIn("<urgente>", text)
        self.assertIn("</b>: Llantera_&lt;Bajío&gt;", text)


@tagged("post_install", "-at_install")
class TestDeclaredDependencies(TelegramBotTestCase):
    def test_category_fields_the_intake_reads_exist(self):
        category = self.env["approval.category"]
        for name, owner in (
            ("has_date", "approval"),
            ("has_product", "approval_product"),
            ("has_journal", "approval_account"),
            ("journal_ids", "approval_account"),
        ):
            self.assertIn(
                name,
                category._fields,
                f"approval.category.{name} is read by the intake and declared "
                f"by {owner}; add {owner} to this module's depends",
            )

    def test_request_fields_the_intake_writes_exist(self):
        request = self.env["approval.request"]
        for name, owner in (
            ("journal_id", "approval_account"),
            ("line_ids", "approval_product"),
        ):
            self.assertIn(
                name,
                request._fields,
                f"approval.request.{name} is written by the intake and declared "
                f"by {owner}; add {owner} to this module's depends",
            )

    def test_models_the_intake_searches_are_present(self):
        self.assertIn(
            "account.journal",
            self.env,
            "_candidate_journals searches account.journal directly, so "
            "approval_account (and through it, account) must be declared",
        )
