from odoo import fields
from odoo.tests.common import TransactionCase

from odoo.addons.asset_ledger.tests.common import (
    create_test_product,
    ensure_publish_date_field,
)


class TestGpsLogReportAssetFields(TransactionCase):
    def test_report_has_asset_fields(self):
        report_fields = self.env["device.data.log.gps.report"]._fields

        self.assertIn("asset_id", report_fields)
        self.assertIn("asset_name", report_fields)
        self.assertIn("license_plate", report_fields)

    def test_asset_id_is_many2one_to_resource_asset(self):
        field = self.env["device.data.log.gps.report"]._fields["asset_id"]

        self.assertEqual(field.comodel_name, "resource.resource")


class TestGpsLogReportQueryExtension(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Report = cls.env["device.data.log.gps.report"]

    def test_select_fields_include_asset_keys(self):
        select_fields = self.Report._get_fields_select()

        self.assertIn("asset_id", select_fields)
        self.assertIn("asset_name", select_fields)
        self.assertIn("license_plate", select_fields)

    def test_select_fields_map_to_asset_table(self):
        select_fields = self.Report._get_fields_select()

        self.assertEqual(select_fields["asset_id"], "asset.id")
        self.assertEqual(select_fields["asset_name"], "asset.name")
        self.assertEqual(select_fields["license_plate"], "plate.value")

    def test_from_tables_join_the_tracked_thing(self):
        from_tables = self.Report._get_from_tables()

        thing_joins = [t for t in from_tables if t[1] == "asset"]

        self.assertEqual(len(thing_joins), 1, "Expected exactly one join for the thing")

        table, _alias, join_type, condition = thing_joins[0]

        self.assertEqual(table, "resource_resource")
        self.assertEqual(join_type, "LEFT JOIN")
        self.assertIn("asset.kind_id IS NOT NULL", condition)
        self.assertIn("tracked_resource.id", condition)

    def test_group_by_fields_include_asset_columns(self):
        group_by = self.Report._get_fields_group_by()

        self.assertIn("asset.id", group_by)
        self.assertIn("asset.name", group_by)
        self.assertIn("plate.value", group_by)

    def test_parent_fields_preserved(self):
        select_fields = self.Report._get_fields_select()
        from_tables = self.Report._get_from_tables()

        self.assertIn("device_id", select_fields)

        base_tables = [t for t in from_tables if t[0] == "gps_filtered"]
        self.assertTrue(base_tables, "Parent base table gps_filtered missing")


class TestGpsLogReportRows(TransactionCase):
    """The registry hooks above assert that the code says what the code says.

    These run the query instead: a wrong column, a join naming a column that
    does not exist or a GROUP BY that misses one only shows up here. The report
    is a materialized relation, so each test refreshes it after building its
    fixture -- rows written in this transaction are invisible until it does.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_publish_date_field(cls.env)
        cls.Report = cls.env["device.data.log.gps.report"]
        cls.config = cls.env["device.profile"].create(
            {
                "name": "Report Test Config",
                "auth_type": "bearer",
                "auth_token": "test_token_report",
            }
        )
        cls.product = create_test_product(
            cls.env,
            name="Report Vehicle Product",
            type="consu",
            tracking="serial",
            asset_kind="vehicle",
        )
        cls.device = cls._device("GPS-REPORT-001")
        cls.vehicle = cls.env["product.trace"].create(
            {
                "name": "REPORT-VH",
                "product_id": cls.product.id,
                "company_id": cls.env.company.id,
                "license_plate": "REP-1234",
                "gps_device_id": cls.device.id,
            }
        )
        cls._log(cls.device)
        cls.env.flush_all()
        cls.Report.refresh()

    @classmethod
    def _device(cls, serial):
        return cls.env["device.device"].create(
            {
                "name": f"Tracker {serial}",
                "serial_number": serial,
                "identifier": serial,
                "credential_id": False,
                "config_id": cls.config.id,
            }
        )

    @classmethod
    def _log(cls, device):
        return cls.env["device.data.log.gps"].create(
            {
                "device_id": device.id,
                "timestamp": fields.Datetime.now(),
                "latitude": 1.0,
                "longitude": 1.0,
            }
        )

    def _rows(self, device):
        return self.Report.search([("device_id", "=", device.id)])

    def test_a_row_carries_the_asset_of_its_device(self):
        rows = self._rows(self.device)

        self.assertTrue(rows, "The device logged a point; it must reach the report.")
        self.assertEqual(rows.asset_id, self.vehicle.asset_id)
        self.assertEqual(rows.asset_name, "Report Vehicle Product REPORT-VH")
        self.assertEqual(rows.license_plate, "REP-1234")

    def test_a_device_without_an_asset_still_reaches_the_report(self):
        orphan = self._device("GPS-REPORT-ORPHAN")
        self._log(orphan)
        self.env.flush_all()
        self.Report.refresh()

        rows = self._rows(orphan)

        self.assertTrue(rows, "The join is a LEFT JOIN; the log must survive it.")
        self.assertFalse(rows.asset_id)

    def test_the_join_does_not_multiply_rows(self):
        rows = self.Report.search([])

        self.assertEqual(
            len(rows),
            len(set(rows.ids)),
            "resource.resource's UNIQUE (gps_device_id) is what keeps the join "
            "one-to-one; without it MIN(log.id) repeats across rows.",
        )
