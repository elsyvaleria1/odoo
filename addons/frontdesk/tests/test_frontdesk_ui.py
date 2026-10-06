from datetime import datetime

import odoo.tests
from odoo import Command
from odoo.tests import JsonRpcException
from odoo.tests.common import HttpCase


@odoo.tests.tagged("post_install", "-at_install")
class TestFrontDeskURL(HttpCase):
    # -------------------------------------------------------------------------
    # TESTS
    # -------------------------------------------------------------------------
    def test_frontdesk_ui(self):
        """Testing the UI of the Frontdesk module"""
        station = self.env["frontdesk.frontdesk"].create(
            {
                "name": "Test Office 1",
                "responsible_ids": [(4, self.env.ref("base.user_admin").id)],
                "self_check_in": True,
                "drink_offer": True,
                "drink_ids": [
                    (4, self.env.ref(f"frontdesk.frontdesk_drink_{i}").id)
                    for i in [1, 2]
                ],
            }
        )
        self.env["frontdesk.visitor"].create(
            {
                "name": "Tony Stark",
                "phone_ids": [
                    Command.create({"number": "1230004567", "type": "mobile"})
                ],
                "email": "stark@industries.com",
                "check_in": datetime.now(),
                "state": "planned",
                "station_id": station.id,
            }
        )
        self.env["hr.employee"].create(
            {
                "name": "Test Host Employee",
                "work_email": "host@example.com",
                "phone_ids": [
                    Command.create({"number": "9876543210", "type": "landline"})
                ],
                "company_id": station.company_id.id,
            }
        )
        kiosk_values = station.action_view_kiosk()
        access_url = kiosk_values.get("url")

        self.start_tour(access_url, "quick_check_in_tour", login="admin")
        station.drink_offer = True
        self.start_tour(access_url, "frontdesk_basic_tour", login="admin")
        station.write(
            {
                "host_selection": True,
                "ask_email": "required",
            }
        )
        self.start_tour(access_url, "required_fields_tour", login="admin")

    def test_an_unknown_kiosk_token_is_a_not_found_error_not_data(self):
        station = self.env["frontdesk.frontdesk"].create({"name": "Test Office 2"})
        wrong = "x" * 64 + "2000-01-01 00:00:00"

        with self.assertRaises(JsonRpcException) as refused:
            self.call_jsonrpc(f"/frontdesk/{station.id}/{wrong}/get_frontdesk_data")

        self.assertEqual(refused.exception.code, 404)
