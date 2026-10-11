from odoo import Command
from odoo.tests import tagged

from odoo.addons.marketing_automation.tests.common import MarketingAutomationCase
from odoo.addons.marketing_automation_whatsapp.tests.common import (
    MarketingAutomationWACase,
)
from odoo.addons.whatsapp.tests.common import MockIncomingWhatsApp, WhatsAppCommon


class WaMaCase(
    WhatsAppCommon,
    MockIncomingWhatsApp,
    MarketingAutomationCase,
    MarketingAutomationWACase,
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.maxDiff = None

        cls.setUpWhatsapp()
        cls.phone = "+32499123456"
        cls.whatsapp_test_customer = cls.env["res.partner"].create(
            {
                "name": "TestWAPartner",
                "phone_ids": [
                    Command.create({"number": cls.phone, "type": "landline"})
                ],
            }
        )

        cls.campaign = cls.env["marketing.campaign"].create(
            {
                "domain": [("id", "in", cls.whatsapp_test_customer.ids)],
                "model_id": cls.env["ir.model"]._get_id("res.partner"),
                "name": "Test Campaign",
            }
        )
        cls.test_wa_template = cls._create_wa_template(
            "res.partner",
            body="Hello {{1}}",
            name="Test-dynamic",
            phone_field="phone_ids",
            variable_ids=[
                (
                    0,
                    0,
                    {
                        "name": "{{1}}",
                        "line_type": "body",
                        "field_type": "free_text",
                        "demo_value": cls.wa_tracked_body_url,
                    },
                )
            ],
        )
        cls.activity = cls._create_activity(
            cls.campaign, wa_template=cls.test_wa_template
        )
        cls.link_base_url = cls.env["link.tracker"].get_base_url()


@tagged("link_tracker")
class TestMarketingAutomation(WaMaCase):
    def test_detect_responses(self):
        self.campaign.sync_participants()

        with self.mockWhatsappGateway():
            self.campaign.execute_activities()

        traces = self.env["marketing.trace"].search(
            [
                ("activity_id", "in", self.activity.ids),
            ]
        )
        with self.mockWhatsappGateway():
            self._receive_whatsapp_message(
                self.whatsapp_account,
                "Hello, it's reply",
                self.phone,
            )
        self.assertEqual(traces.whatsapp_message_id.state, "replied")


@tagged("link_tracker")
class TestLinkTracker(WaMaCase):
    def test_tracked_button(self):
        self.campaign.sync_participants()

        with self.mockWhatsappGateway():
            self.campaign.execute_activities()

        trace = self.env["marketing.trace"].search(
            [
                ("activity_id", "in", self.activity.ids),
                ("res_id", "=", self.whatsapp_test_customer.id),
            ]
        )
        self.assertEqual(len(trace), 1)

        sent_wa_msg = self._wa_msg_sent_vals[0]
        btn_1 = next(
            c
            for c in sent_wa_msg["components"]
            if c["type"] == "button" and c["index"] == 0
        )
        btn_2 = next(
            c
            for c in sent_wa_msg["components"]
            if c["type"] == "button" and c["index"] == 1
        )
        body = next(c for c in sent_wa_msg["components"] if c["type"] == "body")
        link_btn_1 = btn_1["parameters"][0]["text"]
        link_btn_2 = btn_2["parameters"][0]["text"]
        link_body = body["parameters"][0]["text"]

        btn_link_tracker = self.env["link.tracker"].search(
            [("url", "=", self.wa_tracked_btn_url)]
        )
        self.assertEqual(len(btn_link_tracker), 1)
        body_link_tracker = self.env["link.tracker"].search(
            [("url", "=", self.wa_tracked_body_url)]
        )
        self.assertEqual(len(body_link_tracker), 1)

        self.assertEqual(
            link_btn_1, f"r/{btn_link_tracker.code}/w/{trace.whatsapp_message_id.id}"
        )
        self.assertEqual(
            link_body,
            f"{self.link_base_url}/r/{body_link_tracker.code}/w/{trace.whatsapp_message_id.id}",
        )
        self.assertEqual(link_btn_2, "???")

    def test_wa_template_button_component_tracking(self):
        button_component = self.test_wa_template._acquire_template_button_component()
        self.assertDictEqual(
            button_component,
            {
                "type": "BUTTONS",
                "buttons": [
                    {
                        "type": "URL",
                        "text": "url_tracked",
                        "url": self.link_base_url + "/{{1}}",
                        "example": self.link_base_url + "/???",
                    },
                    {
                        "type": "URL",
                        "text": "url_dynamic",
                        "url": self.wa_dynamic_btn_url + "{{1}}",
                        "example": self.wa_dynamic_btn_url + "???",
                    },
                ],
            },
        )
