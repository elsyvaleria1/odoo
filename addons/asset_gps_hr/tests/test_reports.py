from datetime import datetime, timedelta

from freezegun import freeze_time

from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestRemoteGpsLogReportOperator(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Report = cls.env["device.data.log.gps.report"]

    def test_operator_fields_in_select(self):
        select = self.Report._get_fields_select()
        self.assertIn("operator_id", select)
        self.assertIn("operator_name", select)

    def test_employee_join_in_from(self):
        tables = self.Report._get_from_tables()
        emp_joins = [t for t in tables if t[0] == "hr_employee"]
        self.assertEqual(len(emp_joins), 1, "Expected exactly one hr_employee JOIN")
        _, alias, join_type, condition = emp_joins[0]
        self.assertEqual(alias, "emp")
        self.assertEqual(join_type, "LEFT JOIN")
        self.assertIn("employee_id", condition)

    def test_operator_in_group_by(self):
        group_by = self.Report._get_fields_group_by()
        self.assertIn("op.employee_id", group_by)
        self.assertIn("emp.name", group_by)


@tagged("post_install", "-at_install")
class TestAssetTripReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Report = cls.env["asset.trip.report"]

    def test_sql_view_created(self):
        self.env.cr.execute(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.views"
            "  WHERE table_name = %s"
            ")",
            [self.Report._table],
        )
        self.assertTrue(
            self.env.cr.fetchone()[0],
            f"View {self.Report._table} not created — check _query() SQL syntax",
        )

    def test_view_queryable_via_orm(self):
        self.Report.search([], limit=1)


@tagged("post_install", "-at_install")
class TestAssetTripReportHistory(TransactionCase):
    @classmethod
    @freeze_time("2025-12-01")
    def setUpClass(cls):
        super().setUpClass()
        cls.Report = cls.env["asset.trip.report"]
        company = cls.env.company
        config = cls.env["device.profile"].create(
            {"name": "Trip cfg", "auth_type": "bearer", "auth_token": "trip_tok"}
        )
        cls.device = cls.env["device.device"].create(
            {
                "name": "Trip Tracker",
                "identifier": "GPS-TRIP-001",
                "config_id": config.id,
                "credential_id": False,
            }
        )
        cls.first = cls.env["hr.employee"].create(
            {"name": "First Driver", "company_id": company.id}
        )
        cls.second = cls.env["hr.employee"].create(
            {"name": "Second Driver", "company_id": company.id}
        )
        product = cls.env["product.product"].create(
            {
                "name": "Trip Vehicle",
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": cls.env.ref("base.kind_vehicle").id,
            }
        )
        cls.lot = cls.env["product.trace"].create(
            {
                "name": "TRIP-VH",
                "product_id": product.id,
                "company_id": company.id,
                "license_plate": "TRP-001",
                "gps_device_id": cls.device.id,
                "operator_id": cls.first.id,
            }
        )
        cls.lot.operator_id = cls.second
        ledger = (
            cls.env["resource.assignment"]
            .sudo()
            .with_context(active_test=False, skip_custody_push=True)
            .search(
                [
                    ("resource_id", "=", cls.lot.asset_id.id),
                    ("custody_role", "=", "operator"),
                ],
                order="date_start asc, id asc",
            )
        )
        handover = datetime(2026, 2, 1, 12, 0)
        ledger[0].write({"date_start": datetime(2026, 1, 1), "date_end": handover})
        ledger[1].write({"date_start": handover})
        for employee, day in ((cls.first, 10), (cls.second, 40)):
            cls.env["hr.attendance"].create(
                {
                    "employee_id": employee.id,
                    "check_in": datetime(2026, 1, 1, 9) + timedelta(days=day),
                    "check_out": datetime(2026, 1, 1, 17) + timedelta(days=day),
                }
            )
        cls.env.flush_all()

    def test_each_period_keeps_the_operator_of_its_time(self):
        rows = self.env["asset.trip.report"].search(
            [
                ("asset_id", "=", self.lot.asset_id.id),
                ("work_hours_status", "=", "In hours"),
            ]
        )
        self.assertEqual(
            {(row.operator_id, row.date_start.month) for row in rows},
            {(self.first, 1), (self.second, 2)},
        )

    def test_trip_duration_stops_when_tracker_moves_during_attendance(self):
        for hour, odometer in ((9, 100), (10, 500), (12, 140), (13, 900)):
            self.env["device.data.log.gps"].create(
                {
                    "device_id": self.device.id,
                    "timestamp": datetime(2026, 1, 11, hour),
                    "odometer": odometer,
                    "total_odometer": odometer,
                    "odometer_valid": hour != 10,
                    "latitude": 19.4,
                    "longitude": -99.1,
                }
            )
        with freeze_time("2026-01-11 13:00:00"):
            self.lot.gps_device_id = False
        self.env.flush_all()
        rows = self.env["asset.trip.report"].search(
            [
                ("asset_id", "=", self.lot.asset_id.id),
                ("operator_id", "=", self.first.id),
                ("work_hours_status", "=", "In hours"),
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.date_start, datetime(2026, 1, 11, 9))
        self.assertEqual(rows.date_end, datetime(2026, 1, 11, 13))
        self.assertEqual(rows.duration_hours, 4)
        self.assertEqual(rows.distance, 40)

    def test_trip_duration_excludes_temporary_other_operator(self):
        with freeze_time("2025-12-01"):
            self.env["resource.assignment"].create(
                {
                    "resource_id": self.lot.asset_id.id,
                    "assignee_id": self.second.resource_id.id,
                    "custody_role": "operator",
                    "date_start": datetime(2026, 1, 11, 13),
                    "date_end": datetime(2026, 1, 11, 15),
                }
            )
        rows = self.env["asset.trip.report"].search(
            [
                ("asset_id", "=", self.lot.asset_id.id),
                ("operator_id", "=", self.first.id),
                ("work_hours_status", "=", "In hours"),
            ],
            order="date_start",
        )
        self.assertEqual(rows.mapped("duration_hours"), [4, 2])
        self.assertEqual(rows[0].date_end, datetime(2026, 1, 11, 13))
        self.assertEqual(rows[1].date_start, datetime(2026, 1, 11, 15))

    def test_foreign_company_cannot_read_trip_rows(self):
        company = self.env["res.company"].create({"name": "Foreign trip company"})
        reader = new_test_user(
            self.env,
            login="foreign_trip_reader",
            groups="device_gps.group_device_gps_user",
            company_id=company.id,
            company_ids=[company.id],
        )
        self.assertTrue(self.Report.search([("asset_id", "=", self.lot.asset_id.id)]))
        self.assertFalse(
            self.Report.with_user(reader).search([("asset_id", "=", self.lot.asset_id.id)])
        )
        owner_reader = new_test_user(
            self.env,
            login="local_trip_reader",
            groups="device_gps.group_device_gps_user",
            company_id=self.env.company.id,
            company_ids=[self.env.company.id],
        )
        self.assertTrue(
            self.Report.with_user(owner_reader).search(
                [("asset_id", "=", self.lot.asset_id.id)]
            )
        )

    def test_history_has_no_company_rollout_date_cutoff(self):
        start = datetime(2024, 5, 10, 9)
        end = datetime(2024, 5, 10, 17)
        self.env["resource.assignment"].with_context(skip_custody_push=True).create(
            {
                "resource_id": self.lot.asset_id.id,
                "assignee_id": self.first.resource_id.id,
                "custody_role": "operator",
                "date_start": start,
                "date_end": end,
            }
        )
        self.env.cr.execute(
            "UPDATE resource_gps_binding SET date_start = NULL, origin = 'legacy' "
            "WHERE resource_id = %s",
            [self.lot.asset_id.id],
        )
        self.env["resource.gps.binding"].invalidate_model()
        self.env["hr.attendance"].create(
            {"employee_id": self.first.id, "check_in": start, "check_out": end}
        )
        self.env.flush_all()
        rows = self.Report.search(
            [("asset_id", "=", self.lot.asset_id.id), ("date_start", "=", start)]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.duration_hours, 8)
        self.assertEqual(rows.company_id, self.lot.company_id)
