from datetime import datetime

from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged

from odoo.addons.device.tests.common import DeviceTransactionCase


@tagged("post_install", "-at_install")
class TestAttachmentHistory(DeviceTransactionCase):
    def setUp(self):
        super().setUp()
        with freeze_time("2026-09-01 00:00:00"):
            profile = self.env["device.profile"].create(
                {
                    "name": "History",
                    "reports_odometer": True,
                    "odometer_correction_factor": 1,
                }
            )
            self.device = self.env["device.device"].create(
                {
                    "name": "Shared tracker",
                    "identifier": "history-tracker",
                    "config_id": profile.id,
                }
            )
            self.first = self.env["resource.resource"].create(
                {
                    "name": "First target",
                    "type": "material",
                    "tz": "UTC",
                    "gps_device_id": self.device.id,
                }
            )
            self.second = self.first.copy({"name": "Second target", "tz": "Asia/Tokyo"})
        self.History = self.env["resource.gps.binding"]

    def _reading(self, timestamp, value):
        return self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "timestamp": timestamp,
                "odometer": value,
                "odometer_valid": True,
                "latitude": 19.3,
                "longitude": -99.6,
            }
        )

    def _move(self):
        with freeze_time("2026-09-05 00:00:00"):
            self.device.tracked_resource_id = self.second

    def test_reassignment_preserves_history_and_bounds_new_target(self):
        earlier = self._reading("2026-09-03 12:00:00", 1000)
        self._move()
        later = self._reading("2026-09-06 12:00:00", 1200)
        at = datetime(2026, 9, 6, 12)
        self.assertEqual(self.first._gps_position(at), earlier)
        self.assertEqual(self.second._gps_position(at), later)
        self.assertEqual(self.first._gps_odometer_at(earlier.timestamp), 1000)
        self.assertEqual(self.second._gps_odometer_at(earlier.timestamp), 0)
        self.assertEqual(
            self.env["device.data.log.gps"].search(
                self.first.action_view_tracking_history()["domain"]
            ),
            earlier,
        )

    def test_half_open_boundary_and_delayed_observation(self):
        self._move()
        boundary = self._reading("2026-09-05 00:00:00", 1100)
        delayed = self._reading("2026-09-04 23:59:59", 1000)
        self.assertEqual(self.first._gps_position(boundary.timestamp), delayed)
        self.assertEqual(self.second._gps_position(boundary.timestamp), boundary)
        self.assertEqual(
            self.History.search_count(
                [("device_id", "=", self.device.id), ("resource_id", "!=", False)]
            ),
            2,
        )

    def test_first_attachment_does_not_claim_preexisting_observations(self):
        earlier = self._reading("2026-08-31 23:59:59", 900)
        self.assertFalse(self.first._gps_position(earlier.timestamp))
        self.assertIsNone(self.first._gps_odometer_reading(earlier.timestamp))

    def test_unattached_gap_and_noop_do_not_claim_observations(self):
        with freeze_time("2026-09-04"):
            self.first.gps_device_id = False
        gap = self._reading("2026-09-04 12:00:00", 1000)
        self._move()
        self.second.gps_device_id = self.device
        self.assertFalse(self.first._gps_position(gap.timestamp))
        self.assertFalse(self.second._gps_position(gap.timestamp))
        self.assertEqual(
            self.History.search_count(
                [("device_id", "=", self.device.id), ("resource_id", "!=", False)]
            ),
            2,
        )

    def test_history_cannot_be_mutated_through_rpc(self):
        history = self.History.search([("device_id", "=", self.device.id)])
        with self.assertRaises(AccessError):
            history.write({"date_start": "2020-01-01"})
        with self.assertRaises(AccessError):
            history.unlink()
        with self.assertRaises(AccessError):
            self.History.create(
                {"resource_id": self.first.id, "device_id": self.device.id}
            )

    def test_company_scope_and_historical_identity_retention(self):
        self._move()
        company = self.env["res.company"].create({"name": "History other tenant"})
        with self.assertRaises((UserError, ValidationError)), self.cr.savepoint():
            self.first.company_id = company
        with self.assertRaises((UserError, ValidationError)), self.cr.savepoint():
            self.device.company_id = company
        with self.assertRaises((UserError, ValidationError)), self.cr.savepoint():
            self.first.unlink()
        user = new_test_user(
            self.env,
            login="history_reader",
            groups="device_gps.group_device_gps_user",
            company_id=company.id,
            company_ids=[company.id],
        )
        self.assertFalse(
            self.History.with_user(user).search([("device_id", "=", self.device.id)])
        )

    def test_summary_keeps_historical_target_timezone(self):
        self._reading("2026-09-04 21:00:00", 1000)
        self._move()
        self._reading("2026-09-05 21:00:00", 1200)
        report = self.env["device.data.log.gps.report"]
        report.refresh(force_rebuild=True)
        rows = report.search([("device_id", "=", self.device.id)], order="date")
        self.assertEqual(rows.mapped("resource_id"), self.first | self.second)
        self.assertEqual([str(row.date) for row in rows], ["2026-09-04", "2026-09-06"])
        self.assertEqual(rows.mapped("log_count"), [1, 1])

    def test_public_trail_reader_respects_role_and_company(self):
        self._reading("2026-09-03 12:00:00", 1000)
        ordinary = new_test_user(
            self.env, login="plain_trail_reader", groups="base.group_user"
        )
        Log = self.env["device.data.log.gps"]
        with self.assertRaises(AccessError):
            Log.with_user(ordinary).trail_points(
                self.device.ids, "2026-09-01", "2026-09-07"
            )
        company = self.env["res.company"].create({"name": "Trail other tenant"})
        foreign = new_test_user(
            self.env,
            login="foreign_trail_reader",
            groups="device_gps.group_device_gps_user",
            company_id=company.id,
            company_ids=[company.id],
        )
        self.assertFalse(
            Log.with_user(foreign).trail_points(
                self.device.ids, "2026-09-01", "2026-09-07"
            )
        )

    def test_trail_points_resolve_delayed_and_boundary_observations(self):
        self._move()
        self._reading("2026-09-04 23:59:59", 1000)
        self._reading("2026-09-05 00:00:00", 1100)
        points = self.env["device.data.log.gps"].trail_points(
            self.device.ids, "2026-09-01", "2026-09-07"
        )
        self.assertEqual(
            [point["resource_id"] for point in points], [self.first.id, self.second.id]
        )
        self.assertNotEqual(points[0]["binding_id"], points[1]["binding_id"])

    def test_current_snapshot_does_not_follow_previous_target_reading(self):
        old = self._reading("2026-09-04 23:59:59", 1000)
        old.speed = 81
        self.device.log_gps_last_id = old
        self.assertEqual(self.first.gps_current_speed, 81)
        self._move()
        self.assertFalse(self.second.gps_observation_id)
        self.assertFalse(self.second.gps_current_speed)
        owned = self._reading("2026-09-05 00:00:00", 1100)
        owned.speed = 24
        self.device.log_gps_last_id = owned
        self.assertEqual(self.second.gps_observation_id, owned)
        self.assertEqual(self.second.gps_current_speed, 24)
        self.assertEqual(self.second.gps_date_last_data, owned.timestamp)
        self.assertFalse(self.first.gps_observation_id)
        future = self._reading("2099-01-01", 1200)
        self.device.log_gps_last_id = future
        self.assertFalse(self.second.gps_observation_id)

    def test_filtered_holder_does_not_claim_another_holders_interval(self):
        Assignment = self.env["resource.assignment"]
        people = self.env["res.partner"].create(
            [{"name": "History holder one"}, {"name": "History holder two"}]
        )
        with freeze_time("2026-09-01"):
            original = Assignment.create(
                {
                    "resource_id": self.first.id,
                    "assignee_partner_id": people[0].id,
                    "custody_role": "operator",
                    "date_start": "2026-09-01",
                }
            )
            Assignment.create(
                {
                    "resource_id": self.first.id,
                    "assignee_partner_id": people[1].id,
                    "custody_role": "operator",
                    "date_start": "2026-09-03",
                    "date_end": "2026-09-04",
                }
            )
        periods = self.History._custody_periods(
            self.first,
            roles=["operator"],
            assignees=original.assignee_id,
            date_end=datetime(2026, 9, 6),
        )
        self.assertEqual(
            sorted((period.date_start, period.date_end) for period in periods),
            [
                (datetime(2026, 9, 1), datetime(2026, 9, 3)),
                (datetime(2026, 9, 4), datetime(2026, 9, 6)),
            ],
        )
        self._reading("2026-09-03 12:00:00", 1000)
        self.assertFalse(
            self.History._coverage(
                periods, datetime(2026, 9, 3).date(), datetime(2026, 9, 3).date()
            )[original.assignee_id.id]["with_data"]
        )
        self._reading("2026-09-04 12:00:00", 1100)
        self.assertTrue(
            self.History._coverage(
                periods, datetime(2026, 9, 4).date(), datetime(2026, 9, 4).date()
            )[original.assignee_id.id]["with_data"]
        )

    def test_legacy_bootstrap_audit_clock_is_utc_in_a_foreign_sql_session(self):
        self.cr.execute(
            "DELETE FROM resource_gps_binding WHERE device_id = %s", [self.device.id]
        )
        self.cr.execute("SET LOCAL TIME ZONE 'America/Mexico_City'")
        self.cr.execute("SELECT NOW() AT TIME ZONE 'UTC'")
        expected = self.cr.fetchone()[0]
        self.History._bootstrap_legacy()
        binding = self.History.search([("device_id", "=", self.device.id)])
        self.assertEqual(binding.origin, "legacy")
        self.assertEqual(binding.create_date, expected)
        self.assertEqual(binding.write_date, expected)

    def test_idempotent_owner_inverses_do_not_grant_resource_edit_authority(self):
        reader = new_test_user(
            self.env, login="idempotent_resource_reader", groups="base.group_user"
        )
        target = self.first.with_user(reader).with_context(check_idempotence=True)
        count = self.History.search_count([("resource_id", "=", self.first.id)])
        self.assertTrue(
            target.write(
                {"capacity": self.first.capacity, "gps_device_id": self.device.id}
            )
        )
        self.assertEqual(
            self.History.search_count([("resource_id", "=", self.first.id)]), count
        )
        with self.assertRaises(AccessError):
            target.write({"capacity": self.first.capacity + 1})
        with self.assertRaises(AccessError):
            target.write({"gps_device_id": False})
