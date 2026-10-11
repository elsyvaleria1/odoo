from lxml import etree

from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestFrontdeskFavorite(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.alice = new_test_user(
            cls.env,
            login="frontdesk_fav_alice",
            groups="frontdesk.frontdesk_group_user",
        )
        cls.plain, cls.featured, cls.starred = cls.env["frontdesk.frontdesk"].create(
            [
                {"name": name, "responsible_ids": cls.alice.ids}
                for name in ("plain", "featured", "starred")
            ]
        )
        cls.featured.is_featured = True
        cls.starred.with_user(cls.alice).is_user_favorite = True

    def _arch_nodes(self, view_type, xpath):
        views = self.env["frontdesk.frontdesk"].get_views([(False, view_type)])
        return etree.fromstring(views["views"][view_type]["arch"]).xpath(xpath)

    def test_featured_comes_first_then_the_users_favorites(self):
        stations = (
            self.env["frontdesk.frontdesk"]
            .with_user(self.alice)
            .search([("id", "in", (self.plain | self.featured | self.starred).ids)])
        )

        self.assertEqual(stations[:2].ids, (self.featured | self.starred).ids)

    def test_the_kanban_star_stars_for_oneself(self):
        stars = self._arch_nodes("kanban", "//field[@widget='boolean_favorite']/@name")

        self.assertEqual(stars, ["is_user_favorite"])

    def test_the_search_offers_featured_and_my_favorites(self):
        filters = {
            node.get("name"): node.get("domain")
            for node in self._arch_nodes("search", "//filter")
        }

        self.assertEqual(filters.get("featured"), "[('is_featured', '=', True)]")
        self.assertEqual(
            filters.get("my_favorites"), "[('is_user_favorite', '=', True)]"
        )

    def test_featured_and_favorite_read_differently(self):
        labels = self.env["frontdesk.frontdesk"].fields_get(
            ["is_featured", "is_user_favorite"], ["string"]
        )

        self.assertEqual(labels["is_featured"]["string"], "Featured")
        self.assertNotEqual(labels["is_user_favorite"]["string"], "Featured")
