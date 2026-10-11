from datetime import timedelta

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.mail.tests.common import mail_new_test_user


class VisitDeliveriesSetup:
    """A seller with a trip under way, and customers to visit."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.customer_location = cls.env.ref("stock.stock_location_customers")
        cls.out_type = cls.warehouse.out_type_id
        cls.out_type.write(
            {"dispatch_management": True, "dispatch_batch_required": True}
        )
        cls.visitor = mail_new_test_user(
            cls.env,
            login="visit_seller",
            groups="planning.group_planning_user,stock_fleet.group_trip_driver",
            name="Seller",
        )
        cls.visitor_employee = cls.env["hr.employee"].create(
            {"name": "Seller", "user_id": cls.visitor.id, "tz": "UTC"}
        )
        cls.driver = cls.env["hr.employee"].create({"name": "Driver"})
        cls.supervisor = mail_new_test_user(
            cls.env, login="visit_supervisor", groups="stock.group_stock_user"
        )
        kind = cls.env.ref("base.kind_vehicle")
        pickup_model = cls.env["product.product"].create(
            {"name": "Pickup model", "type": "consu", "asset_kind_id": kind.id}
        )
        cls.vehicle = cls.env["resource.resource"].create(
            {"name": "Pickup", "kind_id": kind.id, "product_id": pickup_model.id}
        )
        # A vehicle is on one trip at a time: a second trip on the road takes another.
        cls.other_vehicle = cls.env["resource.resource"].create(
            {"name": "Truck", "kind_id": kind.id, "product_id": pickup_model.id}
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Fertilizer", "is_storable": True}
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.stock_location, 100
        )
        cls.customer = cls.env["res.partner"].create(
            {"name": "Rancho El Sabino", "is_company": True}
        )
        cls.customer_barn = cls.env["res.partner"].create(
            {"name": "Bodega", "type": "delivery", "parent_id": cls.customer.id}
        )
        cls.other_customer = cls.env["res.partner"].create({"name": "La Joya"})

    def _picking(self, partner):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.out_type.id,
                "partner_id": partner.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
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

    def _trip(self, pickings, operator=None, depart=True, vehicle=None):
        trip = self.env["stock.picking.batch"].create(
            {
                "picking_type_id": self.out_type.id,
                "picking_ids": [Command.set(pickings.ids)],
                "vehicle_id": (vehicle or self.vehicle).id,
                "operator_id": (operator or self.visitor_employee).id,
                "supervisor_id": self.supervisor.id,
                "odometer_departure": 1000.0,
            }
        )
        if depart:
            trip.action_depart()
        return trip

    def _visit(self, **values):
        Slot = self.env["planning.slot"].with_user(self.visitor)
        vals = Slot.with_context(field_service_declare_visit=True).default_get(
            list(Slot._fields)
        )
        vals.update({"partner_id": self.customer.id, **values})
        return Slot.create(vals)


@tagged("post_install", "-at_install")
class TestVisitDeliveries(VisitDeliveriesSetup, TransactionCase):
    def test_starting_a_visit_brings_the_customer_goods_on_the_trip(self):
        his = self._picking(self.customer_barn)
        elsewhere = self._picking(self.other_customer)
        self._trip(his | elsewhere)
        on_another_trip = self._picking(self.customer)
        self._trip(on_another_trip, operator=self.driver, vehicle=self.other_vehicle)

        visit = self._visit()
        visit.action_sign_in()

        self.assertEqual(visit.picking_ids, his)

    def test_the_visit_completes_once_every_delivery_has_an_outcome(self):
        delivered, returned = self._picking(self.customer), self._picking(self.customer)
        self._trip(delivered | returned)
        visit = self._visit()
        visit.action_sign_in()
        self.assertEqual(visit.picking_ids, delivered | returned)

        with self.assertRaisesRegex(UserError, "delivered or not delivered"):
            visit.action_complete()

        delivered.with_user(self.visitor).action_deliver()
        unbatch = self.env["wizard.stock.picking.unbatch.undelivered"]
        unbatch.with_user(self.visitor).create(
            {
                "picking_id": returned.id,
                "reason_id": self.env.ref(
                    "stock_fleet.unbatch_reason_customer_absent"
                ).id,
                "note": "Closed gate",
            }
        ).action_confirm()
        visit.action_complete()

        self.assertEqual(visit.state, "4_completed")
        self.assertEqual(delivered.state, "done")
        self.assertEqual(returned.state, "assigned", "it waits for the next trip")
        self.assertFalse(returned.planning_slot_id, "it leaves the visit")
        self.assertIn(
            "Closed gate",
            "".join(visit.message_ids.mapped("body")),
            "the visit keeps why the goods came back",
        )

    def test_goods_that_came_back_are_handed_over_on_the_next_visit(self):
        picking = self._picking(self.customer)
        trip = self._trip(picking)
        first = self._visit()
        first.action_sign_in()
        unbatch = self.env["wizard.stock.picking.unbatch.undelivered"]
        unbatch.with_user(self.visitor).create(
            {
                "picking_id": picking.id,
                "reason_id": self.env.ref(
                    "stock_fleet.unbatch_reason_customer_absent"
                ).id,
                "note": "Closed gate",
            }
        ).action_confirm()
        first.action_complete()
        # The vehicle came back with the goods: its trip closes before it leaves again.
        trip.write({"odometer_return": 1100.0})
        trip.action_return()

        self._trip(picking)
        second = self._visit()
        second.action_sign_in()

        self.assertEqual(second.picking_ids, picking)
        with self.assertRaisesRegex(UserError, "delivered or not delivered"):
            second.action_complete()

    def test_a_transfer_taken_off_the_trip_as_a_correction_leaves_the_visit(self):
        picking = self._picking(self.customer)
        trip = self._trip(picking)
        visit = self._visit()
        visit.action_sign_in()
        self.assertEqual(visit.picking_ids, picking)

        corrector = mail_new_test_user(
            self.env,
            login="visit_corrector",
            groups="stock_fleet.group_trip_correction",
        )
        self.env["wizard.stock.picking.unbatch.correction"].with_user(corrector).create(
            {
                "batch_id": trip.id,
                "reason_id": self.env.ref(
                    "stock_fleet.unbatch_reason_added_by_mistake"
                ).id,
            }
        ).action_confirm()

        self.assertFalse(picking.batch_id)
        self.assertFalse(
            picking.planning_slot_id,
            "it was not handed over on this visit; the next one ties it",
        )
        self.assertIn(
            "as a correction",
            "".join(visit.message_ids.mapped("body")),
            "the visit keeps why the transfer left it",
        )

    def test_a_trip_that_has_not_left_is_not_looked_at(self):
        self._trip(self._picking(self.customer), depart=False)
        visit = self._visit()
        visit.action_sign_in()
        self.assertFalse(visit.picking_ids)

    def test_a_visit_declared_after_the_trip_closed_records_that_day(self):
        picking = self._picking(self.customer)
        trip = self._trip(picking)
        picking.with_user(self.visitor).action_deliver()
        trip.write({"odometer_return": 1100.0})
        trip.action_return()
        self.assertEqual(trip.trip_state, "closed")

        start = picking.date_done
        visit = self._visit(
            start_datetime=start, end_datetime=start + timedelta(hours=1)
        )
        visit.action_complete()

        self.assertEqual(visit.picking_ids, picking)
        self.assertEqual(visit.state, "4_completed")

    def test_a_visit_on_another_day_does_not_take_that_delivery(self):
        picking = self._picking(self.customer)
        self._trip(picking)
        picking.with_user(self.visitor).action_deliver()

        start = picking.date_done - timedelta(days=2)
        visit = self._visit(
            start_datetime=start, end_datetime=start + timedelta(hours=1)
        )
        visit.action_complete()

        self.assertFalse(visit.picking_ids)

    def test_a_colleague_cannot_tie_deliveries_to_my_visit(self):
        visit = self._visit()
        colleague = mail_new_test_user(
            self.env, login="visit_colleague", groups="planning.group_planning_user"
        )
        with self.assertRaises(AccessError):
            visit.with_user(colleague).action_link_trip_deliveries()


@tagged("post_install", "-at_install")
class TestVisitDeliveriesUi(VisitDeliveriesSetup, HttpCase):
    def test_the_seller_delivers_from_the_visit(self):
        picking = self._picking(self.customer)
        self._trip(picking)
        visit = self._visit()
        visit.action_sign_in()

        self.start_tour(
            f"/odoo/my-visits/{visit.id}",
            "planning_field_service_deliver_on_visit",
            login="visit_seller",
        )

        self.assertEqual(picking.state, "done")
        self.assertEqual(visit.state, "4_completed")
