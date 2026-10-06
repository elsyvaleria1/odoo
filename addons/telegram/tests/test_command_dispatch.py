from unittest.mock import patch

from psycopg import IntegrityError

from odoo.tests import tagged

from .common import TelegramBotTestCase
from odoo.addons.telegram.models.telegram_bot import TelegramBot
from odoo.addons.telegram.tools.dispatch import TelegramCommand


class TestCommandDispatch(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.controller = self.env["telegram.router"]

    def test_dispatch_valid_command(self):
        self.test_chat.write({"failed_command_count": 2})

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response):
            self.controller._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/start",
                [],
                self.test_partner,
                self.test_user,
            )

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.failed_command_count, 0)

    def test_dispatch_unknown_command(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.controller._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/unknown",
                [],
                self.test_partner,
                self.test_user,
            )

            self.assertTrue(mock_post.called)

    def test_a_registered_command_with_no_method_still_answers(self):
        command = self.env["telegram.command"].create({"name": "/fantasma"})
        self.test_bot.command_ids = [(4, command.id)]
        handler = type(self.env["telegram.handler.base"])
        declared = handler._telegram_commands

        def commands(this):
            return {
                **declared(this),
                "/fantasma": TelegramCommand("_handle_fantasma_command", "unlinked"),
            }

        with (
            patch.object(handler, "_telegram_commands", commands),
            self.mock_api_gateway_post() as mock_post,
        ):
            self.controller._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/fantasma",
                [],
                self.test_partner,
                self.test_user,
            )

        self.assertTrue(mock_post.called)


class TestCommandPermissions(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.controller = self.env["telegram.router"]

    def test_unlinked_user_denied_partner_commands(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.controller._dispatch_command(
                self.test_bot,
                self.unlinked_chat,
                "/quiensoy",
                [],
                partner=False,
                internal_user=False,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "").lower()
            self.assertTrue(
                "vincul" in text
                or "connect" in text
                or "link" in text
                or "permiso" in text
                or "permission" in text,
                f"Expected denial/linking message, got: {text}",
            )

    def test_partner_allowed_partner_commands(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.controller._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/quiensoy",
                [],
                self.test_partner,
                internal_user=False,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn(self.test_partner.name, text)

    def test_unlinked_user_allowed_public_commands(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.controller._dispatch_command(
                self.test_bot,
                self.unlinked_chat,
                "/start",
                [],
                partner=False,
                internal_user=False,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertTrue(
                "Bienvenido" in text or "Welcome" in text,
                f"Expected welcome message, got: {text}",
            )

    def test_internal_user_has_all_permissions(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.controller._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/quiensoy",
                [],
                self.test_partner,
                self.test_user,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "").lower()
            denial_keywords = [
                "vincul",
                "link",
                "permiso",
                "permission",
                "no puede",
            ]
            has_denial = any(kw in text for kw in denial_keywords)
            self.assertFalse(
                has_denial, f"Internal user should not be denied. Got: {text}"
            )


class TestCommandErrorHandling(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.controller = self.env["telegram.router"]

    def test_handler_exception_increments_failed_state(self):
        initial_count = self.test_chat.failed_command_count

        with patch.object(
            type(self.env["telegram.handler.base"]),
            "_handle_start_command",
            side_effect=Exception("Command error"),
        ):
            mock_response = self.mock_telegram_response(
                success=True, result={"message_id": 1}
            )

            with self.mock_api_gateway_post(mock_response):
                self.controller._dispatch_command(
                    self.test_bot,
                    self.test_chat,
                    "/start",
                    [],
                    self.test_partner,
                    self.test_user,
                )

        self.assertGreater(self.test_chat.failed_command_count, initial_count)

    def test_success_resets_failed_state(self):
        self.test_chat.write(
            {
                "failed_command_count": 2,
                "last_error": "Previous error",
            }
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response):
            self.controller._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/start",
                [],
                self.test_partner,
                self.test_user,
            )

        self.assertEqual(self.test_chat.failed_command_count, 0)
        self.assertFalse(self.test_chat.last_error)

    def test_auto_suggest_help_after_3_failures(self):
        self.test_chat.write({"failed_command_count": 2})

        with patch.object(
            type(self.env["telegram.handler.base"]),
            "_handle_start_command",
            side_effect=Exception("Command error"),
        ):
            mock_response = self.mock_telegram_response(
                success=True, result={"message_id": 1}
            )

            with self.mock_api_gateway_post(mock_response) as mock_post:
                self.controller._dispatch_command(
                    self.test_bot,
                    self.test_chat,
                    "/start",
                    [],
                    self.test_partner,
                    self.test_user,
                )

                calls = mock_post.call_args_list
                self.assertEqual(len(calls), 1)
                payload = calls[0].kwargs.get("json", {})
                self.assertIn("ayuda", payload.get("text", ""))


class TestCommandModel(TelegramBotTestCase):
    def test_create_command(self):
        command = self.env["telegram.command"]._for_name("/mycommand")
        self.assertEqual(command.name, "/mycommand")

    def test_create_command_without_slash_gets_one(self):
        command = self.env["telegram.command"]._for_name("noprefix")
        self.assertEqual(
            command.name,
            "/noprefix",
            "a command is matched against the wire format, so it is stored that way",
        )

    def test_command_name_is_normalised(self):
        command = self.env["telegram.command"].create({"name": " /NormalisedHere "})
        self.assertEqual(command.name, "/normalisedhere")

    def test_a_duplicate_command_is_rejected(self):
        self.env["telegram.command"].create({"name": "/twice"})
        self.env.flush_all()
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env["telegram.command"].create({"name": "/TWICE"})
            self.env.flush_all()

    def test_for_name_returns_the_existing_command(self):
        first = self.env["telegram.command"]._for_name("/reused")
        self.assertEqual(
            self.env["telegram.command"]._for_name("reused"),
            first,
            "production carried duplicate /pago rows before the constraint",
        )

    def test_command_bot_many2many_relationship(self):
        command1 = self.env["telegram.command"]._for_name("/cmd1")
        command2 = self.env["telegram.command"]._for_name("/cmd2")

        self.test_bot.write({"command_ids": [(4, command1.id), (4, command2.id)]})

        self.assertIn(command1, self.test_bot.command_ids)
        self.assertIn(command2, self.test_bot.command_ids)
        self.assertEqual(len(self.test_bot.command_ids), 2)

    def test_command_can_be_shared_between_bots(self):
        command = self.env["telegram.command"]._for_name("/shared")

        telegram_service = self.env.ref("telegram.service_telegram")
        bearer_category = self.env.ref("credential.credential_category_bearer_token")
        new_credential = self.env["credential.credential"].create(
            {
                "name": "Second Bot Credential",
                "category_id": bearer_category.id,
                "endpoint_id": telegram_service.id,
                "bearer_token": "222222:SECOND-BOT-token",
            }
        )
        second_bot = self.env["telegram.bot"].create(
            {
                "name": "Second Bot",
                "credential_id": new_credential.id,
            }
        )

        self.test_bot.write({"command_ids": [(4, command.id)]})
        second_bot.write({"command_ids": [(4, command.id)]})

        self.assertIn(command, self.test_bot.command_ids)
        self.assertIn(command, second_bot.command_ids)

    def test_remove_command_from_bot(self):
        command = self.env["telegram.command"]._for_name("/removable")
        self.test_bot.write({"command_ids": [(4, command.id)]})

        self.test_bot.write({"command_ids": [(3, command.id)]})

        self.assertNotIn(command, self.test_bot.command_ids)
        self.assertTrue(command.exists())

    def test_delete_command_removes_from_bot(self):
        command = self.env["telegram.command"]._for_name("/todelete")
        self.test_bot.write({"command_ids": [(4, command.id)]})

        command_count_before = len(self.test_bot.command_ids)

        command.unlink()

        self.test_bot.invalidate_recordset()
        self.assertEqual(len(self.test_bot.command_ids), command_count_before - 1)


class TestFlowGuard(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.controller = self.env["telegram.router"]
        self.mock_ok = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

    def test_an_idle_chat_has_no_flow_owner(self):
        self.assertIsNone(self.controller._flow_owner(self.test_chat))

    def test_the_flow_owner_names_the_flow(self):
        self.test_chat._flow_start("telegram.handler.base", "other")

        owner = self.controller._flow_owner(self.test_chat)

        self.assertEqual(owner._name, "telegram.handler.base")
        self.assertEqual(
            owner._telegram_flow_label(self.test_bot, self.test_chat), "an operation"
        )

    def test_the_busy_notice_names_the_generic_cancel(self):
        self.test_chat._flow_start("telegram.handler.base", "other")
        with patch.object(TelegramBot, "send_message") as mock_send:
            self.controller._send_flow_busy_notice(
                self.test_bot,
                self.test_chat,
                self.controller._flow_owner(self.test_chat),
            )

        self.assertIn("/cancelar", mock_send.call_args.args[1])

    def test_cancelar_ends_any_flow_after_its_owner_cleans_up(self):
        self.test_chat._flow_start("telegram.handler.base", "other", {"step": 2})
        seen = []
        with (
            patch.object(
                type(self.env["telegram.handler.base"]),
                "_on_flow_cancelled",
                lambda this, bot, chat: seen.append(dict(chat.flow_data)),
            ),
            patch.object(TelegramBot, "send_message") as mock_send,
        ):
            self.controller._dispatch_command(
                self.test_bot, self.test_chat, "/cancelar", [], False, False
            )

        self.assertEqual(seen, [{"step": 2}])
        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)
        self.assertEqual(mock_send.call_args.args[1], "Done, I cancelled an operation.")

    def test_cancelar_with_nothing_open(self):
        with patch.object(TelegramBot, "send_message") as mock_send:
            self.controller._dispatch_command(
                self.test_bot, self.test_chat, "/cancelar", [], False, False
            )

        self.assertEqual(
            mock_send.call_args.args[1], "You have nothing in progress to cancel."
        )

    def test_the_discard_button_lets_the_owner_clean_up(self):
        self.test_chat._flow_start("telegram.handler.base", "other")
        with (
            patch.object(
                type(self.env["telegram.handler.base"]), "_on_flow_cancelled"
            ) as hook,
            self.mock_api_gateway_post(self.mock_ok),
        ):
            self.controller._handle_flow_busy_callback(
                self.test_bot,
                self.test_chat,
                {"id": "cb1", "data": "tg_busy:discard", "message": {}},
                self.test_partner,
                self.test_user,
            )

        hook.assert_called_once()
        self.assertFalse(self.test_chat.flow_owner)

    def test_guard_refuses_start_and_leaves_flow_untouched(self):
        self.test_chat._flow_start("telegram.handler.base", "other", {"step": 2})
        with (
            self.extra_command("/ayuda", starts_flow=True),
            patch.object(TelegramBot, "send_message") as mock_send,
        ):
            self.controller._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/ayuda",
                [],
                self.test_partner,
                self.test_user,
            )

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_owner, "telegram.handler.base")
        self.assertEqual(self.test_chat.flow_data, {"step": 2})
        self.assertIn("in progress", mock_send.call_args.args[1])

    def test_guard_offers_keep_and_restart_buttons(self):
        self.test_chat._flow_start("telegram.handler.base", "other")
        with (
            self.extra_command("/ayuda", starts_flow=True),
            patch.object(TelegramBot, "send_message") as mock_send,
        ):
            self.controller._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/ayuda",
                [],
                self.test_partner,
                self.test_user,
            )

        keyboard = mock_send.call_args.kwargs["reply_markup"]["inline_keyboard"]
        callbacks = [button[0]["callback_data"] for button in keyboard]
        self.assertEqual(callbacks, ["tg_busy:keep", "tg_busy:restart:/ayuda"])

    def test_guard_allows_start_when_idle(self):
        with (
            self.extra_command("/ayuda", starts_flow=True),
            patch.object(TelegramBot, "send_message") as mock_send,
        ):
            self.controller._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/ayuda",
                [],
                self.test_partner,
                self.test_user,
            )

        self.assertNotIn("en proceso", mock_send.call_args.args[1])

    def test_keep_callback_leaves_the_flow_running(self):
        self.test_chat._flow_start("telegram.handler.base", "other", {"step": 2})
        callback_query = {
            "id": "cb1",
            "data": "tg_busy:keep",
            "message": {"message_id": 42},
        }

        with self.mock_api_gateway_post(self.mock_ok):
            self.controller._handle_flow_busy_callback(
                self.test_bot,
                self.test_chat,
                callback_query,
                self.test_partner,
                self.test_user,
            )

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_owner, "telegram.handler.base")
        self.assertEqual(self.test_chat.flow_data, {"step": 2})

    def test_discard_callback_wording_follows_the_trigger(self):
        for data, expected, forbidden in [
            ("tg_busy:discard:message", "Tell me again", "Tap the button"),
            ("tg_busy:discard", "Tap the button", "Tell me again"),
        ]:
            with self.subTest(data=data):
                self.test_chat._flow_start("telegram.handler.base", "other")
                callback_query = {
                    "id": "cb1",
                    "data": data,
                    "message": {"message_id": 42},
                }
                with self.mock_api_gateway_post(self.mock_ok) as mock_post:
                    self.controller._handle_flow_busy_callback(
                        self.test_bot,
                        self.test_chat,
                        callback_query,
                        self.test_partner,
                        self.test_user,
                    )
                texts = [
                    call.kwargs.get("json", {}).get("text", "")
                    for call in mock_post.call_args_list
                ]
                self.assertTrue(any(expected in text for text in texts), texts)
                self.assertFalse(any(forbidden in text for text in texts), texts)
                self.test_chat.invalidate_recordset()
                self.assertFalse(self.test_chat.flow_owner)

    def test_restart_callback_resets_and_redispatches(self):
        self.test_chat._flow_start("telegram.handler.base", "other", {"step": 2})
        callback_query = {
            "id": "cb1",
            "data": "tg_busy:restart:/ayuda",
            "message": {"message_id": 42},
        }

        with (
            self.extra_command("/ayuda", starts_flow=True),
            self.mock_api_gateway_post(self.mock_ok),
            patch.object(
                type(self.env["telegram.handler.base"]), "_handle_help_command"
            ) as mock_help,
        ):
            self.controller._handle_flow_busy_callback(
                self.test_bot,
                self.test_chat,
                callback_query,
                self.test_partner,
                self.test_user,
            )

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)
        self.assertFalse(self.test_chat.flow_data)
        mock_help.assert_called_once()

    def test_restart_callback_rejects_unregistered_command(self):
        self.test_chat._flow_start("telegram.handler.base", "other")
        callback_query = {
            "id": "cb1",
            "data": "tg_busy:restart:/quiensoy",
            "message": {"message_id": 42},
        }

        with (
            self.extra_command("/ayuda", starts_flow=True),
            self.mock_api_gateway_post(self.mock_ok),
            patch.object(
                type(self.env["telegram.router"]), "_dispatch_command"
            ) as mock_dispatch,
        ):
            self.controller._handle_flow_busy_callback(
                self.test_bot,
                self.test_chat,
                callback_query,
                self.test_partner,
                self.test_user,
            )

        mock_dispatch.assert_not_called()
        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_owner, "telegram.handler.base")


@tagged("post_install", "-at_install")
class TestHandlerDeclarations(TelegramBotTestCase):
    def test_the_installed_handlers_declare_no_collision(self):
        commands, _prefixes = self.env["telegram.router"]._check_handler_declarations()
        self.assertEqual(commands["/ayuda"], "telegram.handler.base")

    def test_two_handlers_claiming_a_command_fail(self):
        router = self.env["telegram.router"]
        with (
            patch.object(
                type(router),
                "_handlers",
                lambda this, bot=None: [this.env["telegram.handler.base"]] * 2,
            ),
            self.assertRaises(ValueError),
        ):
            router._check_handler_declarations()

    def test_overlapping_callback_prefixes_fail(self):
        base = type(self.env["telegram.handler.base"])
        router = self.env["telegram.router"]
        calls = iter([("ab:",), ("ab:cd",)])
        with (
            patch.object(base, "_telegram_commands", lambda this: {}),
            patch.object(base, "_telegram_callback_prefixes", lambda this: next(calls)),
            patch.object(
                type(router),
                "_handlers",
                lambda this, bot=None: [
                    this.env["telegram.handler.base"],
                    this.env["telegram.handler.base"],
                ],
            ),
            self.assertRaises(ValueError),
        ):
            router._check_handler_declarations()

    def test_the_default_guard_lets_an_idle_chat_through(self):
        self.assertFalse(
            self.env["telegram.router"]._flow_guard_blocks(
                self.test_bot, self.test_chat, "x"
            )
        )


class TestPerBotCommandAllowlist(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.controller = self.env["telegram.router"]

        def start(this, bot, chat, args, partner=False, internal_user=False):
            return this._handle_start_command(bot, chat, args, partner, internal_user)

        onlyhere = self.extra_command("/onlyhere", start, tier="partner")
        onlyhere.__enter__()
        self.addCleanup(onlyhere.__exit__, None, None, None)

    def _dispatch(self):
        response = self.mock_telegram_response(success=True, result={"message_id": 1})
        with self.mock_api_gateway_post(response) as mock_post:
            self.controller._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/onlyhere",
                [],
                self.test_partner,
                internal_user=False,
            )
        return mock_post.call_args.kwargs["json"]["text"]

    def test_a_registered_handler_still_needs_the_bot_link(self):
        self.assertIn(
            "Unknown command",
            self._dispatch(),
            "one deployment runs several bots off the same code; the per-bot "
            "command list is what keeps them apart",
        )

    def test_linking_the_command_enables_it(self):
        command = self.env["telegram.command"]._for_name("/onlyhere")
        self.test_bot.command_ids = [(4, command.id)]
        self.assertNotIn("desconocido", self._dispatch())

    def test_the_modules_own_commands_need_no_link(self):
        self.assertFalse(self.test_bot.command_ids)
        response = self.mock_telegram_response(success=True, result={"message_id": 1})
        with self.mock_api_gateway_post(response) as mock_post:
            self.controller._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/ayuda",
                [],
                self.test_partner,
                internal_user=False,
            )
        self.assertNotIn("desconocido", mock_post.call_args.kwargs["json"]["text"])
