from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "account_credit_partner_scoring")
class TestCommercialScore(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dimension = cls.env.ref(
            "account_credit_partner_scoring.scorecard_dimension_commercial_score"
        )
        cls.customer = cls.env["res.partner"].create(
            {"name": "Scored Debtor", "is_company": True}
        )
        cls.profile = cls.env["credit.profile"].create(
            {"partner_id": cls.customer.id, "company_id": cls.env.company.id}
        )

    def _rows(self):
        return self.profile.score_line_ids.filtered(
            lambda row: row.dimension_code == "commercial_score"
        )

    def test_the_dimension_ships_active_and_weighs_nothing_for_an_unscored_customer(
        self,
    ):
        self.assertTrue(self.dimension.active)
        self.profile._score_refresh()
        row = self._rows()
        self.assertTrue(row)
        self.assertFalse(row.applicable)
        self.assertNotIn(
            (row.dimension_id.id, row.grouping_key),
            {
                (r.dimension_id.id, r.grouping_key)
                for r in self.profile.score_line_ids.filtered("applicable")
            },
        )

    def test_an_unscored_customer_leaves_the_denominator(self):
        self.profile._score_refresh()
        row = self._rows()
        self.assertTrue(row)
        self.assertFalse(row.applicable)
        self.assertEqual(row.source_key, "commercial_score:none")

    def test_a_scored_customer_enters_on_the_populations_bands(self):
        self.customer._score_refresh()
        self.customer.score_line_ids.sudo().write({"points": 45.0, "max_points": 100.0})
        self.customer.invalidate_recordset(["score"])
        self.assertAlmostEqual(self.customer.score, 45.0)
        self.profile._score_refresh()
        row = self._rows()
        self.assertTrue(row.applicable)
        self.assertEqual(row.value, 45.0)
        self.assertEqual(row.points, 0.85 * self.dimension.weight)
        self.assertEqual(self.profile.tier_id, self.customer.tier_id)
