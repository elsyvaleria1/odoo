from datetime import timedelta
from unittest.mock import patch

from markupsafe import Markup

from odoo import Command, fields
from odoo.exceptions import AccessError

from odoo.addons.telegram.tests.common import NOT_A_MENU as _NOT_A_MENU
from odoo.addons.telegram.tests.common import TelegramBotTestCase


class MailTelegramCase(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_bot.notify_mail = True
        cls.test_user.write(
            {
                "notification_type": "inbox",
                "group_ids": [
                    (4, cls.env.ref("base.group_user").id),
                    (4, cls.env.ref("base.group_partner_manager").id),
                ],
            }
        )
        cls.author_partner = cls._create_partner({"name": "Colleague"})
        cls.author = cls.env["res.users"].create(
            {
                "name": "Colleague",
                "login": "colleague@example.com",
                "partner_id": cls.author_partner.id,
                "group_ids": [(4, cls.env.ref("base.group_user").id)],
            }
        )
        cls.record = cls._create_partner({"name": "Followed Record"})

    def _run_alert_jobs(self) -> None:
        jobs = (
            self.env["ir.job"]
            .sudo()
            .search(
                [
                    ("identity_key", "=like", "mail_telegram.unreachable:%"),
                    ("state", "in", ["scheduled", "pending"]),
                ]
            )
        )
        for job in jobs:
            job.action_run_now()

    def _queued(self):
        return self.env["telegram.message"].search(
            [
                ("chat_id", "=", self.test_chat.id),
                ("message_type", "=", "outbound"),
                _NOT_A_MENU,
            ]
        )

    def _post_to_user(self, **kwargs):
        return self.record.sudo().message_post(
            author_id=self.author_partner.id,
            body=Markup("<p>Revisa <b>esto</b></p>"),
            partner_ids=self.test_partner.ids,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            **kwargs,
        )


class TestDelivery(MailTelegramCase):
    def test_a_notification_is_queued_for_the_bound_user(self):
        message = self._post_to_user()

        queued = self._queued()
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued.mail_message_id, message)
        self.assertEqual(queued.recipient_partner_id, self.test_partner)
        self.assertEqual(queued.state, "outgoing")
        self.assertIn("<b>Colleague</b>", queued.payload["text"])
        self.assertIn("<b>esto</b>", queued.payload["text"])
        buttons = queued.payload["reply_markup"]["inline_keyboard"][0]
        self.assertIn(
            f"/mail/view?model=res.partner&res_id={self.record.id}", buttons[0]["url"]
        )
        self.assertEqual(buttons[1]["callback_data"], f"mt:read:{message.id}")

    def test_away_waits_the_grace_period(self):
        self._post_to_user()
        queued = self._queued()
        self.assertTrue(queued.mail_away_only)
        job = (
            self.env["ir.job"]
            .sudo()
            .search([("identity_key", "=", f"telegram.message:{queued.id}")])
        )
        self.assertGreater(job.eta, fields.Datetime.now() + timedelta(seconds=30))

    def test_always_sends_at_once(self):
        self.test_user._telegram_settings().telegram_notify_inbox = "always"
        self._post_to_user()
        self.assertFalse(self._queued().mail_away_only)

    def test_never_sends_nothing(self):
        self.test_user._telegram_settings().telegram_notify_inbox = "never"
        self._post_to_user()
        self.assertFalse(self._queued())

    def _other_company_chat(self, member=True):
        bot = self._bot_of_another_company("Other Mail Bot")
        bot.notify_mail = True
        if member:
            self.test_user.company_ids = [Command.link(bot.company_id.id)]
        return self.env["telegram.chat"].create(
            {
                "chat_id": self.test_chat.chat_id,
                "chat_type": "private",
                "bot_id": bot.id,
                "account_id": self.test_account.id,
            }
        )

    def _outbound(self, chat):
        return self.env["telegram.message"].search(
            [("chat_id", "=", chat.id), ("message_type", "=", "outbound"), _NOT_A_MENU]
        )

    def test_a_record_of_a_company_is_told_through_that_company_s_bot(self):
        other_chat = self._other_company_chat()
        self.record.company_id = self.test_bot.company_id

        self._post_to_user()

        self.assertEqual(len(self._queued()), 1)
        self.assertFalse(self._outbound(other_chat))

    def test_a_record_s_company_bot_carries_it_past_a_chosen_chat_elsewhere(self):
        self.test_user._telegram_settings().telegram_notify_inbox = "always"
        other_chat = self._other_company_chat()
        self.test_user._update_telegram_notify_chat(other_chat)
        self.record.company_id = self.test_bot.company_id

        self._post_to_user()

        self.assertEqual(len(self._queued()), 1)
        self.assertFalse(self._outbound(other_chat))
        self.assertTrue(self._queued()._still_wanted())

    def test_a_bot_of_a_company_the_user_is_not_in_tells_them_nothing(self):
        other_chat = self._other_company_chat(member=False)

        self._post_to_user()

        self.assertEqual(len(self._queued()), 1)
        self.assertFalse(self._outbound(other_chat))

    def test_a_bot_not_delivering_notifications_sends_nothing(self):
        self.test_bot.notify_mail = False
        self._post_to_user()
        self.assertFalse(self._queued())

    def test_a_message_no_one_reads_in_the_inbox_looks_up_no_bot(self):
        mailed = self._create_partner({"name": "Mailed", "email": "mailed@example.com"})
        record = self._create_partner({"name": "Unfollowed Record"})
        record.message_unsubscribe(record.message_partner_ids.ids)
        bots = type(self.env["telegram.bot"])
        with patch.object(
            bots, "search", autospec=True, side_effect=bots.search
        ) as search:
            record.sudo().message_post(
                author_id=self.author_partner.id,
                body=Markup("<p>Hola</p>"),
                partner_ids=mailed.ids,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        self.assertFalse(
            [call for call in search.call_args_list if "notify_mail" in str(call)]
        )

    def test_a_recipient_reached_on_telegram_otherwise_is_skipped(self):
        self.record = self.record.with_context(
            mail_telegram_skip_partner_ids=self.test_partner.ids
        )

        self._post_to_user()

        self.assertFalse(self._queued())

    def test_skipping_another_recipient_still_delivers(self):
        self.record = self.record.with_context(
            mail_telegram_skip_partner_ids=self.author_partner.ids
        )

        self._post_to_user()

        self.assertEqual(len(self._queued()), 1)

    def test_an_unbound_user_gets_nothing(self):
        self.test_binding._revoke("user")
        self._post_to_user()
        self.assertFalse(self._queued())

    def test_the_author_is_not_sent_their_own_message(self):
        self.record.sudo().message_post(
            author_id=self.test_partner.id,
            body="mine",
            partner_ids=self.test_partner.ids,
            message_type="comment",
        )
        self.assertFalse(self._queued())

    def test_attachments_follow_the_text(self):
        attachment = self.env["ir.attachment"].create(
            {"name": "plano.pdf", "raw": b"%PDF-1.4", "mimetype": "application/pdf"}
        )
        self._post_to_user(attachment_ids=attachment.ids)
        queued = self._queued().sorted("id")
        self.assertEqual(queued.mapped("api_method"), ["sendMessage", "sendDocument"])


class TestStillWanted(MailTelegramCase):
    def test_read_in_odoo_is_not_sent(self):
        message = self._post_to_user()
        message.with_user(self.test_user).set_message_done()
        self.assertFalse(self._queued()._still_wanted())

    def test_unread_is_sent(self):
        self._post_to_user()
        self.assertTrue(self._queued()._still_wanted())

    def test_online_and_away_only_is_not_sent(self):
        self._post_to_user()
        with patch.object(type(self.test_user), "im_status", "online"):
            self.assertFalse(self._queued()._still_wanted())

    def test_a_revoked_binding_is_not_sent(self):
        self._post_to_user()
        self.test_binding._revoke("user")
        self.assertFalse(self._queued()._still_wanted())


class TestDirectChat(MailTelegramCase):
    def test_a_direct_message_reaches_telegram(self):
        channel = (
            self.env["discuss.channel"]
            .with_user(self.author)
            ._get_or_create_chat(partners_to=self.test_partner.ids)
        )
        channel.with_user(self.author).message_post(
            body="¿Tienes un minuto?",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        queued = self._queued()
        self.assertEqual(len(queued), 1)
        self.assertIn("¿Tienes un minuto?", queued.payload["text"])


class TestReplies(MailTelegramCase):
    def _delivered(self, message, msg_uid="900"):
        return self.env["telegram.message"].create(
            {
                "bot_id": self.test_bot.id,
                "chat_id": self.test_chat.id,
                "message_type": "outbound",
                "state": "sent",
                "msg_uid": msg_uid,
                "mail_message_id": message.id,
                "recipient_partner_id": self.test_partner.id,
            }
        )

    def _reply(self, text, reply_to="900", message_id=901):
        update = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id, text=text, message_id=message_id
        )
        update["reply_to_message"] = {"message_id": int(reply_to)}
        with self.mock_api_gateway_post() as post, self.mock_rate_limiter():
            self.env["telegram.router"]._dispatch_message(self.test_bot, update)
        return post

    def test_a_reaction_to_a_notification_is_the_user_s_in_odoo(self):
        parent = self._post_to_user()
        self._delivered(parent)
        update = {
            "chat": {"id": int(self.test_chat.chat_id), "type": "private"},
            "message_id": 900,
            "user": {"id": int(self.test_chat.chat_id), "first_name": "Test"},
            "date": 1234567890,
            "old_reaction": [],
            "new_reaction": [{"type": "emoji", "emoji": "👀"}],
        }
        with self.mock_api_gateway_post():
            self.env["telegram.router"]._handle_update(
                self.test_bot, {"update_id": 6200, "message_reaction": update}
            )
        self.assertEqual(parent.reaction_ids.content, "👀")
        self.assertEqual(parent.reaction_ids.partner_id, self.test_partner)

    def test_a_reply_is_posted_on_the_record_as_the_user(self):
        parent = self._post_to_user()
        self._delivered(parent)

        self._reply("Listo, ya lo revisé")

        posted = self.record.message_ids.filtered(lambda m: m.parent_id == parent)
        self.assertEqual(len(posted), 1)
        self.assertEqual(posted.author_id, self.test_partner)
        self.assertEqual(posted.subtype_id, self.env.ref("mail.mt_comment"))
        self.assertIn("Listo, ya lo revisé", posted.body)
        inbound = self.env["telegram.message"].search(
            [("msg_uid", "=", "901"), ("message_type", "=", "inbound")]
        )
        self.assertEqual(inbound.mail_message_id, posted)

    def test_editing_the_reply_in_telegram_edits_it_in_odoo(self):
        channel = (
            self.env["discuss.channel"]
            .with_user(self.author)
            ._get_or_create_chat(partners_to=self.test_partner.ids)
        )
        parent = channel.with_user(self.author).message_post(
            body="¿Listo?", message_type="comment", subtype_xmlid="mail.mt_comment"
        )
        self._delivered(parent)
        self._reply("primera versión", message_id=961)

        edited = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id, text="versión corregida", message_id=961
        )
        edited["reply_to_message"] = {"message_id": 900}
        self.env["telegram.router"]._dispatch_edited_message(self.test_bot, edited)

        posted = channel.message_ids.filtered(lambda m: m.parent_id == parent)
        self.assertEqual(posted.author_id, self.test_partner)
        self.assertIn("versión corregida", posted.body)
        self.assertNotIn("primera versión", posted.body)

    def test_a_reply_to_a_note_stays_a_note(self):
        note = self.record.sudo().message_post(
            author_id=self.author_partner.id,
            body="interno",
            partner_ids=self.test_partner.ids,
            subtype_xmlid="mail.mt_note",
        )
        self._delivered(note)

        self._reply("visto")

        posted = self.record.message_ids.filtered(lambda m: m.parent_id == note)
        self.assertEqual(posted.subtype_id, self.env.ref("mail.mt_note"))

    def test_external_followers_are_asked_about_first(self):
        customer = self._create_partner({"name": "Customer"})
        portal = self.env["res.users"].create(
            {
                "name": "Customer",
                "login": "customer@example.com",
                "partner_id": customer.id,
                "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
            }
        )
        self.assertTrue(portal.share)
        self.record.message_subscribe(partner_ids=customer.ids)
        parent = self._post_to_user()
        self._delivered(parent)

        post = self._reply("respuesta")

        self.assertFalse(
            self.record.message_ids.filtered(lambda m: m.parent_id == parent)
        )
        keyboard = post.call_args.kwargs["json"]["reply_markup"]
        self.assertIn("mt:vis:comment", keyboard)

        query = self.mock_telegram_callback_query(
            chat_id=self.test_chat.chat_id, callback_data="mt:vis:comment"
        )
        with self.mock_api_gateway_post(), self.mock_rate_limiter():
            self.env["telegram.router"]._dispatch_callback_query(self.test_bot, query)

        posted = self.record.message_ids.filtered(lambda m: m.parent_id == parent)
        self.assertEqual(posted.subtype_id, self.env.ref("mail.mt_comment"))

    def test_a_refused_post_is_explained(self):
        parent = self._post_to_user()
        self._delivered(parent)

        with patch.object(
            type(self.record), "message_post", side_effect=AccessError("no")
        ):
            post = self._reply("respuesta")

        self.assertIn("not write", post.call_args.kwargs["json"]["text"])

    def test_a_reply_to_something_else_is_not_claimed(self):
        parent = self._post_to_user()
        self._delivered(parent)

        self._reply("hola", reply_to="555")

        self.assertFalse(
            self.record.message_ids.filtered(lambda m: m.parent_id == parent)
        )

    def test_mark_as_read(self):
        message = self._post_to_user()
        query = self.mock_telegram_callback_query(
            chat_id=self.test_chat.chat_id, callback_data=f"mt:read:{message.id}"
        )
        with self.mock_api_gateway_post(), self.mock_rate_limiter():
            self.env["telegram.router"]._dispatch_callback_query(self.test_bot, query)

        notification = self.env["mail.notification"].search(
            [
                ("mail_message_id", "=", message.id),
                ("res_partner_id", "=", self.test_partner.id),
            ]
        )
        self.assertTrue(notification.is_read)

    def test_text_without_a_reply_offers_the_recent_threads(self):
        parent = self._post_to_user()
        self._delivered(parent)
        update = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id, text="nota suelta", message_id=950
        )
        with self.mock_api_gateway_post() as post, self.mock_rate_limiter():
            self.env["telegram.router"]._dispatch_message(self.test_bot, update)
        self.assertIn(
            f"mt:to:{parent.id}", post.call_args.kwargs["json"]["reply_markup"]
        )

        query = self.mock_telegram_callback_query(
            chat_id=self.test_chat.chat_id, callback_data=f"mt:to:{parent.id}"
        )
        with self.mock_api_gateway_post(), self.mock_rate_limiter():
            self.env["telegram.router"]._dispatch_callback_query(self.test_bot, query)
        posted = self.record.message_ids.filtered(lambda m: m.parent_id == parent)
        self.assertIn("nota suelta", posted.body)


class TestFirstContactStandIn(TelegramBotTestCase):
    def test_proving_an_identity_moves_the_stand_in_chatter_to_the_contact(self):
        account = self.env["telegram.account"]._from_telegram(
            {"id": 555020, "username": "someone", "first_name": "Someone"}
        )
        stand_in = self._create_partner({"name": "Telegram Stranger"})
        account._bind(stand_in, method="contact")
        stand_in.message_post(body="history of the stranger")

        real = self._create_partner({"name": "Known Customer"})
        account._bind(real, method="invitation")

        self.assertFalse(stand_in.exists())
        self.assertIn(
            "history of the stranger", "".join(real.message_ids.mapped("body"))
        )
