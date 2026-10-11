from odoo import Command
from odoo.tests import new_test_user, tagged

from .common import TelegramBotTestCase


@tagged("post_install", "-at_install")
class TestBotCompany(TelegramBotTestCase):

    OTHER_TOKEN = "223456789:XYZ-DEF1234ghIkl-zyx57W2v1u123ew22"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.main = cls.env.company
        cls.other = cls.env["res.company"].create({"name": "TG Other Company"})
        cls.admin = new_test_user(
            cls.env,
            login="tg_company_admin",
            groups="base.group_system,base.group_multi_company",
            company_id=cls.main.id,
            company_ids=[Command.set((cls.main | cls.other).ids)],
        )
        cls.public = cls.env.ref("base.public_user")
        cls.other_bot = cls.env["telegram.bot"].create(
            {
                "name": "Other Company Bot",
                "company_id": cls.other.id,
                "credential_id": cls._make_bot_credential(
                    "Other Company Bot Credential", cls.OTHER_TOKEN
                ).id,
            }
        )

    def _as_admin(self):
        return (
            self.env["telegram.bot"]
            .with_user(self.admin)
            .with_context(allowed_company_ids=[self.main.id])
        )

    def _owned(self, bot):
        bot = bot.sudo()
        receivers = bot.webhook_receiver_id | bot.mini_app_receiver_id
        return receivers, bot.credential_id | bot.webhook_receiver_id.credential_id

    def test_an_admin_keeps_a_bot_of_a_company_they_have_not_active(self):
        credential = self._make_bot_credential(
            "Admin Bot Credential", "323456789:XYZ-DEF1234ghIkl-zyx57W2v1u123ew33"
        )
        bot = self._as_admin().create(
            {
                "name": "Admin Bot",
                "company_id": self.other.id,
                "credential_id": credential.id,
            }
        )
        receivers, credentials = self._owned(bot)
        self.assertEqual(len(receivers), 2)
        self.assertEqual(receivers.company_id, self.other)
        self.assertEqual(len(credentials), 2)
        self.assertEqual(credentials.company_id, self.other)

        bot.name = "Admin Bot Renamed"
        self.assertEqual(
            sorted(receivers.mapped("name")),
            ["Admin Bot Renamed Mini App", "Admin Bot Renamed webhook"],
        )
        [values] = bot.web_read(
            {"webhook_receiver_id": {"fields": {"display_name": {}}}}
        )
        self.assertEqual(
            values["webhook_receiver_id"]["display_name"], "Admin Bot Renamed webhook"
        )

        bot.company_id = self.main
        self.assertEqual(receivers.company_id, self.main)
        self.assertEqual(credentials.company_id, self.main)

    def test_the_credentials_follow_the_bot_s_company(self):
        receivers, credentials = self._owned(self.other_bot)
        self.assertEqual(credentials.company_id, self.other)

        self.other_bot.company_id = self.main

        self.assertEqual(receivers.company_id, self.main)
        self.assertEqual(credentials.company_id, self.main)

    def test_telegram_is_called_in_the_bot_s_company(self):
        client = self.other_bot._get_telegram_client()
        self.assertEqual(client._client.company_id, self.other.id)

    def test_an_internal_user_reads_only_the_bots_of_their_companies(self):
        employee = new_test_user(
            self.env, login="tg_company_employee", groups="base.group_user"
        )
        bots = self.env["telegram.bot"]
        self.assertNotIn(self.other_bot, bots.with_user(employee).search([]))
        self.assertIn(self.other_bot, self._as_admin().search([]))

    def _webhook(self, chat_id, text="/start"):
        self.patch(self.env.transaction, "default_env", self.env(user=self.public))
        seen = {}

        def start(handler, bot, chat, args, partner=False, internal_user=False):
            seen.update(
                uid=handler.env.uid,
                company=handler.env.company,
                companies=handler.env.companies,
                bot_company=bot.env.company,
            )

        with (
            self.extra_command("/zcompany", start),
            self.mock_api_gateway_post() as post,
            self.mock_rate_limiter(),
        ):
            self.env["telegram.router"]._handle_update(
                self.other_bot.with_user(self.public).sudo(),
                {
                    "update_id": 9701,
                    "message": self.mock_telegram_message(chat_id=chat_id, text=text),
                },
            )
        texts = [
            call.kwargs["json"].get("text", "")
            for call in post.call_args_list
            if call.kwargs.get("json")
        ]
        return seen, texts

    def test_an_internal_user_of_another_company_is_refused(self):
        outsider = new_test_user(
            self.env, login="tg_company_outsider", groups="base.group_user"
        )
        self._bound_account("770001", outsider.partner_id, user=outsider)

        seen, texts = self._webhook("770001", "/zcompany")

        self.assertFalse(seen)
        self.assertTrue(
            any("not a member of the company this bot speaks for" in t for t in texts),
            texts,
        )

    def test_a_member_acts_in_the_bot_s_company_only(self):
        member = new_test_user(
            self.env,
            login="tg_company_member",
            groups="base.group_user",
            company_id=self.main.id,
            company_ids=[Command.set((self.main | self.other).ids)],
        )
        self._bound_account("770002", member.partner_id, user=member)
        command = self.env["telegram.command"].create({"name": "/zcompany"})
        self.other_bot.command_ids = [Command.link(command.id)]

        seen, _texts = self._webhook("770002", "/zcompany")

        self.assertEqual(seen["uid"], member.id)
        self.assertEqual(seen["company"], self.other)
        self.assertEqual(seen["companies"], self.other)
        self.assertEqual(seen["bot_company"], self.other)

    def test_the_public_user_answers_for_a_bot_of_another_company(self):
        _seen, texts = self._webhook("770003", "/zunknown")

        self.assertTrue(any("Unknown command" in text for text in texts), texts)

    def test_a_mini_app_refuses_an_internal_user_of_another_company(self):
        outsider = new_test_user(
            self.env, login="tg_company_app_outsider", groups="base.group_user"
        )
        self._bound_account("770004", outsider.partner_id, user=outsider)
        member = new_test_user(
            self.env,
            login="tg_company_app_member",
            groups="base.group_user",
            company_ids=[Command.set((self.main | self.other).ids)],
        )
        self._bound_account("770005", member.partner_id, user=member)

        self.assertFalse(self.other_bot._mini_app_user("770004"))
        self.assertEqual(self.other_bot._mini_app_user("770005"), member)

    def test_a_mini_app_member_acts_in_the_bot_s_company_only(self):
        member = new_test_user(
            self.env,
            login="tg_company_app_main_first",
            groups="base.group_user",
            company_id=self.main.id,
            company_ids=[Command.set((self.main | self.other).ids)],
        )
        self._bound_account("770006", member.partner_id, user=member)

        user = self.other_bot._mini_app_user("770006")

        self.assertEqual(user, member)
        self.assertEqual((user.env.uid, user.env.su), (member.id, False))
        self.assertEqual(user.env.company, self.other)
        self.assertEqual(user.env.companies, self.other)

    def test_an_admin_reads_the_credential_name_of_a_bot_of_another_company(self):
        bot = self._as_admin().browse(self.other_bot.id)

        [values] = bot.web_read({"credential_id": {"fields": {"display_name": {}}}})

        credential = self.other_bot.credential_id
        self.assertEqual(
            values["credential_id"]["display_name"], credential.display_name
        )
        credential = credential.with_env(bot.env)
        self.assertFalse(credential.has_access("read"))
