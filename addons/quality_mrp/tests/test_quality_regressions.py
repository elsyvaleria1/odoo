# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Regressions found while auditing the quality ring.

Checked against the code before the fix: each of these fails there.
"""

from odoo import Command
from odoo.tests import tagged

from .test_common import TestQualityMrpCommon


@tagged("post_install", "-at_install")
class TestQualityMrpRegressions(TestQualityMrpCommon):
    def _create_mo(self):
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.product_id,
                "product_qty": 1,
                "bom_id": self.bom_id,
            }
        )
        mo.action_confirm()
        return mo

    def test_a_second_confirm_pass_does_not_duplicate_operation_checks(self):
        """The picking side excludes points it already has a check for; so does this one now."""
        point = self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "measure_on": "operation",
            }
        )
        mo = self._create_mo()
        operation_checks = mo.check_ids.filtered(lambda c: c.measure_on == "operation")
        # Count this point's own checks, not every operation check on the order:
        # another module may ship operation points for mrp picking types of its
        # own, and quality_mrp_certificate ships two, so the total is not 1.
        self.assertEqual(
            len(operation_checks.filtered(lambda c: c.point_id == point)), 1
        )

        # Anything that confirms a move of this order again -- a backorder, a
        # move added to a confirmed order -- runs this a second time.
        mo.move_finished_ids._create_quality_checks_for_mo()

        self.assertEqual(
            mo.check_ids.filtered(lambda c: c.measure_on == "operation"),
            operation_checks,
        )

    def test_the_qc_status_answers_for_a_whole_batch(self):
        """`pre_button_mark_done` is called on a set, not on one order.

        `mrp_subcontracting` closes every production behind a receipt in one
        call, so reading a non-stored field off `self` raises there.
        """
        self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "product_ids": [Command.link(self.product_id)],
                "measure_on": "product",
            }
        )
        orders = self._create_mo() | self._create_mo()
        self.assertEqual(len(orders), 2)

        self.assertFalse(orders._is_quality_check_done())

        orders.check_ids.do_pass()

        self.assertTrue(orders._is_quality_check_done())

    def test_do_pass_and_do_fail_still_take_a_recordset(self):
        """`quality_mrp_workorder` auto-installs and used to `check_singleton` them."""
        checks = self.env["quality.check"].create(
            [{"product_id": self.product_id} for _ in range(2)]
        )

        checks.do_pass()
        self.assertEqual(set(checks.mapped("quality_state")), {"pass"})

        checks.do_fail()
        self.assertEqual(set(checks.mapped("quality_state")), {"fail"})

    def test_the_mo_check_flags_follow_their_checks(self):
        self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "product_ids": [Command.link(self.product_id)],
                "measure_on": "product",
            }
        )
        mo = self._create_mo()
        self.assertTrue(mo.check_ids)
        self.assertTrue(mo.quality_check_todo)

        mo.check_ids.do_fail()

        self.assertFalse(mo.quality_check_todo)
        self.assertTrue(mo.quality_check_fail)


@tagged("post_install", "-at_install")
class TestQualityCheckCloseHook(TestQualityMrpCommon):
    def test_a_bare_status_write_runs_the_close_hook(self):
        """`mrp_workorder.check_quality_checks` closes a check by writing the
        field, not by pressing the button, and still expects the move picked."""
        move = self.env["stock.move"].create(
            {
                "product_id": self.product_product_drawer_drawer.id,
                "product_uom_qty": 1,
                "location_id": self.env.ref("stock.stock_location_suppliers").id,
                "location_dest_id": self.env.ref("stock.stock_location_stock").id,
            }
        )
        check = self.env["quality.check"].create({"move_id": move.id})
        self.assertFalse(move.picked)

        check.quality_state = "pass"
        self.env.flush_all()

        self.assertTrue(move.picked, "the close hook did not run on a bare write")

    def test_the_button_runs_it_too(self):
        move = self.env["stock.move"].create(
            {
                "product_id": self.product_product_drawer_drawer.id,
                "product_uom_qty": 1,
                "location_id": self.env.ref("stock.stock_location_suppliers").id,
                "location_dest_id": self.env.ref("stock.stock_location_stock").id,
            }
        )
        check = self.env["quality.check"].create({"move_id": move.id})

        check.do_pass()
        self.env.flush_all()

        self.assertTrue(move.picked)
