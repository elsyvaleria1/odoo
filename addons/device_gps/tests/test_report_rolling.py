import os
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.libs import sealing
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

COMPARED_FIELDS = (
    "log_count",
    "tracked_hours",
    "driving_hours",
    "idling_hours",
    "parked_hours",
    "coasting_hours",
    "distance_gps",
    "distance_odo",
    "distance_best",
    "distance_source",
    "fuel_consumed_total",
    "fuel_refilled_total",
    "engine_hours_total",
    "speed_sum",
    "speed_count",
    "speed_max",
    "movement_count",
    "ignition_on_count",
    "speed_over_warning_events",
)


@tagged("post_install", "-at_install")
class TestGpsReportRolling(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        key_patcher = patch.dict(
            os.environ,
            sealing.rotated_environ("7ftr9ALjwK7f4IqWwnpFxWx4Wn8vetsznoGT3Oh46eU="),
        )
        key_patcher.start()
        cls.addClassCleanup(key_patcher.stop)

        cls.report = cls.env["device.data.log.gps.report"]
        cls.config = cls.env["device.profile"].create(
            {"name": "Rolling Report Config", "reports_odometer": True}
        )

    def _device(self, ref):
        return self.env["device.device"].create(
            {
                "name": f"Rolling {ref}",
                "identifier": f"ROLL-{ref}",
                "config_id": self.config.id,
                "comm_protocol": "http",
            }
        )

    def _log(self, device, moment, *, index=0, ignition=True, moving=True):
        return self.env["device.data.log.gps"].create(
            {
                "device_id": device.id,
                "timestamp": moment,
                "latitude": 19.40 + index * 0.002,
                "longitude": -99.10 - index * 0.002,
                "speed": 30.0 if moving else 0.0,
                "movement": moving,
                "ignition": ignition,
                "odometer": 100000.0 + index * 500,
                "fuel_level_l": 80.0 - index * 0.5,
                "engine_total_hours": 1000.0 + index,
            }
        )

    def _snapshot(self):
        rows = self.report.search_read(
            [], ["device_id", "date", *COMPARED_FIELDS], order="date, device_id"
        )
        snapshot = {}
        for row in rows:
            device = row["device_id"]
            key = (device[0] if isinstance(device, tuple) else device, row["date"])
            snapshot[key] = tuple(
                round(row[name], 4) if isinstance(row[name], float) else row[name]
                for name in COMPARED_FIELDS
            )
        return snapshot

    def _create_fleet(self):
        now = fields.Datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
        busy, sparse, ancient = (
            self._device("BUSY"),
            self._device("SPARSE"),
            self._device("ANCIENT"),
        )
        for day in range(9, -1, -1):
            for index in range(4):
                moment = now - timedelta(days=day, hours=index)
                self._log(busy, moment, index=index)
                if day in (9, 8, 7, 1, 0):
                    self._log(sparse, moment, index=index, moving=index % 2 == 0)
                if day >= 7:
                    self._log(ancient, moment, index=index, ignition=index != 0)
        self.env.flush_all()
        return busy, sparse, ancient

    def test_a_rolling_refresh_matches_a_full_rebuild(self):
        self._create_fleet()
        self.report.refresh(force_rebuild=True)
        expected = self._snapshot()
        self.assertTrue(expected, "fixture produced no report rows")

        self.report.refresh()
        self.assertEqual(
            self._snapshot(),
            expected,
            "a window refresh over unchanged data must be a no-op",
        )

    def test_a_rolling_refresh_picks_up_new_rows_in_the_window(self):
        busy, sparse, _ancient = self._create_fleet()
        self.report.refresh(force_rebuild=True)
        before = self._snapshot()

        now = fields.Datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)
        for index in range(3):
            self._log(busy, now - timedelta(minutes=10 * index), index=index + 4)
            self._log(sparse, now - timedelta(minutes=10 * index), index=index + 4)
        self.env.flush_all()

        self.report.refresh()
        rolling = self._snapshot()
        self.assertNotEqual(rolling, before, "new rows must reach the report")

        self.report.refresh(force_rebuild=True)
        self.assertEqual(
            rolling,
            self._snapshot(),
            "the window refresh disagreed with a full rebuild; the most likely "
            "cause is a partition whose seed row was not re-admitted to the scan",
        )

    def test_a_device_that_never_logged_does_not_break_the_window(self):
        self._create_fleet()
        silent = self._device("SILENT")
        self.report.refresh(force_rebuild=True)
        expected = self._snapshot()

        self.assertTrue(self.report.refresh())
        self.assertEqual(self._snapshot(), expected)
        self.assertNotIn(
            silent.id,
            {key[0] for key in self._snapshot()},
            "a device without logs has no seed and no rows, not a crash",
        )

    def test_periods_before_the_window_are_left_alone(self):
        _busy, _sparse, ancient = self._create_fleet()
        self.report.refresh(force_rebuild=True)
        settled = {
            key: value
            for key, value in self._snapshot().items()
            if key[0] == ancient.id
        }
        self.assertTrue(settled, "fixture produced no settled rows to protect")

        self.report.refresh()
        after = {
            key: value
            for key, value in self._snapshot().items()
            if key[0] == ancient.id
        }
        self.assertEqual(settled, after)

    def test_the_report_is_a_table_not_a_materialized_view(self):
        self.assertEqual(
            self.report._relkind(self.report._table),
            "r",
            "the rolling refresh deletes and inserts rows, which a materialized "
            "view cannot express",
        )

    def test_a_settings_change_that_rewrites_history_forces_a_full_rebuild(self):
        self._create_fleet()
        self.report.refresh(force_rebuild=True)
        self.assertFalse(self.report._rolling_pop_stale())

        self.config.write({"odometer_correction_factor": 0.5})
        self.assertTrue(
            self.report._rolling_pop_stale(),
            "changing the correction factor rewrites already-settled periods, "
            "so the window refresh alone can no longer be trusted",
        )

    def test_switching_the_device_config_recomputes_history(self):
        device = self._device("SWITCH")
        log = self._log(device, fields.Datetime.now(), index=1)
        log.odometer = 100.0
        self.env.flush_all()
        self.assertEqual(log.real_odometer, 100.0)
        self.report._rolling_pop_stale()

        doubled = self.env["device.profile"].create(
            {
                "name": "Rolling Doubled Config",
                "reports_odometer": True,
                "odometer_correction_factor": 2.0,
            }
        )
        device.config_id = doubled
        self.assertTrue(
            self.report._rolling_pop_stale(),
            "moving a device to another config changes how every stored "
            "real_odometer was derived, so the report must rebuild in full",
        )
        Log = self.env["device.data.log.gps"]
        Log._job_recompute_real_odometer([device.id])
        batch_job = (
            self.env["ir.job"]
            .sudo()
            .search(
                [("method_name", "=", "_job_recompute_real_odometer_batch")],
                order="id desc",
                limit=1,
            )
        )
        self.assertIn(log.id, batch_job.record_ids)
        Log.browse(batch_job.record_ids)._job_recompute_real_odometer_batch()
        self.assertEqual(
            log.real_odometer,
            200.0,
            "history must be recomputed under the new config's factor",
        )

    def test_changing_speed_limits_forces_a_full_rebuild(self):
        self._create_fleet()
        self.report.refresh(force_rebuild=True)
        self.assertFalse(self.report._rolling_pop_stale())

        self.config.write(
            {
                "speed_limit_warning": 60.0,
                "speed_limit_alert": 70.0,
                "speed_limit_critical": 90.0,
            }
        )
        self.assertTrue(
            self.report._rolling_pop_stale(),
            "speed_over_*_events are baked against the limits at refresh time, "
            "so new limits rewrite already-settled periods",
        )
