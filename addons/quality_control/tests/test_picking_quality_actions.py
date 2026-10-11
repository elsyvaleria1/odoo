from odoo import Command
from odoo.exceptions import UserError

from .test_common import TestQualityCommon


class TestPickingQualityActions(TestQualityCommon):

    def _create_confirmed_picking(self):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "partner_id": self.partner_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product.id,
                "product_uom_qty": 1,
                "product_uom_id": self.product.uom_id.id,
                "picking_id": picking.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        picking.action_confirm()
        return picking

    def test_picking_quality_flags_and_search(self):
        self.env["quality.point"].create(
            {
                "product_ids": [Command.link(self.product.id)],
                "picking_type_ids": [Command.link(self.picking_type_id)],
            }
        )
        picking = self._create_confirmed_picking()
        self.assertTrue(picking.check_ids)
        self.assertTrue(picking.quality_check_todo)
        self.assertFalse(picking.quality_check_fail)

        found = self.env["stock.picking"].search([("quality_check_todo", "=", True)])
        self.assertIn(picking, found)

        picking.check_ids.do_fail()
        picking.invalidate_recordset(["quality_check_todo", "quality_check_fail"])
        self.assertTrue(picking.quality_check_fail)
        self.assertFalse(picking.quality_check_todo)

    def test_picking_quality_actions(self):
        self.env["quality.point"].create(
            {
                "product_ids": [Command.link(self.product.id)],
                "picking_type_ids": [Command.link(self.picking_type_id)],
            }
        )
        picking = self._create_confirmed_picking()

        action = picking.action_view_quality_check_picking()
        self.assertEqual(action["context"]["default_picking_id"], picking.id)

        action = picking.action_view_on_demand_quality_check()
        self.assertEqual(action["context"]["default_picking_id"], picking.id)
        self.assertEqual(action["context"]["default_product_id"], self.product.id)

        action = picking.button_quality_alert()
        self.assertEqual(action["context"]["default_picking_id"], picking.id)

        alert = self.env["quality.alert"].create(
            {
                "product_id": self.product.id,
                "product_tmpl_id": self.product_tmpl_id,
                "picking_id": picking.id,
            }
        )
        picking.invalidate_recordset(["quality_alert_count"])
        self.assertEqual(picking.quality_alert_count, 1)
        action = picking.open_quality_alert_picking()
        self.assertEqual(action["res_id"], alert.id)
        self.assertEqual(action["views"], [(False, "form")])

    def test_picking_cancel_removes_pending_checks(self):
        self.env["quality.point"].create(
            {
                "product_ids": [Command.link(self.product.id)],
                "picking_type_ids": [Command.link(self.picking_type_id)],
            }
        )
        picking = self._create_confirmed_picking()
        self.assertTrue(picking.check_ids)
        picking.action_cancel()
        self.assertFalse(picking.check_ids)

    def test_picking_done_with_pending_checks_is_refused(self):
        self.env["quality.point"].create(
            {
                "product_ids": [Command.link(self.product.id)],
                "picking_type_ids": [Command.link(self.picking_type_id)],
            }
        )
        picking = self._create_confirmed_picking()
        self.assertTrue(picking.check_ids)

        with self.assertRaisesRegex(UserError, "quality checks"):
            picking._action_done()

    def test_lot_quality_counters_and_actions(self):
        lot = self.env["product.trace"].create(
            {"name": "LOT-QC-1", "product_id": self.product.id}
        )
        self.assertEqual(lot.quality_check_qty, 0)
        self.assertEqual(lot.quality_alert_qty, 0)

        self.env["quality.alert"].create(
            {
                "product_id": self.product.id,
                "product_tmpl_id": self.product_tmpl_id,
                "trace_ids": [Command.link(lot.id)],
            }
        )
        lot.invalidate_recordset(["quality_alert_qty"])
        self.assertEqual(lot.quality_alert_qty, 1)

        action = lot.action_view_quality_checks()
        self.assertIn(("trace_ids", "in", lot.ids), action["domain"])

        action = lot.action_lot_open_quality_alerts()
        self.assertEqual(action["domain"], [("trace_ids", "=", lot.id)])
        self.assertEqual(action["context"]["default_trace_id"], lot.id)
