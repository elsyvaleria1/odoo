import re

from odoo.tests import HttpCase, tagged
from odoo.tests.http import JsonRpcException

from odoo.addons.mail.tests.common import MockEmail
from odoo.addons.stock_fleet_trace.tests.common import TripFixtureMixin

ROUTE = "/stock_fleet_trace/driver/confirm_code"


@tagged("post_install", "-at_install")
class TestDriverConfirmCode(TripFixtureMixin, MockEmail, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.out_type.delivery_proof_required = True
        cls.driver_user.password = "drv_driver"

    def setUp(self):
        super().setUp()
        self.picking = self._delivery(5)
        self.picking.partner_id.email = "sauce@example.com"
        self._trip(self.picking)
        self.authenticate("drv_driver", "drv_driver")

    def _issue(self, picking=None):
        with self.mock_mail_gateway():
            challenge = self.call_jsonrpc(
                f"{ROUTE}/issue", {"picking_id": (picking or self.picking).id}
            )
            code = re.search(r">\s*(\d{6})\s*<", self._new_mails.body_html).group(1)
        return challenge, code

    def _prove(self, challenge, code):
        return self.call_jsonrpc(
            f"{ROUTE}/prove",
            {
                "picking_id": self.picking.id,
                "token": challenge["token"],
                "method": challenge["method"],
                "code": code,
            },
        )

    def test_the_driver_screen_loads_the_plugin_and_its_texts(self):
        page = self.url_open("/stock_fleet_trace/driver")

        self.assertIn(
            "/stock_fleet_trace_proof/static/driver/confirm_code.js", page.text
        )
        self.assertIn("Customer is here: confirm with a code", page.text)

    def test_the_customer_at_the_door_confirms_with_a_code(self):
        challenge, code = self._issue()
        self.assertEqual(challenge["sent_to"], "s****@example.com")

        wrong = self._prove(challenge, f"{(int(code) + 1) % 10**6:06d}")
        right = self._prove(challenge, code)

        self.assertIn("not the one we sent", wrong["error"])
        self.assertEqual(right, {"confirmed": True})
        self.assertEqual(self.picking.confirmation_state, "confirmed")
        self.assertTrue(self.picking._has_delivery_proof())

    def test_only_the_trip_driver_asks_for_a_code(self):
        other = self._delivery(5)
        other.partner_id.email = "other@example.com"

        with self.assertRaises(JsonRpcException):
            self.call_jsonrpc(f"{ROUTE}/issue", {"picking_id": other.id})
