from datetime import datetime, timedelta

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestMaintenanceState(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create(
            {
                "name": "State probe machine",
                "is_storable": True,
                "tracking": "serial",
                "maintenance_ok": True,
                "asset_kind_id": cls.env.ref("base.kind_machinery").id,
            }
        )
        cls.asset = cls.env["product.trace"].create(
            {"name": "STATE-1", "product_id": cls.product.id}
        )

    def _order(self, maintenance_type, date_scheduled_start=None):
        hours_ago = 1 if maintenance_type == "preventive" else 4
        return self.env["maintenance.order"].create(
            {
                "name": "State probe",
                "maintenance_type": maintenance_type,
                "resource_ids": self.asset.asset_id.ids,
                "date_scheduled_start": date_scheduled_start
                or datetime.now() - timedelta(hours=hours_ago),
            }
        )

    def test_an_asset_with_no_order_is_good(self):
        self.assertEqual(self.asset.maintenance_state, "good")

    def test_an_open_corrective_order_makes_the_asset_critical(self):
        self._order("corrective")
        self.assertEqual(self.asset.maintenance_state, "critical")

    def test_a_due_preventive_order_makes_the_asset_a_warning(self):
        self._order("preventive")
        self.assertEqual(self.asset.maintenance_state, "warning")

    def test_a_preventive_order_planned_ahead_leaves_the_asset_good(self):
        self._order(
            "preventive", date_scheduled_start=datetime.now() + timedelta(days=20)
        )
        self.assertEqual(self.asset.maintenance_state, "good")

    def test_corrective_outranks_preventive(self):
        self._order("preventive")
        self._order("corrective")
        self.assertEqual(self.asset.maintenance_state, "critical")

    def test_cancelling_the_order_clears_the_badge(self):
        order = self._order("corrective")
        self.assertEqual(self.asset.maintenance_state, "critical")
        order.action_cancel()
        self.assertEqual(
            self.asset.maintenance_state,
            "good",
            "a cancelled order must not leave the asset badged critical",
        )

    def test_the_badge_follows_the_order_without_a_manual_recompute(self):
        order = self._order("corrective")
        self.assertEqual(self.asset.maintenance_state, "critical")
        order.maintenance_type = "preventive"
        self.assertEqual(self.asset.maintenance_state, "warning")

    def test_the_order_count_matches_the_list_it_opens(self):
        self._order("preventive")
        self._order("corrective")
        action = self.asset.action_view_maintenance_orders()
        opened = self.env["maintenance.order"].search(action["domain"])
        self.assertEqual(self.asset.asset_id.maintenance_count, len(opened))
        self.assertEqual(self.asset.asset_id.maintenance_state, "critical")
        self.assertEqual(self.asset.asset_id.maintenance_count, len(opened))


@tagged("post_install", "-at_install")
class TestOperationalState(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parcel_product = cls.env["product.product"].create(
            {
                "name": "State probe parcel",
                "is_storable": False,
                "asset_kind_id": cls.env.ref("base.kind_property").id,
            }
        )

    def test_an_asset_with_no_location_is_in_storage(self):
        parcel = self.env["product.trace"].create(
            {
                "name": "PARCEL-STATE-1",
                "product_id": self.parcel_product.id,
                "cadastral_id": "PARCEL-STATE-CAD-1",
            }
        )
        self.assertFalse(parcel.location_id)
        self.assertFalse(parcel.is_deployed)
        self.assertFalse(parcel.is_in_maintenance)
        self.assertTrue(
            parcel.is_in_storage,
            "an asset that is neither deployed nor in a workshop is in storage",
        )


@tagged("post_install", "-at_install")
class TestWarehousePickingTypes(TransactionCase):
    """Core calls _create_or_update_picking_types() on warehouses we never saw."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )

    OURS = (
        "deployment_type_id",
        "deployment_return_type_id",
        "maintenance_type_id",
        "maintenance_return_type_id",
    )
    OUR_LOCATIONS = ("wh_deployed_stock_loc_id", "wh_maintenance_stock_loc_id")

    def _forget_locations(self, warehouse):
        # A warehouse that predates this module has these columns empty and has
        # not been written since, which is the state core hands us. Writing
        # False will not reproduce it -- stock.warehouse.write syncs missing
        # locations back on the way through -- so the columns are cleared under
        # the ORM, after flushing whatever it was still holding.
        self.env.flush_all()
        assignments = ", ".join(f'"{name}" = NULL' for name in self.OUR_LOCATIONS)
        self.env.cr.execute(
            f"UPDATE stock_warehouse SET {assignments} WHERE id = %s", (warehouse.id,)
        )
        warehouse.invalidate_recordset(list(self.OUR_LOCATIONS))

    def test_every_picking_type_we_add_is_declared_in_all_four_registries(self):
        warehouse = self.warehouse
        codes = set(warehouse._get_picking_type_codes())
        for name, mapping in (
            ("create", warehouse._prepare_picking_type_create_vals()),
            ("update", warehouse._prepare_picking_type_update_vals()),
            ("barcode", warehouse._get_picking_type_barcode_suffixes()),
        ):
            with self.subTest(registry=name):
                self.assertTrue(
                    set(self.OURS) <= set(mapping) & codes,
                    "_check_picking_type_registry requires every picking type in "
                    "all four registries, so a declaration cannot be made "
                    "conditional on the location it points at",
                )

    def test_the_locations_exist_before_a_declaration_is_read(self):
        self._forget_locations(self.warehouse)

        self.warehouse._create_or_update_picking_types()

        for name in self.OUR_LOCATIONS:
            with self.subTest(location=name):
                self.assertTrue(
                    self.warehouse[name],
                    "default_location_dest_id is NOT NULL, so the location has "
                    "to exist by the time the picking type naming it is built",
                )

    def test_a_warehouse_that_predates_this_module_survives_core_adding_a_type(self):
        self._forget_locations(self.warehouse)

        # point_of_sale does exactly this for every warehouse without a POS
        # operation type; so does anything else adding a picking type later.
        self.warehouse.write(self.warehouse._create_or_update_picking_types())

        for name in self.OURS:
            with self.subTest(picking_type=name):
                self.assertTrue(self.warehouse[name].default_location_dest_id)
