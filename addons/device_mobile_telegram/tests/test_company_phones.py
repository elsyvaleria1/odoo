from markupsafe import Markup

from odoo import Command
from odoo.tests import new_test_user, tagged

from odoo.addons.mail_telegram.tests.test_mail_telegram import MailTelegramCase


@tagged("post_install", "-at_install")
class TestCompanyPhonesOnly(MailTelegramCase):
    """A bot set to company phones delivers a user's Odoo mail only to the
    Telegram account whose shared number is a company phone of theirs."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_bot.write(
            {"bot_username": "notify_bot", "notify_company_phones_only": True}
        )
        cls.test_user._telegram_settings().telegram_notify_inbox = "always"
        # the phone's number is written as its company writes it, without +52
        cls.env.company.country_id = cls.env.ref("base.mx")
        profile = cls.env["device.profile"].create(
            {"name": "Phones", "auth_type": "bearer", "auth_token": "phones_token"}
        )
        cls.phone = cls.env["device.device"].create(
            {
                "name": "Teléfono de Test",
                "identifier": "PHONE-TG-1",
                "config_id": profile.id,
                "comm_protocol": "https",
                "endpoint": "x",
                "device_category_id": cls.env.ref(
                    "device_mobile.device_category_mobile_phone"
                ).id,
                "line_number": "55 1234 5678",
                "user_id": cls.test_user.id,
            }
        )

    def _verify(self, number):
        self.test_account._update_phone(number)

    def _delivered(self):
        return self.env["telegram.message"].search(
            [("chat_id", "=", self.test_chat.id), ("mail_message_id", "!=", False)]
        )

    def _share_own_contact(self, number):
        update = {
            "message_id": 7,
            "from": {"id": 12345, "first_name": "Test"},
            "chat": {"id": 12345, "type": "private"},
            "date": 1,
            "contact": {"phone_number": number, "user_id": 12345, "first_name": "T"},
        }
        self._through_webhook({"update_id": 9401, "message": update})

    def _through_webhook(self, update):
        """Hand an update to the router as the webhook does: as its public
        user, the sender's identity resolved from there."""
        public = self.env.ref("base.public_user")
        self.patch(self.env.transaction, "default_env", self.env(user=public))
        bot = self.test_bot.with_user(public).sudo()
        with self.mock_api_gateway_post(), self.mock_rate_limiter():
            self.env["telegram.router"]._handle_update(bot, update)

    def test_an_account_without_a_number_gets_nothing(self):
        self._post_to_user()

        self.assertFalse(self._delivered())
        self.assertEqual(
            self.test_user._get_telegram_notify_status()[0], "verify_phone"
        )
        self.assertTrue(
            self.test_bot._is_phone_needed_for_mail(self.test_account, self.test_user)
        )

    def test_the_company_phone_s_account_gets_it_whatever_the_prefix(self):
        # an account registered before Mexico dropped the mobile 1 still says it
        self._verify("5215512345678")

        self._post_to_user()

        self.assertEqual(len(self._delivered()), 1)
        self.assertEqual(self.test_user._get_telegram_notify_status()[0], "ready")

    def test_another_number_gets_nothing(self):
        self._verify("+525599999999")

        self._post_to_user()

        self.assertFalse(self._delivered())
        refusal = self.test_bot._get_mail_refusal(self.test_account, self.test_user)
        self.assertIn("+525599999999", refusal)
        self.assertEqual(self.test_user._get_telegram_notify_status()[0], "refused")

    def test_a_foreign_number_ending_alike_is_not_the_phone(self):
        # a US line whose ten digits are the Mexican phone's is another line
        self._verify("+1 551 234 5678")

        self._post_to_user()

        self.assertFalse(self._delivered())

    def test_a_phone_carried_by_somebody_else_does_not_count(self):
        self.phone.user_id = self.author
        self._verify("+525512345678")

        self._post_to_user()

        self.assertFalse(self._delivered())

    def test_an_archived_phone_does_not_count(self):
        self.phone.active = False
        self._verify("+525512345678")

        self.assertFalse(
            self.test_bot._can_deliver_mail(self.test_account, self.test_user)
        )

    def test_without_the_rule_any_connected_account_gets_it(self):
        self.test_bot.notify_company_phones_only = False

        self._post_to_user()

        self.assertEqual(len(self._delivered()), 1)

    def test_a_reply_from_an_unverified_account_asks_for_the_number(self):
        self.test_bot.notify_company_phones_only = False
        self._post_to_user()
        delivered = self._delivered()
        delivered.sudo().msg_uid = "501"
        self.test_bot.notify_company_phones_only = True

        update = self.mock_telegram_message(
            chat_id="12345", text="Listo", message_id=60
        )
        update["reply_to_message"] = {"message_id": 501}
        self._through_webhook({"update_id": 9402, "message": update})

        self.assertFalse(
            self.record.message_ids.filtered(lambda m: "Listo" in (m.body or ""))
        )
        asked = (
            self.env["telegram.message"]
            .search(
                [("chat_id", "=", self.test_chat.id), ("message_type", "=", "outbound")]
            )
            .filtered(
                lambda m: "keyboard" in ((m.payload or {}).get("reply_markup") or {})
            )
        )
        self.assertTrue(asked)

    def test_sharing_the_company_number_opens_the_delivery(self):
        self._share_own_contact("+52 55 1234 5678")

        self.assertEqual(self.test_account.phone, "+525512345678")
        self.assertEqual(self.test_user._get_telegram_notify_chat(), self.test_chat)
        texts = (
            self.env["telegram.message"]
            .search(
                [("chat_id", "=", self.test_chat.id), ("message_type", "=", "outbound")]
            )
            .mapped("text")
        )
        self.assertTrue(any("will arrive here" in (text or "") for text in texts))

    def test_the_phone_shows_the_account_of_its_number(self):
        self._verify("+525512345678")
        self.phone.invalidate_recordset()

        self.assertEqual(self.phone.telegram_account_id, self.test_account)
        self.assertEqual(self.phone.telegram_user_id, self.test_user)


@tagged("post_install", "-at_install")
class TestCompanyPhonesWhoeverAsks(TestCompanyPhonesOnly):
    """The company phones a user carries are read in the bot's company, as
    the user: a poster of another company decides nothing."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.main = cls.env.company
        cls.other = cls.env["res.company"].create({"name": "TG Phones Other"})
        cls.test_bot.company_id = cls.other
        cls.other.country_id = cls.env.ref("base.mx")
        cls.phone.company_id = cls.other
        cls.test_user.write({"company_ids": [Command.set((cls.main | cls.other).ids)]})
        cls.poster = new_test_user(
            cls.env,
            login="tg_phones_poster",
            groups="base.group_user,base.group_partner_manager",
            company_id=cls.main.id,
            company_ids=[Command.set(cls.main.ids)],
        )

    def _post_to_user(self, **kwargs):
        return (
            self.record.with_user(self.poster)
            .with_context(allowed_company_ids=self.main.ids)
            .message_post(
                body=Markup("<p>Revisa</p>"),
                partner_ids=self.test_partner.ids,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                **kwargs,
            )
        )
