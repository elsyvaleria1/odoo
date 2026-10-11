import contextlib
from datetime import timedelta
from unittest.mock import patch

from odoo.tests import tagged, users

from odoo.addons.social.tests.tools import mock_void_external_calls
from odoo.addons.test_event_full.tests.common import TestEventMailCommon
from odoo.addons.whatsapp.tests.common import WhatsAppCase


class TestEventMailFullCommon(TestEventMailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        with mock_void_external_calls():
            cls.social_media = cls.env["social.media"].create(
                {
                    "name": "Social Media",
                }
            )
            cls.social_account = cls.env["social.account"].create(
                {
                    "media_id": cls.social_media.id,
                    "name": "Social Account 1",
                }
            )

        cls.test_social_template = cls.env["social.post.template"].create(
            {
                "account_ids": [(4, cls.social_account.id)],
                "message": "Join the Python side of the force!",
            }
        )

        user_admin = cls.env.ref("base.user_admin")
        cls.whatsapp_account = (
            cls.env["whatsapp.account"]
            .with_user(user_admin)
            .create(
                [
                    {
                        "account_uid": "abcdef123456",
                        "app_secret": "1234567890abcdef",
                        "app_uid": "contact",
                        "name": "Test Account",
                        "notify_user_ids": user_admin.ids,
                        "phone_uid": "1234567890",
                        "token": "event_mail_is_great",
                    },
                ]
            )
        )

        cls.whatsapp_template_sub = cls.env["whatsapp.template"].create(
            {
                "body": "{{1}} registration confirmation.",
                "name": "Test subscription",
                "model_id": cls.env["ir.model"]._get_id("event.registration"),
                "status": "approved",
                "phone_field": "phone_ids",
                "wa_account_id": cls.whatsapp_account.id,
            }
        )
        cls.whatsapp_template_sub.variable_ids.write(
            {
                "field_type": "field",
                "field_name": "event_id",
            }
        )

        cls.whatsapp_template_rem = cls.env["whatsapp.template"].create(
            {
                "body": "{{1}} reminder.",
                "name": "Test reminder",
                "model_id": cls.env["ir.model"]._get_id("event.registration"),
                "status": "approved",
                "phone_field": "phone_ids",
                "wa_account_id": cls.whatsapp_account.id,
            }
        )

        cls.whatsapp_template_rem.variable_ids.write(
            {
                "field_type": "field",
                "field_name": "event_id",
            }
        )

        cls.test_event.write(
            {
                "event_mail_ids": [
                    (
                        0,
                        0,
                        {
                            "interval_unit": "now",
                            "interval_type": "after_sub",
                            "notification_type": "whatsapp",
                            "template_ref": f"whatsapp.template,{cls.whatsapp_template_sub.id}",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "interval_nbr": 3,
                            "interval_unit": "day",
                            "interval_type": "before_event",
                            "notification_type": "social_post",
                            "template_ref": f"social.post.template,{cls.test_social_template.id}",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "interval_nbr": 3,
                            "interval_unit": "day",
                            "interval_type": "before_event",
                            "notification_type": "whatsapp",
                            "template_ref": f"whatsapp.template,{cls.whatsapp_template_rem.id}",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "interval_nbr": 1,
                            "interval_unit": "hour",
                            "interval_type": "after_event",
                            "notification_type": "social_post",
                            "template_ref": f"social.post.template,{cls.test_social_template.id}",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "interval_nbr": 1,
                            "interval_unit": "hour",
                            "interval_type": "after_event",
                            "notification_type": "whatsapp",
                            "template_ref": f"whatsapp.template,{cls.whatsapp_template_rem.id}",
                        },
                    ),
                ],
            }
        )


@tagged("event_mail", "post_install", "-at_install")
class TestEventMailSchedule(TestEventMailFullCommon, WhatsAppCase):
    def execute_event_cron(self, *, freeze_date=None):
        cron = self.event_cron_id.sudo()
        with contextlib.ExitStack() as stack:
            if freeze_date:
                stack.enter_context(self.mock_datetime_and_now(freeze_date))
            stack.enter_context(self.mockSMSGateway())
            stack.enter_context(self.mock_mail_gateway())
            stack.enter_context(self.mockWhatsappGateway())
            capture = stack.enter_context(
                self.capture_triggers("event.event_mail_scheduler")
            )
            cron.method_direct_trigger()
            return capture

    @users("user_eventmanager")
    def test_schedule_event_scalability(self):
        test_event = self.env["event.event"].browse(self.test_event.ids)
        self._create_registrations(test_event, 30)

        after_social = test_event.event_mail_ids.filtered(
            lambda s: (
                s.interval_type == "after_event"
                and s.notification_type == "social_post"
            )
        )
        after_wa = test_event.event_mail_ids.filtered(
            lambda s: (
                s.interval_type == "after_event" and s.notification_type == "whatsapp"
            )
        )
        before_social = test_event.event_mail_ids.filtered(
            lambda s: (
                s.interval_type == "before_event"
                and s.notification_type == "social_post"
            )
        )
        before_wa = test_event.event_mail_ids.filtered(
            lambda s: (
                s.interval_type == "before_event" and s.notification_type == "whatsapp"
            )
        )
        for scheduler in after_social + after_wa + before_social + before_wa:
            self.assertEqual(len(scheduler), 1)
            self.assertEqual(scheduler.mail_count_done, 0)
            self.assertFalse(scheduler.mail_done)

        batch_size, cron_limit = 5, 20
        self.env["ir.config_parameter"].sudo().set_param("mail.batch_size", batch_size)
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.render.cron.limit", cron_limit
        )

        current_now = self.event_date_begin - timedelta(days=1)
        EventMail = type(self.env["event.mail"])
        exec_origin = EventMail._execute_event_based_for_registrations
        with patch.object(
            EventMail,
            "_execute_event_based_for_registrations",
            autospec=True,
            wraps=EventMail,
            side_effect=exec_origin,
        ) as mock_exec:
            capture = self.execute_event_cron(freeze_date=current_now)

        self.assertEqual(after_social.mail_count_done, 0)
        self.assertFalse(after_social.mail_done)
        self.assertEqual(after_wa.mail_count_done, 0)
        self.assertFalse(after_wa.mail_done)
        self.assertEqual(before_social.mail_count_done, 1)
        self.assertTrue(before_social.mail_done)
        self.assertEqual(before_wa.mail_count_done, 20)
        self.assertFalse(before_wa.mail_done)
        self.assertEqual(
            mock_exec.call_count,
            12,
            "Batch of 5 to make 20 registrations: 4 calls / scheduler (incl. mail and sms, not social)",
        )
        self.assertSchedulerCronTriggers(capture, [current_now] * 3)

        capture = self.execute_event_cron(freeze_date=current_now)
        self.assertEqual(before_wa.mail_count_done, 30)
        self.assertTrue(before_wa.mail_done)
        self.assertFalse(capture.records)

        current_now = self.event_date_end + timedelta(hours=1)
        capture = self.execute_event_cron(freeze_date=current_now)

        self.assertEqual(after_social.mail_count_done, 1)
        self.assertTrue(after_social.mail_done)
        self.assertEqual(after_wa.mail_count_done, 20)
        self.assertFalse(after_wa.mail_done)
        self.assertEqual(
            mock_exec.call_count,
            12,
            "Batch of 5 to make 20 registrations: 4 calls / scheduler (incl. mail and sms, not social)",
        )
        self.assertSchedulerCronTriggers(capture, [current_now] * 3)

        capture = self.execute_event_cron(freeze_date=current_now)
        self.assertEqual(after_wa.mail_count_done, 30)
        self.assertTrue(after_wa.mail_done)
        self.assertFalse(capture.records)

    @users("user_eventmanager")
    def test_schedule_subscription_scalability(self):
        test_event = self.env["event.event"].browse(self.test_event.ids)

        sub_wa = test_event.event_mail_ids.filtered(
            lambda s: (
                s.interval_type == "after_sub"
                and s.interval_unit == "now"
                and s.notification_type == "whatsapp"
            )
        )
        self.assertEqual(len(sub_wa), 1)
        self.assertEqual(sub_wa.mail_count_done, 0)

        batch_size, cron_limit = 5, 20
        self.env["ir.config_parameter"].sudo().set_param("mail.batch_size", batch_size)
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.render.cron.limit", cron_limit
        )

        EventMailRegistration = type(self.env["event.mail.registration"])
        exec_origin = EventMailRegistration._execute_on_registrations
        with (
            patch.object(
                EventMailRegistration,
                "_execute_on_registrations",
                autospec=True,
                wraps=EventMailRegistration,
                side_effect=exec_origin,
            ) as mock_exec,
            self.mock_datetime_and_now(self.reference_now + timedelta(hours=1)),
            self.mockSMSGateway(),
            self.mock_mail_gateway(),
            self.mockWhatsappGateway(),
            self.capture_triggers("event.event_mail_scheduler") as capture,
        ):
            self._create_registrations(test_event, 30)

        self.assertEqual(sub_wa.mail_count_done, 20)
        self.assertEqual(
            mock_exec.call_count,
            12,
            "Batch of 5 to make 20 registrations: 4 calls / scheduler (incl. mail and sms)",
        )
        self.assertSchedulerCronTriggers(
            capture, [self.reference_now + timedelta(hours=1)] * 3
        )

        with patch.object(
            EventMailRegistration,
            "_execute_on_registrations",
            autospec=True,
            wraps=EventMailRegistration,
            side_effect=exec_origin,
        ) as mock_exec:
            capture = self.execute_event_cron(
                freeze_date=self.reference_now + timedelta(hours=1)
            )

        self.assertEqual(sub_wa.mail_count_done, 30)
        self.assertFalse(capture.records)
        self.assertEqual(
            mock_exec.call_count,
            6,
            "Batch of 5 to make 10 remaining registrations: 2 calls / scheduler (incl. mail and sms)",
        )
