from odoo import Command
from odoo.tests import TransactionCase, tagged

from .common import TripFixtureMixin

REPORT = "stock_picking_batch.report_picking_batch"


@tagged("post_install", "-at_install")
class TestTripReport(TripFixtureMixin, TransactionCase):
    def _sheet(self, trip):
        html, _type = self.env["ir.actions.report"]._render_qweb_html(REPORT, trip.ids)
        return html.decode()

    def _stops(self, trip):
        return {stop["picking"]: stop for stop in trip._trip_report_stops()}

    def test_each_delivery_weighs_its_share_of_the_trip(self):
        delivered = self._delivery(5)
        absent = self._delivery(2)
        trip = self._trip(delivered | absent)
        trip.action_trip_load()
        trip.action_depart()
        delivered.action_deliver()
        self.env["wizard.stock.picking.unbatch.undelivered"].create(
            {"picking_id": absent.id, "reason_id": self.absent.id}
        ).action_confirm()

        stops = self._stops(trip)

        self.assertEqual(trip.weight_departure, 140.0)
        self.assertEqual(
            (stops[delivered]["departure"], stops[delivered]["delivered"]),
            (100.0, 100.0),
        )
        self.assertEqual(
            (stops[absent]["departure"], stops[absent]["back"]), (40.0, 40.0)
        )
        self.assertTrue(trip._trip_report_weights_match(list(stops.values())))
        sheet = self._sheet(trip)
        self.assertIn("o_trip_weights", sheet)
        self.assertIn(absent.name, sheet)

    def test_the_rescue_trip_rides_in_the_broken_down_trip_sheet(self):
        first = self._delivery(5)
        rest = self._delivery(2)
        trip = self._trip(first | rest)
        trip.action_trip_load()
        trip.action_depart()
        first.action_deliver()
        spill = self.env["stock.trip.incident"].create(
            {
                "batch_id": trip.id,
                "incident_type": "spill",
                "description": "A sack broke on the road",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": 1,
                            "picking_id": rest.id,
                        }
                    )
                ],
            }
        )
        spill.with_user(self.supervisor).action_approve()
        action = (
            self.env["wizard.stock.trip.handover"]
            .with_user(self.supervisor)
            .create(
                {
                    "batch_id": trip.id,
                    "vehicle_id": self.rescue_vehicle.id,
                    "operator_id": self.rescue_driver.id,
                    "odometer_departure": 500.0,
                    "fuel_departure": 60.0,
                    "reason": "Engine failure",
                }
            )
            .action_confirm()
        )
        rescue = self.env["stock.picking.batch"].browse(action["res_id"])

        stops = self._stops(trip)

        self.assertEqual(trip.trip_handover_to_ids, rescue)
        self.assertEqual(
            (
                stops[rest]["departure"],
                stops[rest]["written_off"],
                stops[rest]["handed_over"],
            ),
            (40.0, 20.0, 20.0),
        )
        self.assertIn(rescue.name, stops[rest]["outcome"])
        self.assertTrue(trip._trip_report_weights_match(list(stops.values())))
        sheet = self._sheet(trip)
        self.assertIn("o_trip_rescue", sheet)
        self.assertIn(rescue.name, sheet)
        self.assertIn("Rescue Driver", sheet)
        self.assertIn("Rescue Truck", sheet)
        self.assertIn(rest.name, sheet)
        self.assertIn("Engine failure", sheet)
        self.assertIn(trip.name, self._sheet(rescue))
        self.assertIn("o_trip_write_offs", sheet)
        self.assertIn(spill.name, sheet)
        self.assertIn(spill.scrap_ids.name, sheet)
        handover = trip.trip_support_picking_ids.filtered(
            lambda p: p.trip_support_kind == "handover"
        )
        self.assertIn(handover.name, sheet)
        breakdown = trip._trip_report_breakdown(rescue)
        self.assertIn(breakdown.description, sheet)
        self.assertLessEqual(breakdown.date, rescue.date_departure)
        rescue_rows = rescue._trip_report_stops()
        self.assertTrue(rescue._trip_report_weights_match(rescue_rows), rescue_rows)

    def test_a_loaded_trip_unloads_before_departing(self):
        trip = self._trip(self._delivery(3))
        trip.action_trip_load()

        action = trip.action_trip_unload()

        self.assertEqual(action["res_model"], "stock.picking")
        self.assertTrue(trip.unload_picking_id)

    def test_the_slip_names_who_signed_and_weighs_with_two_decimals(self):
        png = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY"
            "42YAAAAASUVORK5CYII="
        )
        self.product.weight = 0.333
        delivery = self._delivery(5)
        trip = self._trip(delivery)
        trip.action_trip_load()
        trip.action_depart()
        delivery.write({"trip_receiver_name": "Juan Almacenista", "signature": png})
        delivery.action_deliver()

        slip, _type = self.env["ir.actions.report"]._render_qweb_html(
            "stock.report_deliveryslip", delivery.ids
        )
        slip = slip.decode()
        signature = slip[slip.index('name="signature"') :]

        self.assertIn("Juan Almacenista", signature)
        self.assertNotIn(delivery.partner_id.name, signature)
        for html in (slip, self._sheet(trip)):
            self.assertNotRegex(html, r"\d\.\d{3,}\s*kg")
        action = delivery.action_trip_view_signature()
        self.assertEqual((action["res_id"], action["target"]), (delivery.id, "new"))

    def test_the_sheet_speaks_spanish(self):
        self.env["res.lang"]._activate_lang("es_MX")
        self.env["ir.module.module"]._load_module_terms(
            ["stock_fleet_trace"], ["es_MX"], overwrite=True
        )
        delivery = self._delivery(5)
        trip = self._trip(delivery)
        trip.action_trip_load()
        trip.action_depart()
        delivery.action_deliver()

        html, _type = (
            self.env["ir.actions.report"]
            .with_context(lang="es_MX")
            ._render_qweb_html(REPORT, trip.ids)
        )

        for term in ("Peso por entrega", "Peso al salir", "Dado de baja", "Regresó"):
            self.assertIn(term, html.decode())
