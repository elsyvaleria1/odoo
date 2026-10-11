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
        point = self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "measure_on": "operation",
            }
        )
        mo = self._create_mo()
        operation_checks = mo.check_ids.filtered(lambda c: c.measure_on == "operation")
        self.assertEqual(
            len(operation_checks.filtered(lambda c: c.point_id == point)), 1
        )

        mo.move_finished_ids._create_quality_checks_for_mo()

        self.assertEqual(
            mo.check_ids.filtered(lambda c: c.measure_on == "operation"),
            operation_checks,
        )

    def test_the_qc_status_answers_for_a_whole_batch(self):
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
