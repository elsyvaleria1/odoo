from odoo.fields import Command
from odoo.tests import TransactionCase, counting_statements, tagged


@tagged("post_install", "-at_install")
class TestLoyaltyCardBatchCost(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.program = cls.env["loyalty.program"].create(
            {
                "name": "Batch cost",
                "reward_ids": [Command.create({})],
            }
        )

    def _queries_to_issue(self, count):
        partners = self.env["res.partner"].create(
            [{"name": f"Holder {index}"} for index in range(count)]
        )
        self.env.flush_all()
        self.env.invalidate_all()
        with counting_statements(self.env.cr) as statements:
            self.env["loyalty.card"].with_context(loyalty_no_mail=True).create(
                [
                    {
                        "program_id": self.program.id,
                        "partner_id": partner.id,
                        "points": 1,
                    }
                    for partner in partners
                ]
            )
            self.env.flush_all()
            return statements.count

    def test_issuing_cards_costs_one_batch(self):
        self._queries_to_issue(2)

        small = self._queries_to_issue(2)
        large = self._queries_to_issue(20)

        marginal = (large - small) / 18
        self.assertLess(
            marginal,
            1,
            f"issuing a card should cost well under one query each; measured"
            f" {marginal:.2f} ({small} queries for 2, {large} for 20)",
        )
