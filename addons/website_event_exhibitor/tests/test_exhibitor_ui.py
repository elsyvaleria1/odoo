from odoo.tests import HttpCase, tagged

from odoo.addons.website_event_exhibitor.tests.common import TestEventExhibitorCommon


@tagged("post_install", "-at_install")
class TestExhibitorUi(TestEventExhibitorCommon, HttpCase):
    def test_exhibitors_filter_in_place(self):
        self.event_0.write({"exhibitor_menu": True, "is_published": True})
        self.env["event.sponsor"].create(
            [
                {
                    "name": name,
                    "partner_id": self.env["res.partner"]
                    .create({"name": name, "country_id": self.env.ref(country).id})
                    .id,
                    "event_id": self.event_0.id,
                    "sponsor_type_id": self.sponsor_type_0.id,
                    "exhibitor_type": "exhibitor",
                    "is_published": True,
                }
                for name, country in [
                    ("PN Brussels", "base.be"),
                    ("PN Paris", "base.fr"),
                ]
            ]
        )
        self.start_tour(
            f"{self.event_0.website_url}/exhibitors", "exhibitors_partial_navigation"
        )
