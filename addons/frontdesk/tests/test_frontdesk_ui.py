from datetime import datetime

import odoo.tests
from odoo import Command
from odoo.tests import JsonRpcException
from odoo.tests.common import HttpCase


@odoo.tests.tagged("post_install", "-at_install")
class TestFrontDeskURL(HttpCase):
    def test_frontdesk_ui(self):
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

    def test_a_number_given_at_the_kiosk_takes_its_stations_country(self):
        self.env.ref("base.main_company").country_id = self.env.ref("base.fr")
        us = self.env.ref("base.us")
        office = self.env["res.company"].create({"name": "Office", "country_id": us.id})
        station = self.env["frontdesk.frontdesk"].create(
            {"name": "Lobby", "company_id": office.id, "self_check_in": True}
        )

        result = self.call_jsonrpc(
            f"/frontdesk/{station.id}/{station.access_token}/prepare_visitor_data",
            {"name": "Guest", "phone": "202 555 0700", "host_ids": []},
        )

        visitor = self.env["frontdesk.visitor"].browse(result["visitor_id"])
        self.assertEqual(visitor.phone_ids.country_id, us)

    def test_a_visitor_checked_in_at_the_kiosk_belongs_to_its_stations_company(self):
        office = self.env["res.company"].create({"name": "Office"})
        station = self.env["frontdesk.frontdesk"].create(
            {"name": "Lobby", "company_id": office.id, "self_check_in": True}
        )
        self.assertNotEqual(self.env.ref("base.public_user").company_id, office)

        result = self.call_jsonrpc(
            f"/frontdesk/{station.id}/{station.access_token}/prepare_visitor_data",
            {"name": "Guest", "host_ids": []},
        )

        visitor = self.env["frontdesk.visitor"].browse(result["visitor_id"])
        self.assertEqual(visitor.company_id, office)


@odoo.tests.tagged("post_install", "-at_install")
class TestKioskStationScope(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.office = cls.env["res.company"].create({"name": "Office"})
        cls.lobby = cls.env["frontdesk.frontdesk"].create(
            {
                "name": "Lobby",
                "company_id": cls.office.id,
                "self_check_in": True,
                "drink_offer": True,
                "drink_ids": [
                    Command.link(cls.env.ref("frontdesk.frontdesk_drink_1").id)
                ],
            }
        )
        cls.elsewhere = cls.env["frontdesk.frontdesk"].create({"name": "Elsewhere"})
        cls.host = cls.env["hr.employee"].create(
            {"name": "Host", "company_id": cls.office.id, "work_email": "h@example.com"}
        )
        cls.stranger = cls.env["hr.employee"].create(
            {
                "name": "Stranger",
                "company_id": cls.elsewhere.company_id.id,
                "work_email": "s@example.com",
                "pin": "4321",
            }
        )

    def _kiosk(self, route, params):
        return self.call_jsonrpc(
            f"/frontdesk/{self.lobby.id}/{self.lobby.access_token}/{route}", params
        )

    def test_a_kiosk_cannot_check_in_another_stations_visitor(self):
        visitor = self.env["frontdesk.visitor"].create(
            {"name": "Guest", "station_id": self.elsewhere.id}
        )

        with self.assertRaises(JsonRpcException) as refused:
            self._kiosk("prepare_visitor_data", {"visitor_id": visitor.id})

        self.assertEqual(refused.exception.code, 404)
        self.assertEqual(visitor.state, "planned")

    def test_a_kiosk_serves_only_the_drinks_its_station_offers(self):
        visitor = self.env["frontdesk.visitor"].create(
            {"name": "Guest", "station_id": self.lobby.id}
        )
        offered = self.env.ref("frontdesk.frontdesk_drink_1")
        withheld = self.env.ref("frontdesk.frontdesk_drink_2")

        self._kiosk(
            "prepare_visitor_data",
            {"visitor_id": visitor.id, "drink_ids": [offered.id, withheld.id]},
        )

        self.assertEqual(visitor.drink_ids, offered)

    def test_a_kiosk_links_only_hosts_its_station_offers(self):
        result = self._kiosk(
            "prepare_visitor_data",
            {"name": "Guest", "host_ids": [self.host.id, self.stranger.id]},
        )

        visitor = self.env["frontdesk.visitor"].browse(result["visitor_id"])
        self.assertEqual(visitor.host_ids, self.host)

    def test_a_kiosk_host_search_reads_nothing_but_names_and_departments(self):
        result = self._kiosk(
            "hosts_infos",
            {"limit": 10, "offset": 0, "domain": [["display_name", "ilike", "Host"]]},
        )
        self.assertEqual([r["id"] for r in result["records"]], self.host.ids)

        self.stranger.company_id = self.office
        for domain in (
            [["pin", "=", "4321"]],
            ["|", ["display_name", "ilike", "Host"], ["pin", "=", "4321"]],
            [["department_id.name", "ilike", "x"]],
        ):
            with self.subTest(domain=domain):
                with self.assertRaises(JsonRpcException) as refused:
                    self._kiosk(
                        "hosts_infos", {"limit": 10, "offset": 0, "domain": domain}
                    )
                self.assertEqual(refused.exception.code, 404)
