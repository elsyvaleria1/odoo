from unittest.mock import patch

from odoo.tests import tagged, users

from odoo.addons.marketing_automation_whatsapp.tests.test_marketing_statistics import (
    TestWhatsAppStatistics,
)
from odoo.addons.whatsapp.tests.common import MockIncomingWhatsApp


@tagged("marketing_automation")
class TestWATraceProcess(TestWhatsAppStatistics, MockIncomingWhatsApp):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.shared_message = cls.env["whatsapp.message"].create(
            {
                "state": "sent",
                "msg_uid": "wamid.test.shared.message.001",
                "mobile_number": "+5511999999999",
            }
        )

        cls.traces = cls.env["marketing.trace"].create(
            [
                {
                    "activity_id": cls.activity_whatsapp.id,
                    "participant_id": participant.id,
                    "state": "scheduled",
                    "whatsapp_message_id": cls.shared_message.id,
                }
                for participant in cls.participants[:3]
            ]
        )

    @users("user_marketing_automation")
    def test_process_whatsapp_message_with_multiple_traces(self):
        """Testing the processing of a WhatsApp message linked to multiple traces."""
        self._receive_message_update(
            account=self.whatsapp_account,
            display_phone_number="1234567890",
            extra_value={
                "statuses": [
                    {
                        "conversation": {
                            "id": "53182df2384a3454ced08a1ba8a24a7c268",
                            "origin": {"type": "marketing"},
                        },
                        "id": self.shared_message.msg_uid,
                        "recipient_id": str(self.participants[0].id),
                        "status": "delivered",
                        "timestamp": "1753586596",
                    }
                ]
            },
        )
        self.assertEqual(self.shared_message.state, "delivered")

    @users("user_marketing_automation")
    def test_bounce_status_for_message_with_multiple_traces(self):
        """Test processing of a WhatsApp message bounce across multiple traces."""
        self._new_wa_msg = self.shared_message
        self.shared_message.mail_message_id = self.env["mail.message"].create(
            {"model": "marketing.trace", "res_id": self.traces[0].id}
        )
        self.whatsapp_msg_bounce_with_records(records=self.traces[0])
        self.assertEqual(self.shared_message.state, "bounced")
        for trace in self.traces:
            self.assertEqual(trace.state, "canceled")
            self.assertEqual(trace.state_msg, "WhatsApp canceled")


@tagged("marketing_automation")
class TestWATraceLinking(TestWhatsAppStatistics):
    def test_sending_links_only_the_traces_it_sends_for(self):
        record = self.test_contacts[0]
        earlier = self.env["whatsapp.message"].create(
            {"state": "sent", "mobile_number": "+32455000001"}
        )
        earlier_trace = self.env["marketing.trace"].create(
            {
                "activity_id": self.activity_whatsapp.id,
                "participant_id": self.participants[0].id,
                "state": "processed",
                "whatsapp_message_id": earlier.id,
            }
        )
        rerun = self.env["marketing.participant"].create(
            {"campaign_id": self.campaign.id, "res_id": record.id, "is_test": True}
        )
        due_trace = self.env["marketing.trace"].create(
            {
                "activity_id": self.activity_whatsapp.id,
                "participant_id": rerun.id,
                "state": "scheduled",
            }
        )
        fresh = self.env["whatsapp.message"].create(
            {
                "state": "outgoing",
                "mobile_number": "+32455000001",
                "mail_message_id": self.env["mail.message"]
                .create({"model": record._name, "res_id": record.id})
                .id,
            }
        )
        Composer = type(self.env["wizard.whatsapp.message.send"])
        with (
            patch.object(Composer, "create", lambda self, vals: self.browse()),
            patch.object(
                Composer, "_create_whatsapp_messages", lambda self, **kw: fresh
            ),
            patch.object(type(fresh), "_send", lambda self, **kw: None),
        ):
            self.activity_whatsapp._execute_whatsapp(due_trace)

        self.assertEqual(due_trace.whatsapp_message_id, fresh)
        self.assertEqual(earlier_trace.whatsapp_message_id, earlier)
