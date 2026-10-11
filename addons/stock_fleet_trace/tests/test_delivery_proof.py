from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from .common import TripFixtureMixin

PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY"
    "42YAAAAASUVORK5CYII="
)


@tagged("post_install", "-at_install")
class TestTripDeliveryProof(TripFixtureMixin, TransactionCase):
    """Where the signed slip is required, the customer's signature on the driver's
    phone counts as its evidence; one that is not the customer's does not."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.out_type.delivery_proof_required = True
        cls.not_ordered = cls.env.ref("stock_fleet_trace.unbatch_reason_not_ordered")

    def _departed(self, quantity=5):
        delivery = self._delivery(quantity)
        trip = self._trip(delivery)
        trip.action_depart()
        return delivery, trip

    def _phone_delivers(self, trip, delivery, uuid, **payload):
        Event = self.env["stock.trip.offline.event"]
        event = {
            "client_uuid": uuid,
            "event_type": "deliver",
            "picking_id": delivery.id,
            "payload": payload,
            "captured_at": "2026-09-30T18:00:00Z",
            "latitude": 19.29,
            "longitude": -99.65,
            "device_uuid": "phone-1",
            "prev_hash": trip._trip_last_event_hash(),
        }
        event["event_hash"] = Event._trip_hash_event(event)
        trip.with_user(self.driver_user)._trip_receive_offline_events([event])
        return trip.trip_offline_event_ids.filtered(lambda e: e.client_uuid == uuid)

    def _stop_result(self, picking, delivered):
        wizard = (
            self.env["wizard.stock.trip.stop.result"]
            .with_context(default_picking_id=picking.id)
            .create({})
        )
        for line in wizard.line_ids:
            line.qty_delivered = delivered
            if line.qty_rejected:
                line.reason_id = self.not_ordered
        wizard.action_confirm()

    def test_the_customer_signature_on_the_phone_delivers(self):
        delivery, trip = self._departed()
        event = self._phone_delivers(
            trip, delivery, "uuid-signed", receiver_name="Juan Pérez", signature=PNG
        )
        self.assertEqual(event.state, "applied", event.error)
        self.assertEqual(delivery.state, "done")
        self.assertTrue(delivery.signature, "the signature is kept")
        self.assertEqual(delivery.trip_receiver_name, "Juan Pérez")

    def test_a_signature_without_the_receiver_name_does_not_count(self):
        delivery, trip = self._departed()
        event = self._phone_delivers(trip, delivery, "uuid-nameless", signature=PNG)
        self.assertEqual(event.state, "review")
        self.assertIn("the name of whoever received is missing", event.error)
        self.assertNotIn("RedirectWarning", event.error)
        self.assertEqual(delivery.state, "assigned")

    def test_the_driver_does_not_sign_for_the_customer(self):
        delivery, trip = self._departed()
        event = self._phone_delivers(
            trip,
            delivery,
            "uuid-driver",
            receiver_name="  DRIVER ",
            signature=PNG,
        )
        self.assertEqual(event.state, "review")
        self.assertIn("the driver", event.error)
        self.assertEqual(delivery.state, "assigned")

    def test_the_supervisor_and_whoever_validates_do_not_sign_either(self):
        delivery, _trip = self._departed()
        delivery.write({"signature": PNG, "trip_receiver_name": "Supervisor"})
        self.assertIn("the trip supervisor", delivery._customer_signature_problem())
        delivery.trip_receiver_name = self.env.user.name
        self.assertIn("whoever validates", delivery._customer_signature_problem())
        with self.assertRaisesRegex(UserError, "does not count as the customer's"):
            delivery.button_validate()

    def test_the_photo_counts_without_a_signature(self):
        delivery, _trip = self._departed()
        delivery.delivery_proof = PNG
        delivery.with_user(self.driver_user).action_deliver()
        self.assertEqual(delivery.state, "done")

    def test_no_signature_nor_photo_asks_for_the_photo(self):
        delivery, _trip = self._departed()
        with self.assertRaises(RedirectWarning) as refusal:
            delivery.with_user(self.driver_user).action_deliver()
        self.assertEqual(
            refusal.exception.args[1]["context"]["default_resume"], "deliver"
        )

    def test_a_partial_stop_without_evidence_is_never_delivered_whole(self):
        delivery, _trip = self._departed()
        with self.assertRaises(RedirectWarning) as refusal:
            self._stop_result(delivery, 3)
        action = refusal.exception.args[1]
        self.assertFalse(action["context"]["default_resume"])
        wizard = (
            self.env[action["res_model"]]
            .with_context(action["context"])
            .create({"delivery_proof": PNG})
        )
        wizard.action_confirm()
        self.assertEqual(
            delivery.state, "assigned", "the photo alone validates nothing"
        )
        self._stop_result(delivery, 3)
        self.assertEqual(delivery.state, "done")
        self.assertEqual(delivery.trip_delivery_result, "partial")
        self.assertEqual(sum(delivery.move_ids.mapped("quantity")), 3)

    def _sign_in_the_office(self, delivery, **vals):
        return (
            self.env["wizard.stock.picking.delivery.proof"]
            .with_user(self.driver_user)
            .create({"picking_id": delivery.id, "resume": "deliver", **vals})
        )

    def test_the_customer_signs_on_the_delivery_dialog(self):
        delivery, _trip = self._departed()
        with self.assertRaises(RedirectWarning):
            delivery.with_user(self.driver_user).action_deliver()

        self._sign_in_the_office(
            delivery, receiver_name="Rosa Elena Quiroz", signature=PNG
        ).action_confirm()

        self.assertEqual(delivery.state, "done")
        self.assertEqual(delivery.trip_receiver_name, "Rosa Elena Quiroz")
        self.assertTrue(delivery.signature)
        self.assertFalse(delivery.delivery_proof)

    def test_the_dialog_needs_a_photo_or_a_signed_name(self):
        delivery, _trip = self._departed()
        with self.assertRaises(ValidationError):
            self._sign_in_the_office(delivery, signature=PNG)

    def test_the_driver_cannot_sign_the_dialog_for_the_customer(self):
        delivery, _trip = self._departed()
        with self.assertRaises(ValidationError):
            self._sign_in_the_office(
                delivery, receiver_name=self.driver.name, signature=PNG
            ).action_confirm()
        self.assertNotEqual(delivery.state, "done")
