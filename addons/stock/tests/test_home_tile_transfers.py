from datetime import datetime

from freezegun import freeze_time

from odoo.tests import tagged

from odoo.addons.stock.tests.common import TestStockCommon


@tagged("post_install", "-at_install")
@freeze_time("2026-09-26 12:00:00")
class TestHomeTileTransfers(TestStockCommon):
    def _transfers(self):
        self.env.invalidate_all()
        return (
            self.env["home.tile"]
            .with_user(self.user_stock_user)
            .get_tiles([{"id": "transfers_1", "type": "transfers"}])["transfers_1"][
                "data"
            ]
        )

    def _delivery(self, product, planned):
        picking = self.PickingObj.create({"picking_type_id": self.picking_type_out.id})
        self.MoveObj.create(
            {
                "product_id": product.id,
                "product_uom_qty": 2,
                "product_uom_id": product.uom_id.id,
                "picking_id": picking.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "date": planned,
            }
        )
        picking.action_confirm()
        return picking

    def test_the_transfers_tile_counts_ready_late_and_waiting(self):
        before = self._transfers()
        self.StockQuantObj._update_available_quantity(
            self.productA, self.stock_location, 10
        )
        self._delivery(self.productA, datetime(2026, 9, 28, 10, 0)).action_assign()
        self._delivery(self.productB, datetime(2026, 9, 20, 10, 0))

        after = self._transfers()
        self.assertEqual(
            {
                bucket: after[bucket] - before[bucket]
                for bucket in ("ready", "late", "waiting")
            },
            {"ready": 1, "late": 1, "waiting": 1},
        )
        row = next(r for r in after["types"] if r["id"] == self.picking_type_out.id)
        self.assertEqual((row["ready"], row["late"], row["waiting"]), (1, 1, 1))
        self.assertEqual(row["name"], self.picking_type_out.display_name)

    def test_a_type_with_nothing_ready_or_late_is_not_listed(self):
        self._delivery(self.productB, datetime(2026, 9, 28, 10, 0))
        ids = [row["id"] for row in self._transfers()["types"]]
        self.assertNotIn(self.picking_type_out.id, ids)

    def test_the_transfers_tile_keeps_its_statement_count(self):
        request = [{"id": "transfers_1", "type": "transfers"}]
        self.env["home.tile"].with_user(self.user_stock_user).get_tiles(request)
        self.env.invalidate_all()
        # stock_picking_batch adds one grouped count of the types' batches
        batch_statements = int("stock.picking.batch" in self.env)
        with self.assertQueryCount(6 + batch_statements):
            self.env["home.tile"].with_user(self.user_stock_user).get_tiles(request)
