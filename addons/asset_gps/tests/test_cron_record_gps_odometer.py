from datetime import date, timedelta

from freezegun import freeze_time

from odoo import Command, fields
from odoo.tests import tagged

from .test_product_trace import StockLotGpsTestBase


class CronGpsOdometerBase(StockLotGpsTestBase):
    """Fixture and helpers shared by this cron's suites.

    Carries no tests of its own, the way `StockLotGpsTestBase` does not.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config.write(
            {
                "reports_odometer": True,
                "odometer_correction_factor": 1.0,
            }
        )
        cls.device.odometer_initial_offset = 0.0
        cls.Log = cls.env["resource.asset.log"]
        cls.GpsLog = cls.env["device.data.log.gps"]

    def _reading(self, device, odometer, days_ago=1):
        return self.GpsLog.create(
            {
                "device_id": device.id,
                "timestamp": fields.Datetime.now() - timedelta(days=days_ago),
                "latitude": 0.0,
                "longitude": 0.0,
                "odometer": odometer,
                "odometer_valid": True,
            }
        )

    def _gps_logs(self, asset):
        return self.Log.search([("trace_id", "=", asset.id), ("source", "=", "gps")])

    def _tracked_asset(self, name, serial, odometer):
        with freeze_time("2026-01-01"):
            device = self.env["device.device"].create(
                {
                    "name": f"Tracker {serial}",
                    "serial_number": serial,
                    "identifier": serial,
                    "credential_id": False,
                    "config_id": self.config.id,
                }
            )
            device.odometer_initial_offset = 0.0
            asset = self.env["product.trace"].create(
                {
                    "name": name,
                    "product_id": self.product.id,
                    "company_id": self.company.id,
                    "odometer_uom_id": self.km_uom.id,
                    "gps_device_id": device.id,
                }
            )
        self._reading(device, odometer)
        return asset


@tagged("post_install", "-at_install")
class TestCronRecordGpsOdometer(CronGpsOdometerBase):
    def test_an_advancing_reading_books_one_log(self):
        self._reading(self.device, 12000)

        self.env["product.trace"]._cron_record_gps_odometer()

        logs = self._gps_logs(self.vehicle)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs.odometer, 12000)
        self.assertEqual(logs.date, fields.Date.context_today(self.vehicle))
        self.assertEqual(logs.state, "done", "An automated snapshot is not a draft.")
        self.assertEqual(self.vehicle.asset_id.odometer, 12000)

    def test_a_second_run_the_same_day_moves_the_days_row_forward(self):
        self._reading(self.device, 12000)
        self.env["product.trace"]._cron_record_gps_odometer()
        self._reading(self.device, 13000)

        self.env["product.trace"]._cron_record_gps_odometer()

        logs = self._gps_logs(self.vehicle)
        self.assertEqual(
            len(logs),
            1,
            "One GPS snapshot per asset per day, however often the cron runs.",
        )
        self.assertEqual(logs.odometer, 13000, "The day's row follows the counter.")
        self.assertEqual(self.vehicle.asset_id.odometer, 13000)

    def test_a_run_without_progress_leaves_the_days_row_alone(self):
        self._reading(self.device, 12000)
        self.env["product.trace"]._cron_record_gps_odometer()
        log = self._gps_logs(self.vehicle)
        written = log.write_date

        self.env["product.trace"]._cron_record_gps_odometer()

        self.assertEqual(log.odometer, 12000)
        self.assertEqual(log.write_date, written)

    def test_a_reading_at_or_below_the_current_odometer_books_nothing(self):
        # A manual reading the GPS has not caught up with yet. Deleting a booked
        # log would not do: the asset's odometer is computed from that ledger, so
        # removing the row takes the odometer down with it.
        self.Log.create(
            {
                "asset_id": self.vehicle.asset_id.id,
                "odometer": 20000,
                "source": "manual",
                "date": fields.Date.context_today(self.vehicle),
            }
        )
        self.assertEqual(self.vehicle.asset_id.odometer, 20000)
        self._reading(self.device, 11000)

        self.env["product.trace"]._cron_record_gps_odometer()

        self.assertFalse(
            self._gps_logs(self.vehicle),
            "The odometer ledger only moves forward.",
        )

    def test_an_asset_without_a_device_is_skipped(self):
        untracked = self.env["product.trace"].create(
            {
                "name": "CRON-NO-GPS",
                "product_id": self.product.id,
                "company_id": self.company.id,
                "odometer_uom_id": self.km_uom.id,
            }
        )
        self._reading(self.device, 12000)

        self.env["product.trace"]._cron_record_gps_odometer()

        self.assertFalse(self._gps_logs(untracked))
        self.assertTrue(self._gps_logs(self.vehicle))

    def test_every_advancing_asset_in_a_batch_gets_its_own_log(self):
        self._reading(self.device, 12000)
        second = self._tracked_asset("CRON-VH-2", "GPS-CRON-002", 8000)
        third = self._tracked_asset("CRON-VH-3", "GPS-CRON-003", 9000)

        self.env["product.trace"]._cron_record_gps_odometer()

        self.assertEqual(len(self._gps_logs(self.vehicle)), 1)
        self.assertEqual(self._gps_logs(second).odometer, 8000)
        self.assertEqual(self._gps_logs(third).odometer, 9000)

    def test_the_snapshot_day_uses_the_resources_zone_over_the_crons(self):
        """The nightly run fires at 03:10 UTC, which is 21:10 the previous day
        for a UTC-6 fleet. The reading belongs to the operator's day."""
        self.company.partner_id.tz = "America/Mexico_City"
        self.vehicle.asset_id.tz = "America/Mexico_City"

        with freeze_time("2026-09-07 03:10:56"):
            self._reading(self.device, 12000)
            self.assertEqual(
                self.env["product.trace"]._gps_odometer_today(self.company),
                date(2026, 9, 6),
                "OdooBot has no timezone, so the UTC date would say the 7th.",
            )
            self.env["product.trace"]._cron_record_gps_odometer()

        self.assertEqual(self._gps_logs(self.vehicle).date, date(2026, 9, 6))

    def test_snapshot_uses_resource_timezone_within_one_company(self):
        self.company.partner_id.tz = "UTC"
        self.vehicle.asset_id.tz = "America/Mexico_City"
        with freeze_time("2026-09-07 03:10:56"):
            second = self._tracked_asset("CRON-TZ-2", "GPS-TZ-2", 8000)
            second.asset_id.tz = "Asia/Tokyo"
            self._reading(self.device, 12000)
            self.env["product.trace"]._cron_record_gps_odometer()
        self.assertEqual(self._gps_logs(self.vehicle).date, date(2026, 9, 6))
        self.assertEqual(self._gps_logs(second).date, date(2026, 9, 7))

    def test_the_snapshot_day_falls_back_to_utc(self):
        """A company whose partner carries no timezone keeps the old behaviour
        rather than raising on an empty timezone name."""
        self.company.partner_id.tz = False

        with freeze_time("2026-09-07 03:10:56"):
            self.assertEqual(
                self.env["product.trace"]._gps_odometer_today(self.company),
                date(2026, 9, 7),
            )


@tagged("post_install", "-at_install")
class TestCronRecordGpsOdometerAcrossCompanies(CronGpsOdometerBase):
    """The shape production actually ran in.

    The cron fires as OdooBot, and OdooBot sits in company 1 -- the
    unconfigured placeholder, not the operating company that owns the fleet.
    Every test above builds its asset in ``env.company``, so none of them could
    show what that divergence does, and the suite stayed green for as long as
    the nightly run had never once succeeded: the log took the acting company,
    the ledger constraint refused the whole batch, and the snapshot day fell
    back to UTC because the placeholder's partner carries no timezone.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fleet_company = cls.env["res.company"].create({"name": "Fleet Owner"})
        cls.fleet_company.partner_id.tz = "America/Mexico_City"
        cls.env.user.company_ids = [Command.link(cls.fleet_company.id)]
        # The acting company stays the placeholder, timezone and all.
        cls.company.partner_id.tz = False
        cls.vehicle.gps_device_id = False
        with freeze_time("2026-01-01"):
            cls.device = cls.device.copy(
                {"identifier": "FLEET-OWNER-GPS", "company_id": cls.fleet_company.id}
            )
            cls.vehicle = cls.env["product.trace"].create(
                {
                    "name": "FLEET-OWNER-VEHICLE",
                    "product_id": cls.product.id,
                    "company_id": cls.fleet_company.id,
                    "odometer_uom_id": cls.km_uom.id,
                    "gps_device_id": cls.device.id,
                }
            )
        cls.vehicle.asset_id.tz = "America/Mexico_City"

    def test_the_log_is_booked_in_the_assets_company(self):
        self._reading(self.device, 12000)

        self.env["product.trace"]._cron_record_gps_odometer()

        logs = self._gps_logs(self.vehicle)
        self.assertEqual(len(logs), 1, "The whole batch used to be refused.")
        self.assertEqual(
            logs.company_id,
            self.fleet_company,
            "A log belongs to the asset's ledger, not to whoever books it.",
        )

    def test_the_snapshot_day_follows_the_assets_company(self):
        with freeze_time("2026-09-07 03:10:56"):
            self._reading(self.device, 12000)
            self.env["product.trace"]._cron_record_gps_odometer()

        self.assertEqual(
            self._gps_logs(self.vehicle).date,
            date(2026, 9, 6),
            "The acting company has no timezone; the fleet's is UTC-6.",
        )

    def test_a_second_run_the_same_day_still_books_one_row(self):
        """The dedupe keys on the asset's day, not one day for the run."""
        with freeze_time("2026-09-07 03:10:56"):
            self._reading(self.device, 12000)
            self.env["product.trace"]._cron_record_gps_odometer()
            self._reading(self.device, 13000)

            self.env["product.trace"]._cron_record_gps_odometer()

        logs = self._gps_logs(self.vehicle)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs.odometer, 13000)
