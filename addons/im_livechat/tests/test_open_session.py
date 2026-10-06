import odoo
from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import new_test_user
from odoo.tests.common import TransactionCase

OPEN_SESSION = "im_livechat.privilege_open_session"


@odoo.tests.tagged("-at_install", "post_install")
class TestOpenSession(TransactionCase):
    """A session opened without a web request: a messaging bridge brings a
    partner, and the environment is a service user, never the visitor."""

    def setUp(self):
        super().setUp()
        self.online = new_test_user(
            self.env(su=True),
            login="operator_online",
            groups="im_livechat.im_livechat_group_user",
        )
        self.env["mail.presence"].sudo()._update_presence(self.online)
        self.offline = new_test_user(
            self.env(su=True),
            login="operator_offline",
            groups="im_livechat.im_livechat_group_user",
        )
        self.livechat = self.env["im_livechat.channel"].create(
            {"name": "Support", "user_ids": [self.online.id, self.offline.id]}
        )
        self.customer = self.env["res.partner"].create({"name": "Telegram Customer"})

    def test_the_named_partner_is_the_visitor(self):
        channel = self.livechat._open_session(visitor_partner=self.customer)

        members = channel.channel_member_ids
        self.assertEqual(channel.channel_type, "livechat")
        self.assertEqual(channel.livechat_operator_id, self.online.partner_id)
        self.assertEqual(
            members.filtered(lambda m: m.livechat_member_type == "visitor").partner_id,
            self.customer,
        )
        self.assertNotIn(self.env.user.partner_id, members.partner_id)
        self.assertIn("Telegram Customer", channel.name)

    def test_a_session_without_a_visitor_is_still_named(self):
        channel = self.livechat._open_session()
        self.assertTrue(channel.name.startswith("Visitor"))

    def test_a_forced_agent_answers_even_while_offline(self):
        channel = self.livechat._open_session(
            visitor_partner=self.customer, forced_agent=self.offline
        )
        self.assertEqual(channel.livechat_operator_id, self.offline.partner_id)

    def test_nobody_available_opens_nothing_unless_waiting_is_allowed(self):
        self.env["mail.presence"].sudo().search(
            [("user_id", "=", self.online.id)]
        ).unlink()
        self.assertFalse(self.livechat.available_operator_ids)
        self.assertFalse(self.livechat._open_session(visitor_partner=self.customer))

        channel = self.livechat._open_session(
            visitor_partner=self.customer, allow_waiting=True
        )
        self.assertTrue(channel.livechat_operator_id)
        self.assertEqual(channel.livechat_status, "need_help")
        self.assertTrue(channel.livechat_looking_for_help_since_dt)

    def test_a_rating_from_anywhere_is_recorded_and_said(self):
        channel = self.livechat._open_session(visitor_partner=self.customer)

        rating = channel._livechat_rate(5, reason="rápido", partner=self.customer)

        self.assertEqual(rating.rating, 5)
        self.assertEqual(rating.partner_id, self.customer)
        self.assertEqual(rating.rated_partner_id, channel.livechat_operator_id)
        self.assertEqual(rating.message_id.model, "discuss.channel")
        self.assertEqual(rating.message_id.res_id, channel.id)


@odoo.tests.tagged("-at_install", "post_install")
class TestOpenSessionPrivilege(TestOpenSession):
    """A caller that is neither the superuser nor a live chat user -- a
    bridge's public webhook user -- opens a session on the privilege alone."""

    def setUp(self):
        super().setUp()
        self.public = self.env.ref("base.public_user")
        self.public_env = self.env(user=self.public)

    def _as_public(self, records, privileged=True):
        records = records.with_env(self.public_env)
        if privileged:
            records = records.with_privilege(OPEN_SESSION)
        return records

    def test_a_privileged_caller_opens_a_session_on_an_available_operator(self):
        channel = self._as_public(self.livechat)._open_session(
            visitor_partner=self.customer
        )

        self.assertFalse(channel.env.su)
        self.assertEqual(channel.env.uid, self.public.id)
        self.assertEqual(channel.livechat_operator_id, self.online.partner_id)
        self.assertEqual(channel.livechat_status, "in_progress")
        self.assertEqual(channel.sudo().livechat_customer_partner_ids, self.customer)

    def test_a_privileged_caller_reaches_a_forced_agent_and_waits_for_help(self):
        forced = self._as_public(self.livechat)._open_session(
            visitor_partner=self.customer, forced_agent=self.offline
        )
        self.assertEqual(forced.livechat_operator_id, self.offline.partner_id)

        self.env["mail.presence"].sudo().search(
            [("user_id", "=", self.online.id)]
        ).unlink()
        waiting = self._as_public(self.livechat)._open_session(
            visitor_partner=self.customer, allow_waiting=True
        )
        self.assertEqual(waiting.livechat_status, "need_help")
        self.assertTrue(waiting.livechat_looking_for_help_since_dt)

    def test_a_privileged_caller_opens_on_the_chatbot_and_its_welcome(self):
        script = self._script_forwarding_to_a_person()
        channel = self._as_public(self.livechat)._open_session(
            visitor_partner=self.customer, chatbot_script=script
        )

        self.assertEqual(channel.livechat_operator_id, script.operator_partner_id)
        welcome = channel.sudo().message_ids.filtered(
            lambda m: m.author_id == script.operator_partner_id
        )
        self.assertIn("Hola", welcome.mapped("body")[-1])

    def test_without_the_privilege_the_opening_is_refused(self):
        with self.assertRaises(AccessError):
            self._as_public(self.livechat, privileged=False)._open_session(
                visitor_partner=self.customer
            )
        self.assertFalse(
            self.env["discuss.channel"].search(
                [("livechat_channel_id", "=", self.livechat.id)]
            )
        )

    def test_the_privilege_reaches_nothing_beyond_the_opening(self):
        session = self.livechat._open_session(visitor_partner=self.customer)
        session.message_post(
            body="dato privado", message_type="comment", subtype_xmlid="mail.mt_note"
        )
        session.livechat_note = "solo para operadores"
        team = self.env["discuss.channel"].create({"name": "Equipo"})
        portal = new_test_user(
            self.env(su=True), login="o04e_portal", groups="base.group_portal"
        )
        channels = self._as_public(self.env["discuss.channel"])
        env = channels.env

        self.assertEqual(channels.search([("id", "in", (session | team).ids)]), session)
        self.assertFalse(
            env["mail.message"].search(
                [("model", "=", "discuss.channel"), ("res_id", "=", session.id)]
            )
        )
        self.assertFalse(env["res.partner"].search([("id", "=", self.customer.id)]))
        self.assertFalse(env["res.users"].search([("id", "=", portal.id)]))
        with self.assertRaises(AccessError):
            channels.browse(session.id).livechat_note
        with self.assertRaises(AccessError):
            channels.browse(session.id).unlink()
        with self.assertRaises(AccessError):
            channels.create({"name": "Nuevo equipo", "channel_type": "channel"})
        with self.assertRaises(AccessError):
            env["im_livechat.channel"].browse(self.livechat.id).write({"name": "X"})

    def test_a_partner_visitor_forwarded_by_the_public_user_names_the_session(self):
        script = self._script_forwarding_to_a_person()
        channel = self.livechat._open_session(
            visitor_partner=self.customer, chatbot_script=script
        )
        forward = script.script_step_ids.filtered("is_forward_operator")

        self._as_public(channel)._forward_human_operator(forward)

        self.assertEqual(channel.livechat_operator_id, self.online.partner_id)
        operator_name = self.online.livechat_username or self.online.name
        self.assertEqual(channel.name, f"Telegram Customer {operator_name}")

    def _script_forwarding_to_a_person(self):
        script = self.env["chatbot.script"].create({"title": "Recepción"})
        self.env["chatbot.script.step"].create(
            [
                {
                    "step_type": "text",
                    "message": "Hola",
                    "chatbot_script_id": script.id,
                },
                {
                    "step_type": "forward_operator",
                    "message": "Te paso con alguien",
                    "chatbot_script_id": script.id,
                },
            ]
        )
        self.livechat.rule_ids = [Command.create({"chatbot_script_id": script.id})]
        return script
