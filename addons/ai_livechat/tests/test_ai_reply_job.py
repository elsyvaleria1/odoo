from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user

from odoo.addons.ai.models.ai_agent import AIAgent

GENERATE = "_generate_response"


class TestAIReplyJob(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = new_test_user(
            cls.env, login="ai_operator", groups="im_livechat.im_livechat_group_user"
        )
        cls.agent = cls.env["ai.agent"].create({"name": "Asistente"})
        cls.livechat = cls.env["im_livechat.channel"].create(
            {
                "name": "Soporte",
                "user_ids": [cls.operator.id],
                "rule_ids": [(0, 0, {"ai_agent_id": cls.agent.id})],
            }
        )
        cls.visitor = cls.env["res.partner"].create({"name": "Cliente"})

    def _session(self):
        return self.livechat._open_session(
            visitor_partner=self.visitor,
            operator_criteria={"ai_agent_id": self.agent.id},
            extra_vals={"ai_agent_id": self.agent.id},
        )

    def _visitor_says(self, session, text):
        return session.message_post(
            author_id=self.visitor.id,
            body=text,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )

    def _agent_messages(self, session):
        return session.message_ids.filtered(
            lambda m: m.author_id == self.agent.partner_id
        )

    def test_a_session_opened_with_criteria_is_the_agent_s(self):
        session = self._session()
        self.assertEqual(session.ai_agent_id, self.agent)
        self.assertEqual(session.livechat_operator_id, self.agent.partner_id)

    def test_later_queues_one_job_per_message(self):
        session = self._session()
        message = self._visitor_says(session, "¿Horario?")
        session._ai_reply_later(message)
        session._ai_reply_later(message)
        jobs = (
            self.env["ir.job"]
            .sudo()
            .search([("identity_key", "=", f"ai_livechat.reply:{message.id}")])
        )
        self.assertEqual(len(jobs), 1)

    def test_the_job_answers_the_visitor(self):
        session = self._session()
        message = self._visitor_says(session, "¿Horario?")
        with patch.object(AIAgent, GENERATE, return_value=["De 9 a 18 h."]):
            session._ai_reply(message.id)
        self.assertIn("De 9 a 18 h.", self._agent_messages(session)[:1].body)

    def test_an_unreachable_ai_apologises_instead_of_failing(self):
        session = self._session()
        message = self._visitor_says(session, "¿Horario?")
        with patch.object(AIAgent, GENERATE, side_effect=RuntimeError("down")):
            session._ai_reply(message.id)
        self.assertIn("unreachable", self._agent_messages(session)[:1].body)

    def test_a_closed_session_gets_no_answer(self):
        session = self._session()
        message = self._visitor_says(session, "¿Horario?")
        session._close_livechat_session()
        with patch.object(AIAgent, GENERATE, return_value=["tarde"]) as generate:
            session._ai_reply(message.id)
        self.assertFalse(generate.called)

    def test_the_visitor_s_answer_runs_through_the_agent_without_the_superuser(self):
        session = self._session()
        message = self._visitor_says(session, "¿Horario?")
        seen = {}

        def request_llm(service, *args, **kwargs):
            seen["su"] = service.env.su
            seen["uid"] = service.env.uid
            return ["De 9 a 18 h."]

        with patch(
            "odoo.addons.ai.utils.llm_api_service.LLMApiService.request_llm",
            autospec=True,
            side_effect=request_llm,
        ):
            session._ai_reply(message.id)
        self.assertIn("De 9 a 18 h.", self._agent_messages(session)[:1].body)
        self.assertFalse(seen["su"])
        self.assertEqual(seen["uid"], self.env.ref("base.public_user").id)

    def test_which_agent_serves_a_session_is_read_by_an_answer_only(self):
        session = self._session()
        for user in (self.operator, self.env.ref("base.public_user")):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                session.with_user(user).ai_agent_id
        self.assertEqual(
            session.with_user(self.operator)._ai_answering().ai_agent_id, self.agent
        )
