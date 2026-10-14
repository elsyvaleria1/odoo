from psycopg.errors import UniqueViolation

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, counting_statements, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestResourceAssetStock(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vehicle = cls.env.ref("base.kind_vehicle")
        cls.template = cls.env["product.template"].create(
            {
                "name": "Pickup",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": cls.vehicle.id,
            }
        )
        cls.product = cls.template.product_variant_id
        cls.stock_location = cls.env.ref("stock.stock_location_stock")

    def test_an_asset_product_must_be_serial_tracked(self):
        with self.assertRaises(ValidationError):
            self.env["product.template"].create(
                {
                    "name": "Crates",
                    "is_storable": True,
                    "tracking": "lot",
                    "asset_kind_id": self.vehicle.id,
                }
            )

    def test_a_serial_becomes_an_asset(self):
        lot = self.env["product.trace"].create(
            {
                "name": "PK-001",
                "product_id": self.product.id,
                "company_id": self.env.company.id,
            }
        )
        asset = lot.asset_id
        self.assertTrue(asset)
        self.assertEqual(asset.trace_id, lot)
        self.assertEqual(asset.kind_id, self.vehicle)
        self.assertEqual(asset.product_id, self.product)
        self.assertEqual(asset.name, "Pickup PK-001")
        self.assertEqual(asset.type, "material")

    def test_typing_a_product_gives_its_existing_serials_an_asset(self):
        mower = self.env["product.product"].create(
            {"name": "Mower", "is_storable": True, "tracking": "serial"}
        )
        received = self.env["product.trace"].create(
            {"name": "M-1", "product_id": mower.id, "company_id": self.env.company.id}
        )
        self.assertFalse(received.asset_id)
        mower.product_tmpl_id.asset_kind_id = self.vehicle
        self.assertTrue(received.asset_id)
        self.assertEqual(received.asset_id.trace_id, received)
        self.assertEqual(received.asset_id.kind_id, self.vehicle)
        asset = received.asset_id
        mower.product_tmpl_id.asset_kind_id = self.env.ref("base.kind_machinery")
        self.assertEqual(received.asset_id, asset)
        self.assertEqual(
            self.env["resource.resource"].search_count(
                [("trace_id", "=", received.id)]
            ),
            1,
        )

    def test_a_plain_serial_is_not_an_asset(self):
        plain = self.env["product.product"].create(
            {"name": "Bolt box", "is_storable": True, "tracking": "serial"}
        )
        lot = self.env["product.trace"].create(
            {"name": "B-1", "product_id": plain.id, "company_id": self.env.company.id}
        )
        self.assertFalse(lot.asset_id)

    def test_the_asset_reads_the_lot_location(self):
        lot = self.env["product.trace"].create(
            {
                "name": "PK-002",
                "product_id": self.product.id,
                "company_id": self.env.company.id,
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.stock_location, 1, trace_id=lot
        )
        lot.invalidate_recordset()
        self.assertEqual(lot.asset_id.location_id, self.stock_location)

    def test_scrapping_the_serial_disposes_of_the_asset(self):
        lot = self.env["product.trace"].create(
            {
                "name": "PK-003",
                "product_id": self.product.id,
                "company_id": self.env.company.id,
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.stock_location, 1, trace_id=lot
        )
        scrap = self.env["stock.scrap"].create(
            {
                "product_id": self.product.id,
                "trace_id": lot.id,
                "scrap_qty": 1,
                "location_id": self.stock_location.id,
            }
        )
        scrap.action_validate()
        self.assertEqual(scrap.state, "done")
        self.assertEqual(lot.asset_id.state, "disposed")
        self.assertFalse(lot.asset_id.active)

    def test_one_asset_per_lot(self):
        lot = self.env["product.trace"].create(
            {
                "name": "PK-004",
                "product_id": self.product.id,
                "company_id": self.env.company.id,
            }
        )
        from odoo.tools import mute_logger

        with (
            self.assertRaises(UniqueViolation),
            mute_logger("odoo.sql_db", "odoo.db.cursor"),
        ):
            with self.env.cr.savepoint():
                lot.asset_id.copy({"trace_id": lot.id}).flush_recordset()

    def test_giving_an_asset_another_serial_moves_the_lot_link(self):
        lot, other = self.env["product.trace"].create(
            [
                {
                    "name": name,
                    "product_id": self.product.id,
                    "company_id": self.env.company.id,
                }
                for name in ("PK-005", "PK-005B")
            ]
        )
        asset = lot.asset_id
        other.asset_id.trace_id = False
        self.env.flush_all()
        asset.trace_id = other
        self.assertFalse(lot.asset_id)
        self.assertEqual(other.asset_id, asset)
        self.assertEqual(
            self.env["product.trace"].search(
                [("asset_id", "=", asset.id), ("id", "in", (lot | other).ids)]
            ),
            other,
        )

    def test_a_stock_user_without_asset_rights_still_creates_the_asset(self):
        user = new_test_user(
            self.env, login="stock_only", groups="stock.group_stock_user"
        )
        lot = (
            self.env["product.trace"]
            .with_user(user)
            .create(
                {
                    "name": "PK-006",
                    "product_id": self.product.id,
                    "company_id": self.env.company.id,
                }
            )
        )
        self.assertTrue(lot.asset_id)
        self.assertEqual(lot.asset_id.sudo().kind_id, self.vehicle)

    def test_an_asset_follows_its_serial_to_another_location(self):
        lot = self.env["product.trace"].create(
            {
                "name": "PK-LOC",
                "product_id": self.product.id,
                "company_id": self.env.company.id,
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.stock_location, 1, trace_id=lot
        )
        self.assertEqual(lot.asset_id.location_id, self.stock_location)

    def test_an_asset_without_a_serial_keeps_the_location_set_by_hand(self):
        shelf = self.env["stock.location"].create(
            {
                "name": "Tool shelf",
                "usage": "internal",
                "location_id": self.stock_location.id,
            }
        )
        drill = self.env["resource.resource"].create(
            {
                "name": "Drill",
                "kind_id": self.env.ref("base.kind_tool").id,
                "location_id": shelf.id,
            }
        )
        self.assertEqual(drill.location_id, shelf)
        drill.name = "Hammer drill"
        self.assertEqual(drill.location_id, shelf)

    def test_delivering_serials_does_not_search_assets_per_line(self):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        customers = self.env.ref("stock.stock_location_customers")

        def statements_to_deliver(count):
            lots = self.env["product.trace"].create(
                [
                    {
                        "name": f"DELIVER-{count}-{index}",
                        "product_id": self.product.id,
                        "company_id": self.env.company.id,
                    }
                    for index in range(count)
                ]
            )
            for lot in lots:
                self.env["stock.quant"]._update_available_quantity(
                    self.product, warehouse.lot_stock_id, 1, trace_id=lot
                )
            picking = self.env["stock.picking"].create(
                {
                    "picking_type_id": warehouse.out_type_id.id,
                    "location_id": warehouse.lot_stock_id.id,
                    "location_dest_id": customers.id,
                    "move_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product.id,
                                "product_uom_qty": count,
                                "location_id": warehouse.lot_stock_id.id,
                                "location_dest_id": customers.id,
                            },
                        )
                    ],
                }
            )
            picking.action_confirm()
            picking.action_assign()
            picking.move_ids.picked = True
            self.env.flush_all()
            self.env.invalidate_all()
            with counting_statements(self.env.cr) as statements:
                picking.button_validate()
                self.env.flush_all()
            self.assertEqual(picking.state, "done")
            self.assertEqual(lots.asset_id.location_id, customers)
            return statements.count

        few, many = statements_to_deliver(2), statements_to_deliver(12)
        self.assertLess(many - few, 10)


@tagged("post_install", "-at_install")
class TestReceivingAnEnforcedAsset(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vehicle = cls.env.ref("base.kind_vehicle")
        cls.vehicle.enforce_identifiers = True
        cls.template = cls.env["product.template"].create(
            {
                "name": "Enforced pickup",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": cls.vehicle.id,
            }
        )
        cls.product = cls.template.product_variant_id

    def _receive(self, serial):
        warehouse = self.env["stock.warehouse"].search([], limit=1)
        picking_type = warehouse.in_type_id
        picking_type.use_create_lots = True
        supplier = self.env.ref("stock.stock_location_suppliers")
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": supplier.id,
                "location_dest_id": warehouse.lot_stock_id.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1,
                            "location_id": supplier.id,
                            "location_dest_id": warehouse.lot_stock_id.id,
                        },
                    )
                ],
            }
        )
        picking.action_confirm()
        picking.move_ids.move_line_ids.write({"lot_name": serial, "quantity": 1})
        picking.button_validate()
        return picking.move_ids.move_line_ids.trace_id

    def test_a_receipt_creates_the_serial_before_the_plate_exists(self):
        lot = self._receive("RECEIPT-SN-1")

        self.assertEqual(lot.name, "RECEIPT-SN-1")
        self.assertTrue(lot.asset_id)
        self.assertTrue(lot.asset_id.missing_identifier_type_ids)

    def test_the_receipt_exemption_does_not_leak_to_a_direct_create(self):
        with self.assertRaises(ValidationError):
            self.env["resource.resource"].create(
                {"name": "Direct", "kind_id": self.vehicle.id}
            )
