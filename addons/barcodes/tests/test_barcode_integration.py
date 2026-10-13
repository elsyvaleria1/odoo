
from odoo.exceptions import UserError
from odoo.tests import common


class TestBarcodeNomenclatureLifecycle(common.TransactionCase):
    def test_default_nomenclature_cannot_be_deleted(self):
        default = self.env.ref("barcodes.default_barcode_nomenclature")
        with self.assertRaises(UserError):
            default.unlink()

    def test_nomenclature_in_use_cannot_be_deleted(self):
        nomenclature = self.env["barcode.nomenclature"].create({"name": "In Use"})
        self.env.company.barcodes_config_id.nomenclature_id = nomenclature
        with self.assertRaises(UserError):
            nomenclature.unlink()
        self.assertEqual(
            self.env.company.barcodes_config_id.nomenclature_id, nomenclature
        )

    def test_nomenclature_of_an_archived_company_cannot_be_deleted(self):
        nomenclature = self.env["barcode.nomenclature"].create({"name": "Archived"})
        company = self.env["res.company"].create({"name": "Archived Co"})
        company.barcodes_config_id.nomenclature_id = nomenclature
        company.active = False
        with self.assertRaises(UserError):
            nomenclature.unlink()

    def test_unused_nomenclature_can_be_deleted(self):
        nomenclature = self.env["barcode.nomenclature"].create({"name": "Unused"})
        nomenclature.unlink()
        self.assertFalse(nomenclature.exists())

    def test_new_company_gets_the_default_nomenclature(self):
        company = self.env["res.company"].create({"name": "Barcode Co"})
        self.assertEqual(
            company.barcodes_config_id.nomenclature_id,
            self.env.ref("barcodes.default_barcode_nomenclature"),
        )


class TestBarcodeEventsMixin(common.TransactionCase):
    def test_unimplemented_hook_raises_for_the_developer(self):
        scanned = self.env["mixin.barcodes.barcode_events"]
        with self.assertRaises(NotImplementedError) as caught:
            scanned.on_barcode_scanned("12345670")
        self.assertIn("mixin.barcodes.barcode_events", str(caught.exception))

    def test_onchange_clears_the_field_and_forwards_the_barcode(self):
        seen = []
        mixin = self.env["mixin.barcodes.barcode_events"]
        record = mixin.new({"_barcode_scanned": "12345670"})
        self.patch(
            type(mixin),
            "on_barcode_scanned",
            lambda self, barcode: seen.append(barcode),
        )
        record._on_barcode_scanned()
        self.assertEqual(seen, ["12345670"])
        self.assertEqual(record._barcode_scanned, "")

    def test_onchange_ignores_an_empty_barcode(self):
        seen = []
        mixin = self.env["mixin.barcodes.barcode_events"]
        record = mixin.new({"_barcode_scanned": ""})
        self.patch(
            type(mixin),
            "on_barcode_scanned",
            lambda self, barcode: seen.append(barcode),
        )
        self.assertIsNone(record._on_barcode_scanned())
        self.assertEqual(seen, [])
