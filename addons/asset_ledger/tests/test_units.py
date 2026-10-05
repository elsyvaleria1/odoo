from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import create_test_template


@tagged("post_install", "-at_install")
class TestOdometerUnits(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.km = cls.env.ref("uom.product_uom_km")
        cls.mile = cls.env.ref("uom.product_uom_mile")
        cls.template = create_test_template(
            cls.env,
            name="Units probe truck",
            asset_kind="vehicle",
            tracking="serial",
        )
        cls.fuel_product = cls.env.ref("asset_ledger.product_product_fuel_debit")

    def _asset(self, name, uom):
        return self.env["product.trace"].create(
            {
                "name": name,
                "product_id": self.template.product_variant_ids[0].id,
                "license_plate": name,
                "odometer_uom_id": uom.id,
            }
        )

    def _fuel_log(self, asset, date, odometer, litres):
        return self.env["resource.log"].create(
            {
                "asset_id": asset.asset_id.id,
                "product_id": self.fuel_product.id,
                "date": date,
                "odometer": odometer,
                "qty_fuel": litres,
            }
        )

    def test_efficiency_names_the_unit_it_is_actually_in(self):
        metric = self._asset("UNITS-KM", self.km)
        self._fuel_log(metric, "2026-01-01", 1000, 50)
        log = self._fuel_log(metric, "2026-01-02", 1500, 50)

        self.assertEqual(log.efficiency, 10.0)
        self.assertEqual(log.efficiency_uom_name, f"{self.km.display_name}/L")

    def test_a_mile_reading_asset_does_not_claim_kilometres(self):
        imperial = self._asset("UNITS-MI", self.mile)
        self._fuel_log(imperial, "2026-01-01", 1000, 50)
        log = self._fuel_log(imperial, "2026-01-02", 1500, 50)

        self.assertEqual(log.efficiency, 10.0)
        self.assertEqual(log.efficiency_uom_name, f"{self.mile.display_name}/L")
        self.assertNotIn(self.km.display_name, log.efficiency_uom_name)

    def test_the_log_carries_the_unit_its_odometer_is_in(self):
        imperial = self._asset("UNITS-MI-2", self.mile)
        log = self._fuel_log(imperial, "2026-01-01", 1000, 50)

        self.assertEqual(log.odometer_uom_name, self.mile.display_name)

    def test_the_unit_may_still_be_set_before_any_reading(self):
        asset = self._asset("UNITS-FRESH", self.km)
        asset.odometer_uom_id = self.mile
        self.assertEqual(asset.odometer_uom_id, self.mile)

    def test_rewriting_the_same_unit_is_not_a_change(self):
        asset = self._asset("UNITS-NOOP", self.km)
        self._fuel_log(asset, "2026-01-01", 1000, 50)
        asset.odometer_uom_id = self.km
        self.assertEqual(asset.odometer_uom_id, self.km)

    def test_switching_the_unit_would_restate_history_and_is_refused(self):
        asset = self._asset("UNITS-HELD", self.km)
        self._fuel_log(asset, "2026-01-01", 1000, 50)

        with self.assertRaises(ValidationError):
            asset.odometer_uom_id = self.mile


@tagged("post_install", "-at_install")
class TestAreaUnits(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template = create_test_template(
            cls.env, name="Units probe parcel", asset_kind="property"
        )
        cls.parcel = cls.env["product.trace"].create(
            {
                "name": "UNITS-PARCEL",
                "product_id": cls.template.product_variant_ids[0].id,
                "cadastral_id": "UNITS-CAD-1",
                "area": 5000,
            }
        )
        cls.param = cls.env["ir.config_parameter"].sudo()

    def test_area_names_the_metric_unit_by_default(self):
        self.param.set_param("product.area_in_square_ft", "0")
        self.parcel.invalidate_recordset()
        self.assertEqual(
            self.parcel.asset_id.area_uom_name,
            self.env.ref("uom.product_uom_square_meter").display_name,
        )

    def test_area_follows_the_imperial_setting(self):
        self.param.set_param("product.area_in_square_ft", "1")
        self.parcel.invalidate_recordset()
        self.assertEqual(
            self.parcel.asset_id.area_uom_name,
            self.env.ref("uom.product_uom_square_foot").display_name,
        )
