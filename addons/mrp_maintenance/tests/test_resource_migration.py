from odoo.tests import TransactionCase, tagged

from odoo.addons.mrp_maintenance.migration import migrate_equipment_resources


@tagged("post_install", "-at_install")
class TestEquipmentResourceMigration(TransactionCase):
    def test_import_preserves_independent_identities_and_is_idempotent(self):
        # The temporary fixture shadows any archived legacy table in this transaction.
        self.cr.execute(
            "CREATE TEMP TABLE maintenance_equipment (asset_id integer, workcenter_id integer) ON COMMIT DROP"
        )
        machine = self.env["resource.resource"].create(
            {
                "name": "Component",
                "kind_id": self.env.ref("resource_asset.kind_machinery").id,
            }
        )
        station = self.env["mrp.workcenter"].create({"name": "Composite station"})
        resource = station.resource_id
        self.cr.execute(
            "INSERT INTO maintenance_equipment VALUES (%s, %s)",
            (machine.id, station.id),
        )
        self.cr.execute("SET LOCAL search_path TO pg_temp, public")
        migrate_equipment_resources(self.env)
        migrate_equipment_resources(self.env)
        relations = self.env["resource.relation"].search(
            [("member_id", "=", machine.id)]
        )
        self.assertEqual(len(relations), 1)
        self.assertEqual(relations.parent_id, resource)
        self.assertFalse(relations.date_start)
        self.assertEqual(station.resource_id, resource)
        self.assertFalse(station.asset_id)
        self.assertNotEqual(machine, resource)

    def test_missing_identity_aborts_import(self):
        self.cr.execute(
            "CREATE TEMP TABLE maintenance_equipment (asset_id integer, workcenter_id integer) ON COMMIT DROP"
        )
        self.cr.execute("INSERT INTO maintenance_equipment VALUES (-1, -1)")
        self.cr.execute("SET LOCAL search_path TO pg_temp, public")
        with self.assertRaises(ValueError):
            migrate_equipment_resources(self.env)

    def test_ambiguous_legacy_membership_aborts_import(self):
        self.cr.execute(
            "CREATE TEMP TABLE maintenance_equipment (asset_id integer, workcenter_id integer) ON COMMIT DROP"
        )
        machine = self.env["resource.resource"].create(
            {
                "name": "Ambiguous component",
                "kind_id": self.env.ref("resource_asset.kind_machinery").id,
            }
        )
        stations = self.env["mrp.workcenter"].create(
            [{"name": "Station one"}, {"name": "Station two"}]
        )
        self.cr.executemany(
            "INSERT INTO maintenance_equipment VALUES (%s, %s)",
            [(machine.id, station.id) for station in stations],
        )
        self.cr.execute("SET LOCAL search_path TO pg_temp, public")
        with self.assertRaises(ValueError):
            migrate_equipment_resources(self.env)
        self.assertFalse(
            self.env["resource.relation"].search([("member_id", "=", machine.id)])
        )
