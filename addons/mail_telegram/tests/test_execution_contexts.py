from unittest.mock import patch

from markupsafe import Markup

from odoo import Command
from odoo.tests import new_test_user, tagged

from .test_mail_telegram import MailTelegramCase
from odoo.addons.telegram.tools import errors

_CALL = "odoo.addons.telegram.tools.telegram_client.TelegramClient.call"
_ALERT = "Telegram is not delivering your notifications"


@tagged("post_install", "-at_install")
class TestExecutionContexts(MailTelegramCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.main = cls.env.company
        cls.other = cls.env["res.company"].create({"name": "TG Contexts Other"})
        cls.test_bot.company_id = cls.other
        cls.test_user.write({"company_ids": [Command.set((cls.main | cls.other).ids)]})
        cls.test_user._telegram_settings().telegram_notify_inbox = "always"
        cls.poster = new_test_user(
            cls.env,
            login="tg_contexts_poster",
            groups="base.group_user,base.group_partner_manager",
            company_id=cls.main.id,
            company_ids=[Command.set(cls.main.ids)],
        )
        cls.public = cls.env.ref("base.public_user")

    def _post_as_poster(self):
        return (
            self.record.with_user(self.poster)
            .with_context(allowed_company_ids=self.main.ids)
            .message_post(
                body=Markup("<p>Hola</p>"),
                partner_ids=self.test_partner.ids,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        )

    def _webhook_bot(self):
        transaction = self.env.transaction
        self.patch(transaction, "default_env", self.env(user=self.public))
        return self.test_bot.with_user(self.public).sudo()

    def _alerts(self):
        self._run_alert_jobs()
        return self.env["mail.message"].search(
            [("subject", "=", _ALERT), ("partner_ids", "in", self.test_partner.ids)]
        )

    def test_a_poster_of_another_company_notifies_through_the_bot(self):
        self._post_as_poster()

        self.assertEqual(len(self._queued()), 1)

    def _run_delivery_jobs(self, call):
        jobs = (
            self.env["ir.job"]
            .sudo()
            .search(
                [
                    (
                        "identity_key",
                        "in",
                        [f"telegram.message:{m.id}" for m in self._queued()],
                    ),
                    ("state", "in", ["scheduled", "pending"]),
                ]
            )
        )
        with (
            call,
            patch.object(
                type(self.env["telegram.message"]),
                "_consume_send_budget",
                lambda _self: True,
            ),
        ):
            for job in jobs:
                job.action_run_now()
        return jobs

    def test_the_outbox_sends_as_the_recipient(self):
        self._post_as_poster()

        jobs = self._run_delivery_jobs(patch(_CALL, return_value={"message_id": 31}))

        self.assertEqual(jobs.user_id, self.test_user)
        self.assertEqual(self._queued().state, "sent")

    def test_an_attachment_the_poster_sent_reaches_the_recipient(self):
        attachment = (
            self.env["ir.attachment"]
            .with_user(self.poster)
            .create({"name": "lote.txt", "raw": b"lote 3", "mimetype": "text/plain"})
        )
        self.record.with_user(self.poster).with_context(
            allowed_company_ids=self.main.ids
        ).message_post(
            body=Markup("<p>Adjunto</p>"),
            partner_ids=self.test_partner.ids,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            attachment_ids=attachment.ids,
        )

        ids = iter(range(40, 50))
        with patch(
            _CALL, side_effect=lambda *a, **k: {"message_id": next(ids)}
        ) as call:
            self._run_delivery_jobs(call)

        self.assertEqual(set(self._queued().mapped("state")), {"sent"})
        self.assertIn("sendDocument", [c.args[0] for c in call.call_args_list])

    def test_a_refusal_in_the_outbox_alerts_the_recipient(self):
        self._post_as_poster()

        self._run_delivery_jobs(
            patch(
                _CALL,
                side_effect=errors.TelegramBadRequest(
                    400, "Bad Request: chat not found"
                ),
            )
        )

        self.assertEqual(len(self._alerts()), 1)

    def test_blocking_the_bot_through_the_webhook_alerts_the_recipient(self):
        with self.mock_api_gateway_post(), self.mock_rate_limiter():
            self.env["telegram.router"]._handle_update(
                self._webhook_bot(),
                {
                    "update_id": 9301,
                    "my_chat_member": {
                        "chat": {"id": 12345, "type": "private"},
                        "from": {"id": 12345, "first_name": "Test"},
                        "new_chat_member": {"status": "kicked"},
                    },
                },
            )

        self.assertEqual(len(self._alerts()), 1)

    def test_connecting_through_the_webhook_makes_the_destination(self):
        self.test_bot.bot_username = "contexts_bot"
        token = (
            self.env["telegram.link.token"]
            .with_user(self.test_user)
            ._issue_for_session(self.test_bot)
        )
        with self.mock_api_gateway_post(), self.mock_rate_limiter():
            self.env["telegram.router"]._handle_update(
                self._webhook_bot(),
                {
                    "update_id": 9302,
                    "message": {
                        "message_id": 1,
                        "from": {"id": 880031, "first_name": "Teléfono"},
                        "chat": {"id": 880031, "type": "private"},
                        "date": 1,
                        "text": f"/start {token}",
                    },
                },
            )

        chat = self.env["telegram.chat"].search([("chat_id", "=", "880031")])
        self.assertEqual(self.test_user._get_telegram_notify_chat(), chat)

    def test_the_preferences_status_reads_as_the_user(self):
        user = self.test_user.with_user(self.test_user).with_context(
            allowed_company_ids=self.main.ids
        )

        self.assertEqual(user.telegram_notify_state, "ready")
