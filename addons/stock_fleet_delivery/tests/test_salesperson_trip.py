from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSalespersonTrip(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.customer_location = cls.env.ref("stock.stock_location_customers")
        cls.out_type = cls.warehouse.out_type_id
        cls.out_type.write(
            {"dispatch_management": True, "dispatch_batch_required": True}
        )
        cls.seller_user = cls.env["res.users"].create(
            {
                "name": "Seller",
                "login": "trip_seller",
                "group_ids": [
                    Command.set([cls.env.ref("stock_fleet.group_trip_driver").id])
                ],
            }
        )
        cls.supervisor = cls.env["res.users"].create(
            {
                "name": "Supervisor",
                "login": "trip_seller_supervisor",
                "group_ids": [Command.set([cls.env.ref("stock.group_stock_user").id])],
            }
        )
        cls.seller = cls.env["hr.employee"].create(
            {"name": "Seller", "user_id": cls.seller_user.id}
        )
        model = cls.env["product.product"].create(
            {
                "name": "Pickup",
                "type": "consu",
                "asset_kind_id": cls.env.ref("base.kind_vehicle").id,
            }
        )
        cls.car = cls.env["resource.resource"].create(
            {
                "name": "Seller's pickup",
                "kind_id": cls.env.ref("base.kind_vehicle").id,
                "product_id": model.id,
                "operator_id": cls.seller.resource_id.id,
            }
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Fertilizer", "is_storable": True}
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.stock_location, 100
        )
        service = cls.env["product.product"].create(
            {"name": "Freight", "type": "service"}
        )
        cls.carriers = {
            mode: cls.env["delivery.carrier"].create(
                {
                    "name": mode,
                    "delivery_type": "fixed",
                    "product_id": service.id,
                    "dispatch_mode": mode,
                }
            )
            for mode in ("own_fleet", "salesperson")
        }

    def _picking(self, mode):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.out_type.id,
                "partner_id": self.env["res.partner"].create({"name": "Farmer"}).id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "carrier_id": self.carriers[mode].id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1,
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.customer_location.id,
                        }
                    )
                ],
            }
        )
        picking.action_confirm()
        picking.action_assign()
        return picking

    def _trip(self, mode, count=1):
        pickings = self.env["stock.picking"].browse(
            [self._picking(mode).id for _index in range(count)]
        )
        return self.env["stock.picking.batch"].create(
            {
                "picking_type_id": self.out_type.id,
                "picking_ids": [Command.set(pickings.ids)],
                "vehicle_id": self.car.id,
                "operator_id": self.seller.id,
                "supervisor_id": self.supervisor.id,
                "odometer_departure": 1000.0,
            }
        )

    def test_a_salesperson_dispatches_their_own_trip(self):
        trip = self._trip("salesperson")
        trip.with_user(self.seller_user).action_depart()
        self.assertTrue(trip.date_departure)
        self.assertEqual(trip.departed_uid, self.seller_user)

    def test_a_fleet_driver_still_waits_for_the_office(self):
        trip = self._trip("own_fleet")
        with self.assertRaises(UserError):
            trip.with_user(self.seller_user).action_depart()

    def test_a_salesperson_trip_closes_at_its_last_delivery(self):
        trip = self._trip("salesperson", count=2)
        trip.with_user(self.seller_user).action_depart()
        first, last = trip.picking_ids

        first.with_user(self.seller_user).action_deliver()
        self.assertFalse(trip.date_return)
        last.with_user(self.seller_user).action_deliver()

        self.assertTrue(trip.date_return)
        self.assertEqual(trip.trip_state, "closed")
        self.assertFalse(trip.odometer_return)

    def test_a_salesperson_trip_closes_when_its_last_stop_fails(self):
        trip = self._trip("salesperson", count=2)
        trip.with_user(self.seller_user).action_depart()
        first, last = trip.picking_ids

        first.with_user(self.seller_user).action_deliver()
        last._register_delivery_failure("Nobody at the ranch")

        self.assertTrue(trip.date_return)

    def test_a_fleet_trip_waits_for_the_vehicle_to_come_back(self):
        trip = self._trip("own_fleet")
        trip.action_depart()
        trip.picking_ids.action_deliver()
        self.assertFalse(trip.date_return)
        with self.assertRaises(UserError):
            trip.action_return()

    def test_whoever_delivered_is_reminded_of_the_paper_slip(self):
        self.out_type.write({"delivery_proof_required": True, "delivery_paper_days": 3})
        self.out_type.delivery_proof_since = fields.Datetime.now() - timedelta(days=30)
        trip = self._trip("salesperson")
        trip.with_user(self.seller_user).action_depart()
        picking = trip.picking_ids
        picking.with_user(
            self.seller_user
        ).delivery_proof = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        picking.with_user(self.seller_user).action_deliver()
        picking.date_done -= timedelta(days=10)

        self.env["stock.picking"]._cron_remind_delivery_paper()
        self.env["stock.picking"]._cron_remind_delivery_paper()

        self.assertEqual(picking.activity_ids.user_id, self.seller_user)
        self.assertEqual(len(picking.activity_ids), 1)

        picking.delivery_paper_received = True
        self.assertFalse(
            self.env["stock.picking"].search(
                [
                    ("id", "=", picking.id),
                    ("delivery_paper_received", "=", False),
                ]
            )
        )
