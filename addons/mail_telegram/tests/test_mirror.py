from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import new_test_user

from odoo.addons.telegram.tests.common import TelegramBotTestCase

GROUP_ID = -1007001
STRANGER_ID = 770001
_CLIENT_CALL = "odoo.addons.telegram.tools.telegram_client.TelegramClient.call"


class MirrorCase(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_bot.write({"bot_username": "odoo_test_bot", "can_join_groups": True})
        cls.channel = (
            cls.env["discuss.channel"]
            .with_user(cls.test_user)
            .create({"name": "Cuadrilla norte", "channel_type": "telegram"})
        )

    def _group_message(self, text="hola", sender=STRANGER_ID, message_id=1, **extra):
        return {
            "message_id": message_id,
            "from": {"id": sender, "first_name": "Pedro", "language_code": "es"},
            "chat": {"id": GROUP_ID, "type": "supergroup", "title": "Cuadrilla"},
            "date": 1234567890,
            "text": text,
            **extra,
        }

    def _dispatch(self, message):
        with (
            self.mock_api_gateway_post(),
            self.mock_rate_limiter(),
            patch.object(
                type(self.test_bot), "_is_chat_administrator", return_value=True
            ),
            patch.object(type(self.test_bot), "send_message") as send,
        ):
            self.env["telegram.router"]._dispatch_message(self.test_bot, message)
        return send

    def _connect(self):
        wizard = (
            self.env["wizard.telegram.group.link"]
            .with_user(self.test_user)
            .create({"bot_id": self.test_bot.id, "channel_id": self.channel.id})
        )
        wizard.action_issue()
        token = wizard.link.split("startgroup=")[1]
        send = self._dispatch(self._group_message(f"/start {token}", sender=12345))
        return self.env["telegram.chat"].search([("chat_id", "=", str(GROUP_ID))]), send

    def _queued(self, chat):
        return self.env["telegram.message"].search(
            [("chat_id", "=", chat.id), ("message_type", "=", "outbound")], order="id"
        )


class TestConnecting(MirrorCase):
    def test_the_link_connects_the_group_to_the_channel(self):
        chat, send = self._connect()
        mirror = self.env["telegram.mirror"]._of_chat(chat)
        self.assertEqual(mirror._record(), self.channel)
        self.assertEqual(mirror.kind, "group")
        self.assertFalse(chat.rate_limit_enabled)
        self.assertEqual(chat.title, "Cuadrilla")
        self.assertIn("Cuadrilla norte", send.call_args.args[1])
        self.assertIn(
            "Connected to the Telegram group",
            self.channel.message_ids[:1].body,
        )

    def test_a_bot_that_cannot_read_the_group_says_so(self):
        self.test_bot.can_read_all_group_messages = False
        _chat, send = self._connect()
        self.assertIn("privacy mode", send.call_args.args[1])

    def test_the_link_needs_the_user_s_own_telegram(self):
        other = self.env["res.users"].create({"name": "Sin Telegram", "login": "sintg"})
        channel = (
            self.env["discuss.channel"]
            .with_user(other)
            .create({"name": "Otro", "channel_type": "telegram"})
        )
        wizard = (
            self.env["wizard.telegram.group.link"]
            .with_user(other)
            .create({"bot_id": self.test_bot.id, "channel_id": channel.id})
        )
        with self.assertRaisesRegex(Exception, "Connect your own Telegram"):
            wizard.action_issue()

    def test_a_new_channel_is_made_when_none_is_named(self):
        wizard = (
            self.env["wizard.telegram.group.link"]
            .with_user(self.test_user)
            .create({"bot_id": self.test_bot.id, "name": "Almacén"})
        )
        wizard.action_issue()
        self.assertEqual(wizard.channel_id.channel_type, "telegram")
        self.assertTrue(wizard.channel_id.is_member)
        self.assertIn("?startgroup=", wizard.link)


class TestInbound(MirrorCase):
    def test_a_stranger_speaks_as_a_contact_made_for_them(self):
        chat, _send = self._connect()
        self._dispatch(self._group_message("buenos días", message_id=2))

        posted = self.channel.message_ids.filtered(
            lambda m: "buenos días" in (m.body or "")
        )
        self.assertEqual(posted.author_id.name, "Pedro")
        self.assertIn(posted.author_id, self.channel.channel_member_ids.partner_id)
        account = self.env["telegram.account"].search(
            [("tg_user_id", "=", str(STRANGER_ID))]
        )
        self.assertEqual(account.binding_id.method, "contact")
        self.assertFalse(
            self.channel.message_ids.filtered(lambda m: "joined" in (m.body or ""))
        )
        self.assertFalse(
            self._queued(chat).filtered(lambda m: "buenos" in (m.text or ""))
        )

    def test_the_group_speaks_with_its_connector_s_rights(self):
        chat, _send = self._connect()
        self.assertEqual(
            self.env["telegram.mirror"]._of_chat(chat).user_id, self.test_user
        )
        self._dispatch(self._group_message("buenos días", message_id=2))

        posted = self.channel.message_ids.filtered(
            lambda m: "buenos días" in (m.body or "")
        )
        self.assertEqual(posted.author_id.name, "Pedro")
        self.assertEqual(posted.create_uid, self.test_user)

    def test_a_group_whose_connector_may_not_post_there_posts_nothing(self):
        chat, _send = self._connect()
        outsider = new_test_user(
            self.env, login="mirror_outsider", groups="base.group_portal"
        )
        self.env["telegram.mirror"]._of_chat(chat).sudo().user_id = outsider
        self._dispatch(self._group_message("buenos días", message_id=2))

        self.assertFalse(
            self.channel.message_ids.filtered(lambda m: "buenos días" in (m.body or ""))
        )

    def test_a_connected_user_speaks_as_themselves(self):
        self._connect()
        self._dispatch(self._group_message("yo mero", sender=12345, message_id=2))
        posted = self.channel.message_ids.filtered(
            lambda m: "yo mero" in (m.body or "")
        )
        self.assertEqual(posted.author_id, self.test_partner)

    def test_an_edit_in_telegram_edits_the_odoo_message(self):
        chat, _send = self._connect()
        self._dispatch(self._group_message("son 10 cajas", message_id=2))
        with self.mock_api_gateway_post(), self.mock_rate_limiter():
            self.env["telegram.router"]._dispatch_edited_message(
                self.test_bot, self._group_message("son 12 cajas", message_id=2)
            )
        posted = self.channel.message_ids.filtered(lambda m: "cajas" in (m.body or ""))
        self.assertIn("12 cajas", posted.body)
        self.assertFalse(self._queued(chat).filtered(lambda m: m.target_id))


class TestOutbound(MirrorCase):
    def test_an_odoo_message_goes_to_the_group_under_its_author(self):
        chat, _send = self._connect()
        self.channel.with_user(self.test_user).message_post(
            body="Salimos a las 7",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        queued = self._queued(chat).filtered(lambda m: m.mail_message_id)
        self.assertEqual(len(queued), 1)
        self.assertIn("<b>Test User</b>: Salimos a las 7", queued.payload["text"])

    def test_a_reply_answers_the_telegram_message(self):
        chat, _send = self._connect()
        self._dispatch(self._group_message("¿a qué hora?", message_id=5))
        question = self.channel.message_ids.filtered(lambda m: "hora" in (m.body or ""))
        self.channel.with_user(self.test_user).message_post(
            body="A las 7",
            parent_id=question.id,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        answer = self._queued(chat).filtered(lambda m: "A las 7" in (m.text or ""))
        self.assertEqual(answer.reply_to_uid, "5")

    def test_an_edit_and_a_deletion_in_odoo_follow_to_the_group(self):
        chat, _send = self._connect()
        message = self.channel.with_user(self.test_user).message_post(
            body="Salimos a las 7",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        sent = self._queued(chat).filtered(lambda m: m.mail_message_id == message)
        # as the web route does: access checked, then the message in sudo
        self.channel.with_user(self.test_user)._message_update_content(
            message.sudo(), body="Salimos a las 8"
        )
        edit = self._queued(chat).filtered(lambda m: m.api_method == "editMessageText")
        self.assertEqual(edit.target_id, sent)
        self.assertIn("a las 8", edit.payload["text"])

        self.channel.with_user(self.test_user)._message_update_content(
            message.sudo(), body="", attachment_ids=[]
        )
        deletion = self._queued(chat).filtered(
            lambda m: m.api_method == "deleteMessage"
        )
        self.assertEqual(deletion.target_id, sent)

    def test_members_are_not_notified_on_their_own_telegram(self):
        self._connect()
        recipient = {"id": self.test_partner.id, "notif": "inbox"}
        self.assertIsNone(self.channel._telegram_notification_kind(recipient))


class TestTopicsAndLife(MirrorCase):
    def _topic_event(self, event, thread_uid, **data):
        message = self._group_message(
            text="", message_id=90, message_thread_id=thread_uid
        )
        message.pop("text")
        message[event] = data
        return message

    def test_a_forum_topic_is_a_sub_channel_named_and_renamed_with_it(self):
        chat, _send = self._connect()
        self._dispatch(self._topic_event("forum_topic_created", 11, name="Riego"))
        topic = self.env["telegram.mirror"]._of_chat(chat, "11")
        sub_channel = topic._record()
        self.assertEqual(sub_channel.parent_channel_id, self.channel)
        self.assertEqual(sub_channel.name, "Riego")

        self._dispatch(self._topic_event("forum_topic_edited", 11, name="Riego norte"))
        self.assertEqual(sub_channel.name, "Riego norte")
        self.assertFalse(
            self._queued(chat).filtered(lambda m: m.api_method == "editForumTopic")
        )

        self._dispatch(
            self._group_message(
                "abrí la válvula",
                message_id=12,
                message_thread_id=11,
                is_topic_message=True,
            )
        )
        self.assertTrue(
            sub_channel.message_ids.filtered(lambda m: "válvula" in (m.body or ""))
        )

    def test_a_topic_unknown_to_odoo_opens_when_it_speaks(self):
        chat, _send = self._connect()
        self._dispatch(
            self._group_message(
                "ya llegó el camión",
                message_id=20,
                message_thread_id=21,
                is_topic_message=True,
                reply_to_message={
                    "message_id": 21,
                    "forum_topic_created": {"name": "Logística"},
                },
            )
        )
        sub_channel = self.env["telegram.mirror"]._of_chat(chat, "21")._record()
        self.assertEqual(sub_channel.name, "Logística")
        self.assertTrue(
            sub_channel.message_ids.filtered(lambda m: "camión" in (m.body or ""))
        )

    def test_a_thread_opened_in_odoo_becomes_a_topic(self):
        chat, _send = self._connect()
        with patch(_CLIENT_CALL, return_value={"message_thread_id": 31}) as call:
            sub_channel = self.channel.with_user(self.test_user)._create_sub_channel(
                name="Cosecha"
            )
        self.assertEqual(call.call_args.args[0], "createForumTopic")
        mirror = self.env["telegram.mirror"]._of_thread(sub_channel)
        self.assertEqual(mirror.thread_uid, "31")
        sub_channel.with_user(self.test_user).message_post(
            body="Empezamos", message_type="comment", subtype_xmlid="mail.mt_comment"
        )
        sent = self._queued(chat).filtered(lambda m: "Empezamos" in (m.text or ""))
        self.assertEqual(sent.thread_uid, "31")

    def test_the_mirror_follows_the_group_into_its_supergroup(self):
        chat, _send = self._connect()
        chat.chat_type = "group"
        supergroup = chat._migrate_to(-1009999)
        self.assertEqual(
            self.env["telegram.mirror"]._of_chat(supergroup)._record(), self.channel
        )

    def test_removing_the_bot_is_said_in_the_channel(self):
        self._connect()
        with self.mock_api_gateway_post():
            self.env["telegram.router"]._dispatch_my_chat_member(
                self.test_bot,
                {
                    "chat": {"id": GROUP_ID, "type": "supergroup"},
                    "new_chat_member": {"status": "kicked"},
                },
            )
        self.assertIn("was removed", self.channel.message_ids[:1].body)


class TestRecordMirror(MirrorCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_user.group_ids |= cls.env.ref("base.group_partner_manager")
        cls.customer = cls.env["res.partner"].create({"name": "Rancho El Sauz"})

    def _connect_record(self):
        action = self.customer.with_user(self.test_user).action_telegram_connect_group()
        wizard = (
            self.env["wizard.telegram.group.link"]
            .with_user(self.test_user)
            .with_context(**action["context"])
            .create({"bot_id": self.test_bot.id})
        )
        self.assertEqual(wizard.record_name, "Rancho El Sauz")
        wizard.action_issue()
        token = wizard.link.split("startgroup=")[1]
        self._dispatch(self._group_message(f"/start {token}", sender=12345))
        return self.env["telegram.chat"].search([("chat_id", "=", str(GROUP_ID))])

    def test_a_group_mirrors_a_record_s_chatter(self):
        chat = self._connect_record()
        mirror = self.env["telegram.mirror"]._of_chat(chat)
        self.assertEqual((mirror.kind, mirror._record()), ("record", self.customer))

        self._dispatch(self._group_message("ya se regó el lote 3", message_id=2))
        posted = self.customer.message_ids.filtered(
            lambda m: "lote 3" in (m.body or "")
        )
        self.assertEqual(posted.author_id.name, "Pedro")

        self.customer.with_user(self.test_user).message_post(
            body="Gracias", message_type="comment", subtype_xmlid="mail.mt_comment"
        )
        self.customer.with_user(self.test_user).message_post(
            body="Nota interna", message_type="comment", subtype_xmlid="mail.mt_note"
        )
        texts = [m.text or "" for m in self._queued(chat)]
        self.assertTrue(any("Gracias" in text for text in texts))
        self.assertFalse(any("Nota interna" in text for text in texts))

    def test_a_record_the_user_cannot_write_cannot_be_connected(self):
        reader = self.env["res.users"].create(
            {
                "name": "Lector",
                "login": "lector_tg",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.env["telegram.chat"].create(
            {
                "chat_id": "880",
                "chat_type": "private",
                "bot_id": self.test_bot.id,
                "account_id": self._bound_account(
                    "880", reader.partner_id, user=reader
                ).id,
            }
        )
        wizard = (
            self.env["wizard.telegram.group.link"]
            .with_user(reader)
            .create(
                {
                    "bot_id": self.test_bot.id,
                    "res_model": "res.partner",
                    "res_id": self.customer.id,
                }
            )
        )
        with self.assertRaises(AccessError):
            wizard.action_issue()


class TestBroadcast(MirrorCase):
    CHANNEL_ID = -1008001

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.announcements = (
            cls.env["discuss.channel"]
            .with_user(cls.test_user)
            .create({"name": "Avisos", "channel_type": "channel"})
        )

    def _issue(self):
        action = self.announcements.with_user(
            self.test_user
        ).action_telegram_connect_group()
        wizard = (
            self.env["wizard.telegram.group.link"]
            .with_user(self.test_user)
            .with_context(**action["context"])
            .create({"bot_id": self.test_bot.id})
        )
        self.assertEqual(wizard.purpose, "broadcast")
        wizard.action_issue()
        self.assertIn("?startchannel&admin=post_messages", wizard.link)
        return wizard.command

    def _post(self, text, admin=True):
        post = {
            "message_id": 41,
            "chat": {"id": self.CHANNEL_ID, "type": "channel", "title": "Avisos Marin"},
            "date": 1234567890,
            "text": text,
        }
        with (
            self.mock_api_gateway_post(),
            patch.object(
                type(self.test_bot), "_is_chat_administrator", return_value=admin
            ),
            patch.object(type(self.test_bot), "send_message") as send,
        ):
            self.env["telegram.router"]._handle_update(
                self.test_bot, {"update_id": 5001, "channel_post": post}
            )
        chat = self.env["telegram.chat"].search(
            [("chat_id", "=", str(self.CHANNEL_ID))]
        )
        return chat, send

    def test_the_posted_command_connects_the_channel_and_is_deleted(self):
        chat, send = self._post(self._issue())
        mirror = self.env["telegram.mirror"]._of_chat(chat)
        self.assertEqual(
            (mirror.kind, mirror._record()), ("broadcast", self.announcements)
        )
        deletion = self._queued(chat).filtered(
            lambda m: m.api_method == "deleteMessage"
        )
        self.assertEqual(deletion.payload, {"message_id": 41})
        self.assertEqual(send.call_args.args[0], self.test_chat.chat_id)
        self.assertIn("Avisos Marin", send.call_args.args[1])

    def test_posts_are_published_as_the_channel_s_own(self):
        chat, _send = self._post(self._issue())
        self.announcements.with_user(self.test_user).message_post(
            body="Mañana no hay corte",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        published = self._queued(chat).filtered(lambda m: m.mail_message_id)
        self.assertEqual(published.payload["text"], "Mañana no hay corte")

    def test_someone_not_administering_the_channel_connects_nothing(self):
        chat, send = self._post(self._issue(), admin=False)
        self.assertFalse(self.env["telegram.mirror"]._of_chat(chat))
        self.assertTrue(
            self._queued(chat).filtered(lambda m: m.api_method == "deleteMessage")
        )
        self.assertIn("was not connected", send.call_args.args[1])

    def test_a_group_link_does_not_connect_a_channel(self):
        wizard = (
            self.env["wizard.telegram.group.link"]
            .with_user(self.test_user)
            .create({"bot_id": self.test_bot.id, "channel_id": self.channel.id})
        )
        wizard.action_issue()
        token = wizard.link.split("startgroup=")[1]
        chat, _send = self._post(f"/start {token}")
        self.assertFalse(self.env["telegram.mirror"]._of_chat(chat))


class TestReactionsAndTyping(MirrorCase):
    def _react(self, message_id, old=(), new=(), sender=STRANGER_ID):
        update = {
            "chat": {"id": GROUP_ID, "type": "supergroup"},
            "message_id": message_id,
            "user": {"id": sender, "first_name": "Pedro"},
            "date": 1234567890,
            "old_reaction": [{"type": "emoji", "emoji": e} for e in old],
            "new_reaction": [{"type": "emoji", "emoji": e} for e in new],
        }
        with self.mock_api_gateway_post():
            self.env["telegram.router"]._handle_update(
                self.test_bot,
                {"update_id": 6100 + len(new), "message_reaction": update},
            )

    def test_a_reaction_in_the_group_is_the_speaker_s_in_odoo(self):
        self._connect()
        self._dispatch(self._group_message("¿listos?", message_id=40))
        posted = self.channel.message_ids.filtered(
            lambda m: "listos" in (m.body or "")
        ).sudo()

        self._react(40, new=["👍"])
        reactor = posted.reaction_ids.partner_id
        self.assertEqual(posted.reaction_ids.content, "👍")
        self.assertEqual(reactor.name, "Pedro")

        self._react(40, old=["👍"], new=["🔥"])
        self.assertEqual(posted.reaction_ids.mapped("content"), ["🔥"])

    def test_someone_typing_in_odoo_shows_the_bot_typing_once(self):
        self._connect()
        member = self.channel.channel_member_ids.filtered(
            lambda m: m.partner_id == self.test_partner
        )
        mirror = self.env["telegram.mirror"].search([("res_id", "=", self.channel.id)])
        member._notify_typing(True)
        member._notify_typing(True)
        jobs = (
            self.env["ir.job"]
            .sudo()
            .search([("identity_key", "=", f"telegram.typing:{mirror.id}")])
        )
        self.assertEqual(len(jobs), 1)
        with patch.object(type(self.test_bot), "send_chat_action") as action:
            mirror._typing()
        self.assertEqual(action.call_args.args[1], "typing")
