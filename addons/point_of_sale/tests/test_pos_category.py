import logging

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import CommonPosTest, TestPoSCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestPosCategoryGuards(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config

    def test_check_hour_rejects_window_that_never_opens(self):
        category = self.env["pos.category"].create({"name": "Snacks"})

        with self.assertRaises(ValidationError):
            category.write({"hour_after": 10.0, "hour_until": 0.0})

        with self.assertRaises(ValidationError):
            self.env["pos.category"].create(
                {"name": "Drinks", "hour_after": 10.0, "hour_until": 0.0}
            )

        with self.assertRaises(ValidationError):
            category.write({"hour_until": 25.0})

        category.write({"hour_after": 0.0, "hour_until": 24.0})
        self.assertEqual(category.hour_until, 24.0)

    def test_unlink_ignores_session_that_cannot_show_the_category(self):
        category = self.env["pos.category"].create({"name": "Snacks"})
        other_category = self.env["pos.category"].create({"name": "Drinks"})
        self.config.write(
            {
                "limit_categories": True,
                "iface_available_categ_ids": [(6, 0, other_category.ids)],
            }
        )
        self.config.open_ui()

        category.unlink()
        self.assertFalse(category.exists())

    def test_unlink_blocked_by_session_that_shows_the_category(self):
        category = self.env["pos.category"].create({"name": "Snacks"})
        self.config.write(
            {
                "limit_categories": True,
                "iface_available_categ_ids": [(6, 0, category.ids)],
            }
        )
        self.config.open_ui()
        session = self.config.current_session_id

        with self.assertRaisesRegex(UserError, session.name):
            category.unlink()

    def test_unlink_blocked_by_session_restricted_to_no_category(self):
        category = self.env["pos.category"].create({"name": "Snacks"})
        self.config.write(
            {"limit_categories": True, "iface_available_categ_ids": [(5, 0, 0)]}
        )
        self.config.open_ui()

        with self.assertRaises(UserError):
            category.unlink()

    def test_unlink_ignores_session_of_another_company(self):
        category = self.env["pos.category"].create({"name": "Snacks"})
        self.config.open_ui()
        other_company = self.setup_other_company()["company"]

        category.with_context(allowed_company_ids=other_company.ids).unlink()
        self.assertFalse(category.exists())


@tagged("post_install", "-at_install")
class TestPosCategoryDisplayName(CommonPosTest):
    def test_reparenting_renames_the_cached_descendants(self):
        first, second = self.env["pos.category"].create(
            [{"name": "First"}, {"name": "Second"}]
        )
        middle = self.env["pos.category"].create(
            {"name": "Middle", "parent_id": first.id}
        )
        leaf = self.env["pos.category"].create({"name": "Leaf", "parent_id": middle.id})
        self.assertEqual(leaf.display_name, "First / Middle / Leaf")
        middle.parent_id = second
        self.assertEqual(leaf.display_name, "Second / Middle / Leaf")
        first.name = "Detached ancestor"
        self.assertEqual(leaf.display_name, "Second / Middle / Leaf")
        second.name = "New ancestor"
        self.assertEqual(leaf.display_name, "New ancestor / Middle / Leaf")
        middle.parent_id = False
        self.assertEqual(leaf.display_name, "Middle / Leaf")
        _logger.debug("reparented warm category=%s", leaf.display_name)

    def test_renaming_the_root_renames_a_third_level_leaf(self):
        root = self.env["pos.category"].create({"name": "Root"})
        middle = self.env["pos.category"].create(
            {"name": "Middle", "parent_id": root.id}
        )
        leaf = self.env["pos.category"].create({"name": "Leaf", "parent_id": middle.id})
        before = leaf.display_name
        root.name = "Changed"
        stale = leaf.display_name
        self.env.invalidate_all()
        fresh = leaf.display_name
        self.assertEqual(before, "Root / Middle / Leaf")
        self.assertEqual(stale, "Changed / Middle / Leaf")
        self.assertEqual(fresh, "Changed / Middle / Leaf")
        _logger.debug("category depth=3 stale=%r fresh=%r", stale, fresh)
