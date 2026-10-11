from lxml import etree

from odoo.tests import tagged, users

from odoo.addons.mass_mailing.tests.common import MassMailCommon


@tagged("mass_mailing", "post_install", "-at_install")
class TestMailingTemplate(MassMailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mailing = cls.env["mailing.mailing"].create(
            {"subject": "Spring design", "body_arch": "<p>Spring</p>"}
        )

    def _arch_nodes(self, view_type, xpath):
        views = self.env["mailing.mailing"].get_views([(False, view_type)])
        return etree.fromstring(views["views"][view_type]["arch"]).xpath(xpath)

    @users("user_marketing")
    def test_a_design_saved_as_template_is_offered_to_every_marketer(self):
        mailing = self.mailing.with_env(self.env)

        mailing.action_add_to_templates()

        self.assertTrue(mailing.is_template)
        self.assertTrue(mailing.date_template)
        offered = (
            self.env["mailing.mailing"]
            .with_user(self.user_marketing_1)
            .action_fetch_templates()
        )
        self.assertIn(mailing.id, [values["id"] for values in offered])
        self.assertFalse(mailing.with_user(self.user_marketing_1).is_user_favorite)

        mailing.action_remove_from_templates()

        self.assertFalse(mailing.is_template)
        self.assertFalse(mailing.date_template)
        self.assertNotIn(
            mailing.id,
            [
                values["id"]
                for values in self.env["mailing.mailing"].action_fetch_templates()
            ],
        )

    def test_the_star_stars_for_oneself(self):
        for view_type in ("list", "kanban"):
            with self.subTest(view_type=view_type):
                stars = self._arch_nodes(
                    view_type, "//field[@widget='boolean_favorite']/@name"
                )
                self.assertEqual(stars, ["is_user_favorite"])

    def test_the_search_offers_templates_and_my_favorites(self):
        filters = {
            node.get("name"): node.get("domain")
            for node in self._arch_nodes("search", "//filter")
        }

        self.assertEqual(filters.get("filter_template"), "[('is_template', '=', True)]")
        self.assertEqual(
            filters.get("filter_my_favorite"), "[('is_user_favorite', '=', True)]"
        )

    def test_template_and_favorite_read_differently(self):
        labels = self.env["mailing.mailing"].fields_get(
            ["is_template", "is_user_favorite"], ["string"]
        )

        self.assertEqual(labels["is_template"]["string"], "Saved as Template")
        self.assertEqual(labels["is_user_favorite"]["string"], "My Favorite")
