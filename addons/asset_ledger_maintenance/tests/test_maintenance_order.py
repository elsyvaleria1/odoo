from datetime import datetime, timedelta

from freezegun import freeze_time

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import archive_maintenance_approval_categories


@tagged("post_install", "-at_install")
class TestMaintenanceOrderAsset(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        archive_maintenance_approval_categories(cls.env)
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.warehouse.allow_maintenance = True
        cls.product = cls.env["product.product"].create(
            {
                "name": "Transfer probe machine",
                "is_storable": True,
                "tracking": "serial",
                "maintenance_ok": True,
                "asset_kind_id": cls.env.ref("resource_asset.kind_machinery").id,
            }
        )
        cls.lot = cls.env["product.trace"].create(
            {"name": "TRANSFER-1", "product_id": cls.product.id}
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.warehouse.lot_stock_id, 1, trace_id=cls.lot
        )
        cls.lot.invalidate_recordset(["location_id"])
        cls.vendor = cls.env["res.partner"].create({"name": "Transfer probe vendor"})

    def _order(self, **vals):
        return self.env["maintenance.order"].create(
            {
                "name": "Replace hydraulic hose",
                "resource_ids": self.lot.asset_id.resource_id.ids,
                "maintenance_type": "corrective",
                "date_scheduled_start": datetime.now(),
                "duration": 24,
                "vendor_id": self.vendor.id,
                "state": "confirmed",
                **vals,
            }
        )

    def test_an_order_typed_in_does_not_book_its_asset(self):
        self.assertFalse(self._order().block_resource)

    def test_the_cron_leaves_an_order_whose_transfer_was_cancelled(self):
        plan = self.env["maintenance.plan"].create(
            {
                "asset_id": self.lot.asset_id.id,
                "repeat_interval": 1,
                "repeat_unit": "month",
                "date_first_occurrence": datetime.now() - timedelta(days=1),
            }
        )
        order = plan._get_open_order()
        Plan = self.env["maintenance.plan"]
        Plan._cron_start_due_orders()
        order.picking_ids.action_cancel()
        Plan._cron_start_due_orders()
        self.assertEqual(order.picking_ids.mapped("state"), ["cancel"])

    def test_the_cron_badges_a_manual_preventive_order_once_it_falls_due(self):
        self._order(
            maintenance_type="preventive",
            date_scheduled_start=datetime.now() + timedelta(days=2),
        )
        self.assertEqual(self.lot.maintenance_state, "good")
        with freeze_time(datetime.now() + timedelta(days=3)):
            self.env["maintenance.plan"]._cron_recompute_state()
        self.lot.invalidate_recordset(["maintenance_state"])
        self.lot.asset_id.invalidate_recordset(["maintenance_state"])
        self.assertEqual(self.lot.maintenance_state, "warning")
        self.assertEqual(self.lot.asset_id.maintenance_state, "warning")

    def test_a_generic_order_keeps_resource_blocking_enabled(self):
        resource = self.env["resource.resource"].create(
            {"name": "Generic station", "type": "material"}
        )
        order = self.env["maintenance.order"].create(
            {"name": "Generic service", "resource_ids": resource.ids}
        )
        self.assertTrue(order.block_resource)

    def test_an_asset_order_respects_explicit_blocking(self):
        self.assertTrue(self._order(block_resource=True).block_resource)

    def test_asset_order_action_supplies_business_default(self):
        action = self.lot.asset_id.action_create_maintenance_order()
        self.assertIs(action["context"]["default_block_resource"], False)
