from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged

from odoo.addons.device.tests.common import DeviceTransactionCase


@tagged("post_install", "-at_install")
class TestResourceTracking(DeviceTransactionCase):
    @classmethod
    @freeze_time("2026-09-01")
    def setUpClass(cls):
        super().setUpClass()
        profile = cls.env["device.profile"].create(
            {
                "name": "Resource GPS",
                "reports_odometer": True,
                "odometer_correction_factor": 1.0,
            }
        )
        cls.device = cls.env["device.device"].create(
            {
                "name": "Resource tracker",
                "identifier": "resource-tracker",
                "config_id": profile.id,
                "odometer_initial_offset": 0.0,
            }
        )
        cls.resource = cls.env["resource.resource"].create(
            {
                "name": "Tracked resource",
                "type": "material",
                "gps_device_id": cls.device.id,
                "tz": "America/Mexico_City",
                "capacity": 3,
            }
        )
        cls.moment = datetime(2026, 9, 28, 8)

    def test_resource_reads_observations_without_an_asset(self):
        log = self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "timestamp": self.moment,
                "latitude": 19.3,
                "longitude": -99.6,
                "odometer": 1200,
                "odometer_valid": True,
            }
        )
        self.assertEqual(self.device.tracked_resource_id, self.resource)
        self.assertEqual(self.resource._gps_position(self.moment), log)
        self.assertEqual(self.resource._gps_odometer_at(self.moment), 1200)
        self.assertFalse(
            self.resource._gps_position(
                self.moment + timedelta(hours=1), max_age=timedelta(minutes=5)
            )
        )
        self.assertEqual(self.resource.capacity, 3)
        self.assertEqual(self.resource.tz, "America/Mexico_City")
        self.assertEqual(
            self.env["device.data.log.gps"].search(
                self.resource.action_view_tracking_history()["domain"]
            ),
            log,
        )

    def test_operational_date_uses_the_resource_timezone(self):
        moment = datetime(2026, 9, 7, 3, 10)
        self.assertEqual(str(self.resource._get_local_date(moment)), "2026-09-06")
        self.resource.tz = "Asia/Tokyo"
        self.assertEqual(str(self.resource._get_local_date(moment)), "2026-09-07")

    def test_device_side_reassignment_releases_the_previous_resource(self):
        target = self.resource.copy()
        self.assertFalse(target.gps_device_id)
        self.device.tracked_resource_id = target
        self.assertFalse(self.resource.gps_device_id)
        self.assertEqual(target.gps_device_id, self.device)
        target.active = False
        self.device.invalidate_recordset(["tracked_resource_id"])
        self.assertEqual(self.device.tracked_resource_id, target)

    def test_one_device_cannot_track_two_resources(self):
        target = self.resource.copy()
        with self.assertRaises((UserError, ValidationError)), self.cr.savepoint():
            target.gps_device_id = self.device

    def test_company_mismatch_is_refused(self):
        self.resource.gps_device_id = False
        company = self.env["res.company"].create({"name": "Other resource owner"})
        with self.assertRaises(UserError), self.cr.savepoint():
            self.env["resource.resource"].create(
                {
                    "name": "Other company's resource",
                    "company_id": company.id,
                    "gps_device_id": self.device.id,
                }
            )

    def test_human_resources_use_the_same_observation_contract(self):
        self.resource.write(
            {
                "type": "human",
                "partner_id": self.env["res.partner"]
                .create({"name": "Tracked person"})
                .id,
            }
        )
        self.assertEqual(self.device.tracked_resource_id, self.resource)
        self.assertIsNone(self.resource._gps_odometer_reading())

    def test_resource_telemetry_requires_gps_access(self):
        user = new_test_user(
            self.env, login="plain_resource_reader", groups="base.group_user"
        )
        log = self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "timestamp": self.moment,
                "speed": 73,
                "latitude": 19.3,
                "longitude": -99.6,
            }
        )
        self.device.log_gps_last_id = log
        resource = self.resource.with_user(user)
        self.assertTrue(resource.has_access("read"))
        self.assertFalse(self.device.with_user(user).has_access("read"))
        with self.assertRaises(AccessError):
            resource.read(["gps_current_speed"])
        self.assertNotIn("gps_current_speed", resource.fields_get())

    def test_a_tracking_target_with_history_is_archived(self):
        report = self.env["device.data.log.gps.report"]
        report._rolling_pop_stale()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.resource.unlink()
        self.resource.active = False
        self.assertEqual(self.device.tracked_resource_id, self.resource)
        self.assertFalse(report._rolling_pop_stale())

    def test_tracker_company_cannot_diverge_from_its_target(self):
        company = self.env["res.company"].create({"name": "Other tracker company"})
        with self.assertRaises(UserError), self.cr.savepoint():
            self.device.company_id = company

    def test_gps_user_can_read_telemetry(self):
        user = new_test_user(
            self.env,
            login="gps_resource_reader",
            groups="device_gps.group_device_gps_user",
        )
        log = self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "timestamp": self.moment,
                "speed": 73,
                "latitude": 19.3,
                "longitude": -99.6,
            }
        )
        self.device.log_gps_last_id = log
        self.assertEqual(self.resource.with_user(user).gps_current_speed, 73)

    def test_readers_accept_aware_instants(self):
        log = self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "timestamp": self.moment,
                "latitude": 19.3,
                "longitude": -99.6,
                "odometer": 1200,
                "odometer_valid": True,
            }
        )
        instant = self.moment.replace(tzinfo=UTC).astimezone(ZoneInfo("Asia/Tokyo"))
        reading = self.resource._gps_odometer_reading(
            instant, before=timedelta(minutes=5), after=timedelta(minutes=5)
        )
        self.assertEqual(reading.value, 1200)
        self.assertEqual(self.resource._gps_position(instant), log)

    def test_current_odometer_does_not_read_a_future_observation(self):
        for when, value in (
            (self.moment, 1200),
            (self.moment + timedelta(minutes=5), 1300),
        ):
            self.env["device.data.log.gps"].create(
                {
                    "device_id": self.device.id,
                    "timestamp": when,
                    "latitude": 19.3,
                    "longitude": -99.6,
                    "odometer": value,
                    "odometer_valid": True,
                }
            )
        with patch("odoo.fields.Datetime.now", return_value=self.moment):
            self.assertEqual(self.resource._gps_odometer_reading().value, 1200)

    def test_removing_company_clock_configuration_invalidates_summaries(self):
        self.resource.gps_device_id = False
        company = self.resource.company_id
        company.partner_id.tz = False
        company.resource_calendar_id.tz = "America/New_York"
        report = self.env["device.data.log.gps.report"]
        report._rolling_pop_stale()
        company.resource_config_id.unlink()
        self.assertTrue(report._rolling_pop_stale())
