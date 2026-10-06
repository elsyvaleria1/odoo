from odoo.tests.common import TransactionCase


class TelegramApprovalTestBase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.user = cls.env.ref("base.user_admin")

        cls.category = cls.env["approval.category"].create(
            {
                "name": "Test Telegram Category",
                "company_id": cls.company.id,
            }
        )

    def _create_approval_request(self, vals=None):
        default_vals = {
            "name": "Test Request",
            "category_id": self.category.id,
            "request_owner_id": self.user.id,
            "company_id": self.company.id,
        }
        if vals:
            default_vals.update(vals)
        return self.env["approval.request"].create(default_vals)


class TestTelegramDataField(TelegramApprovalTestBase):
    def test_telegram_data_empty(self):
        request = self._create_approval_request()

        self.assertFalse(request.telegram_data)

    def test_telegram_data_stores_json(self):
        data = {
            "partner_fx_name": "Customer ABC",
            "amount": "5000.00",
            "payment_method": "TC",
        }

        request = self._create_approval_request({"telegram_data": data})

        self.assertEqual(request.telegram_data, data)
        self.assertEqual(request.telegram_data["partner_fx_name"], "Customer ABC")
        self.assertEqual(request.telegram_data["amount"], "5000.00")

    def test_telegram_data_full_payload(self):
        data = {
            "partner_fx_name": "Test Partner",
            "product_category": "AGROQUIMICOS",
            "cfdi_use": "GASTOS EN GENERAL",
            "company": "LMMR",
            "partner_cn_name": "CN Partner",
            "payment_method": "TRANSFERENCIA",
            "date": "2024-01-15",
            "amount": "1500.50",
        }

        request = self._create_approval_request({"telegram_data": data})

        self.assertEqual(request.telegram_data["partner_fx_name"], "Test Partner")
        self.assertEqual(request.telegram_data["product_category"], "AGROQUIMICOS")
        self.assertEqual(request.telegram_data["cfdi_use"], "GASTOS EN GENERAL")
        self.assertEqual(request.telegram_data["company"], "LMMR")
        self.assertEqual(request.telegram_data["partner_cn_name"], "CN Partner")
        self.assertEqual(request.telegram_data["payment_method"], "TRANSFERENCIA")
        self.assertEqual(request.telegram_data["date"], "2024-01-15")
        self.assertEqual(request.telegram_data["amount"], "1500.50")


class TestTelegramDataFormatted(TelegramApprovalTestBase):
    def test_formatted_empty_when_no_data(self):
        request = self._create_approval_request()

        self.assertFalse(request.telegram_data_formatted)

    def test_formatted_generates_html(self):
        data = {
            "partner_fx_name": "Test Partner",
            "amount": "1500.00",
        }

        request = self._create_approval_request({"telegram_data": data})

        self.assertTrue(request.telegram_data_formatted)
        self.assertIn("<table", request.telegram_data_formatted)
        self.assertIn("</table>", request.telegram_data_formatted)

    def test_formatted_contains_values(self):
        data = {
            "partner_fx_name": "Customer XYZ",
            "amount": "2500.75",
            "payment_method": "TC",
        }

        request = self._create_approval_request({"telegram_data": data})

        self.assertIn("Customer XYZ", request.telegram_data_formatted)
        self.assertIn("2500.75", request.telegram_data_formatted)
        self.assertIn("TC", request.telegram_data_formatted)

    def test_formatted_contains_spanish_labels(self):
        data = {
            "partner_fx_name": "Test",
            "product_category": "Agroquimicos",
            "cfdi_use": "G03",
            "company": "LMMR",
            "partner_cn_name": "CN Test",
            "payment_method": "Transferencia",
            "date": "2024-01-15",
            "amount": "1000",
        }

        request = self._create_approval_request({"telegram_data": data})

        self.assertIn("Billed to", request.telegram_data_formatted)
        self.assertIn("Product category", request.telegram_data_formatted)
        self.assertIn("CFDI use", request.telegram_data_formatted)
        self.assertIn("Company", request.telegram_data_formatted)
        self.assertIn("Payment applied to", request.telegram_data_formatted)
        self.assertIn("Payment method", request.telegram_data_formatted)
        self.assertIn("Date", request.telegram_data_formatted)
        self.assertIn("Amount", request.telegram_data_formatted)

    def test_formatted_escapes_html_in_values(self):
        data = {
            "partner_fx_name": "<script>alert('xss')</script>",
            "amount": "1000",
        }

        request = self._create_approval_request({"telegram_data": data})

        self.assertNotIn("<script>", request.telegram_data_formatted)
        self.assertIn("&lt;script&gt;", request.telegram_data_formatted)

    def test_formatted_skips_absent_keys(self):
        data = {
            "partner_fx_name": "Only This",
        }

        request = self._create_approval_request({"telegram_data": data})

        self.assertIn("Only This", request.telegram_data_formatted)
        self.assertNotIn("CFDI use", request.telegram_data_formatted)
        self.assertNotIn("Payment method", request.telegram_data_formatted)

    def test_formatted_hides_internal_id_fields(self):
        data = {
            "partner_fx_name": "Visible Partner",
            "partner_fx_id": 42,
            "partner_cn_id": 99,
            "cfdi_use_code": "G03",
        }

        request = self._create_approval_request({"telegram_data": data})

        self.assertIn("Visible Partner", request.telegram_data_formatted)
        self.assertNotIn("partner_fx_id", request.telegram_data_formatted)
        self.assertNotIn("partner_cn_id", request.telegram_data_formatted)
        self.assertNotIn("cfdi_use_code", request.telegram_data_formatted)

    def test_formatted_especie_schema(self):
        data = {
            "partner_fx_name": "Especie Partner",
            "product_category": "VEHICULOS",
            "partner_cn_name": "CN Especie",
            "date": "2024-03-10",
            "amount": "75000",
            "product_reference": "174",
        }

        request = self._create_approval_request({"telegram_data": data})

        self.assertIn("Product reference", request.telegram_data_formatted)
        self.assertIn("174", request.telegram_data_formatted)
        self.assertNotIn("CFDI use", request.telegram_data_formatted)
        self.assertNotIn("Company", request.telegram_data_formatted)
        self.assertNotIn("Payment method", request.telegram_data_formatted)

    def test_formatted_recomputes_on_data_change(self):
        request = self._create_approval_request(
            {"telegram_data": {"partner_fx_name": "Original"}}
        )

        self.assertIn("Original", request.telegram_data_formatted)

        request.telegram_data = {"partner_fx_name": "Updated"}

        self.assertIn("Updated", request.telegram_data_formatted)
        self.assertNotIn("Original", request.telegram_data_formatted)
