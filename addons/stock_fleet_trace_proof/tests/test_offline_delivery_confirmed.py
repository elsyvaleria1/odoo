import re

from odoo.tests import TransactionCase, tagged

from odoo.addons.mail.tests.common import MockEmail
from odoo.addons.stock_fleet_trace.tests.common import (
    OfflineEventsMixin,
    TripFixtureMixin,
)


@tagged("post_install", "-at_install")
class TestOfflineDeliveryConfirmed(
    TripFixtureMixin, OfflineEventsMixin, MockEmail, TransactionCase
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.out_type.delivery_proof_required = True

    def _on_the_road(self):
        delivery = self._delivery(5)
        delivery.partner_id.email = "cliente@example.com"
        trip = self._trip(delivery)
        trip.action_depart()
        return delivery, trip

    def test_a_code_at_the_door_lets_the_offline_delivery_through(self):
        delivery, trip = self._on_the_road()
        at_the_door = delivery.with_user(self.driver_user)
        with self.mock_mail_gateway():
            params = at_the_door.action_issue_confirmation_code()
            code = re.search(r">\s*(\d{6})\s*<", self._new_mails.body_html).group(1)
        at_the_door.action_prove_confirmation_code(
            {
                "token": params["token"],
                "method": "email_code",
                "payload": {"code": code},
            }
        )

        with self.mock_mail_gateway():
            result = self._send(trip, self._event("uuid-door", "deliver", delivery))
            mails = self._new_mails

        self.assertEqual(result["uuid-door"]["state"], "applied")
        self.assertEqual(delivery.state, "done")
        self.assertFalse(delivery.signature)
        self.assertEqual(delivery.confirmation_state, "confirmed")
        self.assertTrue(delivery.delivery_proof_ok)
        self.assertFalse(mails.filtered(lambda mail: mail.subject == "Please confirm"))

    def test_without_a_code_or_a_signature_the_delivery_waits_for_review(self):
        delivery, trip = self._on_the_road()

        result = self._send(trip, self._event("uuid-bare", "deliver", delivery))

        self.assertNotEqual(result["uuid-bare"]["state"], "applied")
        self.assertNotEqual(delivery.state, "done")
