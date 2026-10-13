import datetime
import smtplib
from unittest import mock

from odoo import modules
from odoo.libs.json import loads as json_loads
from odoo.modules.registry import Registry
from odoo.tests import TransactionCase


class MailCase(TransactionCase):
    def test_schedule_notification_parameters_roundtrip(self):
        Schedule = self.env["mail.message.schedule"]
        company = self.env.company
        kwargs = {
            "force_email_company": company,
            "force_send": True,
            "subtitles": ["hello"],
        }
        raw = Schedule._serialize_notification_parameters(kwargs)
        self.assertEqual(json_loads(raw)["force_email_company"], company.id)

        partner = self.env["res.partner"].create({"name": "sched"})
        message = partner.message_post(body="hi", partner_ids=partner.ids)
        schedule = Schedule.create(
            {
                "scheduled_datetime": "2050-01-01 00:00:00",
                "mail_message_id": message.id,
                "notification_parameters": raw,
            }
        )
        params = schedule._deserialize_notification_parameters()
        self.assertEqual(params["force_email_company"], company)
        self.assertIs(params["force_send"], True)
        self.assertEqual(params["subtitles"], ["hello"])

    def test_scheduled_date_accepts_plain_date(self):
        mail = self.env["mail.mail"].create(
            {"scheduled_date": datetime.date(2050, 1, 15)}
        )
        self.assertEqual(mail.scheduled_date, datetime.datetime(2050, 1, 15, 0, 0, 0))
        mail.write({"scheduled_date": datetime.date(2050, 2, 20)})
        self.assertEqual(mail.scheduled_date, datetime.datetime(2050, 2, 20, 0, 0, 0))

    def test_mail_send_non_connected_smtp_session(self):
        disconnected_smtpsession = mock.MagicMock()
        disconnected_smtpsession.quit.side_effect = smtplib.SMTPServerDisconnected
        mail = self.env["mail.mail"].create({})
        with mock.patch(
            "odoo.addons.mail.models.ir_mail_server.IrMail_Server._connect__",
            return_value=disconnected_smtpsession,
        ):
            with mock.patch(
                "odoo.addons.mail.models.mail_mail._logger.info"
            ) as mock_logging_info:
                mail.send()
        disconnected_smtpsession.quit.assert_called_once()
        mock_logging_info.assert_any_call(
            "Ignoring SMTPServerDisconnected while trying to quit non open session"
        )
        self.assertEqual(mail.state, "outgoing")

    def test_send_after_commit_while_registry_loads_leaves_mail_to_queue(self):
        mail = self.env["mail.mail"].create({"email_to": "loading@example.com"})
        self.env.cr.postcommit.clear()
        with (
            mock.patch.object(self.registry, "ready", False),
            mock.patch.object(
                self.registry,
                "signal_changes",
                lambda: Registry.signal_changes(self.registry),
            ),
            self.assertNoLogs("odoo.registry", "WARNING"),
        ):
            with mock.patch.object(modules.module, "current_test", None):
                mail.send_after_commit()
            self.env.cr.postcommit.drain()
        self.assertEqual(mail.state, "outgoing")
