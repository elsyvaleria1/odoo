from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from odoo import fields
from odoo.fields import Command
from odoo.tests import tagged

from ..models.device_machine_bucket import DASHBOARD_WINDOW_DAYS
from .common import DeviceMachinesCommon


@tagged("post_install", "-at_install")
class TestPlcDashboard(DeviceMachinesCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Bucket = cls.env["device.machine.bucket"]
        cls.Run = cls.env["device.machine.workorder"]
        cls.labeler = cls._make_counter_device("Etiquetadora", "Etiquetadora")

    def setUp(self):
        super().setUp()
        self._isolate_the_fleet()
        self._create_counter(self.device, 100)
        self._create_counter(self.labeler, 0)

    def _isolate_the_fleet(self):
        mine = self.device | self.labeler
        others = self.env["device.device"].search(
            [("is_counter_device", "=", True), ("id", "not in", mine.ids)]
        )
        if not others:
            return
        self.env["device.machine.workorder"].search(
            [("device_id", "in", others.ids)]
        ).unlink()
        self.env["device.machine.reading"].search(
            [("device_id", "in", others.ids)]
        ).unlink()
        self.env["device.machine.bucket"].search(
            [("device_id", "in", others.ids)]
        ).unlink()
        others.active = False

    def _recent(self, hours_ago):
        return fields.Datetime.now().replace(tzinfo=UTC) - timedelta(hours=hours_ago)

    def _local_day(self, moment):
        zone = ZoneInfo(self.Bucket._dashboard_timezone())
        return moment.astimezone(zone).date()

    def _today_at(self, hour):
        # Two "hours ago" straddle local midnight for part of every day; a
        # profile test names its hours on one local day.
        zone = ZoneInfo(self.Bucket._dashboard_timezone())
        local = datetime.now(zone).replace(
            hour=hour, minute=30, second=0, microsecond=0
        )
        return local.astimezone(UTC)

    def _payload(self):
        return self.Run.get_dashboard_data()

    def test_unscoped_payload_reads_buckets_not_runs(self):
        self._reading(self.device, self._recent(3), 100)
        self._reading(self.device, self._recent(3), 180)

        self.assertFalse(self.Run.search_count([]), "fixture must have no runs")
        payload = self._payload()

        self.assertEqual(payload["totals"]["bottles"], 80)
        self.assertEqual(payload["totals"]["runs"], 1)
        self.assertIsNone(payload["workorder"])

    def test_idle_counter_device_is_listed_at_zero(self):
        self._reading(self.device, self._recent(3), 100)
        self._reading(self.device, self._recent(3), 150)

        payload = self._payload()
        by_name = {
            machine["name"]: machine["bottles"] for machine in payload["machines"]
        }

        self.assertEqual(payload["totals"]["machines"], 2)
        self.assertEqual(by_name[self.device.display_name], 50)
        self.assertEqual(by_name[self.labeler.display_name], 0)
        self.assertEqual(payload["difference"]["diff"], 50)

    def test_machines_counts_counter_devices_not_producers(self):
        payload = self._payload()

        self.assertEqual(payload["totals"]["bottles"], 0)
        self.assertEqual(payload["totals"]["machines"], 2)

    def test_buckets_outside_the_window_are_excluded(self):
        stale = self._recent(24 * (DASHBOARD_WINDOW_DAYS + 1))
        self._reading(self.device, stale, 100)
        self._reading(self.device, stale + timedelta(minutes=10), 900)

        payload = self._payload()

        self.assertEqual(payload["totals"]["bottles"], 0)
        self.assertEqual(payload["chart"]["labels"], [])

    def test_chart_groups_one_dataset_per_machine(self):
        self._reading(self.device, self._recent(2), 100)
        self._reading(self.device, self._recent(2), 130)

        chart = self._payload()["chart"]

        self.assertEqual(len(chart["labels"]), 1)
        self.assertEqual(len(chart["datasets"]), 2)
        self.assertEqual(sum(sum(ds["data"]) for ds in chart["datasets"]), 30)

    def test_scope_on_a_missing_workorder_yields_zeros(self):
        last = self.env["mrp.workorder"].search([], order="id desc", limit=1)
        missing_id = (last.id or 0) + 1000
        self._reading(self.device, self._recent(2), 100)
        self._reading(self.device, self._recent(2), 400)

        payload = self.Run.get_dashboard_data(missing_id)

        self.assertIsNone(payload["workorder"])
        self.assertEqual(payload["totals"]["bottles"], 0)
        self.assertEqual(payload["totals"]["machines"], 0)
        self.assertFalse(payload["period"])

    def test_hourly_profile_reports_the_peak_hour(self):
        quiet, busy = self._recent(4), self._recent(3)
        self._reading(self.device, quiet, 100)
        self._reading(self.device, quiet, 110)
        self._reading(self.device, busy, 200)
        self._reading(self.device, busy, 500)

        hourly = self._payload()["hourly"]
        busy_label = fields.Datetime.context_timestamp(
            self.Bucket, busy.astimezone(UTC).replace(tzinfo=None)
        ).strftime("%H:00")

        self.assertEqual(hourly["peak"]["hour"], busy_label)
        self.assertEqual(hourly["peak"]["pieces"], 390)
        self.assertEqual(len(hourly["datasets"]), 2)

    def test_hourly_profile_keeps_idle_hours_in_the_span(self):
        self._reading(self.device, self._today_at(1), 100)
        self._reading(self.device, self._today_at(1), 150)
        self._reading(self.device, self._today_at(3), 200)
        self._reading(self.device, self._today_at(3), 260)

        hourly = self._payload()["hourly"]

        self.assertEqual(len(hourly["labels"]), 3)
        self.assertIn(0, hourly["datasets"][0]["data"])

    def test_hourly_profile_is_empty_without_buckets(self):
        hourly = self._payload()["hourly"]

        self.assertEqual(hourly["labels"], [])
        self.assertIsNone(hourly["peak"])

    def test_active_rate_ignores_idle_hours(self):
        self._reading(self.device, self._recent(6), 100)
        self._reading(self.device, self._recent(6), 160)
        self._reading(self.device, self._recent(2), 200)
        self._reading(self.device, self._recent(2), 240)

        payload = self._payload()

        self.assertEqual(payload["totals"]["bottles"], 140)
        self.assertEqual(payload["totals"]["runs"], 2)
        self.assertEqual(payload["rate"]["avg_active"], 70.0)

    def test_scoped_payload_hides_the_hourly_sections(self):
        last = self.env["mrp.workorder"].search([], order="id desc", limit=1)
        payload = self.Run.get_dashboard_data((last.id or 0) + 1000)

        self.assertEqual(payload["hourly"]["labels"], [])
        self.assertIsNone(payload["rate"])

    def test_chosen_day_bounds_the_domain_on_both_sides(self):
        when = self._recent(2)
        yesterday = self._local_day(when) - timedelta(days=1)
        self._reading(self.device, when, 100)
        self._reading(self.device, when, 300)

        chosen = self.Run.get_dashboard_data(None, "window", str(yesterday))

        self.assertEqual(chosen["day_from"], str(yesterday))
        self.assertEqual(chosen["totals"]["bottles"], 0)
        self.assertEqual(chosen["period_label"], yesterday.strftime("%d/%m/%Y"))

    def test_chosen_day_wins_over_the_period(self):
        when = self._recent(2)
        today_local = self._local_day(when)
        self._reading(self.device, when, 100)
        self._reading(self.device, when, 250)

        today = self.Run.get_dashboard_data(None, "window", str(today_local))

        self.assertEqual(today["totals"]["bottles"], 150)
        self.assertEqual(today["day_from"], str(today_local))

    def test_productive_days_ignore_the_selected_scope(self):
        when = self._recent(2)
        self._reading(self.device, when, 150)
        today = self._local_day(when)

        payload = self.Run.get_dashboard_data(
            None, "window", str(today - timedelta(days=9))
        )

        self.assertEqual(payload["totals"]["bottles"], 0)
        self.assertIn(str(today), payload["productive_days"])

    def test_a_range_covers_both_ends_whole(self):
        when = self._recent(2)
        today = self._local_day(when)
        self._reading(self.device, when, 100)
        self._reading(self.device, when, 260)

        span = self.Run.get_dashboard_data(
            None, "window", str(today - timedelta(days=3)), str(today)
        )

        self.assertEqual(span["totals"]["bottles"], 160)
        self.assertEqual(span["day_to"], str(today))
        self.assertIn("–", span["period_label"])

    def test_a_range_ending_before_the_data_excludes_it(self):
        when = self._recent(2)
        today = self._local_day(when)
        self._reading(self.device, when, 100)
        self._reading(self.device, when, 260)

        span = self.Run.get_dashboard_data(
            None,
            "window",
            str(today - timedelta(days=5)),
            str(today - timedelta(days=1)),
        )

        self.assertEqual(span["totals"]["bottles"], 0)

    def test_period_advertised_only_when_unscoped(self):
        payload = self._payload()

        self.assertEqual(payload["period"], "window")
        self.assertTrue(payload["period_label"])

    def test_period_day_excludes_yesterday(self):
        self._reading(self.device, self._recent(30), 100)
        self._reading(self.device, self._recent(30), 400)

        window = self.Run.get_dashboard_data(None, "window")
        day = self.Run.get_dashboard_data(None, "day")

        self.assertEqual(window["totals"]["bottles"], 300)
        self.assertEqual(day["totals"]["bottles"], 0)
        self.assertEqual(day["period"], "day")

    def test_period_boundaries_are_read_in_the_local_zone(self):
        zone = ZoneInfo("America/Mexico_City")
        start = self.Bucket._period_domain("day", "America/Mexico_City")[0][2]
        local = start.replace(tzinfo=UTC).astimezone(zone)

        self.assertEqual((local.hour, local.minute, local.second), (0, 0, 0))

    def test_period_week_starts_on_monday(self):
        zone = ZoneInfo("America/Mexico_City")
        start = self.Bucket._period_domain("week", "America/Mexico_City")[0][2]
        local = start.replace(tzinfo=UTC).astimezone(zone)

        self.assertEqual(local.weekday(), 0)
        self.assertEqual((local.hour, local.minute), (0, 0))

    def test_period_month_starts_on_the_first(self):
        zone = ZoneInfo("America/Mexico_City")
        start = self.Bucket._period_domain("month", "America/Mexico_City")[0][2]
        local = start.replace(tzinfo=UTC).astimezone(zone)

        self.assertEqual(local.day, 1)
        self.assertEqual((local.hour, local.minute), (0, 0))

    def test_unknown_period_falls_back_to_the_window(self):
        payload = self.Run.get_dashboard_data(None, "quarter")

        self.assertEqual(payload["period"], "window")

    def test_every_panel_follows_the_same_period(self):
        self._reading(self.device, self._recent(30), 100)
        self._reading(self.device, self._recent(30), 400)

        day = self.Run.get_dashboard_data(None, "day")

        self.assertEqual(day["totals"]["bottles"], 0)
        self.assertEqual(day["totals"]["runs"], 0)
        self.assertEqual(day["chart"]["labels"], [])
        self.assertEqual(day["hourly"]["labels"], [])
        self.assertIsNone(day["hourly"]["peak"])
        self.assertEqual(day["rate"]["avg_active"], 0.0)

    def test_scoped_payload_still_comes_from_runs(self):
        product = self.env["product.product"].create(
            {"name": "Dashboard Product", "type": "consu", "is_storable": True}
        )
        workcenter = self.env["mrp.workcenter"].create({"name": "Dashboard WC"})
        bom = self.env["mrp.bom"].create(
            {
                "product_id": product.id,
                "product_tmpl_id": product.product_tmpl_id.id,
                "product_qty": 1.0,
                "operation_ids": [
                    Command.create({"name": "Fill", "workcenter_id": workcenter.id})
                ],
            }
        )
        production = self.env["mrp.production"].create(
            {"product_id": product.id, "product_qty": 10.0, "bom_id": bom.id}
        )
        production.action_confirm()
        workorder = production.workorder_ids[:1]
        if not workorder:
            self.skipTest("MRP did not generate a work order in this environment")

        self.Run.create(
            {
                "device_id": self.device.id,
                "workorder_id": workorder.id,
                "count_start": 10,
                "count_end": 35,
                "date_start": datetime(2026, 6, 18, 14, 0, 0),
            }
        )
        self._reading(self.device, self._recent(1), 500)
        self._reading(self.device, self._recent(1), 900)

        payload = self.Run.get_dashboard_data(workorder.id)

        self.assertEqual(payload["totals"]["bottles"], 25)
        self.assertEqual(payload["totals"]["runs"], 1)
        self.assertFalse(payload["period"])
        self.assertEqual(payload["workorder"]["name"], workorder.display_name)
