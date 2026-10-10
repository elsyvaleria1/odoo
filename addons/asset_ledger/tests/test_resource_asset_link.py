from datetime import datetime

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from .common import create_test_product


@tagged("post_install", "-at_install")
class TestResourceAssetLink(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = create_test_product(
            cls.env, name="Pickup", tracking="serial", asset_kind="vehicle"
        )
        cls.plate_type = cls.env.ref("resource.identifier_type_plate")
        cls.vin_type = cls.env.ref("resource.identifier_type_vin")

    def _lot(self, name="PK-1", **vals):
        return self.env["product.trace"].create(
            {
                "name": name,
                "product_id": self.product.id,
                "company_id": self.env.company.id,
                **vals,
            }
        )

    def test_the_product_kind_names_the_asset_kind(self):
        self.assertEqual(self.product.asset_kind_id.code, "vehicle")
        plain = create_test_product(self.env, name="Bolt", tracking="serial")
        self.assertFalse(plain.asset_kind_id)
        self.product.product_tmpl_id.asset_kind_id = self.env.ref("resource.kind_tool")
        self.assertEqual(self.product.asset_kind_id.code, "tool")
        self.product.product_tmpl_id.asset_kind_id = False
        self.assertFalse(self.product.asset_kind_id)

    def test_an_asset_lot_is_a_resource_asset(self):
        lot = self._lot(license_plate="ABC-123", vin_sn="1HGCM82633A004352")
        asset = lot.asset_id
        self.assertTrue(asset)
        self.assertEqual(asset.trace_id, lot)
        self.assertEqual(asset.kind_id.code, "vehicle")
        self.assertEqual(asset.type, "material")
        self.assertEqual(asset._get_identifier("plate"), "ABC-123")
        self.assertEqual(asset._get_identifier("vin"), "1HGCM82633A004352")
        self.assertFalse(asset.missing_identifier_type_ids)

    def test_identity_follows_the_lot(self):
        lot = self._lot(license_plate="ABC-123")
        lot.license_plate = "XYZ-999"
        self.assertEqual(lot.asset_id._get_identifier("plate"), "XYZ-999")
        lot.license_plate = False
        self.assertFalse(lot.asset_id._get_identifier("plate"))
        self.assertIn(self.plate_type, lot.asset_id.missing_identifier_type_ids)

    def test_odometer_follows_the_ledger(self):
        lot = self._lot()
        fuel = self.env.ref("asset_ledger.product_category_fuel")
        log_model = self.env["resource.log"]
        log_model.create(
            {
                "asset_id": lot.asset_id.id,
                "product_id": self.env.ref(
                    "asset_ledger.product_product_fuel_debit"
                ).id,
                "date": datetime(2026, 1, 5),
                "odometer": 1000,
                "state": "done",
            }
        )
        lot.invalidate_recordset()
        meter = lot.asset_id.odometer_meter_id
        self.assertTrue(meter)
        self.assertEqual(meter.value, 1000)
        self.assertEqual(meter.uom_id, lot.odometer_uom_id)
        log_model.create(
            {
                "asset_id": lot.asset_id.id,
                "product_id": self.env.ref(
                    "asset_ledger.product_product_fuel_debit"
                ).id,
                "date": datetime(2026, 1, 9),
                "odometer": 1250,
                "state": "done",
            }
        )
        lot.invalidate_recordset()
        meter.invalidate_recordset()
        self.assertEqual(lot.asset_id.odometer, 1250)
        self.assertEqual(meter.value, 1250)
        self.assertEqual(len(meter.reading_ids), 2)
        self.assertEqual(fuel.log_type, "fuel")

    def test_deleting_the_newest_reading_walks_the_meter_back(self):
        """The lot's odometer falls back to the previous reading, so the meter
        has to fall with it. Nothing links a meter reading to the log that
        produced it, so the correction is recorded rather than erased."""
        lot = self._lot(name="PK-UNLINK")
        log_model = self.env["resource.log"]
        fuel = self.env.ref("asset_ledger.product_product_fuel_debit")
        first = log_model.create(
            {
                "asset_id": lot.asset_id.id,
                "product_id": fuel.id,
                "date": datetime(2026, 2, 1),
                "odometer": 1000,
            }
        )
        newest = log_model.create(
            {
                "asset_id": lot.asset_id.id,
                "product_id": fuel.id,
                "date": datetime(2026, 2, 10),
                "odometer": 2000,
            }
        )
        lot.invalidate_recordset()
        meter = lot.asset_id.odometer_meter_id
        self.assertEqual(lot.asset_id.odometer, 2000)
        self.assertEqual(meter.value, 2000)

        newest.unlink()
        lot.invalidate_recordset()
        meter.invalidate_recordset()
        self.assertEqual(lot.asset_id.odometer, 1000)
        self.assertEqual(
            meter.value,
            1000,
            "the meter kept the reading of a log that no longer exists",
        )
        self.assertTrue(first.exists())

    def test_deleting_the_only_reading_leaves_the_meter_alone(self):
        """With no ledger reading left there is nothing to record: 0 is not a
        measurement, so the meter keeps its last reading and the lot, which
        reads the meter now, keeps showing it."""
        lot = self._lot(name="PK-UNLINK-LAST")
        log = self.env["resource.log"].create(
            {
                "asset_id": lot.asset_id.id,
                "product_id": self.env.ref(
                    "asset_ledger.product_product_fuel_debit"
                ).id,
                "date": datetime(2026, 3, 1),
                "odometer": 500,
            }
        )
        lot.invalidate_recordset()
        meter = lot.asset_id.odometer_meter_id
        self.assertEqual(meter.value, 500)
        log.unlink()
        lot.invalidate_recordset()
        meter.invalidate_recordset()
        self.assertEqual(lot.asset_id.odometer, 500.0)
        self.assertEqual(len(meter.reading_ids), 1)

    def test_retyping_the_model_retypes_the_asset(self):
        """`kind_id` is what every bridge reads to know what this asset is. It
        was written once at create and never again."""
        lot = self._lot(name="PK-RETYPE")
        asset = lot.asset_id
        self.assertEqual(asset.kind_id.code, "vehicle")
        machinery = create_test_product(
            self.env, name="Harvester", tracking="serial", asset_kind="machinery"
        )
        lot.write({"name": "PK-RETYPE-B", "product_id": machinery.id})
        asset.invalidate_recordset()
        self.assertEqual(lot.product_id.asset_kind_id.code, "machinery")
        self.assertEqual(asset.kind_id.code, "machinery")
        self.assertEqual(asset.product_id, machinery)
        self.assertEqual(asset.name, "Harvester PK-RETYPE-B")

    def test_moving_the_lot_moves_the_asset(self):
        lot = self._lot(name="PK-COMPANY")
        asset = lot.asset_id
        self.assertEqual(asset.company_id, self.env.company)
        other = self.env["res.company"].create({"name": "Second company"})
        self.env.user.company_ids = [(4, other.id)]
        lot.company_id = other
        asset.invalidate_recordset()
        self.assertEqual(asset.company_id, other)

    def test_demoting_the_model_leaves_the_kind_alone(self):
        """`resource.asset.kind_id` is required, so a template demoted back to
        a plain product must not blank it -- the asset keeps what it was."""
        lot = self._lot(name="PK-DEMOTE")
        asset = lot.asset_id
        plain = create_test_product(self.env, name="Bolt crate", tracking="serial")
        lot.product_id = plain
        asset.invalidate_recordset()
        self.assertEqual(asset.kind_id.code, "vehicle")
        self.assertEqual(asset.product_id, plain)

    def test_a_plain_serial_gets_no_asset(self):
        plain = create_test_product(self.env, name="Bolt", tracking="serial")
        lot = self.env["product.trace"].create(
            {"name": "B-1", "product_id": plain.id, "company_id": self.env.company.id}
        )
        self.assertFalse(lot.asset_id)

    def test_the_lifecycle_attributes_follow_the_lot(self):
        """`date_acquisition`, `model_year` and `brand_new` existed on both
        models and were written on neither side's behalf; `date_write_off` is
        the asset's `date_disposal`."""
        acquired = datetime(2024, 5, 1).date()
        lot = self._lot(
            name="PK-DATES",
            date_acquisition=acquired,
            model_year=2024,
            brand_new=False,
        )
        asset = lot.asset_id
        self.assertEqual(asset.date_acquisition, acquired)
        self.assertEqual(asset.model_year, 2024)
        self.assertFalse(asset.brand_new)
        self.assertFalse(asset.date_disposal)
        written_off = datetime(2026, 1, 15).date()
        lot.write({"date_write_off": written_off, "model_year": 2025})
        asset.invalidate_recordset()
        self.assertEqual(asset.date_disposal, written_off)
        self.assertEqual(asset.model_year, 2025)

    def test_an_identifier_written_on_the_asset_reaches_the_lot(self):
        lot = self._lot(name="PK-IDENT", license_plate="ABC-123")
        asset = lot.asset_id
        plate = asset.identifier_ids.filtered(lambda i: i.type_id == self.plate_type)
        plate.value = "XYZ-999"
        self.assertEqual(lot.license_plate, "XYZ-999")
        self.env["resource.identifier"].create(
            {
                "resource_id": asset.id,
                "type_id": self.vin_type.id,
                "value": "1HGCM82633A004352",
            }
        )
        self.assertEqual(lot.vin_sn, "1HGCM82633A004352")
        plate.unlink()
        self.assertFalse(lot.license_plate)
        self.assertEqual(lot.vin_sn, "1HGCM82633A004352")

    def test_identity_uniqueness_is_the_identifiers_normalized_one(self):
        self._lot(name="PK-U1", vin_sn="1HGCM82633A004352")
        with self.assertRaises(ValidationError):
            self._lot(name="PK-U2", vin_sn="1hgcm 82633a-004352")
