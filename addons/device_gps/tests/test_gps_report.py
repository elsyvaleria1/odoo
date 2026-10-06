import os
from datetime import date, datetime
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command
from odoo.libs import sealing
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestGpsReportTimezone(TransactionCase):
    @classmethod
    @freeze_time("2026-01-01")
    def setUpClass(cls):
        super().setUpClass()
        key_patcher = patch.dict(
            os.environ,
            sealing.rotated_environ("7ftr9ALjwK7f4IqWwnpFxWx4Wn8vetsznoGT3Oh46eU="),
        )
        key_patcher.start()
        cls.addClassCleanup(key_patcher.stop)

        cls.company = cls.env.ref("base.main_company")
        cls.config = cls.env["device.profile"].create({"name": "GPS Report Config"})
        cls.device = cls.env["device.device"].create(
            {
                "name": "Report Tracker",
                "identifier": "RPT-TZ-001",
                "config_id": cls.config.id,
                "comm_protocol": "http",
                "endpoint": "192.168.1.70",
                "company_id": cls.company.id,
            }
        )
        cls.resource = cls.env["resource.resource"].create(
            {
                "name": "Reported resource",
                "gps_device_id": cls.device.id,
                "tz": "America/Mexico_City",
            }
        )
        cls.report = cls.env["device.data.log.gps.report"]

    def _make_log(self, moment):
        return self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "timestamp": moment,
                "latitude": 19.4326,
                "longitude": -99.1332,
            }
        )

    def test_report_buckets_in_local_timezone(self):
        self._make_log(datetime(2026, 1, 15, 3, 0, 0))
        self.env.flush_all()
        self.assertTrue(self.report.refresh(force_rebuild=True))

        row = self.report.search([("device_id", "=", self.device.id)])
        self.assertEqual(len(row), 1, "one point yields one device-day bucket")
        self.assertEqual(row.date, date(2026, 1, 14), "bucketed on the local day")
        self.assertEqual(row.day_of_week, "3", "Wednesday local, not Thursday UTC")

    @freeze_time("2026-01-01")
    def test_resources_in_one_company_have_their_own_report_dates(self):
        other = self.device.copy({"identifier": "RPT-TZ-TOKYO"})
        self.env["resource.resource"].create(
            {"name": "Tokyo resource", "gps_device_id": other.id, "tz": "Asia/Tokyo"}
        )
        moment = datetime(2026, 1, 15, 3)
        self._make_log(moment)
        self.env["device.data.log.gps"].create(
            {
                "device_id": other.id,
                "timestamp": moment,
                "latitude": 19.4326,
                "longitude": -99.1332,
            }
        )
        self.env.flush_all()
        self.report.refresh(force_rebuild=True)
        rows = self.report.search([("device_id", "in", [self.device.id, other.id])])
        dates = {row.device_id.id: row.date for row in rows}
        self.assertEqual(dates[self.device.id], date(2026, 1, 14))
        self.assertEqual(dates[other.id], date(2026, 1, 15))

    def test_timezone_change_rebuilds_settled_report_dates(self):
        self._make_log(datetime(2026, 1, 15, 3))
        self.env.flush_all()
        self.report.refresh(force_rebuild=True)
        self.resource.tz = "Asia/Tokyo"
        self.env.flush_all()
        self.report.refresh()
        row = self.report.search([("device_id", "=", self.device.id)])
        self.assertEqual(row.date, date(2026, 1, 15))

    @freeze_time("2026-01-15 12:00:00")
    def test_an_unattached_device_uses_its_configured_company_timezone(self):
        self.resource.gps_device_id = False
        self.company.partner_id.tz = "Pacific/Kiritimati"
        self.assertEqual(self.device._gps_timezone(), "Pacific/Kiritimati")
        self._make_log(datetime(2026, 1, 15, 18))
        self.env.flush_all()
        self.report.refresh(force_rebuild=True)
        row = self.report.search([("device_id", "=", self.device.id)])
        self.assertEqual(row.date, date(2026, 1, 16))


@tagged("post_install", "-at_install")
class TestGpsReportCompanyScope(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        key_patcher = patch.dict(
            os.environ,
            sealing.rotated_environ("7ftr9ALjwK7f4IqWwnpFxWx4Wn8vetsznoGT3Oh46eU="),
        )
        key_patcher.start()
        cls.addClassCleanup(key_patcher.stop)

        cls.company_a = cls.env.ref("base.main_company")
        cls.company_b = cls.env["res.company"].create({"name": "GPS Fleet Co B"})
        cls.config = cls.env["device.profile"].create({"name": "Scope Config"})
        cls.device_a = cls.env["device.device"].create(
            {
                "name": "Tracker A",
                "identifier": "SCOPE-A-001",
                "config_id": cls.config.id,
                "comm_protocol": "http",
                "endpoint": "192.168.2.10",
                "company_id": cls.company_a.id,
            }
        )
        cls.device_b = cls.env["device.device"].create(
            {
                "name": "Tracker B",
                "identifier": "SCOPE-B-001",
                "config_id": cls.config.id,
                "comm_protocol": "http",
                "endpoint": "192.168.2.20",
                "company_id": cls.company_b.id,
            }
        )
        moment = datetime(2026, 3, 10, 15, 0, 0)
        for device in (cls.device_a, cls.device_b):
            cls.env["device.data.log.gps"].create(
                {
                    "device_id": device.id,
                    "timestamp": moment,
                    "latitude": 19.4326,
                    "longitude": -99.1332,
                }
            )
        cls.env.flush_all()
        cls.report = cls.env["device.data.log.gps.report"]
        cls.report.refresh(force_rebuild=True)

        cls.user_a = cls.env["res.users"].create(
            {
                "name": "GPS User A",
                "login": "gps_scope_user_a",
                "group_ids": [
                    Command.link(cls.env.ref("device_gps.group_device_gps_user").id)
                ],
                "company_ids": [Command.set([cls.company_a.id])],
                "company_id": cls.company_a.id,
            }
        )

    def test_report_scoped_to_reader_company(self):
        visible = self.report.with_user(self.user_a).search([])
        companies = visible.mapped("company_id")
        self.assertIn(self.company_a, companies, "own-company rows are visible")
        self.assertNotIn(
            self.company_b, companies, "another company's telemetry must not leak"
        )
