from unittest.mock import patch

from psycopg.errors import SerializationFailure

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Datetime as FieldDatetime
from odoo.tests import tagged, users
from odoo.tools import mute_logger

from odoo.addons.base.tests.test_ir_cron import CronMixinCase
from odoo.addons.mail.tests.common import MailCommon
from odoo.addons.test_mail.models.mail_test_access import MailTestAccess
from odoo.addons.test_mail.models.mail_test_lead import MailTestTLead
from odoo.addons.test_mail.tests.common import TestRecipients


@tagged("mail_scheduled_message")
class TestScheduledMessage(MailCommon, TestRecipients):
    """Test Scheduled Message internals"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.reference_now = FieldDatetime.to_datetime("2022-12-24 12:00:00")

        with cls.mock_datetime_and_now(cls, cls.reference_now):
            cls.test_record = (
                cls.env["mail.test.ticket"]
                .with_context(cls._test_context)
                .create(
                    [
                        {
                            "name": "Test Record",
                            "customer_id": cls.partner_1.id,
                            "user_id": cls.user_employee.id,
                        }
                    ]
                )
            )
            cls.private_record = cls.env["mail.test.access"].create(
                {
                    "access": "admin",
                    "name": "Private Record",
                }
            )
            cls.hidden_scheduled_message, cls.visible_scheduled_message = (
                cls.env["mail.scheduled.message"]
                .create(
                    [
                        {
                            "author_id": cls.partner_admin.id,
                            "model": cls.private_record._name,
                            "res_id": cls.private_record.id,
                            "body": "Hidden Scheduled Message",
                            "scheduled_date": "2022-12-24 15:00:00",
                        },
                        {
                            "author_id": cls.partner_admin.id,
                            "model": cls.test_record._name,
                            "res_id": cls.test_record.id,
                            "body": "Visible Scheduled Message",
                            "scheduled_date": "2022-12-24 15:00:00",
                        },
                    ]
                )
                .with_user(cls.user_employee)
            )

    def schedule_message(self, target_record=None, author_id=None, **kwargs):
        with self.mock_datetime_and_now(self.reference_now):
            return self.env["mail.scheduled.message"].create(
                {
                    "author_id": author_id or self.env.user.partner_id.id,
                    "model": target_record._name
                    if target_record
                    else kwargs.pop("model"),
                    "res_id": target_record.id
                    if target_record
                    else kwargs.pop("res_id"),
                    "body": kwargs.pop("body", "Test Body"),
                    "scheduled_date": kwargs.pop(
                        "scheduled_date", "2022-12-24 15:00:00"
                    ),
                    **kwargs,
                }
            )


class TestScheduledMessageAccess(TestScheduledMessage):
    @users("employee")
    def test_scheduled_message_model_without_post_right(self):
        with self.assertRaises(AccessError):
            self.schedule_message(self.private_record)
        with self.assertRaises(AccessError):
            self.hidden_scheduled_message.read()
        self.assertFalse(
            self.env["mail.scheduled.message"].search(
                [["id", "=", self.hidden_scheduled_message.id]]
            )
        )
        with self.assertRaises(AccessError):
            self.hidden_scheduled_message.write({"body": "boum"})
        with self.assertRaises(AccessError):
            self.hidden_scheduled_message.post_message()
        with self.assertRaises(AccessError):
            self.hidden_scheduled_message.unlink()

    @users("employee")
    def test_scheduled_message_model_with_post_right(self):
        self.visible_scheduled_message.read()
        self.assertEqual(
            self.env["mail.scheduled.message"].search(
                [["id", "=", self.visible_scheduled_message.id]]
            ),
            self.visible_scheduled_message,
        )
        with self.assertRaises(AccessError):
            self.visible_scheduled_message.write({"body": "boum"})
        with self.assertRaises(AccessError):
            self.visible_scheduled_message.post_message()
        self.visible_scheduled_message.unlink()

    @users("employee")
    def test_read_access_is_decided_by_the_document(self):
        hidden = self.hidden_scheduled_message.with_env(self.env)
        visible = self.visible_scheduled_message.with_env(self.env)
        self.assertFalse(hidden.has_access("read"))
        with self.assertRaises(AccessError):
            hidden.check_access("read")
        self.assertTrue(visible.has_access("read"))
        visible.check_access("read")
        self.assertEqual((hidden + visible)._filtered_access("read"), visible)

    @users("employee")
    def test_post_access_follows_the_document_operation(self):
        readonly_record = (
            self.env["mail.test.access"]
            .sudo()
            .create({"access": "internal_ro", "name": "Readonly Record"})
        )
        Scheduled = self.env["mail.scheduled.message"]
        for post_value, should_crash in (("read", False), ("write", True)):
            with (
                self.subTest(post_value=post_value),
                patch.object(MailTestAccess, "_mail_post_access", post_value),
            ):
                if should_crash:
                    with self.assertRaises(AccessError):
                        self.schedule_message(readonly_record)
                    continue
                scheduled_message = self.schedule_message(readonly_record)
                self.assertTrue(scheduled_message.has_access("read"))
                self.assertEqual(
                    Scheduled.search([("id", "=", scheduled_message.id)]),
                    scheduled_message,
                )
                with patch.object(MailTestAccess, "_mail_post_access", "write"):
                    self.env.invalidate_all()
                    self.assertFalse(scheduled_message.has_access("read"))
                    self.assertFalse(
                        Scheduled.search([("id", "=", scheduled_message.id)])
                    )

    @users("employee")
    def test_own_scheduled_message(self):
        scheduled_message = self.schedule_message(self.test_record)
        scheduled_message.read()
        self.assertEqual(
            self.env["mail.scheduled.message"].search(
                [["id", "=", scheduled_message.id]]
            ),
            scheduled_message,
        )
        scheduled_message.write({"body": "Hello!"})
        scheduled_message.unlink()


class TestScheduledMessageBusiness(TestScheduledMessage, CronMixinCase):
    @users("employee")
    def test_scheduled_message_restrictions(self):
        with self.assertRaises(ValidationError):
            self.schedule_message(
                self.test_record, scheduled_date="2022-12-24 10:00:00"
            )
        with self.with_user("admin"), self.assertRaises(ValidationError):
            self.schedule_message(self.user_employee)
        scheduled_message = self.schedule_message(self.test_record)
        with self.assertRaises(ValidationError):
            scheduled_message.write({"scheduled_date": "2022-12-24 14:00:00"})
        with self.assertRaises(UserError):
            scheduled_message.write({"res_id": 2})
        with self.assertRaises(UserError):
            scheduled_message.write({"model": "mail.test.track"})
        self.test_record.sudo().unlink()
        self.assertFalse(scheduled_message.exists())

    @users("employee")
    def test_scheduled_message_posting(self):
        schedule_cron_id = self.env.ref("mail.ir_cron_post_scheduled_message").id
        test_lead = self.env["mail.test.lead"].create({})
        with (
            self.mock_mail_gateway(),
            self.mock_mail_app(),
            self.capture_triggers(schedule_cron_id) as capt,
        ):
            scheduled_message_id = self.schedule_message(
                self.test_record,
                scheduled_date="2022-12-24 14:00:00",
                partner_ids=self.test_record.customer_id,
                body="success",
                send_context={"mail_post_autofollow": True},
                subject="Test subject",
            ).id
            self.assertEqual(
                capt.records["call_at"],
                FieldDatetime.to_datetime("2022-12-24 14:00:00"),
            )
            self.assertFalse(self.test_record.message_ids)
            self.assertFalse(self._new_mails)

            failing_schedueld_message_id = self.schedule_message(
                test_lead,
                scheduled_date="2022-12-24 14:00:00",
                partner_ids=self.test_record.customer_id,
                body="fail",
            ).id

            def _message_post_after_hook(self, message, values):
                raise Exception("Boum!")

            with (
                self.mock_datetime_and_now("2022-12-24 14:00:00"),
                patch.object(
                    MailTestTLead, "_message_post_after_hook", _message_post_after_hook
                ),
                mute_logger("odoo.addons.mail.models.mail_scheduled_message"),
            ):
                self.env["mail.scheduled.message"].with_user(
                    self.user_root
                )._post_messages_cron()
            self.assertEqual(len(self._new_mails), 1)
            self.assertMailNotifications(
                self._new_msgs.exists().filtered(lambda m: not m.model),
                [
                    {
                        "content": f"<p>The message scheduled on {test_lead._name}({test_lead.id}) with"
                        " the following content could not be sent:<br>-----<br></p><p>fail</p><br>-----<br>",
                        "message_type": "user_notification",
                        "subtype": "mail.mt_note",
                        "message_values": {
                            "author_id": self.partner_root,
                            "model": False,
                            "res_id": False,
                            "subject": "A scheduled message could not be sent",
                        },
                        "notif": [{"partner": self.partner_employee, "type": "inbox"}],
                    }
                ],
            )
            self.assertMailNotifications(
                self._new_msgs.exists().filtered(
                    lambda m: m.model == self.test_record._name
                ),
                [
                    {
                        "content": "<p>success</p>",
                        "message_type": "notification",
                        "message_values": {
                            "author_id": self.partner_employee,
                            "model": self.test_record._name,
                            "res_id": self.test_record.id,
                            "subject": "Test subject",
                        },
                        "notif": [
                            {"partner": self.test_record.customer_id, "type": "email"}
                        ],
                    }
                ],
            )
            self.assertEqual(self._new_mails[0].state, "sent")
            self.assertIn(
                self.test_record.customer_id, self.test_record.message_partner_ids
            )
            self.assertFalse(
                self.env["mail.scheduled.message"].search(
                    [["id", "in", [scheduled_message_id, failing_schedueld_message_id]]]
                )
            )

    def test_scheduled_message_kept_on_a_transient_failure(self):
        schedule_cron_id = self.env.ref("mail.ir_cron_post_scheduled_message").id
        test_lead = self.env["mail.test.lead"].create({})
        with self.mock_mail_gateway(), self.mock_mail_app():
            scheduled_message = self.schedule_message(
                test_lead,
                scheduled_date="2022-12-24 14:00:00",
                partner_ids=self.test_record.customer_id,
                body="conflict",
            )

            def _message_post_after_hook(self, message, values):
                raise SerializationFailure("could not serialize access")

            with (
                self.mock_datetime_and_now("2022-12-24 14:00:00"),
                patch.object(
                    MailTestTLead, "_message_post_after_hook", _message_post_after_hook
                ),
                self.capture_triggers(schedule_cron_id) as capt,
                mute_logger("odoo.addons.mail.models.mail_scheduled_message"),
            ):
                self.env["mail.scheduled.message"].with_user(
                    self.user_root
                )._post_messages_cron()

        self.assertTrue(scheduled_message.exists())
        self.assertNotIn("conflict", str(test_lead.message_ids.mapped("body")))
        self.assertFalse(
            self.env["mail.message"].search(
                [
                    ("model", "=", False),
                    ("subject", "=", "A scheduled message could not be sent"),
                ]
            )
        )
        self.assertEqual(len(capt.records), 1)

    @users("employee")
    def test_scheduled_message_posting_on_scheduled_time(self):
        self.test_record.message_subscribe(partner_ids=[self.partner_1.id])

        self.schedule_message(
            self.test_record,
            scheduled_date=FieldDatetime.to_string(self.reference_now),
        )

        with (
            self.mock_mail_gateway(),
            self.mock_datetime_and_now(self.reference_now),
            self.sync_env_with_side_cursors(),
        ):
            self.env.ref("mail.ir_cron_post_scheduled_message").with_user(
                self.user_admin
            ).method_direct_trigger()

        self.assertEqual(len(self._new_mails), 1)
        self.assertMailMailWRecord(
            self.test_record,
            [self.partner_1],
            "sent",
            author=self.env.user.partner_id,
        )
