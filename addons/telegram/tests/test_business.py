from unittest.mock import patch

from .common import TelegramBotTestCase

_CALL = "odoo.addons.telegram.tools.telegram_client.TelegramClient.call"

CUSTOMER_ID = 555001


class BusinessCase(TelegramBotTestCase):
    def _connect(self, owner_id=12345, enabled=True, can_reply=True, uid="bc-1"):
        update = {
            "update_id": 9001,
            "business_connection": {
                "id": uid,
                "user": {"id": owner_id, "first_name": "Owner"},
                "user_chat_id": owner_id,
                "date": 1234567890,
                "rights": {"can_reply": can_reply},
                "is_enabled": enabled,
            },
        }
        with self.mock_api_gateway_post() as post, self.mock_rate_limiter():
            self.env["telegram.router"]._handle_update(self.test_bot, update)
        connection = self.env["telegram.business.connection"].search(
            [("connection_uid", "=", uid)]
        )
        return connection, post

    def _business_message(self, text, from_owner=False, uid="bc-1", message_id=1):
        sender = (
            {"id": 12345, "first_name": "Owner"}
            if from_owner
            else {"id": CUSTOMER_ID, "first_name": "Cliente"}
        )
        return {
            "update_id": 9100 + message_id,
            "business_message": {
                "message_id": message_id,
                "business_connection_id": uid,
                "from": sender,
                "chat": {"id": CUSTOMER_ID, "type": "private", "first_name": "Cliente"},
                "date": 1234567890,
                "text": text,
            },
        }


class TestConnections(BusinessCase):
    def test_a_connection_of_a_bound_owner_is_usable(self):
        connection, _post = self._connect()
        self.assertEqual(connection.account_id, self.test_account)
        self.assertEqual(connection.user_id, self.test_user)
        self.assertTrue(connection._usable())

    def test_an_unbound_owner_is_told_to_connect_first(self):
        with patch.object(type(self.test_bot), "send_message") as send:
            connection, _post = self._connect(owner_id=777001)
        self.assertFalse(connection.user_id)
        self.assertFalse(connection._usable())
        chat_id, text = send.call_args.args[:2]
        self.assertEqual(str(chat_id), "777001")
        self.assertIn("Connect Telegram", text)

    def test_a_connection_without_reply_rights_is_not_usable(self):
        connection, _post = self._connect(can_reply=False)
        self.assertFalse(connection._usable())

    def test_a_later_update_disables_it(self):
        connection, _post = self._connect()
        self._connect(enabled=False)
        self.assertFalse(connection.is_enabled)
        self.assertFalse(connection._usable())

    def test_the_owner_losing_their_binding_disables_it(self):
        connection, _post = self._connect()
        self.test_binding.sudo()._revoke("admin")
        self.assertFalse(connection._usable())


class TestBusinessMessages(BusinessCase):
    def _dispatch(self, update):
        seen = []

        def hook(handler, bot, connection, chat, message, from_owner, edited):
            seen.append((connection, chat, message["text"], from_owner, edited))
            return False

        with (
            patch.object(
                type(self.env["telegram.handler.base"]), "_on_business_message", hook
            ),
            self.mock_api_gateway_post(),
            self.mock_rate_limiter(),
        ):
            self.env["telegram.router"]._handle_update(self.test_bot, update)
        return seen

    def test_a_customer_message_reaches_handlers_in_its_own_chat(self):
        connection, _post = self._connect()
        seen = self._dispatch(self._business_message("hola"))

        self.assertEqual(len(seen), 1)
        seen_connection, chat, text, from_owner, edited = seen[0]
        self.assertEqual(seen_connection, connection)
        self.assertEqual(chat.business_connection_id, connection)
        self.assertEqual(chat.chat_id, str(CUSTOMER_ID))
        self.assertEqual(chat.account_id.tg_user_id, str(CUSTOMER_ID))
        self.assertEqual((text, from_owner, edited), ("hola", False, False))

    def test_the_owner_writing_is_told_apart(self):
        self._connect()
        seen = self._dispatch(self._business_message("buenas", from_owner=True))
        _connection, chat, _text, from_owner, _edited = seen[0]
        self.assertTrue(from_owner)
        self.assertEqual(chat.account_id.tg_user_id, str(CUSTOMER_ID))

    def test_nothing_reaches_handlers_through_an_unusable_connection(self):
        self._connect(enabled=False)
        self.assertEqual(self._dispatch(self._business_message("hola")), [])

    def test_a_business_chat_and_the_customer_own_chat_coexist(self):
        self._connect()
        self._dispatch(self._business_message("hola"))
        own = self.env["telegram.chat"]._acquire_chat(
            CUSTOMER_ID, self.test_bot.id, chat_type="private"
        )
        chats = self.env["telegram.chat"].search(
            [("chat_id", "=", str(CUSTOMER_ID)), ("bot_id", "=", self.test_bot.id)]
        )
        self.assertEqual(len(chats), 2)
        self.assertFalse(own.business_connection_id)

    def test_what_odoo_sends_there_goes_out_as_the_owner(self):
        connection, _post = self._connect()
        seen = self._dispatch(self._business_message("hola"))
        chat = seen[0][1]
        message = self.test_bot.sudo()._queue_text(chat, "respuesta")
        with patch(_CALL, return_value={"message_id": 5}) as call:
            message._deliver()
        payload = call.call_args.args[1]
        self.assertEqual(payload["business_connection_id"], connection.connection_uid)

    def test_personal_notifications_never_pick_a_business_chat(self):
        self._connect()
        seen = self._dispatch(self._business_message("hola"))
        chat = seen[0][1]
        customer = self.env["res.partner"].create({"name": "Cliente"})
        chat.account_id._bind(customer, method="contact")
        self.assertFalse(self.env["telegram.chat"]._for_partner(customer))
