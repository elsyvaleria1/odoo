from odoo import Command
from odoo.tests import TransactionCase


class TestPrecomputeRequired(TransactionCase):
    def test_a_required_precompute_the_draft_reads_otherwise_is_corrected_after_create(
        self,
    ):
        Order = self.env["test_orm.precompute.total"]
        other = Order.create({"line_ids": [Command.create({"qty": 2})]})
        order = Order.create(
            {"line_ids": [Command.update(other.line_ids.id, {"qty": 3})]}
        )
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertFalse(order.line_ids)
        self.assertEqual(order.total, 0)
        self.assertEqual(other.total, 3)
