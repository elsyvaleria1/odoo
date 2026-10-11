from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import ensure_publish_date_field


@tagged("post_install", "-at_install")
class TestProductTemplate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ProductTemplate = cls.env["product.template"]
        cls._has_publish_date_field = ensure_publish_date_field(cls.env)

    def _create_product(self, vals):
        if self._has_publish_date_field:
            vals.setdefault("publish_date", fields.Datetime.now())
        return self.ProductTemplate.with_context(mail_notrack=True).create(vals)

    def test_create_vehicle_asset(self):
        vehicle = self._create_product(
            {
                "name": "Test Truck",
                "asset_kind_id": self.env.ref("base.kind_vehicle").id,
                "power": 250,
                "co2": 180.5,
                "fuel_tank_capacity": 80,
                "doors": 4,
                "seats": 5,
            }
        )

        self.assertEqual(vehicle.asset_kind_id.code, "vehicle")
        self.assertEqual(vehicle.power, 250)
        self.assertEqual(vehicle.co2, 180.5)
        self.assertEqual(vehicle.fuel_tank_capacity, 80)
        self.assertEqual(vehicle.doors, 4)
        self.assertEqual(vehicle.seats, 5)

    def test_create_equipment_asset(self):
        equipment = self._create_product(
            {
                "name": "Industrial Crane",
                "asset_kind_id": self.env.ref("base.kind_equipment").id,
                "power": 500,
                "weight_capacity": 5000.0,
            }
        )

        self.assertEqual(equipment.asset_kind_id.code, "equipment")
        self.assertEqual(equipment.power, 500)
        self.assertEqual(equipment.weight_capacity, 5000.0)

    def test_create_machinery_asset(self):
        machinery = self._create_product(
            {
                "name": "Excavator",
                "asset_kind_id": self.env.ref("base.kind_machinery").id,
                "power": 350,
                "fuel_tank_capacity": 120,
            }
        )

        self.assertEqual(machinery.asset_kind_id.code, "machinery")
        self.assertEqual(machinery.power, 350)
        self.assertEqual(machinery.fuel_tank_capacity, 120)

    def test_create_it_asset(self):
        it_asset = self._create_product(
            {
                "name": "Server Rack",
                "asset_kind_id": self.env.ref("base.kind_it").id,
                "power": 2,
            }
        )

        self.assertEqual(it_asset.asset_kind_id.code, "it")
        self.assertEqual(it_asset.power, 2)

    def test_create_property_asset(self):
        property_asset = self._create_product(
            {
                "name": "Warehouse Building",
                "asset_kind_id": self.env.ref("base.kind_property").id,
                "volume_capacity": 10000.0,
            }
        )

        self.assertEqual(property_asset.asset_kind_id.code, "property")
        self.assertEqual(property_asset.volume_capacity, 10000.0)

    def test_create_tools_asset(self):
        tool = self._create_product(
            {
                "name": "Power Drill Set",
                "asset_kind_id": self.env.ref("base.kind_tool").id,
                "weight_capacity": 5.0,
            }
        )

        self.assertEqual(tool.asset_kind_id.code, "tool")
        self.assertEqual(tool.weight_capacity, 5.0)

    def test_a_plain_product_names_no_kind(self):
        product = self._create_product(
            {
                "name": "Generic Product",
            }
        )

        self.assertFalse(product.asset_kind_id)

    def test_fuel_efficiency_fields(self):
        vehicle = self._create_product(
            {
                "name": "Efficient Car",
                "asset_kind_id": self.env.ref("base.kind_vehicle").id,
                "fuel_efficiency_theoretical": 15.0,
                "fuel_efficiency_min": 12.0,
                "fuel_efficiency_max": 18.0,
            }
        )

        self.assertEqual(vehicle.fuel_efficiency_theoretical, 15.0)
        self.assertEqual(vehicle.fuel_efficiency_min, 12.0)
        self.assertEqual(vehicle.fuel_efficiency_max, 18.0)

    def test_capacity_fields(self):
        truck = self._create_product(
            {
                "name": "Cargo Truck",
                "asset_kind_id": self.env.ref("base.kind_vehicle").id,
                "weight_capacity": 3500.0,
                "volume_capacity": 25.0,
            }
        )

        self.assertEqual(truck.weight_capacity, 3500.0)
        self.assertEqual(truck.volume_capacity, 25.0)

    def test_range_field(self):
        electric_car = self._create_product(
            {
                "name": "Electric Vehicle",
                "asset_kind_id": self.env.ref("base.kind_vehicle").id,
                "vehicle_range": 450,
            }
        )

        self.assertEqual(electric_car.vehicle_range, 450)

    def test_compute_fuel_efficiency_uom_name(self):
        icp = self.env["ir.config_parameter"].sudo()
        vehicle = self._create_product(
            {
                "name": "Test Vehicle",
                "asset_kind_id": self.env.ref("base.kind_vehicle").id,
                "fuel_efficiency_theoretical": 15.0,
            }
        )
        icp.set_param("product.fuel_efficiency_in_mpg", "0")
        vehicle.invalidate_recordset(["fuel_efficiency_uom_name"])
        expected_kml = self.env.ref("base.product_uom_km_per_liter").display_name
        self.assertEqual(vehicle.fuel_efficiency_uom_name, expected_kml)

        icp.set_param("product.fuel_efficiency_in_mpg", "1")
        vehicle.invalidate_recordset(["fuel_efficiency_uom_name"])
        expected_mpg = self.env.ref("base.product_uom_miles_per_galon").display_name
        self.assertEqual(vehicle.fuel_efficiency_uom_name, expected_mpg)

    def test_promoting_a_template_gives_its_lots_an_asset(self):
        """Core creates the `resource.resource` from `stock.lot.create` alone, so
        a unit received before the promotion had none and stayed invisible to
        every `resource.resource` consumer."""
        template = self._create_product(
            {
                "name": "Promotable crate",
                "is_storable": True,
                "tracking": "serial",
            }
        )
        lot = self.env["product.trace"].create(
            {
                "name": "PROMOTE-1",
                "product_id": template.product_variant_ids[0].id,
                "company_id": self.env.company.id,
            }
        )
        self.assertFalse(lot.asset_id)

        template.write({"asset_kind_id": self.env.ref("base.kind_machinery").id})
        lot.invalidate_recordset()
        self.assertTrue(lot.asset_id)
        self.assertEqual(lot.asset_id.kind_id.code, "machinery")
        self.assertEqual(lot.asset_id.trace_id, lot)

    def test_retyping_an_asset_template_creates_nothing_new(self):
        """Only the empty-to-set edge backfills. A template that was already an
        asset kind has its lots' assets; PA2-05's sync retypes them."""
        template = self._create_product(
            {
                "name": "Already typed truck",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": self.env.ref("base.kind_vehicle").id,
            }
        )
        lot = self.env["product.trace"].create(
            {
                "name": "RETYPE-1",
                "product_id": template.product_variant_ids[0].id,
                "company_id": self.env.company.id,
            }
        )
        asset = lot.asset_id
        self.assertTrue(asset)
        template.write({"asset_kind_id": self.env.ref("base.kind_machinery").id})
        lot.invalidate_recordset()
        self.assertEqual(lot.asset_id, asset, "a second asset was created")

    def test_change_default_attribute(self):
        field_info = self.ProductTemplate._fields["asset_kind_id"]
        self.assertTrue(field_info.change_default)

    def test_every_kind_this_module_names_is_seeded(self):
        for code in ("equipment", "it", "machinery", "property", "tool", "vehicle"):
            self.assertTrue(
                self.env.ref(f"base.kind_{code}", raise_if_not_found=False),
                code,
            )
