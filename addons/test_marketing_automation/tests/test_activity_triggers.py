from datetime import timedelta

from odoo.fields import Datetime
from odoo.tests import tagged, users
from odoo.tools import mute_logger

from odoo.addons.test_marketing_automation.tests.common import TestMACommon


class ActivityTriggersCase(TestMACommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.date_reference = Datetime.from_string("2023-11-08 09:00:00")

        cls.test_records_base = cls._create_marketauto_records(
            model="marketing.test.sms", count=2
        )
        cls.test_records = cls.test_records_base
        cls.test_customers = cls.test_records.customer_id
        cls.test_records_ko = cls.test_records_base[4] + cls.test_records_base[9]
        cls.test_records_ok = cls.test_records - cls.test_records_ko

        cls.campaign = cls.env["marketing.campaign"].create(
            {
                "domain": [("id", "in", cls.test_records.ids)],
                "model_id": cls.env["ir.model"]._get_id("marketing.test.sms"),
                "name": "Test Campaign",
            }
        )

        cls.test_mailing_mail = cls._create_mailing(
            "marketing.test.sms",
            email_from=cls.user_marketing_automation.email_formatted,
            keep_archives=True,
            mailing_type="mail",
            user_id=cls.user_marketing_automation.id,
        )
        cls.test_mailing_sms = cls._create_mailing(
            "marketing.test.sms",
            mailing_type="sms",
            user_id=cls.user_marketing_automation.id,
        )
        cls.test_wa_template = cls._create_wa_template(
            "marketing.test.sms",
        )

        cls.test_sa_descr = cls.env["ir.actions.server"].create(
            [
                {
                    "code": f"""
for record in records:
    record.write({{'description': (record.description or '') + ' - {description}'}})""",
                    "model_id": cls.env["ir.model"]._get_id("marketing.test.sms"),
                    "name": f"Update {description}",
                    "state": "code",
                }
                for description in [
                    "mail_open",
                    "mail_not_open",
                    "mail_reply",
                    "mail_not_reply",
                    "mail_click",
                    "mail_not_click",
                    "mail_bounce",
                    "sms_click",
                    "sms_not_click",
                    "sms_bounce",
                    "whatsapp_click",
                    "whatsapp_not_click",
                    "whatsapp_read",
                    "whatsapp_not_read",
                    "whatsapp_replied",
                    "whatsapp_not_replied",
                    "whatsapp_bounced",
                    "action",
                ]
            ]
        )
        (
            cls.test_sa_descr_mail_open,
            cls.test_sa_descr_mail_not_open,
            cls.test_sa_descr_mail_reply,
            cls.test_sa_descr_mail_not_reply,
            cls.test_sa_descr_mail_click,
            cls.test_sa_descr_mail_not_click,
            cls.test_sa_descr_mail_bounce,
            cls.test_sa_descr_sms_click,
            cls.test_sa_descr_sms_not_click,
            cls.test_sa_descr_sms_bounce,
            cls.test_sa_descr_wa_click,
            cls.test_sa_descr_wa_not_click,
            cls.test_sa_descr_wa_read,
            cls.test_sa_descr_wa_not_read,
            cls.test_sa_descr_wa_replied,
            cls.test_sa_descr_wa_not_replied,
            cls.test_sa_descr_wa_bounced,
            cls.test_sa_descr_action,
        ) = cls.test_sa_descr
        cls.test_sa_unlink = cls.env["ir.actions.server"].create(
            {
                "code": "records.unlink()",
                "model_id": cls.env["ir.model"]._get_id("marketing.test.sms"),
                "name": "Unlink",
                "state": "code",
            }
        )

        cls.env.flush_all()


@tagged("marketing_automation", "ma_sync")
class TestActivityTriggers(ActivityTriggersCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.activity_begin_mail = cls._create_activity(
            cls.campaign,
            create_date=cls.date_reference,
            mailing=cls.test_mailing_mail,
            interval_number=1,
            interval_type="hour",
            trigger_type="begin",
        )
        cls.activity_begin_sms = cls._create_activity(
            cls.campaign,
            create_date=cls.date_reference,
            mailing=cls.test_mailing_sms,
            interval_number=1,
            interval_type="hour",
            trigger_type="begin",
        )
        cls.activity_begin_wa = cls._create_activity(
            cls.campaign,
            create_date=cls.date_reference,
            wa_template=cls.test_wa_template,
            interval_number=1,
            interval_type="hour",
            trigger_type="begin",
        )
        cls.activity_begin_sa = cls._create_activity(
            cls.campaign,
            create_date=cls.date_reference,
            action=cls.test_sa_descr_action,
            interval_number=1,
            interval_type="hour",
            trigger_type="begin",
        )

        (
            cls.activity_sa_mail_not_open,
            cls.activity_sa_mail_open,
            cls.activity_sa_mail_not_reply,
            cls.activity_sa_mail_reply,
            cls.activity_sa_mail_not_click,
            cls.activity_sa_mail_click,
            cls.activity_sa_mail_bounce,
            cls.activity_sa_sms_not_click,
            cls.activity_sa_sms_click,
            cls.activity_sa_sms_bounce,
            cls.activity_sa_wa_not_read,
            cls.activity_sa_wa_read,
            cls.activity_sa_wa_not_replied,
            cls.activity_sa_wa_replied,
            cls.activity_sa_wa_not_click,
            cls.activity_sa_wa_click,
            cls.activity_sa_wa_bounced,
        ) = (
            cls._create_activity(
                cls.campaign,
                action=server_action,
                parent_id=parent.id,
                interval_number=itv,
                interval_type="day",
                trigger_type=trigger_type,
            )
            for trigger_type, server_action, parent, itv in (
                (
                    "mail_not_open",
                    cls.test_sa_descr_mail_not_open,
                    cls.activity_begin_mail,
                    5,
                ),
                ("mail_open", cls.test_sa_descr_mail_open, cls.activity_begin_mail, 1),
                (
                    "mail_not_reply",
                    cls.test_sa_descr_mail_not_reply,
                    cls.activity_begin_mail,
                    5,
                ),
                (
                    "mail_reply",
                    cls.test_sa_descr_mail_reply,
                    cls.activity_begin_mail,
                    1,
                ),
                (
                    "mail_not_click",
                    cls.test_sa_descr_mail_not_click,
                    cls.activity_begin_mail,
                    5,
                ),
                (
                    "mail_click",
                    cls.test_sa_descr_mail_click,
                    cls.activity_begin_mail,
                    1,
                ),
                (
                    "mail_bounce",
                    cls.test_sa_descr_mail_bounce,
                    cls.activity_begin_mail,
                    1,
                ),
                (
                    "sms_not_click",
                    cls.test_sa_descr_sms_not_click,
                    cls.activity_begin_sms,
                    5,
                ),
                ("sms_click", cls.test_sa_descr_sms_click, cls.activity_begin_sms, 1),
                ("sms_bounce", cls.test_sa_descr_sms_bounce, cls.activity_begin_sms, 1),
                (
                    "whatsapp_not_read",
                    cls.test_sa_descr_wa_not_read,
                    cls.activity_begin_wa,
                    5,
                ),
                ("whatsapp_read", cls.test_sa_descr_wa_read, cls.activity_begin_wa, 1),
                (
                    "whatsapp_not_replied",
                    cls.test_sa_descr_wa_not_replied,
                    cls.activity_begin_wa,
                    5,
                ),
                (
                    "whatsapp_replied",
                    cls.test_sa_descr_wa_replied,
                    cls.activity_begin_wa,
                    1,
                ),
                (
                    "whatsapp_not_click",
                    cls.test_sa_descr_wa_not_click,
                    cls.activity_begin_wa,
                    5,
                ),
                (
                    "whatsapp_click",
                    cls.test_sa_descr_wa_click,
                    cls.activity_begin_wa,
                    1,
                ),
                (
                    "whatsapp_bounced",
                    cls.test_sa_descr_wa_bounced,
                    cls.activity_begin_wa,
                    1,
                ),
            )
        )
        cls.activity_mail_activity = cls._create_activity(
            cls.campaign,
            action=cls.test_sa_descr_action,
            parent_id=cls.activity_begin_mail.id,
            interval_number=2,
            interval_type="hour",
            trigger_type="activity",
        )
        cls.activity_sms_activity = cls._create_activity(
            cls.campaign,
            action=cls.test_sa_descr_action,
            parent_id=cls.activity_begin_sms.id,
            interval_number=2,
            interval_type="hour",
            trigger_type="activity",
        )
        cls.activity_wa_activity = cls._create_activity(
            cls.campaign,
            action=cls.test_sa_descr_action,
            parent_id=cls.activity_begin_wa.id,
            interval_number=2,
            interval_type="hour",
            trigger_type="activity",
        )

    def test_assert_initial_values(self):
        self.assertEqual(len(self.test_records), 10)
        self.assertEqual(len(self.test_customers), 6)

        self._launch_campaign(self.campaign, date_reference=self.date_reference)
        for activity in (
            self.activity_begin_mail
            + self.activity_begin_sms
            + self.activity_begin_wa
            + self.activity_begin_sa
        ):
            self.assertMarketAutoTraces(
                [
                    {
                        "records": self.test_records,
                        "status": "scheduled",
                        "fields_values": {
                            "schedule_date": self.date_reference + timedelta(hours=1),
                        },
                    }
                ],
                activity,
            )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    @users("user_marketing_automation")
    def test_reaction_triggers(self):
        campaign = self.campaign.with_env(self.env)
        test_records = self.test_records.with_env(self.env)
        test_records_ok = self.test_records_ok.with_env(self.env)
        test_records_ko = self.test_records_ko.with_env(self.env)

        self._launch_campaign(campaign, date_reference=self.date_reference)
        self.assertActivityWoTrace(
            self.activity_sa_mail_open
            + self.activity_sa_mail_not_open
            + self.activity_sa_mail_reply
            + self.activity_sa_mail_not_reply
            + self.activity_sa_mail_click
            + self.activity_sa_mail_not_click
            + self.activity_sa_mail_bounce
            + self.activity_sa_sms_not_click
            + self.activity_sa_sms_click
            + self.activity_sa_sms_bounce
            + self.activity_sa_wa_not_read
            + self.activity_sa_wa_read
            + self.activity_sa_wa_not_replied
            + self.activity_sa_wa_replied
            + self.activity_sa_wa_not_click
            + self.activity_sa_wa_click
            + self.activity_sa_wa_bounced
            + self.activity_mail_activity
            + self.activity_sms_activity
            + self.activity_wa_activity
        )

        date_send = self.date_reference + timedelta(hours=1)
        date_opened = date_send + timedelta(hours=2)
        date_not_action = date_send + timedelta(
            days=5
        )
        with (
            self.mock_datetime_and_now(date_send),
            self.mockWhatsappGateway(),
            self.patchWhatsappCronTrigger(),
            self.mock_mail_gateway(),
            self.mockSMSGateway(),
        ):
            campaign.execute_activities()

        self.assertMarketAutoTraces(
            [
                {
                    "records": test_records_ok,
                    "records_to_partner": {
                        r.id: r.customer_id for r in test_records_ok
                    },
                    "status": "processed",
                    "fields_values": {
                        "schedule_date": self.date_reference + timedelta(hours=1),
                    },
                    "trace_status": "sent",
                },
                {
                    "records": test_records_ko,
                    "status": "canceled",
                    "fields_values": {
                        "schedule_date": self.date_reference + timedelta(hours=1),
                        "state_msg": "Email cancelled",
                    },
                    "trace_failure_type": "mail_email_missing",
                    "trace_status": "cancel",
                },
            ],
            self.activity_begin_mail,
        )
        self.assertMarketAutoTraces(
            [
                {
                    "records": test_records_ok,
                    "status": "processed",
                    "fields_values": {
                        "schedule_date": self.date_reference + timedelta(hours=1),
                    },
                    "trace_status": "outgoing",
                }
            ]
            + [
                {
                    "records": record,
                    "status": "canceled",
                    "fields_values": {
                        "schedule_date": self.date_reference + timedelta(hours=1),
                        "state_msg": "SMS cancelled",
                    },
                    "trace_content": f"Test SMS for {record.name} click on",
                    "trace_failure_type": "sms_number_missing",
                    "trace_status": "cancel",
                }
                for record in test_records_ko
            ],
            self.activity_begin_sms,
        )
        self.assertMarketAutoTraces(
            [
                {
                    "records": test_records_ok,
                    "status": "processed",
                    "fields_values": {
                        "schedule_date": self.date_reference + timedelta(hours=1),
                    },
                    "trace_content": "<p>Hello your much wow template value</p>",
                    "trace_status": "sent",
                }
            ]
            + [
                {
                    "records": record,
                    "status": "error",
                    "fields_values": {
                        "schedule_date": self.date_reference + timedelta(hours=1),
                        "state_msg": "WhatsApp failed",
                    },
                    "trace_content": "<p>Hello your much wow template value</p>",
                    "trace_failure_type": "phone_invalid",
                    "trace_status": "error",
                }
                for record in test_records_ko
            ],
            self.activity_begin_wa,
        )
        self.assertMarketAutoTraces(
            [
                {
                    "records": test_records,
                    "status": "processed",
                    "fields_values": {
                        "schedule_date": self.date_reference + timedelta(hours=1),
                    },
                }
            ],
            self.activity_begin_sa,
        )

        for sub_activity, schedule_date in [
            (self.activity_sa_mail_open, False),
            (self.activity_sa_mail_not_open, date_not_action),
            (self.activity_sa_mail_reply, False),
            (self.activity_sa_mail_not_reply, date_not_action),
            (self.activity_sa_mail_click, False),
            (self.activity_sa_mail_not_click, date_not_action),
            (
                self.activity_sa_mail_bounce,
                False,
            ),
            (self.activity_sa_sms_click, False),
            (self.activity_sa_sms_not_click, date_not_action),
            (self.activity_sa_sms_bounce, False),
            (self.activity_sa_wa_read, False),
            (self.activity_sa_wa_not_read, date_not_action),
            (self.activity_sa_wa_replied, False),
            (self.activity_sa_wa_not_replied, date_not_action),
            (self.activity_sa_wa_click, False),
            (self.activity_sa_wa_not_click, date_not_action),
            (self.activity_sa_wa_bounced, False),
            (self.activity_mail_activity, date_send + timedelta(hours=2)),
            (self.activity_sms_activity, date_send + timedelta(hours=2)),
            (self.activity_wa_activity, date_send + timedelta(hours=2)),
        ]:
            self.assertMarketAutoTraces(
                [
                    {
                        "records": test_records,
                        "status": "scheduled",
                        "fields_values": {
                            "schedule_date": schedule_date,
                        },
                    }
                ],
                sub_activity,
            )

        for action, action_sa, opposite_sa in (
            ("mail_open", self.activity_sa_mail_open, self.activity_sa_mail_not_open),
            (
                "mail_reply",
                self.activity_sa_mail_reply,
                self.activity_sa_mail_not_reply,
            ),
            (
                "mail_click",
                self.activity_sa_mail_click,
                self.activity_sa_mail_not_click,
            ),
            ("sms_click", self.activity_sa_sms_click, self.activity_sa_sms_not_click),
            ("whatsapp_read", self.activity_sa_wa_read, self.activity_sa_wa_not_read),
            (
                "whatsapp_replied",
                self.activity_sa_wa_replied,
                self.activity_sa_wa_not_replied,
            ),
            (
                "whatsapp_click",
                self.activity_sa_wa_click,
                self.activity_sa_wa_not_click,
            ),
        ):
            todo = test_records_ok[:5]
            with self.mock_datetime_and_now(date_opened):
                for record in todo:
                    if action == "mail_open":
                        self.gateway_mail_trace_open(
                            self.activity_begin_mail.mass_mailing_id, record
                        )
                        state_msg = "Parent activity mail opened"
                    elif action == "mail_reply":
                        self.gateway_mail_trace_reply(
                            self.activity_begin_mail.mass_mailing_id, record
                        )
                        state_msg = "Parent activity mail replied"
                    elif action == "mail_click":
                        self.gateway_mail_trace_click(
                            self.activity_begin_mail.mass_mailing_id, record, "LINK"
                        )
                        state_msg = "Parent activity mail clicked"
                    elif action == "sms_click":
                        self.gateway_sms_click(
                            self.activity_begin_sms.mass_mailing_id,
                            record,
                            use_sent_sms=False,
                        )
                        state_msg = "Parent activity SMS clicked"
                    elif action == "whatsapp_read":
                        self.whatsapp_msg_read_with_records(record)
                        state_msg = "Parent Whatsapp message got opened"
                    elif action == "whatsapp_replied":
                        self.whatsapp_answer_with_records(record, mock=False)
                        state_msg = "Parent Whatsapp was replied to"
                    elif action == "whatsapp_click":
                        self.whatsapp_msg_click_with_records(record, button_index=0)
                        state_msg = "Parent Whatsapp message was clicked"
            self.assertMarketAutoTraces(
                [
                    {
                        "records": todo,
                        "status": "scheduled",
                        "fields_values": {
                            "schedule_date": date_opened + timedelta(days=1),
                            "state_msg": False,
                        },
                    },
                    {
                        "records": test_records - todo,
                        "status": "scheduled",
                        "fields_values": {
                            "schedule_date": False,
                        },
                    },
                ],
                action_sa,
            )
            self.assertMarketAutoTraces(
                [
                    {
                        "records": todo,
                        "status": "canceled",
                        "fields_values": {
                            "schedule_date": date_opened,
                            "state_msg": state_msg,
                        },
                    },
                    {
                        "records": test_records - todo,
                        "status": "scheduled",
                        "fields_values": {
                            "schedule_date": date_not_action,
                        },
                    },
                ],
                opposite_sa,
            )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    @users("user_marketing_automation")
    def test_reaction_triggers_bounce(self):
        campaign = self.campaign.with_env(self.env)
        test_records = self.test_records.with_env(self.env)
        test_records_ok = self.test_records_ok.with_env(self.env)

        self._launch_campaign(campaign, date_reference=self.date_reference)

        date_send = self.date_reference + timedelta(hours=1)
        date_opened = date_send + timedelta(hours=2)
        with (
            self.mock_datetime_and_now(date_send),
            self.mockWhatsappGateway(),
            self.patchWhatsappCronTrigger(),
            self.mock_mail_gateway(),
            self.mockSMSGateway(),
        ):
            campaign.execute_activities()

        for action, action_sa in (
            ("mail_bounce", self.activity_sa_mail_bounce),
            ("sms_bounce", self.activity_sa_sms_bounce),
            ("whatsapp_bounced", self.activity_sa_wa_bounced),
        ):
            todo = test_records_ok[:5]
            with self.mock_datetime_and_now(date_opened):
                for record in todo:
                    if action == "mail_bounce":
                        self.gateway_mail_trace_bounce(
                            self.activity_begin_mail.mass_mailing_id, record
                        )
                        state_msg = "Parent activity mail bounced"
                    elif action == "sms_bounce":
                        self.gateway_sms_bounce(
                            self.activity_begin_sms.mass_mailing_id, record
                        )
                        state_msg = "Parent activity SMS bounced"
                    elif action == "whatsapp_bounced":
                        self.whatsapp_msg_bounce_with_records(record)
                        state_msg = "Parent whatsapp was bounced"
            self.assertMarketAutoTraces(
                [
                    {
                        "records": todo,
                        "status": "scheduled",
                        "fields_values": {
                            "schedule_date": date_opened + timedelta(days=1),
                            "state_msg": False,
                        },
                    },
                    {
                        "records": test_records - todo,
                        "status": "scheduled",
                        "fields_values": {
                            "schedule_date": False,
                        },
                    },
                ],
                action_sa,
            )
            for brother in action_sa.parent_id.child_ids - action_sa:
                self.assertMarketAutoTraces(
                    [
                        {
                            "records": todo,
                            "status": "canceled",
                            "fields_values": {
                                "schedule_date": date_opened,
                                "state_msg": state_msg,
                            },
                        },
                        {
                            "records": test_records - todo,
                            "status": "scheduled",
                        },
                    ],
                    brother,
                )

    @users("user_marketing_automation")
    def test_reaction_triggers_multiple(self):
        campaign = self.campaign.with_env(self.env)
        test_records = self.test_records.with_env(self.env)
        test_records_ok = self.test_records_ok.with_env(self.env)

        self.test_reaction_triggers()

        date_opened = (
            self.date_reference + timedelta(hours=1) + timedelta(hours=2)
        )
        date_subaction = date_opened + timedelta(days=1)

        with (
            self.mock_datetime_and_now(date_subaction),
            self.mockWhatsappGateway(),
            self.patchWhatsappCronTrigger(),
            self.mock_mail_gateway(),
            self.mockSMSGateway(),
        ):
            campaign.execute_activities()

        todo = test_records_ok[:5]
        for subaction in (
            self.activity_sa_mail_open,
            self.activity_sa_mail_reply,
            self.activity_sa_mail_click,
            self.activity_sa_sms_click,
            self.activity_sa_wa_read,
            self.activity_sa_wa_replied,
            self.activity_sa_wa_click,
            self.activity_sa_wa_click,
        ):
            with self.subTest(subaction_name=subaction.name):
                self.assertMarketAutoTraces(
                    [
                        {
                            "records": todo,
                            "status": "processed",
                            "fields_values": {
                                "schedule_date": date_subaction,
                                "state_msg": False,
                            },
                        },
                        {
                            "records": test_records - todo,
                            "status": "scheduled",
                            "fields_values": {
                                "schedule_date": False,
                            },
                        },
                    ],
                    subaction,
                )

        for action, action_sa, opposite_sa in (
            ("mail_open", self.activity_sa_mail_open, self.activity_sa_mail_not_open),
            (
                "mail_reply",
                self.activity_sa_mail_reply,
                self.activity_sa_mail_not_reply,
            ),
        ):
            todo = test_records_ok[:5]
            with self.subTest(action=action):
                with self.mock_datetime_and_now(date_opened):
                    for record in todo:
                        if action == "mail_open":
                            self.gateway_mail_trace_open(
                                self.activity_begin_mail.mass_mailing_id, record
                            )
                        elif action == "mail_reply":
                            self.gateway_mail_trace_reply(
                                self.activity_begin_mail.mass_mailing_id, record
                            )
                        elif action == "mail_click":
                            self.gateway_mail_trace_click(
                                self.activity_begin_mail.mass_mailing_id, record, "LINK"
                            )
                        elif action == "sms_click":
                            self.gateway_sms_click(
                                self.activity_begin_sms.mass_mailing_id,
                                record,
                                use_sent_sms=False,
                            )
                        elif action == "whatsapp_read":
                            self.whatsapp_msg_read_with_records(record)
                        elif action == "whatsapp_replied":
                            self.whatsapp_answer_with_records(record, mock=False)
                        elif action == "whatsapp_click":
                            self.whatsapp_msg_click_with_records(record, button_index=0)
                self.assertMarketAutoTraces(
                    [
                        {
                            "records": todo,
                            "status": "processed",
                            "fields_values": {
                                "schedule_date": date_subaction,
                            },
                        },
                        {
                            "records": test_records - todo,
                            "status": "scheduled",
                            "fields_values": {
                                "schedule_date": False,
                            },
                        },
                    ],
                    action_sa,
                )
                self.assertMarketAutoTraces(
                    [
                        {
                            "records": todo,
                            "status": "canceled",
                        },
                        {
                            "records": test_records - todo,
                            "status": "scheduled",
                        },
                    ],
                    opposite_sa,
                )

    @users("user_marketing_automation")
    def test_schedule_date_based_on_triggers_new(self):
        self._launch_campaign(self.campaign)
        date_send = self.date_reference + timedelta(hours=1)

        with self.mock_datetime_and_now(date_send), self.mock_mail_gateway():
            self.campaign.execute_activities()

        new_activity = self._create_activity_mail(
            self.campaign,
            self.env.user,
            act_values={
                "interval_number": 1,
                "interval_type": "day",
                "trigger_type": "begin",
            },
        )

        new_test_records = self._create_marketauto_records(
            model="marketing.test.sms", count=1
        )
        self.campaign.write(
            {"domain": [("id", "in", (self.test_records + new_test_records).ids)]}
        )
        with self.mock_datetime_and_now(self.date_reference + timedelta(hours=3)):
            self.campaign.sync_participants()
        self.assertMarketAutoTraces(
            [
                {
                    "records": new_test_records,
                    "status": "scheduled",
                    "fields_values": {
                        "schedule_date": self.date_reference
                        + timedelta(days=1, hours=3),
                    },
                }
            ],
            new_activity,
        )
        for activity in (
            self.activity_begin_mail
            + self.activity_begin_sms
            + self.activity_begin_wa
            + self.activity_begin_sa
        ):
            self.assertMarketAutoTraces(
                [
                    {
                        "records": new_test_records,
                        "status": "scheduled",
                        "fields_values": {
                            "schedule_date": self.date_reference
                            + timedelta(hours=4),
                        },
                    }
                ],
                activity,
                strict=False,
            )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    @users("user_marketing_automation")
    def test_schedule_date_based_on_triggers_update(self):
        self._launch_campaign(self.campaign, date_reference=self.date_reference)
        date_send = self.date_reference + timedelta(hours=1)
        date_subaction = date_send + timedelta(days=5)

        with self.mock_datetime_and_now(date_send), self.mock_mail_gateway():
            self.campaign.execute_activities()

        with self.mock_datetime_and_now(self.date_reference + timedelta(hours=2)):
            (
                self.activity_begin_mail
                + self.activity_begin_sms
                + self.activity_begin_wa
                + self.activity_begin_sa
            ).write(
                {
                    "interval_number": 2,
                    "interval_type": "day",
                }
            )
            self.campaign.action_update_participants()

        for sub_activity, expected_schedule_date in [
            (self.activity_sa_mail_not_open, date_subaction),
            (self.activity_sa_mail_open, False),
            (self.activity_sa_mail_not_reply, date_subaction),
            (self.activity_sa_mail_reply, False),
            (self.activity_sa_mail_not_click, date_subaction),
            (self.activity_sa_mail_click, False),
            (
                self.activity_sa_mail_bounce,
                False,
            ),
            (self.activity_sa_sms_not_click, date_subaction),
            (self.activity_sa_sms_click, False),
            (self.activity_sa_sms_bounce, False),
            (self.activity_sa_wa_not_read, date_subaction),
            (self.activity_sa_wa_read, False),
            (self.activity_sa_wa_not_replied, date_subaction),
            (self.activity_sa_wa_replied, False),
            (self.activity_sa_wa_not_click, date_subaction),
            (self.activity_sa_wa_click, False),
            (self.activity_sa_wa_bounced, False),
            (self.activity_mail_activity, date_send + timedelta(hours=2)),
            (self.activity_sms_activity, date_send + timedelta(hours=2)),
            (self.activity_wa_activity, date_send + timedelta(hours=2)),
        ]:
            self.assertMarketAutoTraces(
                [
                    {
                        "records": self.test_records,
                        "status": "scheduled",
                        "fields_values": {
                            "schedule_date": expected_schedule_date,
                        },
                    }
                ],
                sub_activity,
            )

        with self.mock_datetime_and_now(self.date_reference + timedelta(hours=3)):
            (
                self.activity_sa_mail_not_open
                + self.activity_sa_mail_open
                + self.activity_sa_mail_not_reply
                + self.activity_sa_mail_reply
                + self.activity_sa_mail_not_click
                + self.activity_sa_mail_click
                + self.activity_sa_mail_bounce
                +
                self.activity_sa_sms_not_click
                + self.activity_sa_sms_click
                + self.activity_sa_sms_bounce
                +
                self.activity_sa_wa_not_read
                + self.activity_sa_wa_read
                + self.activity_sa_wa_not_replied
                + self.activity_sa_wa_replied
                + self.activity_sa_wa_not_click
                + self.activity_sa_wa_click
                + self.activity_sa_wa_bounced
                +
                self.activity_mail_activity
                + self.activity_sms_activity
                + self.activity_wa_activity
            ).write(
                {
                    "interval_number": 2,
                    "interval_type": "day",
                }
            )
            self.campaign.action_update_participants()
        date_subaction = date_send + timedelta(days=2)

        for sub_activity, expected_schedule_date in [
            (self.activity_sa_mail_not_open, date_subaction),
            (self.activity_sa_mail_open, False),
            (self.activity_sa_mail_not_reply, date_subaction),
            (self.activity_sa_mail_reply, False),
            (self.activity_sa_mail_not_click, date_subaction),
            (self.activity_sa_mail_click, False),
            (
                self.activity_sa_mail_bounce,
                False,
            ),
            (self.activity_sa_sms_not_click, date_subaction),
            (self.activity_sa_sms_click, False),
            (self.activity_sa_sms_bounce, False),
            (self.activity_sa_wa_not_read, date_subaction),
            (self.activity_sa_wa_not_replied, date_subaction),
            (self.activity_sa_wa_not_click, date_subaction),
            (self.activity_sa_wa_click, False),
            (self.activity_sa_wa_bounced, False),
            (self.activity_mail_activity, date_subaction),
            (self.activity_sms_activity, date_subaction),
            (self.activity_wa_activity, date_subaction),
        ]:
            self.assertMarketAutoTraces(
                [
                    {
                        "records": self.test_records,
                        "status": "scheduled",
                        "fields_values": {
                            "schedule_date": expected_schedule_date,
                        },
                    }
                ],
                sub_activity,
            )

        new_now = self.date_reference + timedelta(hours=5)
        date_subaction_new = new_now + timedelta(days=2)
        with self.mock_datetime_and_now(new_now):
            self.gateway_mail_trace_open(
                self.activity_begin_mail.mass_mailing_id, self.test_records[0]
            )
            self.gateway_mail_trace_reply(
                self.activity_begin_mail.mass_mailing_id, self.test_records[1]
            )
            self.gateway_mail_trace_click(
                self.activity_begin_mail.mass_mailing_id, self.test_records[2], "LINK"
            )

        for record, sub_activity, exp_status, exp_schedule_date in [
            (self.test_records[0], self.activity_sa_mail_not_open, "canceled", new_now),
            (
                self.test_records[0],
                self.activity_sa_mail_open,
                "scheduled",
                date_subaction_new,
            ),
        ]:
            self.assertMarketAutoTraces(
                [
                    {
                        "records": record,
                        "status": exp_status,
                        "fields_values": {
                            "schedule_date": exp_schedule_date,
                        },
                    }
                ],
                sub_activity,
                strict=False,
            )

        with self.mock_datetime_and_now(self.date_reference + timedelta(hours=3)):
            (
                self.activity_sa_mail_not_open
                + self.activity_sa_mail_open
                + self.activity_sa_mail_not_reply
                + self.activity_sa_mail_reply
                + self.activity_sa_mail_not_click
                + self.activity_sa_mail_click
                + self.activity_sa_mail_bounce
                +
                self.activity_sa_sms_not_click
                + self.activity_sa_sms_click
                + self.activity_sa_sms_bounce
                +
                self.activity_sa_wa_not_read
                + self.activity_sa_wa_read
                + self.activity_sa_wa_not_replied
                + self.activity_sa_wa_replied
                + self.activity_sa_wa_not_click
                + self.activity_sa_wa_click
                + self.activity_sa_wa_bounced
            ).write(
                {
                    "interval_number": 5,
                    "interval_type": "day",
                }
            )
            self.campaign.action_update_participants()
        date_subaction_upd = new_now + timedelta(days=5)

        for record, sub_activity, exp_status, exp_schedule_date in [
            (
                self.test_records[0],
                self.activity_sa_mail_open,
                "scheduled",
                date_subaction_upd,
            ),
        ]:
            self.assertMarketAutoTraces(
                [
                    {
                        "records": record,
                        "status": exp_status,
                        "fields_values": {
                            "schedule_date": exp_schedule_date,
                        },
                    }
                ],
                sub_activity,
                strict=False,
            )
