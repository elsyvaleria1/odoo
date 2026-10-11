
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLoyaltyGenerateScope(TransactionCase):
    """Who the coupon-generation wizard issues to, and what it records."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.program = cls.env["loyalty.program"].create(
            {"name": "Scoped", "reward_ids": [Command.create({})]}
        )
        cls.partner = cls.env["res.partner"].create({"name": "Chosen"})

    def _wizard(self, **values):
        return self.env["wizard.loyalty.program.create.card"].create(
            {"program_id": self.program.id, "points_granted": 1, **values}
        )

    def test_selecting_nobody_means_every_partner(self):
        partner_count = self.env["res.partner"].search_count([])
        self.assertGreater(partner_count, 1, "the database has partners to reach")

        wizard = self._wizard(mode="selected")

        self.assertEqual(wizard.coupon_qty, partner_count)
        self.assertEqual(len(wizard.generate_coupons()), partner_count)

    def test_selecting_a_customer_issues_one_coupon(self):
        wizard = self._wizard(
            mode="selected", customer_ids=[Command.set(self.partner.ids)]
        )

        coupons = wizard.generate_coupons()

        self.assertEqual(coupons.partner_id, self.partner)

    def test_a_batch_of_wizards_records_each_ones_grant(self):
        first, second = self.env["wizard.loyalty.program.create.card"].create(
            [
                {
                    "program_id": self.program.id,
                    "mode": "anonymous",
                    "coupon_qty": 2,
                    "points_granted": 5,
                    "description": "First batch",
                },
                {
                    "program_id": self.program.id,
                    "mode": "anonymous",
                    "coupon_qty": 3,
                    "points_granted": 9,
                    "description": "Second batch",
                },
            ]
        )

        coupons = (first + second).generate_coupons()
        history = self.env["loyalty.history"].search([("card_id", "in", coupons.ids)])

        self.assertEqual(len(coupons), 5)
        self.assertEqual(sorted(history.mapped("issued")), [5, 5, 9, 9, 9])
        self.assertEqual(
            sorted(set(history.mapped("description"))), ["First batch", "Second batch"]
        )

    def test_anonymous_coupons_are_held_by_nobody(self):
        wizard = self._wizard(mode="anonymous", coupon_qty=3)

        coupons = wizard.generate_coupons()

        self.assertEqual(len(coupons), 3)
        self.assertFalse(coupons.partner_id)
