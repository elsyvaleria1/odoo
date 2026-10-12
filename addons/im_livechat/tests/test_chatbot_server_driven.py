from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestChatbotServerDriven(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chatbot_script = cls.env["chatbot.script"].create({"title": "Bridge Bot"})
        steps = cls.env["chatbot.script.step"].sudo()
        cls.step_hello, cls.step_dispatch = steps.create(
            [
                {
                    "step_type": "text",
                    "message": "Hello! I'm a bot!",
                    "chatbot_script_id": cls.chatbot_script.id,
                },
                {
                    "step_type": "question_selection",
                    "message": "How can I help you?",
                    "chatbot_script_id": cls.chatbot_script.id,
                },
            ]
        )
        cls.step_dispatch_buy_software, _pricing = cls.env[
            "chatbot.script.answer"
        ].create(
            [
                {"name": "Buy software", "script_step_id": cls.step_dispatch.id},
                {"name": "Pricing", "script_step_id": cls.step_dispatch.id},
            ]
        )
        steps.create(
            {
                "step_type": "text",
                "message": "Great choice.",
                "chatbot_script_id": cls.chatbot_script.id,
                "triggering_answer_ids": [(4, cls.step_dispatch_buy_software.id)],
            }
        )
        cls.livechat_channel = cls.env["im_livechat.channel"].create(
            {
                "name": "Bridge Channel",
                "rule_ids": [(0, 0, {"chatbot_script_id": cls.chatbot_script.id})],
            }
        )

    def _session(self):
        visitor = self.env["res.partner"].create({"name": "Bridged Visitor"})
        channel = self.livechat_channel._open_session(
            visitor_partner=visitor, chatbot_script=self.chatbot_script
        )
        return channel, visitor

    def test_opening_posts_the_welcome_up_to_the_first_question(self):
        channel, _visitor = self._session()

        self.assertEqual(channel.chatbot_current_step_id, self.step_dispatch)
        self.assertIn(
            "How can I help you?", "".join(channel.message_ids.mapped("body"))
        )

    def test_without_an_answer_the_script_waits(self):
        channel, _visitor = self._session()

        self.assertFalse(channel._chatbot_run())
        self.assertEqual(channel.chatbot_current_step_id, self.step_dispatch)

    def test_an_answer_moves_the_script_on(self):
        channel, visitor = self._session()
        message = channel.chatbot_message_ids.filtered(
            lambda m: m.script_step_id == self.step_dispatch
        )
        message.user_script_answer_id = self.step_dispatch_buy_software
        channel.message_post(
            author_id=visitor.id,
            body=self.step_dispatch_buy_software.name,
            message_type="comment",
        )

        channel._chatbot_run()

        self.assertNotEqual(channel.chatbot_current_step_id, self.step_dispatch)
        self.assertTrue(channel.chatbot_current_step_id)

    def test_an_exhausted_script_closes_the_session(self):
        channel, _visitor = self._session()
        channel.sudo().chatbot_current_step_id = False

        status, step, message = channel._chatbot_advance()

        self.assertEqual(status, "ended")
        self.assertFalse(step or message)
        self.assertTrue(channel.livechat_end_dt)
