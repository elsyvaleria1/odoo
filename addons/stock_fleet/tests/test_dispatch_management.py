from lxml import etree

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDispatchManagement(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.customer_location = cls.env.ref("stock.stock_location_customers")
        cls.dock = cls.env["stock.location"].create(
            {
                "name": "Dock A",
                "usage": "internal",
                "location_id": cls.warehouse.view_location_id.id,
            }
        )
        cls.out_type = cls.warehouse.out_type_id
        cls.out_type.dock_ids = [Command.set(cls.dock.ids)]
        cls.in_type = cls.warehouse.in_type_id
        cls.in_type.dock_ids = [Command.set(cls.dock.ids)]

        cls.model = cls.env["product.product"].create(
            {
                "name": "Test Van",
                "type": "consu",
                "asset_kind_id": cls.env.ref("resource.kind_vehicle").id,
                "weight_capacity": 100.0,
                "volume_capacity": 20.0,
            }
        )
        cls.driver = cls.env["res.partner"].create({"name": "Driver"})
        cls.vehicle = cls.env["resource.resource"].create(
            {
                "name": "Van",
                "kind_id": cls.env.ref("resource.kind_vehicle").id,
                "product_id": cls.model.id,
                "operator_id": cls.env["resource.resource"]
                .create(
                    {
                        "name": "Driver",
                        "type": "human",
                        "partner_id": cls.driver.id,
                    }
                )
                .id,
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Freight",
                "is_storable": True,
                "weight": 10.0,
                "volume": 2.0,
            }
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.stock_location, 1000
        )

    def _picking(self, picking_type=None, zip_code=False, quantity=1):
        picking_type = picking_type or self.out_type
        partner = self.env["res.partner"].create(
            {"name": f"P{zip_code or 'x'}", "zip": zip_code}
        )
        outgoing = picking_type.code == "outgoing"
        src = self.stock_location if outgoing else self.customer_location
        dest = self.customer_location if outgoing else self.stock_location
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "partner_id": partner.id,
                "location_id": src.id,
                "location_dest_id": dest.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": quantity,
                            "location_id": src.id,
                            "location_dest_id": dest.id,
                        }
                    )
                ],
            }
        )
        picking.action_confirm()
        return picking

    def _delivery_fed_through_transit(self, quantity=3):
        """Deliver from a shipping transit that an earlier leg already filled."""
        transit = self.env["stock.location"].create(
            {
                "name": "Shipping transit",
                "usage": "transit",
                "location_id": self.warehouse.view_location_id.id,
                "company_id": self.warehouse.company_id.id,
            }
        )
        delivery = self.env["stock.picking"].create(
            {
                "picking_type_id": self.out_type.id,
                "partner_id": self.env["res.partner"].create({"name": "Customer"}).id,
                "location_id": transit.id,
                "location_dest_id": self.customer_location.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": quantity,
                            "location_id": transit.id,
                            "location_dest_id": self.customer_location.id,
                        }
                    )
                ],
            }
        )
        leg = self.env["stock.picking"].create(
            {
                "picking_type_id": self.warehouse.int_type_id.id,
                "location_id": self.stock_location.id,
                "location_dest_id": transit.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": quantity,
                            "location_id": self.stock_location.id,
                            "location_dest_id": transit.id,
                            "move_dest_ids": [Command.link(delivery.move_ids.id)],
                        }
                    )
                ],
            }
        )
        delivery.action_confirm()
        leg.action_confirm()
        leg.action_assign()
        leg.move_ids.picked = True
        leg.button_validate()
        return delivery

    def _batch(self, pickings, picking_type=None, **vals):
        return self.env["stock.picking.batch"].create(
            {
                "picking_type_id": (picking_type or self.out_type).id,
                "picking_ids": [Command.set(pickings.ids)],
                **vals,
            }
        )

    def test_a_dock_moves_the_source_of_an_outgoing_transfer(self):
        picking = self._picking()
        original = picking.move_ids.location_id
        batch = self._batch(picking, dock_id=self.dock.id)
        self.assertEqual(batch.dock_id, self.dock)
        self.assertEqual(picking.move_ids.location_id, self.dock)
        self.assertNotEqual(picking.move_ids.location_id, original)

    def test_a_dock_moves_the_destination_of_an_incoming_transfer(self):
        picking = self._picking(picking_type=self.in_type)
        batch = self._batch(picking, picking_type=self.in_type, dock_id=self.dock.id)
        self.assertEqual(batch.dock_id, self.dock)
        self.assertEqual(picking.move_ids.location_dest_id, self.dock)

    def test_clearing_the_dock_restores_the_transfer_own_destination(self):
        picking = self._picking(picking_type=self.in_type)
        batch = self._batch(picking, picking_type=self.in_type, dock_id=self.dock.id)
        self.assertEqual(picking.move_ids.location_dest_id, self.dock)
        batch.dock_id = False
        self.assertEqual(picking.move_ids.location_dest_id, picking.location_dest_id)

    def test_transfers_are_sequenced_by_the_partner_postcode(self):
        far = self._picking(zip_code="9000")
        near = self._picking(zip_code="1000")
        middle = self._picking(zip_code="5000")
        self._batch(far | near | middle)
        self.assertEqual(near.batch_sequence, 1)
        self.assertEqual(middle.batch_sequence, 2)
        self.assertEqual(far.batch_sequence, 3)

    def test_the_load_is_measured_against_the_vehicle_model(self):
        picking = self._picking(quantity=5)
        picking.move_ids.quantity = 5
        batch = self._batch(picking, vehicle_id=self.vehicle.id)
        self.assertEqual(batch.vehicle_model_id, self.model)
        self.assertFalse(batch.driver_id, "the vehicle's holder is not the driver")
        self.assertEqual(batch.estimated_shipping_weight, 50.0)
        self.assertEqual(batch.used_weight_percentage, 50.0)

    def test_the_load_is_the_demand_until_reserved_then_the_shipping_weight(self):
        picking = self._picking(quantity=3)
        batch = self._batch(picking, vehicle_id=self.vehicle.id)
        picking.action_unreserve()
        self.assertFalse(picking.move_line_ids)
        self.assertEqual(batch.trip_shipping_weight, 30.0)
        self.assertEqual(batch.used_weight_percentage, 30.0)
        # Reserved on a pallet: the shipping weight carries the pallet's tare.
        pallet = self.env["stock.package.type"].create(
            {"name": "Pallet", "base_weight": 20.0}
        )
        picking.action_assign()
        picking.move_line_ids.result_package_id = self.env["stock.package"].create(
            {"package_type_id": pallet.id}
        )
        self.assertEqual(batch.trip_shipping_weight, 50.0)
        self.assertEqual(batch.used_weight_percentage, 50.0)

    def test_a_pallet_shared_by_two_deliveries_weighs_once(self):
        first = self._picking(quantity=2)
        second = self._picking(quantity=3)
        batch = self._batch(first | second, vehicle_id=self.vehicle.id)
        pallet = self.env["stock.package"].create(
            {
                "package_type_id": self.env["stock.package.type"]
                .create({"name": "Pallet", "base_weight": 20.0})
                .id
            }
        )
        (first | second).move_line_ids.result_package_id = pallet
        self.assertEqual(batch.trip_shipping_weight, 50.0 + 20.0)

    def test_a_batch_with_no_vehicle_reports_no_load_percentage(self):
        picking = self._picking(quantity=5)
        picking.move_ids.quantity = 5
        batch = self._batch(picking)
        self.assertFalse(batch.vehicle_id)
        self.assertEqual(batch.used_weight_percentage, 0.0)
        self.assertEqual(batch.used_volume_percentage, 0.0)

    def test_merging_carries_the_vehicle_and_the_dock(self):
        first = self._batch(
            self._picking(), vehicle_id=self.vehicle.id, dock_id=self.dock.id
        )
        second = self._batch(self._picking())
        (first | second).action_merge()
        self.assertEqual(first.vehicle_id.id, self.vehicle.id)
        self.assertEqual(first.dock_id, self.dock)

    def test_docking_a_reserved_transfer_throws_its_reservation_away(self):
        picking = self._picking(quantity=3)
        picking.action_assign()
        self.assertEqual(picking.state, "assigned")
        self.assertTrue(picking.move_ids.move_line_ids)

        self._batch(picking, dock_id=self.dock.id)
        picking.invalidate_recordset()
        self.assertEqual(picking.move_ids.location_id, self.dock)
        self.assertFalse(
            picking.move_ids.move_line_ids,
            "Setting a dock rewrites the move source, which unreserves it. "
            "Assembling a truckload therefore drops the reservation on every "
            "outgoing transfer the batch picks straight from stock.",
        )
        self.assertNotEqual(picking.state, "assigned")

    def test_a_delivery_fed_through_a_transit_joins_a_docked_batch_reserved(self):
        delivery = self._delivery_fed_through_transit()
        transit = delivery.location_id
        self.assertEqual(delivery.state, "assigned")
        batch = self._batch(self._picking(), dock_id=self.dock.id)

        batch.picking_ids = [Command.link(delivery.id)]
        delivery.invalidate_recordset()
        self.assertEqual(
            delivery.move_ids.location_id,
            transit,
            "The goods wait in the transit the earlier leg filled; re-sourcing "
            "the delivery at the dock left it waiting for goods that are not there.",
        )
        self.assertEqual(delivery.state, "assigned")
        self.assertTrue(delivery.move_ids.move_line_ids)

    def test_docking_a_batch_keeps_a_delivery_fed_through_a_transit(self):
        delivery = self._delivery_fed_through_transit()
        batch = self._batch(delivery)

        batch.dock_id = self.dock
        delivery.invalidate_recordset()
        self.assertEqual(delivery.move_ids.location_id, delivery.location_id)
        self.assertEqual(delivery.state, "assigned")

    def test_clearing_the_dock_restores_the_transfer_own_source(self):
        picking = self._picking()
        batch = self._batch(picking, dock_id=self.dock.id)
        self.assertEqual(picking.move_ids.location_id, self.dock)

        batch.dock_id = False
        self.assertEqual(
            picking.move_ids.location_id,
            picking.location_id,
            "Only the destination was reset, so a cleared dock left the delivery "
            "sourced at the dock and no reservation could find its goods.",
        )

    def test_leaving_a_docked_batch_restores_the_transfer_own_source(self):
        picking = self._picking(quantity=3)
        self._batch(picking, dock_id=self.dock.id)
        self.assertEqual(picking.move_ids.location_id, self.dock)

        picking.batch_id = False
        self.assertEqual(picking.move_ids.location_id, picking.location_id)
        picking.action_assign()
        self.assertEqual(picking.state, "assigned")

    def test_the_vehicle_and_the_load_sit_in_the_batch_column(self):
        form = self.env.ref("stock_picking_batch.stock_picking_batch_form")
        arch = etree.fromstring(
            self.env["stock.picking.batch"].get_view(form.id, "form")["arch"]
        )
        for name in ("vehicle_id", "operator_id", "vehicle_model_id"):
            field = arch.xpath(f"//field[@name='{name}']")[0]
            self.assertEqual(
                field.getparent().get("id"),
                "batch_delivery_data",
                "As a group of its own it sat below the taller trip section and "
                "left a gap under the description.",
            )

    def test_a_transfer_added_after_the_batch_exists_is_sequenced_too(self):
        near = self._picking(zip_code="1000")
        batch = self._batch(near)
        far = self._picking(zip_code="9000")
        middle = self._picking(zip_code="5000")
        batch.picking_ids = [Command.link(far.id), Command.link(middle.id)]
        self.assertEqual(
            [near.batch_sequence, middle.batch_sequence, far.batch_sequence],
            [1, 2, 3],
            "order_on_zip ran in create only, so a transfer joining an existing "
            "batch kept sequence 0 and the route order the map view and the "
            "report read was absent.",
        )
