from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form

from .test_common import TestQualityMrpCommon


class TestQualityMrpFlows(TestQualityMrpCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.simple_product = cls.env["product.product"].create(
            {"name": "Untracked Widget", "is_storable": True}
        )
        cls.point_all = cls.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(cls.picking_type_id)],
                "measure_on": "operation",
                "test_type_id": cls.env.ref("quality_control.test_type_passfail").id,
            }
        )

    def _create_mo(self, qty=1.0):
        mo_form = Form(self.env["mrp.production"])
        mo_form.product_id = self.simple_product
        mo_form.product_qty = qty
        mo = mo_form.save()
        mo.action_confirm()
        return mo

    def test_compute_check_flags(self):
        second_point = self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "measure_on": "operation",
                "test_type_id": self.env.ref("quality_control.test_type_passfail").id,
            }
        )
        mo = self._create_mo()
        self.assertEqual(len(mo.check_ids), 2)
        self.assertTrue(mo.quality_check_todo)
        self.assertFalse(mo.quality_check_fail)

        mo.check_ids.filtered(lambda c: c.point_id == second_point).do_fail()
        mo.invalidate_recordset(["quality_check_todo", "quality_check_fail"])
        self.assertTrue(mo.quality_check_todo)
        self.assertTrue(mo.quality_check_fail)

    def test_quality_alert_actions(self):
        mo = self._create_mo()
        action = mo.button_quality_alert()
        self.assertEqual(action["context"]["default_production_id"], mo.id)
        self.assertEqual(action["views"], [(False, "form")])

        alert = self.env["quality.alert"].create(
            {
                "production_id": mo.id,
                "product_id": self.simple_product.id,
                "product_tmpl_id": self.simple_product.product_tmpl_id.id,
            }
        )
        self.assertEqual(mo.quality_alert_count, 1)
        action = mo.open_quality_alert_mo()
        self.assertEqual(action["res_id"], alert.id)
        self.assertEqual(action["views"], [(False, "form")])
        self.assertEqual(action["context"]["default_production_id"], mo.id)

    def test_mark_done_requires_quality_checks(self):
        mo = self._create_mo()
        mo.qty_producing = 1.0
        self.assertEqual(mo.check_ids.quality_state, "none")

        with self.assertRaises(UserError):
            mo.button_mark_done()

        res = mo.with_context(from_wizard=True).button_mark_done()
        self.assertEqual(res["tag"], "display_notification")
        self.assertEqual(res["params"]["type"], "warning")

        mo.check_ids.do_pass()
        mo.button_mark_done()
        self.assertEqual(mo.state, "done")

    def test_action_cancel_removes_pending_checks(self):
        mo = self._create_mo()
        self.assertTrue(mo.check_ids)
        mo.action_cancel()
        self.assertFalse(mo.check_ids)

    def test_check_quality_and_on_demand_actions(self):
        mo = self._create_mo()
        action = mo.check_quality()
        self.assertEqual(action["res_model"], "wizard.quality.check.decide")

        mo.check_ids.do_pass()
        self.assertIsNone(mo.check_quality())

        action = mo.action_view_on_demand_quality_check()
        self.assertEqual(action["context"]["default_production_id"], mo.id)
        self.assertEqual(
            action["context"]["default_product_id"], self.simple_product.id
        )

    def test_check_computes_and_product_constraint(self):
        mo = self._create_mo()
        check = mo.check_ids
        self.assertEqual(check.allowed_product_ids, mo.move_finished_ids.product_id)
        self.assertTrue(check.hide_picking_id)
        self.assertFalse(check.hide_production_id)

        mo.qty_producing = 1.0
        self.assertEqual(check.qty_line, 1.0)

        with self.assertRaises(ValidationError):
            check.product_id = self.product_product_drawer_drawer
