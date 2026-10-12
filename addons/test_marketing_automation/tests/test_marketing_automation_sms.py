from dateutil.relativedelta import relativedelta

from odoo import Command
from odoo.fields import Datetime
from odoo.tests import tagged, users

from odoo.addons.test_marketing_automation.tests.common import TestMACommon


@tagged("post_install", "-at_install", "marketing_automation", "twilio")
class TestMarketingAutomationSms(TestMACommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.date_reference = Datetime.from_string("2025-08-22 11:15:30")
        cls.env["res.lang"]._activate_lang("fr_FR")
        cls._setup_sms_twilio(cls.user_marketing_automation.company_id)

        cls.test_records_base = cls._create_marketauto_records(
            model="marketing.test.sms", count=2
        )
        cls.test_records_failure = cls.env["marketing.test.sms"].create(
            [
                {
                    "email_from": "wrong",
                    "name": "Wrong",
                    "phone_ids": [
                        Command.create({"number": "87645", "type": "mobile"})
                    ],
                },
                {
                    "email_from": cls.test_records_base[1].email_from,
                    "phone_ids": [Command.set(cls.test_records_base[1].phone_ids.ids)],
                    "name": cls.test_records_base[1].name,
                },
            ]
        )
        (cls.test_records_failure_wrong, cls.test_records_failure_dupe) = (
            cls.test_records_failure
        )
        cls.test_records = cls.test_records_base + cls.test_records_failure

        cls.campaign = (
            cls.env["marketing.campaign"]
            .with_user(cls.user_marketing_automation)
            .create(
                {
                    "model_id": cls.env["ir.model"]._get_id("marketing.test.sms"),
                    "name": "Test SMS Campaign",
                }
            )
        )
        cls.act1_sms_mailing = cls._create_mailing(
            "marketing.test.sms",
            mailing_type="sms",
            body_plaintext="SMS for {{ object.name }}: mega promo on https://test.example.com",
            sms_allow_unsubscribe=True,
        ).with_user(cls.user_marketing_automation)
        cls.act1 = cls._create_activity(
            cls.campaign,
            mailing=cls.act1_sms_mailing,
            trigger_type="begin",
            interval_number=1,
            interval_type="hour",
        ).with_user(cls.user_marketing_automation)
        cls.act1_1_sact = cls.env["ir.actions.server"].create(
            {
                "code": "records.action_archive()",
                "model_id": cls.env["ir.model"]._get("marketing.test.sms").id,
                "name": "Archive records",
                "state": "code",
            }
        )
        cls.act1_1 = cls._create_activity(
            cls.campaign,
            action=cls.act1_1_sact,
            parent_id=cls.act1.id,
            trigger_type="sms_bounce",
            interval_number=0,
        ).with_user(cls.user_marketing_automation)

        cls.env.flush_all()

    def test_assert_initial_values(self):
        self.assertEqual(len(self.test_records), 12)
        self.assertEqual(self.campaign.state, "draft")

    @users("user_marketing_automation")
    def test_marketing_automation_flow(self):
        data_reference_start = self.date_reference + relativedelta(hours=1)
        test_records = self.test_records.with_user(self.env.user)

        act1 = self.act1.with_user(self.env.user)
        _act1_1 = self.act1_1.with_user(self.env.user)
        campaign = self.campaign.with_user(self.env.user)

        with self.mock_datetime_and_now(self.date_reference):
            campaign.action_start_campaign()
            campaign.sync_participants()

        self.assertEqual(campaign.running_participant_count, len(test_records))
        self.assertEqual(
            set(campaign.participant_ids.mapped("res_id")), set(test_records.ids)
        )
        self.assertEqual(set(campaign.participant_ids.mapped("state")), {"running"})

        self.assertMarketAutoTraces(
            [
                {
                    "fields_values": {
                        "schedule_date": data_reference_start,
                    },
                    "participants": campaign.participant_ids,
                    "records": test_records,
                    "status": "scheduled",
                }
            ],
            act1,
        )

        test_records_1_ko = (
            test_records.filtered(
                lambda r: not r.phone_ids or r._phone_get_number().number == "87645"
            )
            + self.test_records_failure_dupe
        )
        test_records_1_ok = test_records.filtered(lambda r: r not in test_records_1_ko)

        with (
            self.mock_datetime_and_now(data_reference_start),
            self.mockSMSGateway(),
            self.mock_sms_twilio_send(),
        ):
            campaign.execute_activities()
            self.env.flush_all()
            with self.registry.cursor() as cr:
                self.env(cr=cr)["sms.sms"].sudo()._process_queue()
            self.env.invalidate_all()

        self.assertEqual(self._sms_twilio_send_mock.call_count, 8)

        sms_batch = self._new_sms.filtered(
            lambda sms: sms.mailing_trace_ids.res_id in test_records_1_ok.ids,
        )
        self.simulate_sms_twilio_status(
            sms_batch, self.user_marketing_automation.company_id
        )

        self.assertMarketAutoTraces(
            [
                {
                    "fields_values": {
                        "schedule_date": data_reference_start,
                        "state_msg": False,
                    },
                    "records": test_records_1_ok,
                    "status": "processed",
                    "trace_status": "sent",
                },
                {
                    "fields_values": {
                        "schedule_date": data_reference_start,
                        "state_msg": "SMS cancelled",
                    },
                    "records": self.test_records_failure_wrong,
                    "status": "canceled",
                    "trace_failure_type": "sms_number_format",
                    "trace_sms_number": "87645",
                    "trace_status": "cancel",
                },
                {
                    "fields_values": {
                        "schedule_date": data_reference_start,
                        "state_msg": "SMS cancelled",
                    },
                    "records": self.test_records_failure_dupe,
                    "status": "canceled",
                    "trace_failure_type": "sms_duplicate",
                    "trace_status": "cancel",
                },
                {
                    "check_sms": False,
                    "fields_values": {
                        "schedule_date": data_reference_start,
                        "state_msg": "SMS cancelled",
                    },
                    "records": (
                        test_records_1_ko
                        - self.test_records_failure_wrong
                        - self.test_records_failure_dupe
                    ),
                    "status": "canceled",
                    "trace_failure_type": "mail_email_missing",
                    "trace_status": "cancel",
                },
            ],
            act1,
        )
