from pathlib import Path

from odoo.libs.documents import Document
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.extract.tools import CHEAP, run
from odoo.addons.extract_delivery.tools.shipping_order import find_totals

OCR_TEXT = (Path(__file__).parent / "fixtures" / "shipping_order_ocr.txt").read_text()


@tagged("post_install", "-at_install")
class TestShippingOrder(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["delivery.carrier"].create(
            {
                "name": "Tres Guerras",
                "product_id": cls.env["product.product"]
                .create({"name": "Freight", "type": "service"})
                .id,
                "tracking_ref_pattern": "[A-Z]{3}[0-9]{8}",
                "tracking_ref_example": "TOL01584640",
            }
        )

    def _read(self, text, barcodes=None):
        document = Document.of(text=text, name="sheet.txt")
        if barcodes is not None:
            document.seed("barcodes", barcodes)
        return run(document, "shipping_order", self.env, up_to=CHEAP)

    def test_the_sheet_s_text_gives_route_service_date_and_amounts(self):
        values = self._read(OCR_TEXT).flat()
        self.assertEqual(values["tracking_ref"], "TOL01584640")
        self.assertEqual(values["origin"], "TOLUCA, EDO. DE MEXICO")
        self.assertEqual(values["destination"], "TAPACHULA, CHIS.")
        self.assertEqual(values["service"], "ocurre")
        self.assertEqual(str(values["date"]), "2026-10-08")
        self.assertEqual(values["total"], 4731.25)
        self.assertEqual(values["subtotal"], 4078.66)
        self.assertEqual(values["tax_amount"], 652.59)
        self.assertEqual(values["tax_withheld"], 0.0)

    def test_the_barcode_gives_the_tracking_number_a_carrier_recognises(self):
        result = self._read("Total\n100.00", barcodes=["7501234567890", "TOL01584640"])
        self.assertEqual(result.flat()["tracking_ref"], "TOL01584640")
        self.assertIn("shipping_order_barcode", result.ran)

    def test_a_code_no_carrier_recognises_is_not_a_tracking_number(self):
        result = self._read("Total\n100.00", barcodes=["7501234567890"])
        self.assertIsNone(result.flat().get("tracking_ref"))
        self.assertIn("tracking_ref", result.missing)

    def test_the_total_is_the_sheet_s_not_the_charges_column_header(self):
        text = "TOTAL\nFlete\n3,847.04\n3,847.04\nSubTotal\nIva\n3,847.04\n615.53\n0.00\nTotal\n4,462.57"
        self.assertEqual(
            find_totals(text),
            {
                "total": 4462.57,
                "subtotal": 3847.04,
                "tax_amount": 615.53,
                "tax_withheld": 0.0,
            },
        )

    def test_withheld_vat_is_subtracted(self):
        text = "SubTotal\nIva\nIva Ret.cc\n1,000.00\n160.00\n40.00\nTotal\n1,120.00"
        totals = find_totals(text)
        self.assertEqual(totals["tax_withheld"], 40.0)
        self.assertEqual(totals["subtotal"], 1000.0)

    def test_amounts_that_do_not_add_up_are_flagged(self):
        result = self._read(
            "TOL01584640\nSubTotal\nIva\n1,000.00\n160.00\nTotal\n1,300.00"
        )
        self.assertEqual(result.flat()["total"], 1300.0)
        self.assertNotIn(
            "subtotal", result.flat(), "no pair of figures gives the total"
        )
