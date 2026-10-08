import ast
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, RedirectWarning, UserError, ValidationError
from odoo.service.model import call_kw
from odoo.tests import TransactionCase, tagged
from odoo.tools.authority_keys import strip_authority_keys


@tagged("post_install", "-at_install")
class TestTrip(TransactionCase):
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

        cls.driver_user = cls.env["res.users"].create(
            {
                "name": "Driver",
                "login": "trip_driver",
                "group_ids": [
                    Command.set([cls.env.ref("stock_fleet.group_trip_driver").id])
                ],
            }
        )
        cls.supervisor = cls.env["res.users"].create(
            {
                "name": "Supervisor",
                "login": "trip_supervisor",
                "group_ids": [Command.set([cls.env.ref("stock.group_stock_user").id])],
            }
        )
        cls.corrector = cls.env["res.users"].create(
            {
                "name": "Corrector",
                "login": "trip_corrector",
                "group_ids": [
                    Command.set([cls.env.ref("stock_fleet.group_trip_correction").id])
                ],
            }
        )
        cls.driver = cls.env["hr.employee"].create(
            {"name": "Driver", "user_id": cls.driver_user.id}
        )
        cls.other_driver = cls.env["hr.employee"].create({"name": "Other Driver"})
        cls.model = cls.env["product.product"].create(
            {
                "name": "Test Truck",
                "type": "consu",
                "asset_kind_id": cls.env.ref("resource_asset.kind_vehicle").id,
            }
        )
        cls.vehicle = cls.env["resource.resource"].create(
            {
                "name": "Truck",
                "kind_id": cls.env.ref("resource_asset.kind_vehicle").id,
                "product_id": cls.model.id,
                "operator_id": cls.driver.resource_id.id,
            }
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Freight", "is_storable": True, "weight": 10.0}
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.stock_location, 1000
        )

    def _picking(self, quantity=1, product=None):
        product = product or self.product
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.out_type.id,
                "partner_id": self.env["res.partner"].create({"name": "Customer"}).id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_uom_qty": quantity,
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

    def _trip(self, pickings, **vals):
        return self.env["stock.picking.batch"].create(
            {
                "picking_type_id": self.out_type.id,
                "picking_ids": [Command.set(pickings.ids)],
                "vehicle_id": self.vehicle.id,
                "operator_id": self.driver.id,
                "supervisor_id": self.supervisor.id,
                "odometer_departure": 1000.0,
                **vals,
            }
        )

    def test_the_operator_is_chosen_per_trip_not_taken_from_the_vehicle(self):
        # The vehicle's holder (self.driver) takes it home; who drives a trip is
        # chosen for that trip.
        trip = self._trip(self._picking(), operator_id=False)
        self.assertFalse(trip.operator_id)
        self.assertFalse(trip.driver_id)
        self.assertEqual(trip.trip_state, "planned")
        with self.assertRaisesRegex(UserError, "Operator"):
            trip.action_depart()
        trip.operator_id = self.other_driver
        self.assertEqual(trip.driver_id, self.other_driver.partner_id)

    def test_a_custody_change_does_not_reach_the_trip(self):
        trip = self._trip(self._picking())
        trip.action_depart()
        self.vehicle.operator_id = self.other_driver.resource_id
        trip.invalidate_recordset()
        self.assertEqual(trip.operator_id, self.driver)
        self.assertEqual(trip.driver_id, self.driver.partner_id)

    def test_departure_stamps_and_freezes_the_trip(self):
        trip = self._trip(self._picking())
        trip.action_depart()
        self.assertTrue(trip.date_departure)
        self.assertEqual(trip.departed_uid, self.env.user)
        self.assertEqual(trip.trip_state, "in_transit")
        with self.assertRaises(UserError):
            trip.write({"operator_id": self.other_driver.id})
        with self.assertRaises(UserError):
            trip.write({"odometer_departure": 1500.0})
        trip.write({"odometer_departure": 1000.0})  # same value: not a change

    def test_departure_lists_what_is_missing(self):
        trip = self._trip(self._picking(), supervisor_id=False, odometer_departure=0.0)
        with self.assertRaisesRegex(UserError, "Supervisor"):
            trip.action_depart()

    def test_the_supervisor_cannot_be_the_operator(self):
        trip = self._trip(self._picking(), supervisor_id=self.driver_user.id)
        with self.assertRaisesRegex(UserError, "cannot be its operator"):
            trip.action_depart()

    def test_a_trip_does_not_leave_with_transfers_that_are_not_ready(self):
        missing = self.env["product.product"].create(
            {"name": "Out of stock", "is_storable": True}
        )
        picking = self._picking(product=missing)
        self.assertEqual(picking.state, "confirmed")
        trip = self._trip(picking)
        with self.assertRaisesRegex(UserError, "not ready"):
            trip.action_depart()

    def test_a_transfer_outside_a_departed_trip_is_not_validated(self):
        loose = self._picking()
        with self.assertRaisesRegex(UserError, "must be delivered from a trip"):
            loose.button_validate()
        picking = self._picking()
        self._trip(picking)
        with self.assertRaisesRegex(UserError, "has not departed"):
            picking.button_validate()

    def test_a_type_without_the_rule_validates_freely(self):
        self.out_type.dispatch_batch_required = False
        picking = self._picking()
        picking.move_ids.picked = True
        picking.button_validate()
        self.assertEqual(picking.state, "done")

    def test_a_delivery_rides_the_vehicle_whether_or_not_trips_are_compulsory(self):
        picking = self._picking()
        for compulsory in (True, False):
            with self.subTest(compulsory=compulsory):
                self.out_type.dispatch_batch_required = compulsory
                self.assertTrue(picking._rides_trip_vehicle())
                self.assertEqual(picking._requires_trip(), compulsory)
                self.assertTrue(picking._trip_vehicle_returns())

    def test_a_receipt_never_rides_the_trip_vehicle(self):
        in_type = self.warehouse.in_type_id
        in_type.dispatch_batch_required = True
        receipt = self.env["stock.picking"].create(
            {
                "picking_type_id": in_type.id,
                "location_id": self.env.ref("stock.stock_location_suppliers").id,
                "location_dest_id": self.stock_location.id,
            }
        )
        self.assertFalse(receipt._rides_trip_vehicle())
        self.assertFalse(receipt._requires_trip())

    def test_the_driver_delivers_and_the_transfer_stays_on_the_trip(self):
        picking = self._picking()
        trip = self._trip(picking)
        trip.action_depart()
        picking.action_deliver()
        self.assertEqual(picking.state, "done")
        self.assertEqual(picking.batch_id, trip)
        self.assertEqual(trip.trip_delivered_count, 1)

    def test_an_undelivered_stop_leaves_the_trip_with_its_reason(self):
        delivered, failed = self._picking(), self._picking()
        trip = self._trip(delivered | failed)
        trip.action_depart()
        absent = self.env.ref("stock_fleet.unbatch_reason_customer_absent")
        wizard = self.env["wizard.stock.picking.unbatch.undelivered"].create(
            {"picking_id": failed.id, "reason_id": absent.id, "note": "Gate closed"}
        )
        wizard.action_confirm()
        self.assertFalse(failed.batch_id)
        self.assertEqual(failed.delivery_failure_reason_id, absent)
        self.assertEqual(failed.delivery_failure_reason, "Customer absent: Gate closed")
        self.assertEqual(failed.state, "assigned")
        self.assertEqual(trip.picking_ids, delivered)

    def test_the_return_closes_the_trip_and_logs_the_odometer(self):
        picking = self._picking()
        trip = self._trip(picking)
        trip.action_depart()
        picking.action_deliver()
        with self.assertRaisesRegex(UserError, "odometer at return"):
            trip.action_return()
        with self.assertRaises(ValidationError):
            trip.odometer_return = 900.0
        trip.odometer_return = 1250.0
        trip.action_return()
        self.assertEqual(trip.trip_state, "closed")
        log = self.env["resource.log"].search([("picking_batch_id", "=", trip.id)])
        self.assertEqual(log.odometer, 1250.0)
        self.assertEqual(log.source, "delivery")
        with self.assertRaises(UserError):
            trip.odometer_return = 1300.0

    def test_a_reader_of_the_vehicle_dates_the_departure_and_the_return(self):
        picking = self._picking()
        trip = self._trip(picking, odometer_return=1250.0)
        now = fields.Datetime.now()
        left, back = now - timedelta(hours=3), now - timedelta(hours=1)
        trip.with_context(trip_departure_date=left).action_depart()
        self.assertEqual(trip.date_departure, left)
        picking.action_deliver()
        with self.assertRaisesRegex(UserError, "before the trip departed"):
            trip.with_context(
                trip_return_date=left - timedelta(minutes=1)
            ).action_return()
        with self.assertRaisesRegex(UserError, "in the future"):
            trip.with_context(trip_return_date=now + timedelta(hours=1)).action_return()
        trip.with_context(trip_return_date=back).action_return()
        self.assertEqual(trip.date_return, back)

    def test_a_batch_that_does_not_dispatch_has_no_trip_state(self):
        in_type = self.warehouse.in_type_id
        in_type.dispatch_management = False
        batch = self.env["stock.picking.batch"].create({"picking_type_id": in_type.id})
        self.assertFalse(batch.trip_state)

    def test_a_done_batch_that_never_left_is_not_a_trip(self):
        self.out_type.dispatch_batch_required = False
        picking = self._picking()
        batch = self._trip(picking, vehicle_id=False)
        picking.move_ids.picked = True
        batch.action_done()
        self.assertEqual(batch.state, "done")
        self.assertFalse(batch.trip_state)

    def test_a_batch_with_its_vehicle_is_validated_only_once_departed(self):
        # Even where trips are optional, transfers put on a vehicle are delivered
        # from its trip.
        self.out_type.dispatch_batch_required = False
        picking = self._picking()
        trip = self._trip(picking)
        picking.move_ids.picked = True
        with self.assertRaisesRegex(UserError, "has not departed"):
            trip.action_done()

    def test_the_batch_validates_its_transfers_inside_a_departed_trip(self):
        pickings = self._picking() | self._picking()
        trip = self._trip(pickings)
        trip.action_depart()
        pickings.move_ids.picked = True
        trip.action_done()
        self.assertEqual(set(pickings.mapped("state")), {"done"})
        self.assertEqual(trip.trip_state, "in_transit")

    def test_no_transfer_boards_a_trip_that_already_left(self):
        trip = self._trip(self._picking())
        trip.action_depart()
        late = self._picking()
        with self.assertRaisesRegex(UserError, "cannot be added"):
            late.batch_id = trip
        with self.assertRaisesRegex(UserError, "cannot be added"):
            trip.picking_ids |= late
        self.assertFalse(late.batch_id)

    def test_a_pending_transfer_cannot_leave_a_departed_trip(self):
        pending, other = self._picking(), self._picking()
        trip = self._trip(pending | other)
        trip.action_depart()
        with self.assertRaisesRegex(
            RedirectWarning, "only as not delivered"
        ) as refusal:
            pending.batch_id = False
        action = refusal.exception.args[1]
        self.assertEqual(
            action["res_model"], "wizard.stock.picking.unbatch.undelivered"
        )
        self.assertEqual(
            action["views"],
            [(False, "form")],
            "The client reads the views of an action a RedirectWarning carries; "
            "without them the button crashed on 'map' of undefined.",
        )
        self.assertEqual(
            action["context"]["default_picking_id"],
            pending.id,
            "The refusal opens the reasons for the transfer, so the way out is one "
            "click away instead of a dead end.",
        )
        with self.assertRaisesRegex(RedirectWarning, "only as not delivered"):
            trip.picking_ids = [Command.unlink(pending.id)]
        with self.assertRaisesRegex(RedirectWarning, "only as not delivered"):
            pending.batch_id = self._trip(self._picking())
        self.assertEqual(
            trip.picking_ids,
            pending | other,
            "A departed trip is the record of what the vehicle carried; a transfer "
            "taken off it by hand left no reason for coming back.",
        )

    def test_a_transfer_on_a_trip_is_not_added_to_another(self):
        picking = self._picking()
        trip = self._trip(picking)
        other = self._trip(self._picking())
        with self.assertRaisesRegex(UserError, "is already on"):
            picking.batch_id = other
        with self.assertRaisesRegex(UserError, "is already on"):
            other.picking_ids = [Command.link(picking.id)]
        self.assertEqual(
            picking.batch_id,
            trip,
            "Adding it to another batch moved it without warning, and the first "
            "trip lost a stop nobody had taken off.",
        )
        picking.batch_id = False
        other.picking_ids = [Command.link(picking.id)]
        self.assertEqual(picking.batch_id, other)

    def test_merging_trips_gathers_their_transfers(self):
        first, second = self._picking(), self._picking()
        trip = self._trip(first)
        (trip | self._trip(second)).action_merge()
        self.assertEqual(trip.picking_ids, first | second)

    def test_a_trip_offers_only_transfers_without_a_batch(self):
        taken, free = self._picking(), self._picking()
        self._trip(taken)
        trip = self._trip(self._picking())
        self.assertNotIn(taken, trip.allowed_picking_ids)
        self.assertIn(free, trip.allowed_picking_ids)

    def test_a_transfer_leaves_a_trip_freely_before_it_departs(self):
        kept, removed = self._picking(), self._picking()
        trip = self._trip(kept | removed)
        removed.batch_id = False
        self.assertEqual(trip.picking_ids, kept)

    def test_a_partial_delivery_stays_on_the_departed_trip(self):
        picking, other = self._picking(quantity=5), self._picking()
        trip = self._trip(picking | other)
        trip.action_depart()
        picking.move_ids.quantity = 3
        picking.move_ids.picked = True
        picking.button_validate(skip_backorder=True)
        self.assertEqual(picking.state, "done")
        self.assertEqual(picking.batch_id, trip, "the trip records what it delivered")
        backorder = picking.backorder_ids
        self.assertTrue(backorder)
        self.assertFalse(backorder.batch_id, "the rest waits for the next trip")
        self.assertEqual(backorder.move_ids.product_uom_qty, 2)

    def test_the_batch_does_not_shed_a_pending_transfer_of_a_departed_trip(self):
        delivered, pending = self._picking(), self._picking()
        trip = self._trip(delivered | pending)
        trip.action_depart()
        delivered.move_ids.picked = True
        with self.assertRaisesRegex(RedirectWarning, "only as not delivered"):
            trip.action_done()

    def test_the_trip_does_not_close_with_a_stop_without_outcome(self):
        delivered, pending = self._picking(), self._picking()
        trip = self._trip(delivered | pending)
        trip.action_depart()
        delivered.action_deliver()
        trip.odometer_return = 1200.0
        with self.assertRaisesRegex(UserError, "have no outcome"):
            trip.action_return()
        self.assertFalse(
            trip.date_return,
            "The trip closed with a stop nobody delivered nor sent back, so the "
            "transfer stayed pending on a closed trip with no reason.",
        )
        self.env["wizard.stock.picking.unbatch.undelivered"].create(
            {
                "picking_id": pending.id,
                "reason_id": self.env.ref(
                    "stock_fleet.unbatch_reason_customer_absent"
                ).id,
            }
        ).action_confirm()
        trip.action_return()
        self.assertEqual(trip.trip_state, "closed")

    def test_a_departed_trip_cannot_be_cancelled(self):
        picking = self._picking()
        trip = self._trip(picking)
        trip.action_depart()
        with self.assertRaisesRegex(UserError, "cannot be cancelled"):
            trip.action_cancel()
        self.assertEqual(picking.batch_id, trip)

    def test_a_trip_that_has_not_left_can_be_cancelled(self):
        picking = self._picking()
        trip = self._trip(picking)
        trip.action_cancel()
        self.assertEqual(trip.state, "cancel")
        self.assertFalse(picking.batch_id)

    def _sheet(self, batch):
        return (
            self.env["ir.actions.report"]
            ._render_qweb_html("stock_picking_batch.report_picking_batch", batch.ids)[0]
            .decode()
        )

    def test_the_trip_sheet_names_the_crew_and_drops_the_office_columns(self):
        supervisor = self.env["res.users"].create(
            {"name": "Rosa Supervisa", "login": "rosa_supervisa"}
        )
        sheet = self._sheet(self._trip(self._picking(), supervisor_id=supervisor.id))
        self.assertIn("Rosa Supervisa", sheet)
        self.assertIn("Scheduled Date:", sheet)
        self.assertNotIn(
            'name="th_state"',
            sheet,
            "The sheet rides with the load; the operator scans each transfer's "
            "barcode, and its status and date belong to the office.",
        )

    def test_a_batch_that_does_not_dispatch_keeps_the_office_columns(self):
        in_type = self.warehouse.in_type_id
        in_type.dispatch_management = False
        batch = self.env["stock.picking.batch"].create({"picking_type_id": in_type.id})
        self.assertIn('<th name="th_state">Status</th>', self._sheet(batch))

    def test_the_trip_sheet_barcodes_are_wide_enough_for_a_phone(self):
        sheet = self._sheet(self._trip(self._picking() | self._picking()))
        self.assertEqual(sheet.count('name="td_trip_barcode"'), 2)
        self.assertEqual(sheet.count("width: 75mm; height: 11.25mm;"), 2)
        self.assertEqual(
            sheet.count("padding: 4mm 5mm;"),
            2,
            "The image is drawn without a quiet zone: the cell's padding is it.",
        )
        self.assertNotIn(
            "width:200px;height:50px;",
            sheet,
            "The office barcode prints 0.25 mm bars with no quiet zone: the "
            "operators' phones could not read one apart from the next.",
        )

    def test_the_sheet_title_is_the_batch_name_alone(self):
        trip = self._trip(self._picking())
        sheet = self._sheet(trip)
        self.assertNotIn("Summary:", sheet)
        self.assertIn(f"<h3><span>{trip.name}</span></h3>", sheet)

    def test_a_batch_that_does_not_dispatch_keeps_the_office_barcode(self):
        self.out_type.dispatch_management = False
        batch = self.env["stock.picking.batch"].create(
            {
                "picking_type_id": self.out_type.id,
                "picking_ids": [Command.set(self._picking().ids)],
            }
        )
        sheet = self._sheet(batch)
        self.assertIn("width:200px;height:50px;", sheet)
        self.assertNotIn('name="td_trip_barcode"', sheet)

    def test_a_transfer_opened_from_its_batch_can_be_validated_or_sent_back(self):
        view = self.env.ref("stock_picking_batch.view_stock_picking_form_inherited")
        arch = self.env["stock.picking"].get_view(view.id, "form")["arch"]
        self.assertIn('name="button_validate"', arch)
        self.assertIn('name="action_not_delivered"', arch)
        picking = self._picking()
        trip = self._trip(picking)
        self.assertFalse(picking.trip_date_departure)
        trip.action_depart()
        self.assertEqual(picking.trip_date_departure, trip.date_departure)

    def test_the_route_offers_only_the_reasons_given_on_the_route(self):
        reasons = self.env["stock.picking.unbatch.reason"]
        # The catalogue this module ships; other modules may add their own.
        shipped = self.env["ir.model.data"].search(
            [("module", "=", "stock_fleet"), ("model", "=", reasons._name)]
        )
        self.assertEqual(len(shipped), 8)
        wizard_model = self.env["wizard.stock.picking.unbatch.undelivered"]
        domain = wizard_model._fields["reason_id"].domain
        offered = reasons.search(ast.literal_eval(domain))
        self.assertNotIn(
            self.env.ref("stock_fleet.unbatch_reason_added_by_mistake"), offered
        )
        self.assertIn(self.env.ref("stock_fleet.unbatch_reason_credit_hold"), offered)

    def test_a_reason_given_before_departure_does_not_send_a_stop_back(self):
        picking = self._picking()
        self._trip(picking).action_depart()
        wizard = self.env["wizard.stock.picking.unbatch.undelivered"].create(
            {
                "picking_id": picking.id,
                "reason_id": self.env.ref(
                    "stock_fleet.unbatch_reason_added_by_mistake"
                ).id,
            }
        )
        with self.assertRaisesRegex(UserError, "before it leaves"):
            wizard.action_confirm()

    def test_a_departed_trip_cannot_be_deleted(self):
        trip = self._trip(self._picking())
        trip.action_depart()
        with self.assertRaisesRegex(UserError, "cannot be deleted"):
            trip.unlink()

    def test_the_driver_closes_the_trip_the_supervisor_dispatched(self):
        picking = self._picking()
        trip = self._trip(picking)
        driver_trip = trip.with_user(self.driver_user)
        with self.assertRaisesRegex(UserError, "not by its operator"):
            driver_trip.action_depart()
        trip.with_user(self.supervisor).action_depart()
        picking.with_user(self.driver_user).action_deliver()
        driver_trip.odometer_return = 1180.0
        driver_trip.action_return()
        self.assertEqual(trip.trip_state, "closed")
        log = (
            self.env["resource.log"].sudo().search([("picking_batch_id", "=", trip.id)])
        )
        self.assertEqual(log.odometer, 1180.0)

    def test_the_trip_sheet_prints_in_spanish(self):
        # The sheet's inheritance must not depend on the words of the language
        # it renders in: its headers are translated before it applies.
        self.env["res.lang"]._activate_lang("es_MX")
        self.env["ir.module.module"]._load_module_terms(
            ["stock_picking_batch", "stock_fleet"], ["es_MX"], overwrite=True
        )
        trip = self._trip(self._picking())
        html, _ = (
            self.env["ir.actions.report"]
            .with_context(lang="es_MX")
            ._render_qweb_html("stock_picking_batch.report_picking_batch", trip.ids)
        )
        self.assertIn(trip.name, html.decode())

    # ------------------------------------------------------------------
    # Taking a transfer off a departed trip as a correction
    # ------------------------------------------------------------------
    def _correction(self, trip, reason="unbatch_reason_added_by_mistake", user=None):
        return (
            self.env["wizard.stock.picking.unbatch.correction"]
            .with_user(user or self.corrector)
            .create(
                {
                    "batch_id": trip.id,
                    "reason_id": self.env.ref(f"stock_fleet.{reason}").id,
                }
            )
        )

    def test_a_transfer_that_should_not_travel_comes_off_as_a_correction(self):
        delivered, pending = self._picking(), self._picking()
        trip = self._trip(delivered | pending)
        trip.action_depart()
        delivered.action_deliver()
        wizard = self._correction(trip)
        self.assertEqual(
            wizard.picking_ids,
            pending,
            "The wizard offers the pending transfers, all ticked; a delivered one "
            "is what the vehicle carried and stays on the trip.",
        )
        wizard.note = "Loaded for the wrong route"
        wizard.action_confirm()
        self.assertFalse(pending.batch_id)
        self.assertEqual(pending.state, "assigned")
        self.assertFalse(
            pending.delivery_failure_reason_id,
            "A correction is not a delivery failure: nothing failed on the route.",
        )
        self.assertFalse(pending.delivery_failure_reason)
        self.assertEqual(trip.picking_ids, delivered)
        self.assertTrue(
            any(
                "as a correction: Added by mistake: Loaded for the wrong route"
                in str(message.body)
                for message in pending.message_ids
            )
        )
        self.assertTrue(
            any(
                f"{pending.name} taken off the trip as a correction"
                in str(message.body)
                for message in trip.message_ids
            )
        )
        self.assertEqual(trip.trip_state, "in_transit")

    def test_a_closed_trip_gives_up_the_transfers_left_pending(self):
        # Trips closed before they waited for their transfers kept the pending
        # ones trapped on them: the way out was a delivery failure.
        self.out_type.dispatch_batch_required = False
        pending = self._picking()
        trip = self._trip(pending)
        trip.action_depart()
        trip.write({"odometer_return": 1100.0, "date_return": fields.Datetime.now()})
        self.assertEqual(trip.trip_state, "closed")
        self._correction(
            trip, reason="unbatch_reason_operations_instruction"
        ).action_confirm()
        self.assertFalse(pending.batch_id)
        self.assertEqual(pending.state, "assigned")
        self.assertEqual(trip.trip_state, "closed")
        self.assertEqual(
            trip.state,
            "done",
            "A closed trip left without transfers ended with no deliveries; it is "
            "not cancelled, since the vehicle did go out.",
        )

    def test_without_the_rule_a_departed_trip_waits_for_its_transfers(self):
        self.out_type.dispatch_batch_required = False
        pending = self._picking()
        trip = self._trip(pending)
        trip.action_depart()
        trip.odometer_return = 1100.0
        with self.assertRaisesRegex(UserError, "have no outcome"):
            trip.action_return()
        pending.action_deliver()
        trip.action_return()
        self.assertEqual(trip.trip_state, "closed")

    def test_without_the_rule_a_transfer_on_a_trip_is_delivered_from_it(self):
        self.out_type.dispatch_batch_required = False
        picking = self._picking()
        self.assertFalse(picking._requires_trip())
        trip = self._trip(picking)
        self.assertTrue(picking._requires_trip())
        with self.assertRaisesRegex(UserError, "has not departed"):
            picking.button_validate()
        trip.action_depart()
        picking.action_deliver()
        self.assertEqual(picking.state, "done")

    def test_only_trip_corrections_take_a_transfer_off_a_departed_trip(self):
        pending = self._picking()
        trip = self._trip(pending)
        trip.action_depart()
        with self.assertRaises(AccessError):
            self._correction(trip, user=self.supervisor)
        with self.assertRaisesRegex(RedirectWarning, "only as not delivered"):
            pending.with_user(self.supervisor).with_context(
                trip_unbatch_correction=True
            ).write({"batch_id": False})
        self.assertEqual(
            pending.batch_id,
            trip,
            "The context key alone opened the way; the correction is the group's.",
        )
        self.assertEqual(
            strip_authority_keys({"trip_unbatch_correction": True, "lang": "en_US"}),
            {"lang": "en_US"},
            "A client does not send the correction key: only the wizard sets it.",
        )

    def test_a_correction_is_not_a_route_failure_nor_a_delivered_stop(self):
        delivered, pending = self._picking(), self._picking()
        trip = self._trip(delivered | pending)
        wizard = self._correction(trip)
        with self.assertRaisesRegex(UserError, "has not left"):
            wizard.action_confirm()
        trip.action_depart()
        delivered.action_deliver()
        with self.assertRaisesRegex(UserError, "travelled and came back"):
            self._correction(
                trip, reason="unbatch_reason_customer_absent"
            ).action_confirm()
        wizard = self._correction(trip)
        wizard.picking_ids = delivered | pending
        with self.assertRaisesRegex(UserError, "only its pending"):
            wizard.action_confirm()
        self.assertEqual(trip.picking_ids, delivered | pending)
        reasons = self.env["stock.picking.unbatch.reason"].search(
            ast.literal_eval(wizard._fields["reason_id"].domain)
        )
        self.assertIn(
            self.env.ref("stock_fleet.unbatch_reason_operations_instruction"), reasons
        )
        self.assertIn(self.env.ref("stock_fleet.unbatch_reason_credit_hold"), reasons)
        self.assertNotIn(
            self.env.ref("stock_fleet.unbatch_reason_customer_absent"), reasons
        )

    def test_a_vehicle_does_not_leave_while_a_trip_of_it_is_on_the_road(self):
        first = self._trip(self._picking())
        first.action_depart()
        second = self._trip(self._picking(), operator_id=self.other_driver.id)
        with self.assertRaisesRegex(UserError, "still out on trip"):
            second.action_depart()
        self.assertFalse(second.date_departure)
        first.picking_ids.action_deliver()
        first.odometer_return = 1100.0
        first.action_return()
        second.odometer_departure = 1100.0
        second.action_depart()
        self.assertEqual(
            second.trip_state,
            "in_transit",
            "Once the vehicle's last trip is back, it leaves again.",
        )

    def test_a_rescue_vehicle_leaves_with_the_crew_of_a_trip_on_the_road(self):
        # In a breakdown the operator moves on to another vehicle: only the vehicle
        # is held to one trip at a time.
        broken = self._trip(self._picking())
        broken.action_depart()
        rescue_vehicle = self.env["resource.resource"].create(
            {
                "name": "Rescue Truck",
                "kind_id": self.env.ref("resource_asset.kind_vehicle").id,
                "product_id": self.model.id,
            }
        )
        rescue = self._trip(self._picking(), vehicle_id=rescue_vehicle.id)
        rescue.action_depart()
        self.assertEqual(rescue.operator_id, broken.operator_id)
        self.assertEqual(rescue.trip_state, "in_transit")

    def test_a_client_cannot_open_a_departed_trip_with_a_context_key(self):
        pending, other = self._picking(), self._picking()
        trip = self._trip(pending | other)
        trip.action_depart()
        for key in (
            "trip_unbatch_undelivered",
            "trip_unbatch_correction",
            "trip_merge",
        ):
            self.assertEqual(
                strip_authority_keys({key: True, "lang": "en_US"}),
                {"lang": "en_US"},
                f"A client sends {key} and skips the lock it opens.",
            )
        pickings = self.env["stock.picking"].with_user(self.supervisor)
        with self.assertRaisesRegex(RedirectWarning, "only as not delivered"):
            call_kw(
                pickings,
                "write",
                [pending.ids, {"batch_id": False}],
                {"context": {"trip_unbatch_undelivered": True}},
            )
        self.assertEqual(
            trip.picking_ids,
            pending | other,
            "Any stock user took a transfer off a departed trip by RPC, with no "
            "reason and without the trip corrections group.",
        )

    def test_a_trip_emptied_on_the_route_stays_out_until_it_returns(self):
        picking = self._picking()
        trip = self._trip(picking)
        trip.action_depart()
        self.env["wizard.stock.picking.unbatch.undelivered"].create(
            {
                "picking_id": picking.id,
                "reason_id": self.env.ref(
                    "stock_fleet.unbatch_reason_customer_absent"
                ).id,
            }
        ).action_confirm()
        self.assertFalse(trip.picking_ids)
        self.assertEqual(
            trip.trip_state,
            "in_transit",
            "The last stop came back and the batch cancelled itself with the "
            "vehicle still on the road, hiding the return.",
        )
        trip.odometer_return = 1150.0
        trip.action_return()
        self.assertEqual(trip.trip_state, "closed")
        self.assertEqual(trip.state, "done")
