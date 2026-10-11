"""The two rating mixins ask different questions and no longer share an answer."""

from odoo.tests import TransactionCase, tagged

RATED_FIELDS = (
    "rating_ids",
    "rating_count",
    "rating_avg",
    "rating_percentage_satisfaction",
)
PARENT_FIELDS = (
    "rating_child_ids",
    "rating_child_count",
    "rating_child_avg",
    "rating_child_percentage_satisfaction",
    "rating_child_avg_percentage",
)


@tagged("post_install", "-at_install")
class TestRatingMixinCollision(TransactionCase):
    def test_the_two_mixins_share_no_field_name(self):
        parent = self.env["mixin.rating.parent"]._fields
        rated = self.env["mixin.rating"]._fields
        shared = sorted(set(parent) & set(rated) & set(RATED_FIELDS + PARENT_FIELDS))
        self.assertFalse(
            shared,
            "the rating mixins mean different things by these names: %s" % shared,
        )

    def test_each_mixin_still_declares_its_own_vocabulary(self):
        parent = self.env["mixin.rating.parent"]._fields
        for name in PARENT_FIELDS:
            with self.subTest(field=name):
                self.assertIn(name, parent)

    def test_rating_child_avg_percentage_is_not_computed_beside_its_average(self):
        parent = self.env["mixin.rating.parent"]._fields
        self.assertNotEqual(
            parent["rating_child_avg_percentage"].compute,
            parent["rating_child_avg"].compute,
        )
