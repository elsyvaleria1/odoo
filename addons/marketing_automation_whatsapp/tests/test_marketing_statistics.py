from datetime import timedelta

from odoo import Command
from odoo.fields import Datetime
from odoo.tests import tagged, users

from odoo.addons.marketing_automation.tests.common import MarketingAutomationCommon
from odoo.addons.whatsapp.tests.common import WhatsAppCommon


@tagged("marketing_automation")
class TestWhatsAppStatistics(MarketingAutomationCommon, WhatsAppCommon):
    """Test that WhatsApp statistics are correctly aggregated with email statistics."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.date_reference = Datetime.from_string("2024-11-08 09:00:00")

        cls.participants = cls.env["marketing.participant"].create(
            [
                {
                    "campaign_id": cls.campaign.id,
                    "res_id": record.id,
                    "state": "running",
                }
                for record in cls.test_contacts[:8]
            ]
        )

        cls.activity_email = cls._create_activity_mail(
            cls.campaign,
            user=cls.user_marketing_automation,
        )

        cls.whatsapp_template = cls.env["whatsapp.template"].create(
            {
                "body": "Hello World!",
                "name": "Test-Message",
                "status": "approved",
                "wa_account_id": cls.whatsapp_account.id,
            }
        )

        cls.activity_whatsapp = cls.env["marketing.activity"].create(
            {
                "name": "Test WhatsApp Activity",
                "activity_type": "whatsapp",
                "whatsapp_template_id": cls.whatsapp_template.id,
                "campaign_id": cls.campaign.id,
                "model_id": cls.env["ir.model"]._get_id("res.partner"),
                "parent_id": cls.activity_email.id,
                "trigger_type": "activity",
                "interval_number": 1,
                "interval_type": "hour",
            }
        )

    def _setup_email_traces(self, trace_configs, participants, activity):
        mailing_traces = self.env["mailing.trace"].create(
            [
                {
                    "model": self.campaign.model_name,
                    "res_id": participant.res_id,
                    "sent_datetime": self.date_reference
                    if marketing_trace_state == "processed"
                    else False,
                    "trace_status": status,
                    "links_click_datetime": self.date_reference + timedelta(hours=1)
                    if has_click
                    else False,
                    "trace_type": "mail",
                }
                for (marketing_trace_state, status, has_click), participant in zip(
                    trace_configs, participants, strict=False
                )
            ]
        )

        self.env["marketing.trace"].create(
            [
                {
                    "activity_id": activity.id,
                    "participant_id": participant.id,
                    "state": state,
                    "mailing_trace_ids": [Command.set(mailing_trace.ids)],
                }
                for (state, _, _), mailing_trace, participant in zip(
                    trace_configs, mailing_traces, participants, strict=False
                )
            ]
        )

    def _setup_whatsapp_traces(self, trace_configs, participants, activity):
        whatsapp_messages = self.env["whatsapp.message"].create(
            [
                {
                    "state": message_state,
                    "links_click_datetime": self.date_reference + timedelta(hours=1)
                    if has_click
                    else False,
                }
                for _, message_state, has_click in trace_configs
            ]
        )

        self.env["marketing.trace"].create(
            [
                {
                    "activity_id": activity.id,
                    "participant_id": participant.id,
                    "state": marketing_trace_state,
                    "whatsapp_message_id": whatsapp_message.id,
                }
                for (marketing_trace_state, _, _), whatsapp_message, participant in zip(
                    trace_configs, whatsapp_messages, participants, strict=False
                )
            ]
        )

    @users("user_marketing_automation")
    def test_statistics_aggregation(self):

        self._setup_email_traces(
            [
                ("processed", "sent", False),
                ("processed", "open", False),
                ("processed", "reply", True),
                ("processed", "bounce", True),
                ("rejected", "bounce", False),
                ("rejected", "bounce", False),
            ],
            self.participants,
            self.activity_email,
        )

        self._setup_whatsapp_traces(
            [
                ("processed", "sent", False),
                ("processed", "delivered", False),
                ("processed", "read", True),
                ("processed", "replied", True),
                ("processed", "error", False),
                ("rejected", "error", False),
            ],
            self.participants,
            self.activity_whatsapp,
        )

        self.assertRecordValues(
            self.activity_email,
            [
                {
                    "processed": 4,
                    "rejected": 2,
                    "total_bounce": 3,
                    "total_click": 2,
                    "total_open": 2,
                    "total_reply": 1,
                    "total_sent": 4,
                }
            ],
        )

        self.assertRecordValues(
            self.activity_whatsapp,
            [
                {
                    "processed": 0,
                    "rejected": 2,
                    "total_click": 2,
                    "total_open": 2,
                    "total_reply": 1,
                    "total_sent": 4,
                }
            ],
        )
