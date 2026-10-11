from dateutil.relativedelta import relativedelta

from odoo import Command
from odoo.fields import Datetime
from odoo.tests import tagged, users
from odoo.tools import mute_logger

from odoo.addons.base.tests.test_ir_cron import CronMixinCase
from odoo.addons.test_mail.data.test_mail_data import MAIL_TEMPLATE
from odoo.addons.test_marketing_automation.tests.common import TestMACommon


@tagged("marketing_automation")
class TestMarketAutoFlow(TestMACommon, CronMixinCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.date_reference = Datetime.from_string(
            "2014-08-01 15:02:32"
        )
        cls.env["res.lang"]._activate_lang("fr_FR")

        cls.test_records_base = cls._create_marketauto_records(
            model="marketing.test.sms", count=2
        )
        cls.test_records_failure = cls.env["marketing.test.sms"].create(
            [
                {
                    "email_from": "filter.me@test.example.com",
                    "name": "FilterMe",
                    "phone_ids": [
                        Command.create({"number": "0455987654", "type": "mobile"})
                    ],
                },
                {
                    "email_from": "wrong",
                    "name": "Wrong Email",
                    "phone_ids": [
                        Command.create({"number": "wrong", "type": "mobile"})
                    ],
                },
                {
                    "email_from": cls.test_records_base[1].email_from,
                    "name": cls.test_records_base[1].name,
                    "phone_ids": [Command.set(cls.test_records_base[1].phone_ids.ids)],
                },
            ]
        )
        (
            cls.test_records_filtered,
            cls.test_records_failure_wrong,
            cls.test_records_failure_dupe,
        ) = cls.test_records_failure
        cls.test_records_all = cls.test_records_base + cls.test_records_failure
        cls.test_records = cls.test_records_all - cls.test_records_filtered
        cls.test_records_contact_ko = (
            cls.test_records.filtered(
                lambda r: (
                    not r.email_from or r.email_from == "wrong"
                )
            )
            + cls.test_records_failure_dupe
        )
        cls.test_records_contact_ok = cls.test_records - cls.test_records_contact_ko


        cls.campaign = (
            cls.env["marketing.campaign"]
            .with_user(cls.user_marketing_automation)
            .create(
                {
                    "domain": [("name", "!=", "Invalid")],
                    "model_id": cls.env["ir.model"]._get_id("marketing.test.sms"),
                    "name": "Test Campaign",
                }
            )
        )
        cls.act1_mailing = cls._create_mailing(
            "marketing.test.sms",
            email_from=cls.user_marketing_automation.email_formatted,
            keep_archives=True,
        ).with_user(cls.user_marketing_automation)
        cls.act1 = cls._create_activity(
            cls.campaign,
            mailing=cls.act1_mailing,
            trigger_type="begin",
            interval_number=0,
        ).with_user(cls.user_marketing_automation)

        cls.act1_1_mailing = cls._create_mailing(
            "marketing.test.sms",
            mailing_type="sms",
            body_plaintext="SMS for {{ object.name }}: mega promo on https://test.example.com",
            sms_allow_unsubscribe=True,
        ).with_user(cls.user_marketing_automation)
        cls.act1_1 = cls._create_activity(
            cls.campaign,
            mailing=cls.act1_1_mailing,
            parent_id=cls.act1.id,
            trigger_type="mail_reply",
            interval_number=1,
            interval_type="hour",
        ).with_user(cls.user_marketing_automation)
        cls.act1_2_sact = cls.env["ir.actions.server"].create(
            {
                "code": """
for record in records:
    record.write({'description': record.description + ' - Did not answer, sad campaign is sad.'})""",
                "model_id": cls.env["ir.model"]._get("marketing.test.sms").id,
                "name": "Update description",
                "state": "code",
            }
        )
        cls.act1_2 = cls._create_activity(
            cls.campaign,
            action=cls.act1_2_sact,
            parent_id=cls.act1.id,
            trigger_type="mail_not_open",
            interval_number=1,
            interval_type="day",
            activity_domain=[("email_from", "!=", False)],
        ).with_user(cls.user_marketing_automation)
        cls.act1_3_wa_template = cls._create_wa_template(
            "marketing.test.sms",
            user=cls.user_marketing_automation.id,
        ).with_user(cls.user_marketing_automation)
        cls.act1_3 = cls._create_activity(
            cls.campaign,
            wa_template=cls.act1_3_wa_template,
            parent_id=cls.act1.id,
            trigger_type="activity",
            interval_number=1,
            interval_type="week",
        ).with_user(cls.user_marketing_automation)

        cls.act1_1_1_mailing = cls._create_mailing(
            "marketing.test.sms",
            mailing_type="sms",
            body_plaintext="Confirmation for {{ object.name }}",
            sms_allow_unsubscribe=False,
        ).with_user(cls.user_marketing_automation)
        cls.act1_1_1 = cls._create_activity(
            cls.campaign,
            mailing=cls.act1_1_1_mailing,
            parent_id=cls.act1_1.id,
            trigger_type="sms_click",
            interval_number=0,
        ).with_user(cls.user_marketing_automation)

        cls.act1_3_1_wa_template = cls._create_wa_template(
            "marketing.test.sms",
            body="WA Confirmation",
            name="Confirmation sub template",
            user=cls.user_marketing_automation.id,
        ).with_user(cls.user_marketing_automation)
        cls.act1_3_1 = cls._create_activity(
            cls.campaign,
            wa_template=cls.act1_3_1_wa_template,
            parent_id=cls.act1_3.id,
            trigger_type="whatsapp_replied",
            interval_number=0,
        ).with_user(cls.user_marketing_automation)

        cls.env.flush_all()

    def test_assert_initial_values(self):
        self.assertEqual(len(self.test_records_all), 13)
        self.assertEqual(len(self.test_records), 12)
        self.assertEqual(self.campaign.state, "draft")

    @mute_logger(
        "odoo.addons.base.models.ir_model",
        "odoo.addons.mail.models.mail_mail",
        "odoo.addons.mass_mailing.models.mailing",
        "odoo.addons.mass_mailing_sms.models.mailing_mailing",
    )
    @users("user_marketing_automation")
    def test_marketing_automation_flow(self):
        date_reference = self.date_reference
        test_records = self.test_records.with_user(self.env.user)

        act1 = self.act1.with_user(self.env.user)
        act1_1 = self.act1_1.with_user(self.env.user)
        act1_2 = self.act1_2.with_user(self.env.user)
        act1_1_1 = self.act1_1_1.with_user(self.env.user)
        act1_3 = self.act1_3.with_user(self.env.user)
        act1_3_1 = self.act1_3_1.with_user(self.env.user)
        campaign = self.campaign.with_user(self.env.user)
        campaign.write(
            {
                "domain": [("name", "!=", "FilterMe")],
            }
        )


        with (
            self.mock_datetime_and_now(self.date_reference),
            self.capture_triggers(
                "marketing_automation.ir_cron_campaign_sync_participants"
            ) as captured_triggers,
        ):
            campaign.action_start_campaign()
        self.assertEqual(campaign.state, "running")

        self.assertEqual(len(captured_triggers.records), 1)
        self.assertEqual(
            captured_triggers.records[0].cron_id,
            self.env.ref("marketing_automation.ir_cron_campaign_sync_participants"),
        )
        self.assertEqual(captured_triggers.records[0].call_at, self.date_reference)

        with (
            self.mock_datetime_and_now(date_reference),
            self.capture_triggers(
                "automation.ir_cron_data_automation_resume"
            ) as captured_triggers,
        ):
            campaign.sync_participants()

        self.assertEqual(campaign.running_participant_count, len(test_records))
        self.assertEqual(
            set(campaign.participant_ids.mapped("res_id")), set(test_records.ids)
        )
        self.assertEqual(set(campaign.participant_ids.mapped("state")), {"running"})

        self.assertMarketAutoTraces(
            [
                {
                    "status": "scheduled",
                    "records": test_records,
                    "participants": campaign.participant_ids,
                    "fields_values": {
                        "schedule_date": date_reference,
                    },
                }
            ],
            act1,
        )

        self.assertEqual(len(captured_triggers.records), 1)
        self.assertEqual(
            captured_triggers.records[0].cron_id,
            self.env.ref("automation.ir_cron_data_automation_resume"),
        )
        self.assertEqual(captured_triggers.records[0].call_at, self.date_reference)

        for act in act1_1 + act1_1_1 + act1_2 + act1_3 + act1_3_1:
            self.assertEqual(act.trace_ids, self.env["marketing.trace"])

        test_records_contact_ko = self.test_records_contact_ko.with_env(self.env)
        test_records_contact_ok = self.test_records_contact_ok.with_env(self.env)

        with (
            self.mock_datetime_and_now(self.date_reference),
            self.mock_mail_gateway(),
            self.capture_triggers(
                "automation.ir_cron_data_automation_resume"
            ) as captured_triggers,
        ):
            campaign.execute_activities()

        self.assertMarketAutoTraces(
            [
                {
                    "status": "processed",
                    "records": test_records_contact_ok,
                    "records_to_partner": {
                        r.id: r.customer_id for r in test_records_contact_ok
                    },
                    "trace_status": "sent",
                    "fields_values": {
                        "schedule_date": date_reference,
                    },
                },
                {
                    "status": "canceled",
                    "records": self.test_records_failure_wrong,
                    "fields_values": {
                        "schedule_date": date_reference,
                        "state_msg": "Email cancelled",
                    },
                    "trace_email": self.test_records_failure_wrong.email_from,
                    "trace_failure_type": "mail_email_invalid",
                    "trace_status": "cancel",
                },
                {
                    "status": "canceled",
                    "records": self.test_records_failure_dupe,
                    "fields_values": {
                        "schedule_date": date_reference,
                        "state_msg": "Email cancelled",
                    },
                    "trace_email": self.test_records_failure_dupe.email_normalized,
                    "trace_failure_type": "mail_dup",
                    "trace_status": "cancel",
                },
                {
                    "status": "canceled",
                    "records": (
                        test_records_contact_ko
                        - self.test_records_failure_wrong
                        - self.test_records_failure_dupe
                    ),
                    "fields_values": {
                        "schedule_date": date_reference,
                        "state_msg": "Email cancelled",
                    },
                    "trace_failure_type": "mail_email_missing",
                    "trace_status": "cancel",
                },
            ],
            act1,
        )

        self.assertMarketAutoTraces(
            [
                {
                    "status": "scheduled",
                    "records": test_records,
                    "participants": campaign.participant_ids,
                    "fields_values": {
                        "schedule_date": False,
                    },
                }
            ],
            act1_1,
        )
        self.assertMarketAutoTraces(
            [
                {
                    "status": "scheduled",
                    "records": test_records,
                    "participants": campaign.participant_ids,
                    "fields_values": {
                        "schedule_date": date_reference + relativedelta(days=1),
                    },
                }
            ],
            act1_2,
        )
        self.assertMarketAutoTraces(
            [
                {
                    "status": "scheduled",
                    "records": test_records,
                    "participants": campaign.participant_ids,
                    "fields_values": {
                        "schedule_date": date_reference + relativedelta(weeks=1),
                    },
                }
            ],
            act1_3,
        )

        self.assertEqual(2, len(captured_triggers.records))
        for trigger in captured_triggers.records:
            self.assertEqual(
                self.env.ref("automation.ir_cron_data_automation_resume"),
                trigger.cron_id,
            )
        self.assertEqual(
            sorted(r.call_at for r in captured_triggers.records),
            [
                self.date_reference + relativedelta(days=1),
                self.date_reference + relativedelta(weeks=1),
            ],
            "Should have 1 day / 1 week triggers: two sub activities with should have triggers",
        )

        with self.mock_datetime_and_now(self.date_reference):
            campaign.execute_activities()
        for act in act1_1 + act1_2 + act1_3:
            self.assertEqual(set(act.trace_ids.mapped("state")), {"scheduled"})
        for act in act1_1_1 + act1_3_1:
            self.assertFalse(
                act.trace_ids,
                "Grand children should have traces only when their respective parent is executed",
            )


        date_reference_reply = date_reference + relativedelta(hours=1)
        test_records_mail_replied = test_records_contact_ok[:2]
        with (
            self.mock_datetime_and_now(date_reference_reply),
            self.capture_triggers(
                "automation.ir_cron_data_automation_resume"
            ) as captured_triggers,
        ):
            for record in test_records_mail_replied:
                self.gateway_mail_reply_wrecord(MAIL_TEMPLATE, record)

        self.assertMarketAutoTraces(
            [
                {
                    "status": "processed",
                    "records": test_records_mail_replied,
                    "records_to_partner": {
                        r.id: r.customer_id for r in test_records_mail_replied
                    },
                    "trace_status": "reply",
                    "fields_values": {
                        "schedule_date": date_reference,
                    },
                },
                {
                    "status": "processed",
                    "records": test_records_contact_ok - test_records_mail_replied,
                    "records_to_partner": {
                        r.id: r.customer_id
                        for r in test_records_contact_ok - test_records_mail_replied
                    },
                    "trace_status": "sent",
                    "fields_values": {
                        "schedule_date": date_reference,
                    },
                },
                {
                    "status": "canceled",
                    "records": self.test_records_failure_wrong,
                    "fields_values": {
                        "schedule_date": date_reference,
                        "state_msg": "Email cancelled",
                    },
                    "trace_email": self.test_records_failure_wrong.email_from,
                    "trace_failure_type": "mail_email_invalid",
                    "trace_status": "cancel",
                },
                {
                    "status": "canceled",
                    "records": self.test_records_failure_dupe,
                    "fields_values": {
                        "schedule_date": date_reference,
                        "state_msg": "Email cancelled",
                    },
                    "trace_email": self.test_records_failure_dupe.email_normalized,
                    "trace_failure_type": "mail_dup",
                    "trace_status": "cancel",
                },
                {
                    "status": "canceled",
                    "records": (
                        test_records_contact_ko
                        - self.test_records_failure_wrong
                        - self.test_records_failure_dupe
                    ),
                    "fields_values": {
                        "schedule_date": date_reference,
                        "state_msg": "Email cancelled",
                    },
                    "trace_failure_type": "mail_email_missing",
                    "trace_status": "cancel",
                },
            ],
            act1,
        )

        self.assertMarketAutoTraces(
            [
                {
                    "status": "scheduled",
                    "records": test_records_mail_replied,
                    "fields_values": {
                        "schedule_date": date_reference_reply + relativedelta(hours=1),
                    },
                },
                {
                    "status": "scheduled",
                    "records": test_records - test_records_mail_replied,
                    "fields_values": {
                        "schedule_date": False,
                    },
                },
            ],
            act1_1,
        )
        self.assertMarketAutoTraces(
            [
                {
                    "status": "scheduled",
                    "records": test_records - test_records_mail_replied,
                    "fields_values": {
                        "schedule_date": date_reference + relativedelta(days=1),
                    },
                },
                {
                    "status": "canceled",
                    "records": test_records_mail_replied,
                    "fields_values": {
                        "schedule_date": date_reference_reply,
                    },
                },
            ],
            act1_2,
        )
        self.assertMarketAutoTraces(
            [
                {
                    "status": "scheduled",
                    "records": test_records,
                    "participants": campaign.participant_ids,
                    "fields_values": {
                        "schedule_date": date_reference + relativedelta(weeks=1),
                    },
                }
            ],
            act1_3,
        )

        self.assertEqual(len(captured_triggers.records), 1)
        for captured_trigger in captured_triggers.records:
            self.assertEqual(
                captured_trigger.cron_id,
                self.env.ref("automation.ir_cron_data_automation_resume"),
            )
            self.assertEqual(
                captured_trigger.call_at, date_reference_reply + relativedelta(hours=1)
            )


        date_reference_new = date_reference + relativedelta(hours=2)

        with (
            self.mock_datetime_and_now(date_reference_new),
            self.mockSMSGateway(),
            self.capture_triggers(
                "automation.ir_cron_data_automation_resume"
            ) as captured_triggers,
        ):
            campaign.execute_activities()

        self.assertMarketAutoTraces(
            [
                {
                    "status": "processed",
                    "records": test_records_mail_replied,
                    "fields_values": {
                        "schedule_date": date_reference_reply + relativedelta(hours=1),
                    },
                    "trace_status": "outgoing",
                },
                {
                    "status": "scheduled",
                    "records": test_records - test_records_mail_replied,
                    "fields_values": {
                        "schedule_date": False,
                    },
                },
            ],
            act1_1,
        )
        self.assertMarketAutoTraces(
            [
                {
                    "status": "scheduled",
                    "records": test_records_mail_replied,
                    "fields_values": {
                        "schedule_date": False,
                    },
                }
            ],
            act1_1_1,
        )

        self.assertFalse(captured_triggers.records)

        self.env.flush_all()
        with (
            self.mock_datetime_and_now(date_reference_new),
            self.mockSMSGateway(),
            self.capture_triggers(
                "automation.ir_cron_data_automation_resume"
            ) as captured_triggers,
            self.registry.cursor() as cr,
        ):
            self.env(cr=cr)["sms.sms"].sudo()._process_queue()
            self.env.invalidate_all()

        self.assertMarketAutoTraces(
            [
                {
                    "status": "processed",
                    "records": test_records_mail_replied,
                    "fields_values": {
                        "schedule_date": date_reference_reply + relativedelta(hours=1),
                    },
                    "trace_status": "pending",
                },
                {
                    "status": "scheduled",
                    "records": test_records - test_records_mail_replied,
                    "fields_values": {
                        "schedule_date": False,
                    },
                },
            ],
            act1_1,
        )

        self.assertFalse(captured_triggers.records)


        self._clear_outgoing_sms()
        test_records_sms_clicked = test_records_mail_replied[0]
        sms_sent = self._find_sms_sent(
            test_records_sms_clicked.customer_id,
            test_records_sms_clicked.phone_sanitized,
        )

        with (
            self.mock_datetime_and_now(date_reference_new),
            self.mockSMSGateway(),
            self.capture_triggers(
                "automation.ir_cron_data_automation_resume"
            ) as captured_triggers,
        ):
            self.gateway_sms_sent_click(sms_sent)

        self.assertFalse(captured_triggers.records)

        self.env.flush_all()
        with (
            self.mock_datetime_and_now(date_reference_new),
            self.mockSMSGateway(),
            self.capture_triggers(
                "automation.ir_cron_data_automation_resume"
            ) as captured_triggers,
            self.registry.cursor() as cr,
        ):
            self.env(cr=cr)["sms.sms"].sudo()._process_queue()
            self.env.invalidate_all()

        self.assertFalse(captured_triggers.records)

        self.assertMarketAutoTraces(
            [
                {
                    "status": "processed",
                    "records": test_records_sms_clicked,
                    "fields_values": {
                        "schedule_date": date_reference_new,
                    },
                    "trace_content": f"Confirmation for {test_records_sms_clicked.name}",
                    "trace_status": "pending",
                },
                {
                    "status": "scheduled",
                    "records": test_records_mail_replied - test_records_sms_clicked,
                    "fields_values": {
                        "schedule_date": False,
                    },
                },
            ],
            act1_1_1,
        )


        date_reference_new = date_reference + relativedelta(days=1, hours=2)
        self._clear_outgoing_sms()
        with (
            self.mock_datetime_and_now(date_reference_new),
            mute_logger("odoo.addons.marketing_automation.models.marketing_activity"),
            self.capture_triggers(
                "automation.ir_cron_data_automation_resume"
            ) as captured_triggers,
        ):
            campaign.execute_activities()

        self.assertMarketAutoTraces(
            [
                {
                    "status": "processed",
                    "records": test_records_contact_ok - test_records_mail_replied,
                    "fields_values": {
                        "schedule_date": date_reference_new,
                    },
                },
                {
                    "status": "error",
                    "records": (
                        self.test_records_failure_wrong + self.test_records_failure_dupe
                    ),
                    "fields_values": {
                        "schedule_date": date_reference_new,
                        "state_msg_content": "Exception in server action",
                    },
                },
                {
                    "status": "rejected",
                    "records": (
                        test_records_contact_ko
                        - self.test_records_failure_wrong
                        - self.test_records_failure_dupe
                    ),
                    "fields_values": {
                        "schedule_date": date_reference + relativedelta(days=1),
                    },
                },
                {
                    "status": "canceled",
                    "records": test_records_mail_replied,
                    "fields_values": {
                        "schedule_date": date_reference_reply,
                    },
                },
            ],
            act1_2,
        )

        for record in test_records_contact_ko | test_records_mail_replied:
            self.assertNotIn(
                "Did not answer, sad campaign is sad", (record.description or "")
            )
        for record in test_records_contact_ok - test_records_mail_replied:
            self.assertIn(
                "Did not answer, sad campaign is sad", (record.description or "")
            )
        self.assertFalse(captured_triggers.records)

        date_reference_new = date_reference + relativedelta(weeks=1, hours=1)
        with (
            self.mock_datetime_and_now(date_reference_new),
            self.mockWhatsappGateway(),
            self.patchWhatsappCronTrigger(),
            self.capture_triggers(
                "automation.ir_cron_data_automation_resume"
            ) as captured_triggers,
        ):
            campaign.execute_activities()

        self.assertMarketAutoTraces(
            [
                {
                    "status": "processed",
                    "records": test_records_contact_ok,
                    "fields_values": {
                        "schedule_date": date_reference_new,
                    },
                    "trace_content": "<p>Hello your much wow template value</p>",
                    "trace_status": "sent",
                },
                {
                    "status": "processed",
                    "records": self.test_records_failure_dupe,
                    "fields_values": {
                        "schedule_date": date_reference_new,
                    },
                    "trace_content": "<p>Hello your much wow template value</p>",
                    "trace_status": "sent",
                },
                {
                    "status": "error",
                    "records": self.test_records_failure_wrong,
                    "fields_values": {
                        "schedule_date": date_reference_new,
                    },
                    "trace_failure_reason": False,
                    "trace_failure_type": "phone_invalid",
                    "trace_status": "error",
                },
                {
                    "status": "error",
                    "records": (
                        test_records_contact_ko
                        - self.test_records_failure_wrong
                        - self.test_records_failure_dupe
                    ),
                    "fields_values": {
                        "schedule_date": date_reference_new,
                    },
                    "trace_failure_reason": False,
                    "trace_failure_type": "phone_invalid",
                    "trace_status": "error",
                },
            ],
            act1_3,
        )
        self.assertMarketAutoTraces(
            [
                {
                    "status": "scheduled",
                    "records": test_records,
                    "fields_values": {
                        "schedule_date": False,
                    },
                }
            ],
            act1_3_1,
        )

        date_wa_reply = date_reference + relativedelta(weeks=1, hours=2)
        with self.mock_datetime_and_now(date_wa_reply):
            self.whatsapp_answer_with_records(test_records_contact_ok[0:2], mock=True)
        self.assertMarketAutoTraces(
            [
                {
                    "status": "processed",
                    "records": test_records_contact_ok[0:2],
                    "fields_values": {
                        "schedule_date": date_reference_new,
                    },
                    "trace_status": "replied",
                    "wa_from_mock": False,
                },
                {
                    "status": "processed",
                    "records": test_records_contact_ok[2:],
                    "fields_values": {
                        "schedule_date": date_reference_new,
                    },
                    "trace_status": "sent",
                    "wa_from_mock": False,
                },
            ],
            act1_3,
            strict=False,
        )
        self.assertMarketAutoTraces(
            [
                {
                    "status": "scheduled",
                    "records": test_records - test_records_contact_ok[0:2],
                    "fields_values": {
                        "schedule_date": False,
                    },
                },
                {
                    "status": "processed",
                    "records": test_records_contact_ok[0:2],
                    "fields_values": {
                        "schedule_date": date_wa_reply,
                    },
                    "trace_status": "sent",
                },
            ],
            act1_3_1,
        )
