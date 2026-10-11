import time

from odoo import Command
from odoo.libs.json import dumps as json_dumps
from odoo.tests import new_test_user, tagged

from odoo.addons.approval.tests.common import pool_step
from odoo.addons.telegram.tests.common import TelegramBotHttpCase
from odoo.addons.telegram.tests.test_web_app_init_data import signed_init_data


@tagged("post_install", "-at_install")
class TestApprovalMiniAppRoute(TelegramBotHttpCase):

    def _post(self, path, **data):
        self.env.flush_all()
        return self.url_open(
            f"/telegram/approval/app/{self.test_bot.id}{path}",
            data=data or {"": ""},
            method="POST",
        )

    def _signed(self, user_id):
        return signed_init_data(
            self.TEST_BOT_TOKEN,
            {"auth_date": str(int(time.time())), "user": json_dumps({"id": user_id})},
        )

    def test_signed_init_data_opens_the_pending_list_and_mints_a_session(self):
        response = self._post(
            "/pending", init_data=self._signed(int(self.test_chat.chat_id))
        )

        body = response.json()
        self.assertTrue(body["ok"], body)
        self.assertEqual(body["requests"], [])
        self.assertEqual(
            self.test_bot._resolve_mini_app_session(body["session"]),
            self.test_chat.chat_id,
        )

    def test_the_session_it_minted_is_an_identity_of_its_own(self):
        session = self.test_bot._mint_mini_app_session(self.test_chat.chat_id)

        response = self._post("/pending", s=session)

        self.assertTrue(response.json()["ok"])

    def test_no_identity_is_refused_in_the_app_s_shape(self):
        response = self._post("/pending")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": False, "error": "auth"})

    def test_a_forged_init_data_is_refused(self):
        response = self._post("/pending", init_data=self._signed(7) + "x")

        self.assertEqual(response.json(), {"ok": False, "error": "auth"})

    def test_an_unlinked_telegram_user_is_told_so(self):
        response = self._post("/pending", init_data=self._signed(424242))

        body = response.json()
        self.assertEqual((body["ok"], body["error"]), (False, "unlinked"))

    def test_an_unlinked_caller_reads_the_bot_s_language(self):
        self.env["res.lang"]._activate_lang("es_MX")
        self.test_bot.lang = "es_MX"

        labels = self._post("/pending", init_data=self._signed(424242)).json()["labels"]

        self.assertEqual(
            labels["unlinked"],
            "Primero conecta esta cuenta de Telegram con tu usuario de Odoo.",
        )

    def test_the_labels_come_in_the_caller_s_language(self):
        self.env["res.lang"]._activate_lang("es_MX")
        signed = self._signed(int(self.test_chat.chat_id))

        self.test_user.lang = "en_US"
        english = self._post("/pending", init_data=signed).json()["labels"]
        self.test_user.lang = "es_MX"
        spanish = self._post("/pending", init_data=signed).json()["labels"]

        self.assertEqual(
            (english["lang"], english["title"], english["states"]["pending"]),
            ("en-US", "My approvals", "Submitted"),
        )
        self.assertEqual(
            (spanish["lang"], spanish["title"], spanish["states"]["pending"]),
            ("es-MX", "Mis aprobaciones", "Enviada"),
        )
        self.assertEqual(
            spanish["more_lines"].replace("%(count)s", "3"), "… y 3 líneas más"
        )

    def test_an_unknown_bot_is_refused_and_recorded(self):
        self.env.flush_all()
        response = self.url_open(
            "/telegram/approval/app/0/pending",
            data={"init_data": self._signed(7)},
            method="POST",
        )

        self.assertEqual(response.json(), {"ok": False, "error": "not_found"})
        row = self.env["integration.exchange"].search(
            [
                ("state", "=", "refused"),
                ("refusal_reason", "=", "endpoint_not_found"),
                ("channel_name", "like", "telegram.bot:%"),
            ]
        )
        self.assertEqual(row.channel_name, "telegram.bot: bot 0")

    def test_an_admitted_call_is_recorded_without_what_the_user_typed(self):
        self._post("/pending", init_data=self._signed(int(self.test_chat.chat_id)))

        receiver = self.test_bot.mini_app_receiver_id
        row = self.env["integration.exchange"].search(
            [("channel_id", "=", f"integration.receiver,{receiver.id}")]
        )
        self.assertEqual(len(row), 1)
        self.assertEqual(row.event_type, "mini_app")
        self.assertFalse(row.request_payload)


@tagged("post_install", "-at_install")
class TestApprovalMiniAppDecision(TelegramBotHttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.ref("base.main_company")
        admin = cls.env.ref("base.user_admin")
        cls.co_approver = new_test_user(
            cls.env, login="tg_app_co_approver", groups="base.group_user"
        )
        joint = cls.env["approval.category"].create(
            {
                "name": "Mini App Joint Category",
                "company_id": company.id,
                "sequence_code": "TGAPPJ",
                "step_ids": pool_step(
                    [(cls.test_user.id, False, 10), (cls.co_approver.id, False, 10)],
                    minimum=2,
                ),
            }
        )
        cls.joint_request = cls.env["approval.request"].create(
            {"category_id": joint.id, "request_owner_id": admin.id}
        )
        cls.joint_request.action_confirm()
        cls.own_row = cls.joint_request.approver_ids.filtered(
            lambda row: row.user_id == cls.test_user
        )
        cls.co_row = cls.joint_request.approver_ids - cls.own_row
        foreign = cls.env["approval.category"].create(
            {
                "name": "Mini App Foreign Category",
                "company_id": company.id,
                "sequence_code": "TGAPPF",
                "step_ids": pool_step([(cls.co_approver.id, False, 10)], minimum=1),
            }
        )
        cls.foreign_request = cls.env["approval.request"].create(
            {"category_id": foreign.id, "request_owner_id": admin.id}
        )
        cls.foreign_request.action_confirm()

    def _session(self):
        return self.test_bot._mint_mini_app_session(self.test_chat.chat_id)

    def _act(self, row):
        self.env.flush_all()
        return self.url_open(
            f"/telegram/approval/app/{self.test_bot.id}/act",
            data={"s": self._session(), "approver_id": row.id, "action": "approve"},
            method="POST",
        ).json()

    def _attachment(self, request):
        attachment = self.env["ir.attachment"].create(
            {
                "name": "proof.txt",
                "raw": b"proof",
                "res_model": "approval.request",
                "res_id": request.id,
                "mimetype": "text/plain",
            }
        )
        self.env.flush_all()
        return self.url_open(
            f"/telegram/approval/app/{self.test_bot.id}/attachment/{attachment.id}"
            f"?s={self._session()}"
        )

    def test_the_approver_approves_as_themself(self):
        self.assertEqual(self._act(self.own_row), {"ok": True})

        self.own_row.invalidate_recordset()
        self.assertEqual(self.own_row.state, "approved")
        self.assertEqual(self.own_row.decided_by_user_id, self.test_user)
        self.assertEqual(self.own_row.write_uid, self.test_user)

    def test_a_co_approver_s_row_is_not_the_caller_s_to_decide(self):
        self.assertEqual(self._act(self.co_row), {"ok": False, "error": "not_pending"})

        self.co_row.invalidate_recordset()
        self.assertEqual(self.co_row.state, "pending")

    def test_the_pending_list_holds_what_the_approver_reads(self):
        self.env.flush_all()
        body = self.url_open(
            f"/telegram/approval/app/{self.test_bot.id}/pending",
            data={"s": self._session()},
            method="POST",
        ).json()

        self.assertTrue(body["ok"], body)
        self.assertEqual(
            [item["id"] for item in body["requests"]], [self.joint_request.id]
        )
        self.assertTrue(body["requests"][0]["can_act"])

    def test_an_approver_opens_the_attachment_of_their_request(self):
        response = self._attachment(self.joint_request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"proof")

    def test_the_attachment_of_a_request_they_cannot_read_is_not_found(self):
        response = self._attachment(self.foreign_request)

        self.assertEqual(response.status_code, 404)

    def _other_company_request(self):
        bot = self._bot_of_another_company("Other Approval Bot")
        (self.test_user | self.co_approver).write(
            {"company_ids": [Command.link(bot.company_id.id)]}
        )
        category = self.env["approval.category"].create(
            {
                "name": "Mini App Other Company Category",
                "company_id": bot.company_id.id,
                "sequence_code": "TGAPPO",
                "step_ids": pool_step([(self.test_user.id, False, 10)], minimum=1),
            }
        )
        request = (
            self.env["approval.request"]
            .with_company(bot.company_id)
            .create(
                {
                    "category_id": category.id,
                    "request_owner_id": self.co_approver.id,
                }
            )
        )
        request.action_confirm()
        self.env.flush_all()
        return bot, request, bot._mint_mini_app_session(self.test_chat.chat_id)

    def test_another_company_s_bot_lists_that_company_s_requests_only(self):
        bot, request, session = self._other_company_request()

        body = self.url_open(
            f"/telegram/approval/app/{bot.id}/pending",
            data={"s": session},
            method="POST",
        ).json()

        self.assertTrue(body["ok"], body)
        self.assertEqual([item["id"] for item in body["requests"]], [request.id])
        self.assertTrue(body["requests"][0]["can_act"])

    def test_another_company_s_bot_decides_in_that_company(self):
        bot, request, session = self._other_company_request()

        body = self.url_open(
            f"/telegram/approval/app/{bot.id}/act",
            data={
                "s": session,
                "approver_id": request.approver_ids.id,
                "action": "approve",
            },
            method="POST",
        ).json()

        self.assertEqual(body, {"ok": True})
        request.invalidate_recordset()
        self.assertEqual(request.approver_ids.state, "approved")
        self.assertEqual(request.approver_ids.decided_by_user_id, self.test_user)
