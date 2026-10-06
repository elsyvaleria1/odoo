from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged

from odoo.addons.base.models.access_link import LinkRefused, hash_token


@tagged("post_install", "-at_install", "access_link")
class TestRatingLinks(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({"name": "Rating customer"})
        cls.rated = cls.env["res.partner"].create({"name": "Rated record"})

    def _rating(self):
        return self.env["rating.rating"].create(
            {
                "res_model_id": self.env["ir.model"]._get_id("res.partner"),
                "res_id": self.rated.id,
                "partner_id": self.customer.id,
            }
        )

    def _links(self, rating):
        return (
            self.env["access.link"]
            .sudo()
            .search([("res_model", "=", "rating.rating"), ("res_id", "=", rating.id)])
        )

    def test_a_rating_asked_is_answered_through_its_customers_link(self):
        rating = self._rating()
        link = self._links(rating)
        self.assertEqual(
            (len(link), link.partner_id, link.role, link.cause),
            (1, self.customer, "comment", "notification"),
        )
        self.assertAlmostEqual(
            link.date_to,
            fields.Datetime.now() + timedelta(days=365),
            delta=timedelta(minutes=5),
        )
        self.assertEqual(link.token_hash, hash_token(rating.access_token))
        self.assertEqual(
            self.rated._rating_get_access_token(self.customer), rating.access_token
        )
        self.env.cr.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'rating_rating' AND column_name = 'access_token'"
        )
        self.assertEqual(self.env.cr.fetchone()[0], 0, "no token is kept in clear")

    def test_a_token_opens_its_own_rating_only(self):
        rating, other = self._rating(), self._rating()
        self.assertEqual(
            self.url_open(f"/rate/{rating.access_token}/5").status_code, 200
        )
        mutated = rating.access_token[:-1] + (
            "A" if rating.access_token[-1] != "A" else "B"
        )
        self.assertEqual(self.url_open(f"/rate/{mutated}/5").status_code, 404)
        with self.assertRaises(LinkRefused):
            self.env["access.link"]._resolve(
                rating.access_token, model="rating.rating", res_id=other.id
            )
