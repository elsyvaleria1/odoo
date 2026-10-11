from datetime import datetime, timedelta

from odoo.exceptions import AccessError, ValidationError
from odoo.libs.json import dumps as json_dumps
from odoo.tests import new_test_user, tagged

from odoo.addons.device.tests.common import DeviceTransactionCase


@tagged("post_install", "-at_install")
class TestVisitReplay(DeviceTransactionCase):
    def setUp(self):
        super().setUp()
        self.device = self._create_device_device(
            device_category_id=self.env.ref("device.device_category_gps").id
        )
        self.partner = self.env["res.partner"].create({"name": "Replay customer"})
        self.fence = self.env["device.geo.fence"].create(
            {
                "name": "Replay parcel",
                "area_type": "parcel",
                "geofence_type": "polygon",
                "partner_id": self.partner.id,
                "schedule_type": "always",
                "polygon_points": json_dumps(
                    [[19.39, -99.11], [19.41, -99.11], [19.41, -99.09], [19.39, -99.09]]
                ),
            }
        )
        self.Visit = self.env["device.client.visit"]

    def _position(self, timestamp):
        return self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "timestamp": timestamp,
                "latitude": 19.4,
                "longitude": -99.1,
            }
        )

    def test_replay_is_idempotent_and_preserves_open_visits(self):
        self._position("2026-08-18 12:00:00")
        self._position("2026-08-18 13:00:00")
        start, end = datetime(2026, 8, 18), datetime(2026, 8, 19)
        self.assertEqual(
            self.Visit._rebuild_from_gps_logs(self.device.ids, start, end), 1
        )
        self.assertEqual(
            self.Visit._rebuild_from_gps_logs(self.device.ids, start, end), 1
        )
        visit = self.Visit.search([("device_id", "=", self.device.id)])
        self.assertEqual(len(visit), 1)
        self.assertEqual(visit.duration_hours, 1)
        visit.departure = False
        self.device.client_visit_log_id = visit
        self.assertEqual(
            self.Visit._rebuild_from_gps_logs(self.device.ids, start, end), 0
        )
        self.assertEqual(self.device.client_visit_log_id, visit)

    def test_sleep_and_long_silence_use_the_live_trackers_threshold(self):
        start = datetime(2026, 8, 18)
        for hours in (0, 3, 10):
            self._position(start + timedelta(hours=hours))
        self.assertEqual(
            self.Visit._rebuild_from_gps_logs(
                self.device.ids, start, start + timedelta(days=1)
            ),
            2,
        )
        visits = self.Visit.search(
            [("device_id", "=", self.device.id)], order="arrival"
        )
        self.assertEqual(visits.mapped("duration_hours"), [3, 0])

    def test_generic_wizard_uses_half_open_days_in_its_selected_timezone(self):
        self._position("2026-03-08 05:00:00")
        self._position("2026-03-08 06:00:00")
        self._position("2026-03-09 04:00:00")
        wizard = self.env["wizard.device.gps.visit.rebuild"].create(
            {
                "device_ids": self.device.ids,
                "date_from": "2026-03-08",
                "date_to": "2026-03-08",
                "tz": "America/New_York",
            }
        )
        action = wizard.action_rebuild()
        self.assertEqual(action["params"]["type"], "success")
        visits = self.Visit.search([("device_id", "=", self.device.id)])
        self.assertEqual(len(visits), 1)
        self.assertEqual(visits.duration_hours, 1)

    def test_replay_is_manager_only(self):
        reader = new_test_user(
            self.env, login="replay_reader", groups="device_gps.group_device_gps_user"
        )
        with self.assertRaises(AccessError):
            self.Visit.with_user(reader)._rebuild_from_gps_logs(
                self.device.ids, datetime(2026, 8, 18), datetime(2026, 8, 19)
            )
        with self.assertRaises(AccessError):
            self.env["wizard.device.gps.visit.rebuild"].with_user(reader).create({})

    def test_foreign_device_cannot_be_replayed_by_another_company(self):
        company = self.env["res.company"].create({"name": "Foreign replay company"})
        manager = new_test_user(
            self.env,
            login="foreign_replay_manager",
            groups="device_gps.group_device_gps_manager",
            company_id=company.id,
            company_ids=[company.id],
        )
        with self.assertRaises(AccessError):
            self.Visit.with_user(manager)._rebuild_from_gps_logs(
                self.device.ids, datetime(2026, 8, 18), datetime(2026, 8, 19)
            )

    def test_multi_company_manager_does_not_match_a_foreign_parcel(self):
        company = self.env["res.company"].create({"name": "Foreign replay parcel"})
        self.fence.company_id = company
        self._position("2026-08-18 12:00:00")
        self._position("2026-08-18 13:00:00")
        manager = new_test_user(
            self.env,
            login="both_replay_manager",
            groups="device_gps.group_device_gps_manager",
            company_id=self.env.company.id,
            company_ids=[self.env.company.id, company.id],
        )
        self.assertEqual(
            self.Visit.with_user(manager)
            .with_context(allowed_company_ids=manager.company_ids.ids)
            ._rebuild_from_gps_logs(
                self.device.ids, datetime(2026, 8, 18), datetime(2026, 8, 19)
            ),
            0,
        )

    def test_empty_and_reversed_windows_cannot_delete_history(self):
        for start, end in (
            (datetime(2026, 8, 18), datetime(2026, 8, 18)),
            (datetime(2026, 8, 19), datetime(2026, 8, 18)),
        ):
            with self.assertRaises(ValidationError):
                self.Visit._rebuild_from_gps_logs(self.device.ids, start, end)
