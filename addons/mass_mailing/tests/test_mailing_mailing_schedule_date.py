from datetime import datetime

from freezegun import freeze_time

from odoo.tests import Form, users
from odoo.tools import mute_logger

from odoo.addons.base.tests.test_ir_cron import CronMixinCase
from odoo.addons.mass_mailing.tests.common import MassMailCommon


class TestMailingScheduleDateWizard(MassMailCommon, CronMixinCase):
    @mute_logger("odoo.addons.mail.models.mail_mail")
    @users("user_marketing")
    def test_mailing_next_departure(self):

        cron_job = self.env.ref("mass_mailing.ir_cron_mass_mailing_queue").sudo()
        cron_job.write({"nextcall": datetime(2023, 2, 18, 9, 0)})
        cron_job_id = cron_job.id

        with freeze_time(datetime(2023, 2, 17, 9, 0)):
            with self.capture_triggers(cron_job_id) as capt:
                mailing = self.env["mailing.mailing"].create(
                    {
                        "name": "mailing",
                        "subject": "some subject",
                        "mailing_model_id": self.env["ir.model"]._get("res.partner").id,
                        "state": "draft",
                    }
                )
                mailing.action_launch()
            capt.records.check_singleton()

            self.assertEqual(mailing.next_departure, datetime(2023, 2, 17, 9, 0))
            self.assertIsNot(mailing.schedule_date, cron_job.nextcall)
            self.assertEqual(mailing.schedule_type, "now")
            self.assertEqual(mailing.state, "in_queue")
            self.assertEqual(capt.records.call_at, datetime(2023, 2, 17, 9, 0))

        with freeze_time(datetime(2023, 2, 17, 9, 0)):
            with self.capture_triggers(cron_job_id) as capt:
                mailing = self.env["mailing.mailing"].create(
                    {
                        "name": "mailing",
                        "subject": "some subject",
                        "mailing_model_id": self.env["ir.model"]._get("res.partner").id,
                        "state": "draft",
                        "schedule_date": datetime(2023, 2, 17, 11, 0),
                        "schedule_type": "scheduled",
                    }
                )
                mailing.action_schedule()
            capt.records.check_singleton()

            self.assertEqual(mailing.schedule_date, datetime(2023, 2, 17, 11, 0))
            self.assertEqual(mailing.next_departure, datetime(2023, 2, 17, 11, 0))
            self.assertEqual(mailing.schedule_type, "scheduled")
            self.assertEqual(mailing.state, "in_queue")
            self.assertEqual(capt.records.call_at, datetime(2023, 2, 17, 11, 0))

        with freeze_time(datetime(2023, 2, 17, 9, 0)):
            with self.capture_triggers(cron_job_id) as capt:
                mailing = self.env["mailing.mailing"].create(
                    {
                        "name": "mailing",
                        "subject": "some subject",
                        "mailing_model_id": self.env["ir.model"]._get("res.partner").id,
                        "state": "draft",
                        "schedule_date": datetime(2024, 2, 17, 11, 0),
                        "schedule_type": "scheduled",
                    }
                )
                mailing.action_schedule()
            capt.records.check_singleton()

            self.assertEqual(mailing.schedule_date, datetime(2024, 2, 17, 11, 0))
            self.assertEqual(mailing.next_departure, datetime(2024, 2, 17, 11, 0))
            self.assertEqual(mailing.schedule_type, "scheduled")
            self.assertEqual(mailing.state, "in_queue")
            self.assertEqual(capt.records.call_at, datetime(2024, 2, 17, 11, 0))

        with freeze_time(datetime(2023, 2, 17, 9, 0)):
            with self.capture_triggers(cron_job_id) as capt:
                mailing = self.env["mailing.mailing"].create(
                    {
                        "name": "mailing",
                        "subject": "some subject",
                        "mailing_model_id": self.env["ir.model"]._get("res.partner").id,
                        "state": "draft",
                        "schedule_date": datetime(2024, 2, 17, 11, 0),
                        "schedule_type": "scheduled",
                    }
                )

                wizard_form = Form(
                    self.env["wizard.mailing.mailing.schedule"].with_context(
                        default_mass_mailing_id=mailing.id
                    )
                )

                wizard_form.schedule_date = datetime(2022, 2, 17, 11, 0)
                wizard = wizard_form.save()
                wizard.action_schedule_date()
            capt.records.check_singleton()

            self.assertEqual(mailing.schedule_date, datetime(2022, 2, 17, 11, 0))
            self.assertEqual(mailing.next_departure, datetime(2023, 2, 17, 9, 0))
            self.assertEqual(mailing.schedule_type, "scheduled")
            self.assertEqual(mailing.state, "in_queue")
            self.assertEqual(capt.records.call_at, datetime(2022, 2, 17, 11, 0))

    def test_mailing_schedule_date(self):
        mailing = self.env["mailing.mailing"].create(
            {
                "name": "mailing",
                "subject": "some subject",
                "mailing_model_id": self.env["ir.model"]._get("res.partner").id,
            }
        )
        wizard_form = Form(
            self.env["wizard.mailing.mailing.schedule"].with_context(
                default_mass_mailing_id=mailing.id
            )
        )

        wizard_form.schedule_date = datetime(2021, 4, 30, 9, 0)
        wizard = wizard_form.save()
        wizard.action_schedule_date()

        self.assertEqual(mailing.schedule_date, datetime(2021, 4, 30, 9, 0))
        self.assertEqual(mailing.schedule_type, "scheduled")
        self.assertEqual(mailing.state, "in_queue")
