from odoo.exceptions import AccessError
from odoo.libs.json import dumps as json_dumps
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestClientVisitCompany(common.TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env["res.company"].create({"name": "Visit Co A"})
        self.other_company = self.env["res.company"].create({"name": "Visit Co B"})
        self.config = self.env["device.profile"].create({"name": "Company Config"})
        self.device = self.env["device.device"].create(
            {
                "name": "Company Tracker",
                "identifier": "COMPANY-001",
                "config_id": self.config.id,
                "comm_protocol": "http",
                "imei": "TEST-IMEI-COMPANY-001",
                "device_category_id": self.env.ref("device.device_category_gps").id,
                "company_id": self.company.id,
            }
        )
        self.client = self.env["res.partner"].create({"name": "Company Client"})
        self.parcel = self.env["device.geo.fence"].create(
            {
                "name": "Company Parcel",
                "company_id": self.company.id,
                "area_type": "parcel",
                "geofence_type": "polygon",
                "schedule_type": "always",
                "partner_id": self.client.id,
                "polygon_points": json_dumps(
                    [
                        [19.39, -99.11],
                        [19.41, -99.11],
                        [19.41, -99.09],
                        [19.39, -99.09],
                    ]
                ),
            }
        )

    def _record_a_visit(self):
        log = self.env["device.data.log.gps"].create(
            {"device_id": self.device.id, "latitude": 19.40, "longitude": -99.10}
        )
        self.device.sudo().log_gps_last_id = log.id
        self.env.flush_all()
        self.env["device.device"]._cron_track_client_visits()
        return self.env["device.client.visit"].search(
            [("device_id", "=", self.device.id)]
        )

    def _gps_user_of(self, company, login):
        return self.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "company_id": company.id,
                "company_ids": [(6, 0, [company.id])],
                "group_ids": [(4, self.env.ref("device_gps.group_device_gps_user").id)],
            }
        )

    def test_the_visit_takes_the_devices_company(self):
        visit = self._record_a_visit()

        self.assertEqual(visit.company_id, self.company)

    def test_a_user_of_another_company_cannot_read_the_visit(self):
        visit = self._record_a_visit()
        outsider = self._gps_user_of(self.other_company, "visit.outsider@test.example")

        self.assertFalse(
            visit.with_user(outsider).search([("id", "=", visit.id)]),
            "the company guard has to keep another company's visits out of the "
            "Visitas a Clientes report",
        )
        with self.assertRaises(AccessError):
            visit.with_user(outsider).read(["partner_id"])

    def test_a_user_of_the_same_company_can_read_the_visit(self):
        visit = self._record_a_visit()
        insider = self._gps_user_of(self.company, "visit.insider@test.example")

        self.assertEqual(visit.with_user(insider).partner_id, self.client)

    def test_live_tracking_does_not_match_another_companys_parcel(self):
        self.parcel.company_id = self.other_company
        self._record_a_visit()
        self.assertFalse(
            self.env["device.client.visit"].search([("device_id", "=", self.device.id)])
        )
