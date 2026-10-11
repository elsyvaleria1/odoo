import hashlib
import hmac
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import psycopg

from odoo import Command
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import freeze_time

from odoo.addons.approval_telegram.controllers.approval_miniapp_controller import (
    ApprovalMiniAppController,
)
from odoo.addons.approval_telegram.services.approval_notifier import (
    TelegramApprovalNotifier,
)
from odoo.addons.telegram.models.telegram_bot import TelegramBot
from odoo.addons.telegram.models.telegram_bot_receiver import (
    MINI_APP_SESSION_TTL_HOURS,
)
from odoo.addons.telegram.tests.common import NOT_A_MENU, TelegramBotTestCase
from odoo.addons.telegram.tools.telegram_client import TelegramClient


class ApprovalRequestTestBase(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Telegram Test Category",
                "company_id": cls.company.id,
                "sequence_code": "TGTEST",
            }
        )
        cls.step = cls.env["approval.category.step"].create(
            {
                "category_id": cls.category.id,
                "name": "Telegram Step",
                "minimum": 1,
                "member_ids": [
                    Command.create(
                        {"user_id": cls.test_user.id, "notify_telegram": True}
                    )
                ],
            }
        )
        cls.step_member = cls.step.member_ids
        cls.approval_request = cls.env["approval.request"].create(
            {
                "category_id": cls.category.id,
                "request_owner_id": cls.env.ref("base.user_admin").id,
            }
        )
        cls.approval_request.action_confirm()
        cls.approver = cls.approval_request.approver_ids.filtered(
            lambda approver: approver.user_id == cls.test_user
        )


class TestApprovalRequestConfig(ApprovalRequestTestBase):
    def test_bot_notify_field(self):
        self.assertIn("notify_approvals", self.env["telegram.bot"]._fields)

    def test_step_member_notify_field(self):
        row = self.env["approval.category.step.member"].create(
            {
                "step_id": self.step.id,
                "user_id": self.env.ref("base.user_admin").id,
            }
        )
        self.assertFalse(row.notify_telegram, "notify_telegram must be opt-in")

    def test_decision_flow_is_named_in_the_busy_notice(self):
        handler = self.env["telegram.handler.approval"]
        self.assertEqual(
            handler._telegram_flow_label(self.test_bot, self.test_chat),
            "an approval decision awaiting a comment",
        )


class TestApprovalNotifier(ApprovalRequestTestBase):
    def _queued(self):
        return self.env["telegram.message"].search(
            [
                ("chat_id", "=", self.test_chat.id),
                ("message_type", "=", "outbound"),
                ("state", "=", "outgoing"),
                NOT_A_MENU,
            ]
        )

    def test_push_is_queued_for_the_linked_chat(self):
        self.test_bot.notify_approvals = True
        with patch.object(TelegramBot, "send_message") as mock_send:
            self.env["telegram.approval.notifier"]._notify_approver(self.approver)
        self.assertFalse(mock_send.called, "a push waits for the commit")
        queued = self._queued()
        self.assertEqual(len(queued), 1)
        self.assertIn("inline_keyboard", queued.payload["reply_markup"])

    def test_push_is_plain_text(self):
        self.test_bot.notify_approvals = True
        self.env["telegram.approval.notifier"]._notify_approver(self.approver)
        self.assertNotIn("parse_mode", self._queued().payload)

    def test_a_resubmission_says_so_in_the_recipients_language(self):
        self.test_bot.notify_approvals = True
        self.env["telegram.approval.notifier"]._notify_approver(
            self.approver, resubmitted=True
        )
        self.assertIn("resubmitted", self._queued().payload["text"])

    def test_a_bot_of_another_company_does_not_push_the_request(self):
        other_bot = self._bot_of_another_company("Other Approval Push Bot")
        other_bot.notify_approvals = True
        other_chat = self.env["telegram.chat"].create(
            {
                "chat_id": self.test_chat.chat_id,
                "chat_type": "private",
                "bot_id": other_bot.id,
                "account_id": self.test_account.id,
            }
        )
        outbound = [
            ("chat_id", "=", other_chat.id),
            ("message_type", "=", "outbound"),
            NOT_A_MENU,
        ]

        self.env["telegram.approval.notifier"]._notify_approver(self.approver)

        self.assertFalse(self.env["telegram.message"].search(outbound))
        self.test_bot.notify_approvals = True
        self.env["telegram.approval.notifier"]._notify_approver(self.approver)
        self.assertEqual(len(self._queued()), 1)
        self.assertFalse(self.env["telegram.message"].search(outbound))

    def test_no_push_when_bot_disabled(self):
        self.test_bot.notify_approvals = False
        self.env["telegram.approval.notifier"]._notify_approver(self.approver)
        self.assertFalse(self._queued())

    def test_no_push_when_toggle_off(self):
        self.test_bot.notify_approvals = True
        self.step_member.notify_telegram = False
        self.env["telegram.approval.notifier"]._notify_approver(self.approver)
        self.assertFalse(self._queued())

    def test_no_push_when_not_a_member_of_the_step(self):
        self.test_bot.notify_approvals = True
        self.approver.sudo().step_ids = False
        self.env["telegram.approval.notifier"]._notify_approver(self.approver)
        self.assertFalse(self._queued())

    def test_notify_enabled_helper(self):
        self.assertTrue(self.approver._telegram_notify_enabled())
        self.step_member.notify_telegram = False
        self.assertFalse(self.approver._telegram_notify_enabled())


class TestMiniAppInitData(TelegramBotTestCase):
    def _signed_init_data(self, token, fields_):
        data_check_string = "\n".join(
            f"{key}={value}" for key, value in sorted(fields_.items())
        )
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        valid_hash = hmac.new(
            secret, data_check_string.encode(), hashlib.sha256
        ).hexdigest()
        return urlencode({**fields_, "hash": valid_hash})

    def test_valid_and_tampered_init_data(self):
        fields_ = {
            "auth_date": str(int(time.time())),
            "user": json_dumps({"id": 12345}),
        }

        good = self._signed_init_data(self.TEST_BOT_TOKEN, fields_)
        parsed = self.test_bot._resolve_init_data(good)
        self.assertTrue(parsed)
        self.assertEqual(json_loads(parsed["user"])["id"], 12345)
        self.assertEqual(self.test_bot._mini_app_user_id(parsed), "12345")

        bad = urlencode({**fields_, "hash": "deadbeef"})
        self.assertIsNone(self.test_bot._resolve_init_data(bad))

        stale = self._signed_init_data(
            self.TEST_BOT_TOKEN,
            {**fields_, "auth_date": str(int(time.time()) - 2 * 24 * 60 * 60)},
        )
        self.assertIsNone(
            self.test_bot._resolve_init_data(stale),
            "a captured initData must not authenticate for ever",
        )


class TestMiniAppSignedSession(TelegramBotTestCase):
    def test_session_round_trip(self):
        session = self.test_bot._mint_mini_app_session("12345")

        resolved = self.test_bot._resolve_mini_app_session(session)

        self.assertEqual(resolved, "12345")

    def test_session_is_bound_to_its_bot(self):
        other_credential = self.env["credential.credential"].create(
            {
                "name": "Other Session Credential",
                "category_id": self.test_credential.category_id.id,
                "endpoint_id": self.test_credential.endpoint_id.id,
                "bearer_token": "999888777:ZZZ-YYY1234ghIkl-zyx57W2v1u123ew11",
            }
        )
        other_bot = self.env["telegram.bot"].create(
            {"name": "Other Session Bot", "credential_id": other_credential.id}
        )
        session = self.test_bot._mint_mini_app_session("12345")

        self.assertIsNone(other_bot._resolve_mini_app_session(session))

    def test_tampered_session_is_rejected(self):
        session = self.test_bot._mint_mini_app_session("12345")

        for index in (12, 30, 48):
            with self.subTest(index=index):
                mutated = (
                    session[:index]
                    + ("a" if session[index] != "a" else "b")
                    + session[index + 1 :]
                )
                self.assertIsNone(self.test_bot._resolve_mini_app_session(mutated))

    def test_expired_session_is_rejected(self):
        session = self.test_bot._mint_mini_app_session("12345")
        later = datetime.now(UTC) + timedelta(hours=MINI_APP_SESSION_TTL_HOURS + 1)

        with freeze_time(later):
            self.assertIsNone(self.test_bot._resolve_mini_app_session(session))

    def test_garbage_session_is_rejected(self):
        for value in ("", "not-a-token", "a.b.c"):
            self.assertIsNone(self.test_bot._resolve_mini_app_session(value))

    def _resolve(self, **params):
        mocked = MagicMock()
        mocked.get_http_params.return_value = params
        mocked.httprequest.mimetype = "application/x-www-form-urlencoded"
        with patch("odoo.addons.telegram.models.telegram_bot_receiver.request", mocked):
            resolution = self.env["telegram.bot"]._receiver_for_mini_app(
                bot_id=self.test_bot.id
            )
        self.assertTrue(resolution.verify({}, b""))
        return resolution

    def test_session_path_never_reads_the_bot_token(self):
        session = self.test_bot._mint_mini_app_session(self.test_chat.chat_id)

        with patch.object(
            TelegramBot,
            "_get_bot_token",
            side_effect=AssertionError("the session path must not read the token"),
        ):
            resolution = self._resolve(s=session)

        telegram_user_id = resolution.extra["telegram_user_id"]
        self.assertEqual(telegram_user_id, self.test_chat.chat_id)
        self.assertEqual(self.test_bot._mini_app_user(telegram_user_id), self.test_user)

    def test_init_data_path_still_reads_the_token(self):
        with patch.object(
            TelegramBot, "_get_bot_token", return_value=self.TEST_BOT_TOKEN
        ) as mock_token:
            resolution = self._resolve(
                init_data=TestMiniAppInitData._signed_init_data(
                    self,
                    self.TEST_BOT_TOKEN,
                    {
                        "auth_date": str(int(time.time())),
                        "user": json_dumps({"id": int(self.test_chat.chat_id)}),
                    },
                )
            )

        mock_token.assert_called()
        telegram_user_id = resolution.extra["telegram_user_id"]
        self.assertEqual(telegram_user_id, self.test_chat.chat_id)
        self.assertEqual(self.test_bot._mini_app_user(telegram_user_id), self.test_user)


class TestDecisionFlowGuard(ApprovalRequestTestBase):
    def _press(self, data):
        callback_query = self.mock_telegram_callback_query(
            callback_data=data, chat_id=self.test_chat.chat_id, message_id=7
        )
        with patch.object(TelegramBot, "send_message") as mock_send:
            self.env["telegram.router"]._dispatch_callback_query(
                self.test_bot, callback_query
            )
        return mock_send

    def test_decision_refused_while_another_flow_runs(self):
        self.test_chat._flow_start("telegram.handler.base", "other", {"step": 2})

        mock_send = self._press("ar:rr:1:0")

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_owner, "telegram.handler.base")
        self.assertEqual(self.test_chat.flow_data, {"step": 2})
        self.assertIn("in progress", mock_send.call_args.args[1])

    def test_notice_offers_a_single_discard_button(self):
        self.test_chat._flow_start("telegram.handler.base", "other")

        mock_send = self._press("ar:cf:1:date")

        keyboard = mock_send.call_args.kwargs["reply_markup"]["inline_keyboard"]
        callbacks = [button[0]["callback_data"] for button in keyboard]
        self.assertEqual(callbacks, ["tg_busy:discard"])
        self.assertIn("tap the button again", mock_send.call_args.args[1])

    def test_own_decision_flow_is_not_blocked(self):
        self.test_chat._flow_start("telegram.handler.approval", "refusal_note")

        mock_send = self._press("ar:rr:1:0")

        self.assertNotIn("in progress", mock_send.call_args.args[1])

    def test_idle_chat_is_not_blocked(self):
        mock_send = self._press("ar:rr:1:0")

        self.assertNotIn("in progress", mock_send.call_args.args[1])

    def test_approve_goes_through_while_another_flow_runs(self):
        self.test_chat._flow_start("telegram.handler.base", "other", {"step": 2})

        mock_send = self._press("ar:a:0")

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_owner, "telegram.handler.base")
        self.assertFalse(mock_send.called)

    def test_decision_flow_text_goes_to_the_approval_handler(self):
        self.test_chat._flow_start("telegram.handler.approval", "fix_text")
        message = self.mock_telegram_message(chat_id=self.test_chat.chat_id, text="   ")

        with patch.object(TelegramBot, "send_message") as mock_send:
            self.env["telegram.router"]._dispatch_message(self.test_bot, message)

        self.assertEqual(
            mock_send.call_args.args[1], "Please type the requested value."
        )

    def test_decision_handler_declarations(self):
        handler = self.env["telegram.handler.approval"]

        self.assertEqual(handler._telegram_callback_prefixes(), ("ar:",))
        self.assertEqual(handler._telegram_commands(), {})
        self.assertTrue(handler._feature_enabled(self.test_bot))

    def test_discard_button_clears_the_way(self):
        self.test_chat._flow_start("telegram.handler.base", "other", {"step": 2})
        callback_query = {
            "id": "cb1",
            "data": "tg_busy:discard",
            "message": {"message_id": 7},
        }

        with patch.object(TelegramBot, "send_message") as mock_send:
            self.env["telegram.router"]._handle_flow_busy_callback(
                self.test_bot,
                self.test_chat,
                callback_query,
                self.test_partner,
                self.test_user,
            )

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)
        self.assertFalse(self.test_chat.flow_data)
        self.assertIn("Tap the button", mock_send.call_args.args[1])


class TestConversationReset(ApprovalRequestTestBase):
    def test_ending_the_flow_clears_the_decision_draft(self):
        self.test_chat._flow_start(
            "telegram.handler.approval",
            "refusal_note",
            {"approver_id": self.approver.id},
        )
        self.env["telegram.handler.approval"]._flow_end(self.test_chat)
        self.assertFalse(self.test_chat.flow_owner)
        self.assertFalse(self.test_chat.flow_data)

    def test_end_approval_flow_as_internal_user(self):
        self.test_chat._flow_start(
            "telegram.handler.approval",
            "refusal_note",
            {"approver_id": self.approver.id},
        )

        self.env["telegram.handler.approval"].with_user(self.test_user)._flow_end(
            self.test_chat.with_user(self.test_user)
        )

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)
        self.assertFalse(self.test_chat.flow_data)

    def test_cancel_command_ends_the_decision_flow(self):
        self.test_chat._flow_start(
            "telegram.handler.approval",
            "refusal_note",
            {"approver_id": self.approver.id},
        )
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id, text="/cancelar"
        )

        with patch.object(TelegramBot, "send_message") as mock_send:
            self.env["telegram.router"]._dispatch_message(self.test_bot, message)

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)
        self.assertEqual(
            mock_send.call_args.args[1],
            "Done, I cancelled an approval decision awaiting a comment.",
        )


class MiniAppPayloadMixin:
    def _payload(self):
        with patch.object(
            ApprovalMiniAppController,
            "_reasons_payload",
            staticmethod(lambda category: []),
        ):
            return ApprovalMiniAppController._approver_payload(
                self.approver, self.test_user
            )


class TestMiniAppLinesPayload(MiniAppPayloadMixin, ApprovalRequestTestBase):
    def test_non_sale_request_reports_no_lines(self):
        payload = self._payload()

        self.assertEqual(payload["lines"], [])
        self.assertEqual(payload["lines_more"], 0)
        self.assertEqual(payload["lines_source"], "")
        self.assertEqual(payload["reason"], self.approval_request.reason or "")

    def test_request_lines_still_win_over_the_fallback(self):
        product = self.env["product.product"].create(
            {
                "name": "Payload Product",
                "type": "consu",
            }
        )
        draft = self.env["approval.request"].create(
            {
                "category_id": self.category.id,
                "request_owner_id": self.env.ref("base.user_admin").id,
            }
        )
        self.env["approval.request.line"].create(
            {
                "approval_request_id": draft.id,
                "product_id": product.id,
                "quantity": 3.0,
                "price_unit": 7.0,
            }
        )

        detail = ApprovalMiniAppController._lines_payload(draft)

        self.assertEqual(len(detail["lines"]), 1)
        self.assertEqual(detail["lines"][0]["product"], product.display_name)
        self.assertEqual(detail["lines"][0]["quantity"], 3.0)
        self.assertEqual(detail["more"], 0)
        self.assertFalse(detail["live"], "request lines are not live order lines")


class _StubSaleRequest:
    line_ids = ()

    def __init__(self, *order_names):
        self._orders = order_names

    def _get_sale_display_lines(self, limit=None):
        return [
            {
                "order": name,
                "product": f"Product {index}",
                "description": "",
                "quantity": 1.0,
                "uom": "Units",
                "price_unit": 5.0,
                "subtotal": 5.0,
                "currency": "$",
            }
            for index, name in enumerate(self._orders)
        ], 0


class TestMiniAppLiveLines(MiniAppPayloadMixin, ApprovalRequestTestBase):
    def test_single_order_is_named_once_in_the_heading(self):
        detail = ApprovalMiniAppController._lines_payload(_StubSaleRequest("OV/1"))

        self.assertTrue(detail["live"])
        self.assertEqual(detail["source"], "OV/1")
        self.assertEqual(detail["lines"][0]["order"], "")

    def test_several_orders_stay_labelled_per_row(self):
        detail = ApprovalMiniAppController._lines_payload(
            _StubSaleRequest("OV/1", "OV/2")
        )

        self.assertEqual(detail["source"], "OV/1, OV/2")
        self.assertEqual([line["order"] for line in detail["lines"]], ["OV/1", "OV/2"])

    def _draft_with_reason(self, reason):
        draft = self.env["approval.request"].create(
            {
                "category_id": self.category.id,
                "request_owner_id": self.env.ref("base.user_admin").id,
                "reason": reason,
            }
        )
        approver = draft.approver_ids.filtered(
            lambda item: item.user_id == self.test_user
        )
        self.assertTrue(approver, "category should have seeded the approver")
        return draft, approver[:1]

    def _payload_for(self, approver, detail):
        with (
            patch.object(
                ApprovalMiniAppController,
                "_reasons_payload",
                staticmethod(lambda category: []),
            ),
            patch.object(
                ApprovalMiniAppController,
                "_lines_payload",
                staticmethod(lambda req: detail),
            ),
        ):
            return ApprovalMiniAppController._approver_payload(approver, self.test_user)

    def test_live_lines_suppress_the_frozen_reason(self):
        snapshot = "<p>Sales Order: OV/1</p><ul><li>Product 0</li></ul>"
        _draft, approver = self._draft_with_reason(snapshot)

        payload = self._payload_for(
            approver,
            {
                "lines": [{"product": "Product 0", "quantity": 1.0, "price_unit": 1.0}],
                "more": 0,
                "live": True,
                "source": "OV/1",
            },
        )

        self.assertEqual(payload["reason"], "")
        self.assertEqual(payload["lines_source"], "OV/1")

    def test_request_own_reason_survives_when_lines_are_not_live(self):
        note = "<p>Hospedaje Tampico</p>"
        _draft, approver = self._draft_with_reason(note)

        payload = self._payload_for(
            approver,
            {
                "lines": [{"product": "Travel", "quantity": 1.0, "price_unit": 9.0}],
                "more": 0,
                "live": False,
                "source": "",
            },
        )

        self.assertEqual(payload["reason"], note)


class TestTerminalNotificationErrors(ApprovalRequestTestBase):
    def _fire_terminal_transition(self, error):
        with self.mock_api_gateway_post():
            self.approver.with_user(self.test_user).action_approve()
        self.assertEqual(self.approval_request.state, "approved")
        with patch.object(
            TelegramApprovalNotifier, "_notify_owner_outcome", side_effect=error
        ):
            self.approval_request._notify_if_terminal_transition("new")

    def test_a_concurrent_update_reaches_the_retry_layer(self):
        error = psycopg.errors.SerializationFailure(
            "could not serialize access due to concurrent update"
        )

        with self.assertRaises(psycopg.errors.SerializationFailure):
            self._fire_terminal_transition(error)

    def test_a_telegram_outage_still_does_not_block_the_approval(self):
        self.test_bot.notify_approvals = True
        with (
            self.mock_api_gateway_post(),
            patch.object(TelegramClient, "call", side_effect=ValueError("down")),
        ):
            self.approver.with_user(self.test_user).action_approve()
        self.assertEqual(self.approval_request.state, "approved")
