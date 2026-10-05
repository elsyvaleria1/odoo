from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

from .common import ensure_publish_date_field


@tagged("post_install", "-at_install")
class TestProductTrace(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        has_publish_date = ensure_publish_date_field(cls.env)

        cls.ProductTrace = cls.env["product.trace"]
        cls.ProductAssetLog = cls.env["resource.log"]
        cls.ProductTemplate = cls.env["product.template"]
        cls.ProductProduct = cls.env["product.product"]
        cls.Partner = cls.env["res.partner"]

        vals = {
            "name": "Pickup Truck",
            "asset_kind_id": cls.env.ref("resource_asset.kind_vehicle").id,
            "fuel_tank_capacity": 80,
            "type": "consu",
            "is_storable": True,
            "tracking": "serial",
        }
        if has_publish_date:
            vals["publish_date"] = fields.Datetime.now()
        cls.vehicle_template = cls.ProductTemplate.create(vals)

        cls.vehicle_product = cls.vehicle_template.product_variant_id

        cls.manufacturer = cls.Partner.create(
            {
                "name": "Test Manufacturer",
                "is_company": True,
            }
        )
        cls.vehicle_product.manufacturer_id = cls.manufacturer

        cls.fuel_category = cls.env.ref(
            "asset_ledger.product_category_fuel", raise_if_not_found=False
        )
        cls.toll_category = cls.env.ref(
            "asset_ledger.product_category_highway_toll", raise_if_not_found=False
        )
        cls.service_category = cls.env.ref(
            "asset_ledger.product_category_maintenance_and_repairs",
            raise_if_not_found=False,
        )
        if not all(
            (
                cls.fuel_category,
                cls.toll_category,
                cls.service_category,
            )
        ):
            parent_categ = cls.env["product.category"].create({"name": "Services"})
            if not cls.fuel_category:
                cls.fuel_category = cls.env["product.category"].create(
                    {"name": "Fuel", "parent_id": parent_categ.id, "log_type": "fuel"}
                )
            if not cls.toll_category:
                cls.toll_category = cls.env["product.category"].create(
                    {
                        "name": "Highway Toll",
                        "parent_id": parent_categ.id,
                        "log_type": "highway",
                    }
                )
            if not cls.service_category:
                cls.service_category = cls.env["product.category"].create(
                    {
                        "name": "Maintenance and Repairs",
                        "parent_id": parent_categ.id,
                        "log_type": "service",
                    }
                )

        cls.fuel_product = cls.ProductProduct.create(
            {
                "name": "Gasoline",
                "categ_id": cls.fuel_category.id,
                "type": "service",
            }
        )
        cls.toll_product = cls.ProductProduct.create(
            {
                "name": "Toll Card Reload",
                "categ_id": cls.toll_category.id,
                "type": "service",
            }
        )
        cls.insurance_product = cls.ProductProduct.create(
            {
                "name": "Vehicle Insurance",
                "categ_id": cls.service_category.id,
                "type": "service",
            }
        )
        cls.service_product = cls.ProductProduct.create(
            {
                "name": "Brake Service",
                "categ_id": cls.service_category.id,
                "type": "service",
            }
        )

    def test_create_asset_basic(self):
        asset = self.ProductTrace.create(
            {
                "name": "SN-001",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        self.assertEqual(asset.name, "SN-001")
        self.assertEqual(asset.product_id, self.vehicle_product)
        self.assertEqual(asset.asset_id.kind_id.code, "vehicle")

    def test_create_vehicle_with_license_plate(self):
        asset = self.ProductTrace.create(
            {
                "name": "SN-002",
                "product_id": self.vehicle_product.id,
                "license_plate": "ABC-123",
                "company_id": self.env.company.id,
            }
        )

        self.assertEqual(asset.license_plate, "ABC-123")

    def test_license_plate_null_allows_duplicates_in_same_company(self):
        first = self.ProductTrace.create(
            {
                "name": "SN-NULL-1",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )
        second = self.ProductTrace.create(
            {
                "name": "SN-NULL-2",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )
        self.assertFalse(first.license_plate)
        self.assertFalse(second.license_plate)
        self.assertNotEqual(first.id, second.id)

    def test_license_plate_unique_per_company(self):
        self.ProductTrace.create(
            {
                "name": "SN-003",
                "product_id": self.vehicle_product.id,
                "license_plate": "XYZ-789",
                "company_id": self.env.company.id,
            }
        )

        with (
            self.assertRaises(ValidationError),
            mute_logger("odoo.db.cursor"),
            self.cr.savepoint(),
        ):
            self.ProductTrace.create(
                {
                    "name": "SN-004",
                    "product_id": self.vehicle_product.id,
                    "license_plate": "XYZ-789",
                    "company_id": self.env.company.id,
                }
            )

    def test_vin_sn_unique_globally(self):
        self.ProductTrace.create(
            {
                "name": "SN-005",
                "product_id": self.vehicle_product.id,
                "vin_sn": "1FTFW1ET5NKE12346",
                "company_id": self.env.company.id,
            }
        )

        with (
            self.assertRaises(ValidationError),
            mute_logger("odoo.db.cursor"),
            self.cr.savepoint(),
        ):
            self.ProductTrace.create(
                {
                    "name": "SN-006",
                    "product_id": self.vehicle_product.id,
                    "vin_sn": "1FTFW1ET5NKE12346",
                    "company_id": self.env.company.id,
                }
            )

    def test_cadastral_id_unique_globally(self):
        self.ProductTrace.create(
            {
                "name": "PROP-001",
                "product_id": self.vehicle_product.id,
                "cadastral_id": "CAD-12345",
                "company_id": self.env.company.id,
            }
        )
        with (
            self.assertRaises(ValidationError),
            mute_logger("odoo.db.cursor"),
            self.cr.savepoint(),
        ):
            self.ProductTrace.create(
                {
                    "name": "PROP-002",
                    "product_id": self.vehicle_product.id,
                    "cadastral_id": "CAD-12345",
                    "company_id": self.env.company.id,
                }
            )

    def test_cadastral_id_independent_from_vin_sn(self):
        vehicle = self.ProductTrace.create(
            {
                "name": "VEH-SHARED",
                "product_id": self.vehicle_product.id,
                "vin_sn": "SHARED00000000042",
                "company_id": self.env.company.id,
            }
        )
        property_lot = self.ProductTrace.create(
            {
                "name": "PROP-SHARED",
                "product_id": self.vehicle_product.id,
                "cadastral_id": "SHARED00000000042",
                "company_id": self.env.company.id,
            }
        )
        self.assertEqual(vehicle.vin_sn, "SHARED00000000042")
        self.assertEqual(property_lot.cadastral_id, "SHARED00000000042")
        self.assertFalse(vehicle.cadastral_id)
        self.assertFalse(property_lot.vin_sn)

    def test_engine_sn_unique_globally(self):
        self.ProductTrace.create(
            {
                "name": "SN-007",
                "product_id": self.vehicle_product.id,
                "engine_sn": "ENG987654321",
                "company_id": self.env.company.id,
            }
        )

        with (
            self.assertRaises(ValidationError),
            mute_logger("odoo.db.cursor"),
            self.cr.savepoint(),
        ):
            self.ProductTrace.create(
                {
                    "name": "SN-008",
                    "product_id": self.vehicle_product.id,
                    "engine_sn": "ENG987654321",
                    "company_id": self.env.company.id,
                }
            )

    def test_compute_display_name_vehicle_with_plate(self):
        asset = self.ProductTrace.create(
            {
                "name": "SN-009",
                "product_id": self.vehicle_product.id,
                "license_plate": "TEST-999",
                "company_id": self.env.company.id,
            }
        )

        expected = f"{self.manufacturer.name} / {self.vehicle_product.name} / TEST-999"
        self.assertEqual(asset.display_name, expected)

    def test_compute_display_name_vehicle_without_plate(self):
        asset = self.ProductTrace.create(
            {
                "name": "SN-010",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        self.assertIn("SN-010", asset.display_name)
        self.assertIn(self.manufacturer.name, asset.display_name)

    def test_compute_display_name_mixed_recordset(self):
        non_vehicle_template = self.ProductTemplate.create(
            {
                "name": "Generic Tool",
                "asset_kind_id": self.env.ref("resource_asset.kind_tool").id,
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
            }
        )
        non_vehicle_product = non_vehicle_template.product_variant_id

        vehicles = self.ProductTrace.create(
            [
                {
                    "name": f"SN-MIX-VEH-{i}",
                    "product_id": self.vehicle_product.id,
                    "license_plate": f"MIX-VEH-{i}",
                    "company_id": self.env.company.id,
                }
                for i in range(3)
            ]
        )
        non_vehicles = self.ProductTrace.create(
            [
                {
                    "name": f"SN-MIX-OTH-{i}",
                    "product_id": non_vehicle_product.id,
                    "company_id": self.env.company.id,
                }
                for i in range(3)
            ]
        )
        mixed = vehicles | non_vehicles
        mixed.invalidate_recordset(["display_name"])

        for asset in mixed:
            self.assertTrue(
                asset.display_name,
                f"display_name empty on asset {asset.name}",
            )

    def test_odometer_initial(self):
        asset = self.ProductTrace.create(
            {
                "name": "SN-019",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        self.assertEqual(asset.asset_id.odometer, 0.0)

    def test_odometer_with_logs(self):
        asset = self.ProductTrace.create(
            {
                "name": "SN-020",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        self.ProductAssetLog.create(
            {
                "asset_id": asset.asset_id.id,
                "product_id": self.fuel_product.id,
                "odometer": 10000.0,
            }
        )
        self.ProductAssetLog.create(
            {
                "asset_id": asset.asset_id.id,
                "product_id": self.fuel_product.id,
                "odometer": 15000.0,
            }
        )
        self.ProductAssetLog.create(
            {
                "asset_id": asset.asset_id.id,
                "product_id": self.fuel_product.id,
                "odometer": 12000.0,
            }
        )

        asset.invalidate_recordset()
        self.assertEqual(asset.asset_id.odometer, 12000.0)

    def test_count_logs_all(self):
        asset = self.ProductTrace.create(
            {
                "name": "SN-021",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        self.ProductAssetLog.create(
            {
                "asset_id": asset.asset_id.id,
                "product_id": self.fuel_product.id,
            }
        )
        self.ProductAssetLog.create(
            {
                "asset_id": asset.asset_id.id,
                "product_id": self.toll_product.id,
            }
        )
        self.ProductAssetLog.create(
            {
                "asset_id": asset.asset_id.id,
                "product_id": self.insurance_product.id,
            }
        )

        asset.invalidate_recordset()
        self.assertEqual(asset.asset_id.count_logs_all, 3)

    def test_count_logs_service(self):
        asset = self.ProductTrace.create(
            {
                "name": "SN-022",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        self.ProductAssetLog.create(
            {"asset_id": asset.asset_id.id, "product_id": self.service_product.id}
        )
        self.ProductAssetLog.create(
            {"asset_id": asset.asset_id.id, "product_id": self.service_product.id}
        )
        self.ProductAssetLog.create(
            {"asset_id": asset.asset_id.id, "product_id": self.fuel_product.id}
        )
        self.ProductAssetLog.create(
            {"asset_id": asset.asset_id.id, "product_id": self.toll_product.id}
        )

        asset.invalidate_recordset()
        self.assertEqual(asset.asset_id.count_logs_service, 2)

    def test_action_view_logs_service(self):
        asset = self.ProductTrace.create(
            {
                "name": "SN-027",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        action = asset.action_view_logs_service()

        self.assertEqual(action["res_model"], "resource.log")
        self.assertIn(("asset_id", "=", asset.asset_id.id), action["domain"])
        self.assertIn(("log_type", "=", "service"), action["domain"])
        self.assertEqual(action["context"]["default_asset_id"], asset.asset_id.id)

    def test_action_view_logs_all(self):
        asset = self.ProductTrace.create(
            {
                "name": "SN-029",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        action = asset.action_view_logs_all()

        self.assertEqual(action["res_model"], "resource.log")
        self.assertEqual(action["domain"], [("asset_id", "=", asset.asset_id.id)])
        self.assertEqual(action["context"]["default_asset_id"], asset.asset_id.id)

    def test_brand_new_default(self):
        asset = self.ProductTrace.create(
            {
                "name": "SN-030",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        self.assertTrue(asset.brand_new)

    def test_trailer_hook_default(self):
        asset = self.ProductTrace.create(
            {
                "name": "SN-031",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        vehicle = self.env["resource.asset.vehicle"].browse(asset.asset_id.id)
        self.assertFalse(vehicle.trailer_hook)

    def test_financial_fields(self):
        today = fields.Date.today()
        future_date = today + timedelta(days=365)

        asset = self.ProductTrace.create(
            {
                "name": "SN-032",
                "product_id": self.vehicle_product.id,
                "date_acquisition": today,
                "date_write_off": future_date,
                "value_original": 50000.0,
                "value_residual": 35000.0,
                "account_prefix": "VEH",
                "company_id": self.env.company.id,
            }
        )

        self.assertEqual(asset.date_acquisition, today)
        self.assertEqual(asset.date_write_off, future_date)
        self.assertEqual(asset.value_original, 50000.0)
        self.assertEqual(asset.value_residual, 35000.0)
        self.assertEqual(asset.account_prefix, "VEH")

    def test_service_activity_none(self):
        asset = self.ProductTrace.create(
            {
                "name": "SN-035",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        self.assertEqual(asset.asset_id.service_activity, "none")

    def test_service_activity_overdue(self):
        asset = self.ProductTrace.create(
            {
                "name": "SN-035b",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )
        log = self.ProductAssetLog.create(
            {
                "asset_id": asset.asset_id.id,
                "product_id": self.service_product.id,
            }
        )
        activity_type = self.env.ref(
            "mail.mail_activity_data_todo", raise_if_not_found=False
        )
        if not activity_type:
            self.skipTest("mail.mail_activity_data_todo not available")
        log.activity_schedule(
            "mail.mail_activity_data_todo",
            date_deadline=fields.Date.today() - timedelta(days=2),
        )
        asset.invalidate_recordset()
        self.assertEqual(asset.asset_id.service_activity, "overdue")

    def test_odometer_uom_default(self):
        asset = self.ProductTrace.create(
            {
                "name": "SN-036",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        km_uom = self.env.ref("uom.product_uom_km", raise_if_not_found=False)
        if km_uom:
            self.assertEqual(asset.odometer_uom_id, km_uom)

    def test_action_view_logs_fuel(self):
        asset = self.ProductTrace.create(
            {
                "name": "SN-FUEL-ACT",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        action = asset.action_view_logs_fuel()

        self.assertEqual(action["res_model"], "resource.log")
        self.assertIn(("asset_id", "=", asset.asset_id.id), action["domain"])
        self.assertIn(("log_type", "=", "fuel"), action["domain"])
        self.assertEqual(action["context"]["default_asset_id"], asset.asset_id.id)
        self.assertEqual(
            action["context"]["default_product_category_id"],
            self.fuel_category.id,
        )


@tagged("post_install", "-at_install")
class TestStockLotTransportCapacity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        has_publish_date = ensure_publish_date_field(cls.env)

        vals = {
            "name": "Capacity Test Vehicle",
            "type": "consu",
            "is_storable": True,
            "tracking": "serial",
        }
        if has_publish_date:
            vals["publish_date"] = fields.Datetime.now()
        cls.vehicle_template = cls.env["product.template"].create(vals)
        cls.vehicle_product = cls.vehicle_template.product_variant_id

    def _asset(self, name, **vals):
        return self.env["product.trace"].create(
            {
                "name": name,
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
                **vals,
            }
        )

    def test_the_model_rating_reaches_its_units(self):
        self.vehicle_template.write(
            {"weight_capacity": 1500.0, "volume_capacity": 25.5}
        )
        asset = self._asset("CAP-001")

        self.assertEqual(asset.product_id.weight_capacity, 1500.0)
        self.assertEqual(asset.product_id.volume_capacity, 25.5)

    def test_an_unrated_model_leaves_its_units_at_zero(self):
        asset = self._asset("CAP-003")

        self.assertEqual(asset.product_id.weight_capacity, 0.0)
        self.assertEqual(asset.product_id.volume_capacity, 0.0)

    def test_rerating_the_model_moves_every_unit(self):
        self.vehicle_template.write(
            {"weight_capacity": 1000.0, "volume_capacity": 10.0}
        )
        asset = self._asset("CAP-004")

        self.vehicle_template.write(
            {"weight_capacity": 2000.0, "volume_capacity": 20.0}
        )

        self.assertEqual(asset.product_id.weight_capacity, 2000.0)
        self.assertEqual(asset.product_id.volume_capacity, 20.0)

    def test_capacity_sits_beside_the_other_model_ratings(self):
        self.vehicle_template.write(
            {
                "fuel_tank_capacity": 80,
                "weight_capacity": 3500.0,
                "volume_capacity": 40.0,
            }
        )
        asset = self._asset("CAP-005", license_plate="CAP-123")

        self.assertEqual(asset.license_plate, "CAP-123")
        self.assertEqual(asset.product_id.fuel_tank_capacity, 80)
        self.assertEqual(asset.product_id.weight_capacity, 3500.0)
        self.assertEqual(asset.product_id.volume_capacity, 40.0)


@tagged("post_install", "-at_install")
class TestLotIdentityIsTheAssets(TransactionCase):
    """The lot's identity columns are relates onto `resource.asset`, so core's
    identifier rules have to reach a value written on the serial."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template = cls.env["product.template"].create(
            {
                "name": "IMEI probe",
                "asset_kind_id": cls.env.ref("resource_asset.kind_equipment").id,
                "is_storable": True,
                "tracking": "serial",
            }
        )

    def _lot(self, name, **vals):
        return self.env["product.trace"].create(
            {
                "name": name,
                "product_id": self.template.product_variant_ids[0].id,
                **vals,
            }
        )

    def test_an_imei_written_on_the_serial_is_globally_unique(self):
        self._lot("IMEI-A", imei="356938035643809")

        with (
            self.assertRaises(ValidationError),
            mute_logger("odoo.db.cursor"),
            self.cr.savepoint(),
        ):
            self._lot("IMEI-B", imei="356938035643809")

    def test_copying_a_serial_does_not_duplicate_its_imei(self):
        lot = self._lot("IMEI-C", imei="356938035643810")

        self.assertFalse(lot.copy().imei)
