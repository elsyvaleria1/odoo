import importlib.util
from pathlib import Path

from odoo.db import schema
from odoo.tools import SQL

from .test_product_trace import StockLotGpsTestBase
from odoo.addons.asset_gps.tools.compatibility import register_legacy_gps_privileges


class TestResourceAttachmentMigration(StockLotGpsTestBase):
    """Exercise migration against inherited tables with legacy attachment data."""

    def _migrate(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "1.14.0"
            / "post-migrate.py"
        )
        spec = importlib.util.spec_from_file_location("gps_attachment_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.migrate(self.cr, "19.0.1.13.0")
        self.env.invalidate_all()

    def _legacy_attachment(self):
        self.asset = self.vehicle.asset_id
        self.asset.gps_device_id = False
        self.env.flush_all()
        # An old deployment has no attachment timeline yet.
        self.cr.execute(
            "DELETE FROM resource_gps_binding WHERE device_id = %s",
            [self.device.id],
        )
        self.env["resource.gps.binding"].invalidate_model()
        schema.create_column(self.cr, "resource_asset", "gps_device_id", "int4")
        self.concrete_table = self.env[
            self.asset._get_model_for_kind(self.asset.kind_id)
        ]._table
        # Detaching and reattaching preserves a child's local column copy,
        # matching an old concrete model that also declared the field.
        self.cr.execute(
            SQL(
                "ALTER TABLE %s NO INHERIT resource_asset",
                SQL.identifier(self.concrete_table),
            )
        )
        self.cr.execute(
            SQL(
                "ALTER TABLE %s INHERIT resource_asset",
                SQL.identifier(self.concrete_table),
            )
        )
        self.cr.execute(
            "UPDATE resource_asset SET gps_device_id = %s WHERE id = %s",
            [self.device.id, self.asset.id],
        )

    def test_attachment_survives_and_legacy_columns_are_removed(self):
        self._legacy_attachment()
        self.asset.active = False
        report = self.env["device.data.log.gps.report"]
        report._rolling_pop_stale()
        self._migrate()
        self.assertTrue(report._rolling_pop_stale())
        self.assertEqual(self.asset.gps_device_id, self.device)
        self.assertEqual(self.device.tracked_resource_id, self.asset.resource_id)
        self.assertEqual(self.device.asset_id, self.asset)
        binding = self.env["resource.gps.binding"].search(
            [("resource_id", "=", self.asset.resource_id.id)]
        )
        self.assertEqual(binding.origin, "legacy")
        self.assertFalse(binding.date_start)
        self.assertFalse(binding.date_end)
        self.assertFalse(self.asset.active)
        self.assertFalse(
            schema.column_exists(self.cr, "resource_asset", "gps_device_id")
        )
        self.assertFalse(
            schema.column_exists(self.cr, self.concrete_table, "gps_device_id")
        )
        # Safe to retry after the old columns have gone.
        self._migrate()
        self.assertEqual(self.asset.gps_device_id, self.device)

    def test_conflicting_resource_attachment_is_refused_before_data_changes(self):
        self._legacy_attachment()
        other = self.device.copy({"identifier": "migration-conflict-tracker"})
        self.asset.gps_device_id = other
        self.env.flush_all()
        with self.assertRaisesRegex(ValueError, "attachments disagree"):
            self._migrate()
        self.assertEqual(self.asset.gps_device_id, other)
        self.assertTrue(
            schema.column_exists(self.cr, "resource_asset", "gps_device_id")
        )
        self.cr.execute(
            "SELECT gps_device_id FROM resource_asset WHERE id = %s", [self.asset.id]
        )
        self.assertEqual(self.cr.fetchone()[0], self.device.id)

    def test_duplicate_target_is_refused_before_data_changes(self):
        self._legacy_attachment()
        other = self.asset.with_context(skip_asset_identity_check=True).copy()
        self.env.flush_all()
        self.cr.execute(
            "UPDATE resource_asset SET gps_device_id = %s WHERE id = %s",
            [self.device.id, other.id],
        )
        with self.assertRaisesRegex(ValueError, "several resources"):
            self._migrate()
        self.assertFalse(self.asset.resource_id.gps_device_id)
        self.assertFalse(other.resource_id.gps_device_id)
        self.assertTrue(
            schema.column_exists(self.cr, "resource_asset", "gps_device_id")
        )

    def test_cross_company_legacy_attachment_is_refused(self):
        self._legacy_attachment()
        company = self.env["res.company"].create({"name": "Legacy tracker company"})
        self.device.company_id = company
        self.env.flush_all()
        with self.assertRaisesRegex(ValueError, "companies disagree"):
            self._migrate()
        self.assertFalse(self.asset.resource_id.gps_device_id)
        self.assertTrue(
            schema.column_exists(self.cr, "resource_asset", "gps_device_id")
        )

    def test_legacy_privilege_ids_are_aliases_of_shared_policy(self):
        self.assertEqual(
            self.env.ref("asset_gps.privilege_read_vehicle_gps"),
            self.env.ref("device_gps.privilege_read_resource_odometer"),
        )
        self.assertEqual(
            self.env.ref("asset_gps.privilege_read_vehicle_gps_logs"),
            self.env.ref("device_gps.privilege_read_resource_odometer_logs"),
        )

    def test_legacy_privilege_policy_is_migrated_without_duplicate_groups(self):
        group = self.env.ref("device_gps.privilege_read_resource_odometer")
        access = self.env.ref("device_gps.privilege_read_resource_odometer_logs")
        old_group = group.copy({"name": "Old GPS privilege"})
        old_access = access.copy({"group_id": old_group.id})
        self.env["ir.model.data"]._update_xmlids(
            [
                {"xml_id": "asset_gps.privilege_read_vehicle_gps", "record": old_group},
                {
                    "xml_id": "asset_gps.privilege_read_vehicle_gps_logs",
                    "record": old_access,
                },
            ]
        )
        register_legacy_gps_privileges(self.env)
        self.assertEqual(self.env.ref("asset_gps.privilege_read_vehicle_gps"), group)
        self.assertEqual(
            self.env.ref("asset_gps.privilege_read_vehicle_gps_logs"), access
        )
        self.assertFalse(old_group.exists())
        self.assertFalse(old_access.exists())
        register_legacy_gps_privileges(self.env)
