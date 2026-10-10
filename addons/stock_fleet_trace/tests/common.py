from odoo import Command


class TripFixtureMixin:
    """A CDG-like delivery flow, a traced trip type, a driver and vehicles."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.customer_location = cls.env.ref("stock.stock_location_customers")
        cls.transit = cls.env["stock.location"].create(
            {
                "name": "Shipping transit",
                "usage": "transit",
                "location_id": cls.warehouse.view_location_id.id,
                "company_id": cls.warehouse.company_id.id,
            }
        )
        cls.out_type = cls.warehouse.out_type_id
        cls.out_type.write(
            {
                "dispatch_management": True,
                "dispatch_batch_required": True,
                "trip_trace": True,
            }
        )
        cls.supervisor = cls.env["res.users"].create(
            {
                "name": "Supervisor",
                "login": "drv_supervisor",
                "group_ids": [
                    Command.set([cls.env.ref("stock.group_stock_manager").id])
                ],
            }
        )
        driver_group = cls.env.ref("stock_fleet.group_trip_driver")
        cls.driver_user = cls.env["res.users"].create(
            {
                "name": "Driver",
                "login": "drv_driver",
                "lang": "en_US",
                "group_ids": [Command.set([driver_group.id])],
            }
        )
        cls.driver = cls.env["hr.employee"].create(
            {"name": "Driver", "user_id": cls.driver_user.id}
        )
        cls.other_driver = cls.env["hr.employee"].create({"name": "Other Driver"})
        cls.rescue_driver = cls.env["hr.employee"].create({"name": "Rescue Driver"})
        kind = cls.env.ref("resource.kind_vehicle")
        model = cls.env["product.product"].create(
            {"name": "Test Truck", "type": "consu", "asset_kind_id": kind.id}
        )
        cls.vehicle = cls.env["resource.resource"].create(
            {"name": "Truck", "kind_id": kind.id, "product_id": model.id}
        )
        cls.rescue_vehicle = cls.env["resource.resource"].create(
            {"name": "Rescue Truck", "kind_id": kind.id, "product_id": model.id}
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Fertiliser", "is_storable": True, "weight": 20.0}
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.stock_location, 1000
        )
        cls.absent = cls.env.ref("stock_fleet.unbatch_reason_customer_absent")

    def _delivery(self, quantity):
        """A delivery fed through the shipping transit, as CDG runs SHIP -> OUT."""
        delivery = self.env["stock.picking"].create(
            {
                "picking_type_id": self.out_type.id,
                "partner_id": self.env["res.partner"].create({"name": "Cliente"}).id,
                "location_id": self.transit.id,
                "location_dest_id": self.customer_location.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": quantity,
                            "location_id": self.transit.id,
                            "location_dest_id": self.customer_location.id,
                        }
                    )
                ],
            }
        )
        ship = self.env["stock.picking"].create(
            {
                "picking_type_id": self.warehouse.int_type_id.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.transit.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": quantity,
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.transit.id,
                            "move_dest_ids": [Command.link(delivery.move_ids.id)],
                        }
                    )
                ],
            }
        )
        delivery.action_confirm()
        ship.action_confirm()
        ship.action_assign()
        ship.move_ids.picked = True
        ship.button_validate()
        delivery.action_assign()
        return delivery

    def _trip(self, pickings, operator=None, supervisor=None):
        return self.env["stock.picking.batch"].create(
            {
                "picking_type_id": self.out_type.id,
                "picking_ids": [Command.set(pickings.ids)],
                "vehicle_id": self.vehicle.id,
                "operator_id": (operator or self.driver).id,
                "supervisor_id": (supervisor or self.supervisor).id,
                "odometer_departure": 1000.0,
                "fuel_departure": 80.0,
            }
        )


class OfflineEventsMixin:
    """What the driver's phone sends: events chained as it chains them."""

    def _chain(self, trip, events):
        """Set prev_hash/event_hash on ``events`` as the phone would, in order."""
        Event = self.env["stock.trip.offline.event"]
        chain_hash = trip._trip_last_event_hash()
        for event in events:
            event["prev_hash"] = chain_hash
            event["event_hash"] = Event._trip_hash_event(event)
            chain_hash = event["event_hash"]
        return events

    def _send(self, trip, *events, user=None, chain=True, head=None):
        """Send events as the driver's phone does, one dict per event."""
        events = list(events)
        if chain:
            self._chain(trip, events)
        trip = trip.with_user(user or self.driver_user)
        return trip._trip_receive_offline_events(events, head=head)

    def _event(self, uuid, event_type, picking=None, **payload):
        return {
            "client_uuid": uuid,
            "event_type": event_type,
            "picking_id": picking.id if picking else False,
            "payload": payload,
            "captured_at": "2026-09-29T15:30:00Z",
            "latitude": 20.6597,
            "longitude": -103.3496,
            "device_uuid": "phone-1",
        }
