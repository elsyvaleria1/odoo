from odoo.tests import new_test_user, tagged

from .test_credit_profile import CreditProfileCase


@tagged("post_install", "-at_install")
class TestHomeTileCreditReviews(CreditProfileCase):
    def _reviews(self):
        return self.env["home.tile"].get_tiles(
            [{"id": "credit_reviews_1", "type": "credit_reviews"}]
        )["credit_reviews_1"]["data"]

    def test_the_credit_tile_lists_the_open_reviews_assigned_to_me(self):
        partner = self._partner("Tile Customer", credit_grade_id=self.unconditional.id)
        review = partner.sudo().credit_profile_id._open_review("manual")
        review.user_id = self.env.user
        data = self._reviews()
        self.assertIn(review.id, [r["id"] for r in data["reviews"]])
        row = next(r for r in data["reviews"] if r["id"] == review.id)
        self.assertEqual(row["partner"], partner.display_name)
        self.assertTrue(row["kind"])

        review.user_id = new_test_user(self.env, login="tile_reviewer")
        self.assertNotIn(review.id, [r["id"] for r in self._reviews()["reviews"]])

    def _assigned_review(self, name):
        partner = self._partner(name, credit_grade_id=self.unconditional.id)
        review = partner.sudo().credit_profile_id._open_review("manual")
        review.user_id = self.env.user
        return review

    def test_the_review_waiting_longest_comes_first(self):
        older = self._assigned_review("Waiting Customer")
        newer = self._assigned_review("Fresh Customer")
        self.env.cr.execute(
            "UPDATE credit_review SET create_date = create_date - interval '3 days'"
            " WHERE id = %s",
            [older.id],
        )
        self.env.invalidate_all()
        ids = [r["id"] for r in self._reviews()["reviews"]]
        self.assertLess(ids.index(older.id), ids.index(newer.id))

    def test_the_credit_tile_keeps_its_statement_count(self):
        for name in ("Pin One", "Pin Two"):
            self._assigned_review(name)
        request = [{"id": "credit_reviews_1", "type": "credit_reviews"}]
        self.env["home.tile"].get_tiles(request)
        self.env.invalidate_all()
        with self.assertQueryCount(6):
            self.env["home.tile"].get_tiles(request)
