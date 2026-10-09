import re

from odoo import Command
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.mail.tests.common import MockEmail

ROUTE = "/stock_fleet_trace/driver/confirm_code"


@tagged("post_install", "-at_install")
class TestDriverConfirmCode(MockEmail, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock_location = warehouse.lot_stock_id
        cls.customer_location = cls.env.ref("stock.stock_location_customers")
        cls.out_type = warehouse.out_type_id
        cls.out_type.delivery_proof_required = True
        cls.driver = new_test_user(
            cls.env, login="proof_door_driver", groups="stock_fleet.group_trip_driver"
        )
        cls.customer = cls.env["res.partner"].create(
            {"name": "Agricola El Sauce", "email": "sauce@example.com"}
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Fertilizer", "is_storable": True}
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.stock_location, 100
        )
        cls.picking = cls.env["stock.picking"].create(
            {
                "picking_type_id": cls.out_type.id,
                "partner_id": cls.customer.id,
                "location_id": cls.stock_location.id,
                "location_dest_id": cls.customer_location.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": cls.product.id,
                            "product_uom_qty": 5,
                            "location_id": cls.stock_location.id,
                            "location_dest_id": cls.customer_location.id,
                        }
                    )
                ],
            }
        )
        cls.picking.action_confirm()
        cls.picking.action_assign()

    def _issue(self):
        with self.mock_mail_gateway():
            challenge = self.call_jsonrpc(
                f"{ROUTE}/issue", {"picking_id": self.picking.id}
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
        self.authenticate("proof_door_driver", "proof_door_driver")

        page = self.url_open("/stock_fleet_trace/driver")

        self.assertIn(
            "/stock_fleet_trace_proof/static/driver/confirm_code.js", page.text
        )
        self.assertIn("Customer is here: confirm with a code", page.text)

    def test_the_customer_at_the_door_confirms_with_a_code(self):
        self.authenticate("proof_door_driver", "proof_door_driver")
        challenge, code = self._issue()
        self.assertEqual(challenge["sent_to"], "s****@example.com")

        wrong = self._prove(challenge, f"{(int(code) + 1) % 10**6:06d}")
        right = self._prove(challenge, code)

        self.assertIn("not the one we sent", wrong["error"])
        self.assertEqual(right, {"confirmed": True})
        self.assertEqual(self.picking.confirmation_state, "confirmed")
        self.assertTrue(self.picking._has_delivery_proof())
