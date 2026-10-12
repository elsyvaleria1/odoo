from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .test_smart_approval import SmartApprovalTestBase
from odoo.addons.approval.tests.common import pool_step

_THRESHOLD = "smart_approval.confidence_threshold"


@tagged("post_install", "-at_install")
class TestRequestIntakeAuthority(SmartApprovalTestBase):
    def _send(self, call):
        response = self.mock_telegram_response(success=True, result={"message_id": 1})
        with self.mock_api_gateway_post(response) as mock_post:
            call()
        return mock_post.call_args.kwargs.get("json", {}).get("text", "")

    def _intake(self, category):
        self.test_chat._flow_start(
            "telegram.handler.approval_ai",
            "evidence_question",
            {
                "raw_text": "necesito aprobar algo",
                "category_id": category.id,
                "evidence_done": True,
            },
        )
        return self._send(
            lambda: self.handler._create_request(
                self.test_bot, self.test_chat, self.test_user
            )
        )

    def _raised(self):
        return self.env["approval.request"].search(
            [("request_owner_id", "=", self.test_user.id)]
        )

    def test_a_request_is_raised_as_its_sender(self):
        self._intake(self.category)

        request = self._raised()
        self.assertEqual(request.create_uid, self.test_user)
        self.assertEqual(request.state, "pending")

    def test_a_request_is_filed_in_the_bot_s_company(self):
        other_company = self.env["res.company"].create({"name": "TG AI Bot Company"})
        (self.test_user | self.env.ref("base.user_admin")).company_ids = [
            Command.link(other_company.id)
        ]
        self.test_bot.company_id = other_company
        category = self.env["approval.category"].create(
            {
                "name": "Bot Company Requests",
                "sequence_code": "TGAIBOT",
                "company_id": other_company.id,
                "step_ids": pool_step(
                    [(self.env.ref("base.user_admin").id, False, 10)], minimum=1
                ),
            }
        )

        self.assertIn(category, self.handler._candidate_categories(self.test_bot))
        self.assertNotIn(
            self.category, self.handler._candidate_categories(self.test_bot)
        )
        self._intake(category)

        self.assertEqual(self._raised().company_id, other_company)

    def test_a_category_the_sender_cannot_reach_raises_nothing(self):
        other_company = self.env["res.company"].create({"name": "TG AI Other Company"})
        category = self.env["approval.category"].create(
            {
                "name": "Other Company Requests",
                "sequence_code": "TGAIOTHER",
                "company_id": other_company.id,
            }
        )

        text = self._intake(category)

        self.assertIn("could not create the request", text)
        self.assertFalse(self._raised())

    def test_an_unlinked_sender_mid_intake_is_stopped(self):
        self.test_chat._flow_start(
            "telegram.handler.approval_ai",
            "journal_choice",
            {"category_id": self.category.id},
        )
        query = self.mock_telegram_callback_query(
            callback_data="sa_jrnl:1", chat_id=self.test_chat.chat_id
        )

        text = self._send(
            lambda: self.handler._on_callback(
                self.test_bot, self.test_chat, query, False, False
            )
        )

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)
        self.assertIn("no longer linked", text)

    def test_the_threshold_privilege_reads_that_one_parameter(self):
        self.env["ir.config_parameter"].set_param(_THRESHOLD, "0.9")
        params = self.env["ir.config_parameter"].with_user(self.test_user)
        privileged = params.with_privilege(
            "approval_ai_telegram.privilege_read_confidence_threshold"
        )

        with self.assertRaises(AccessError):
            params.get_param(_THRESHOLD)
        self.assertEqual(privileged.get_param(_THRESHOLD), "0.9")
        with self.assertRaises(AccessError):
            privileged.get_param("web.base.url")
        self.assertEqual(
            self.handler._confidence_threshold(self.test_bot.with_user(self.test_user)),
            0.9,
        )
