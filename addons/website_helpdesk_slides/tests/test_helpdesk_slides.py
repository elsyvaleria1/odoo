from odoo.tests import HttpCase, tagged

from odoo.addons.helpdesk.tests.common import HelpdeskCommon


@tagged("-at_install", "post_install")
class TestHelpdeskSlides(HttpCase, HelpdeskCommon):
    def test_top_channels(self):
        slide_channels = self.env["slide.channel"].create(
            [
                {
                    "name": f"This is channel number {channel_record}",
                    "website_published": True,
                }
                for channel_record in range(1, 8)
            ]
        )

        slide_partners = self.env["res.partner"].create(
            [
                {
                    "name": f"Theodore the {index}'th",
                }
                for index in range(28)
            ]
        )

        slides = self.env["slide.slide"].create(
            [
                {
                    "name": f"Slide for channel number {slide_record + 1}",
                    "channel_id": slide_channels[slide_record].id,
                    "is_published": True,
                }
                for slide_record in range(7)
            ]
        )

        partner_ids = slide_partners.ids
        self.env["slide.slide.partner"].create(
            [
                {
                    "slide_id": slide_value.id,
                    "partner_id": partner_ids.pop(),
                }
                for index, slide_value in enumerate(slides)
                for _ in range(index + 1)
            ]
        )

        self.test_team.website_slide_channel_ids = slide_channels.ids

        self.test_team.invalidate_recordset(["website_top_channels"])

        self.assertEqual(
            self.test_team.website_top_channels,
            slide_channels[6:1:-1],
            "The top channels should be the ones with the most views, in this case the last 5 from last to first",
        )
