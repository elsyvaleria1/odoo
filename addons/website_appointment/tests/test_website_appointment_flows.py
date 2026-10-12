from unittest.mock import patch

from odoo import Command
from odoo.tests.common import HttpCase, tagged

from odoo.addons.website.models.website_snippet_filter import (
    WebsiteSnippetFilter as WebsiteSnippetFilterBase,
)


@tagged("post_install", "-at_install")
class TestWebsiteAppointmentFlows(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.appointment_type = cls.env["appointment.type"].create(
            {
                "appointment_tz": "UTC",
                "is_auto_assign": True,
                "min_schedule_hours": 1.0,
                "max_schedule_days": 8,
                "min_cancellation_hours": 2,
                "name": "yoga session",
                "manage_capacity": True,
                "schedule_based_on": "resources",
                "is_published": True,
            }
        )

    def test_search_appointments_autocomplete(self):
        response = self.call_jsonrpc(
            "/website/snippet/autocomplete",
            {
                "search_type": "appointments",
                "term": "yoga",
                "max_nb_chars": 100,
                "options": {"displayDescription": True},
            },
        )
        self.assertGreaterEqual(response["results_count"], 1)
        urls = [result["website_url"] for result in response["results"]]
        self.assertIn("/appointment/%s" % self.appointment_type.id, urls)

    def test_autocomplete_serves_the_window_at_the_offset(self):
        self.env["appointment.type"].create(
            [{"name": f"zqw pager {index}", "is_published": True} for index in range(7)]
        )

        def names(**params):
            result = self.call_jsonrpc(
                "/website/snippet/autocomplete",
                {
                    "search_type": "appointments",
                    "term": "zqw pager",
                    "order": "name asc",
                    **params,
                },
            )
            return [row["name"] for row in result["results"]]

        everything = names(limit=10)
        self.assertEqual(len(everything), 7)
        self.assertEqual(names(limit=3, offset=3), everything[3:6])

    def test_website_url_and_backend_menu(self):
        self.assertEqual(
            self.appointment_type.website_url,
            "/appointment/%s" % self.appointment_type.id,
        )
        draft = self.env["appointment.type"].new({"name": "unsaved"})
        self.assertFalse(draft.website_url)
        self.assertEqual(
            self.appointment_type.get_backend_menu_id(),
            self.env.ref("calendar.mail_menu_calendar").id,
        )

    def test_action_share_invite_carries_website(self):
        action = self.appointment_type.action_share_invite()
        self.assertIn("default_website_id", action["context"])

    def test_invite_cross_website_warning(self):
        website_1 = self.env["website"].search([], limit=1)
        website_2 = self.env["website"].create({"name": "Second Website"})
        self.appointment_type.website_id = website_2

        invite = self.env["appointment.invite"].create(
            {
                "appointment_type_ids": [Command.set(self.appointment_type.ids)],
                "website_id": website_1.id,
            }
        )
        self.assertIn("yoga session", invite.appointment_type_warning_msg)
        self.assertTrue(invite.disable_save_button)

        invite.website_id = website_2
        self.assertFalse(invite.appointment_type_warning_msg)

    def test_cta_data(self):
        website = self.env["website"].get_current_website()
        cta_data = website.prepare_configurator_cta_data("schedule_appointments", "any")
        self.assertEqual(cta_data["cta_btn_href"], "/appointment")

    def test_snippet_filter_hardcoded_sample(self):
        snippet_filter = self.env["website.snippet.filter"]
        sample = snippet_filter._get_hardcoded_sample(self.env["appointment.type"])
        self.assertEqual(len(sample), 3)
        self.assertTrue(all(item.get("name") for item in sample))
        self.assertIn("message_intro", sample[0])

        with patch.object(
            WebsiteSnippetFilterBase,
            "_get_hardcoded_sample",
            return_value=[{"name": "delegated"}],
        ):
            other = snippet_filter._get_hardcoded_sample(self.env["res.partner"])
        self.assertEqual(other, [{"name": "delegated"}])
