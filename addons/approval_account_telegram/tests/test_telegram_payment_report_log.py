from odoo.exceptions import AccessError
from odoo.libs.json import dumps as json_dumps
from odoo.tests import TransactionCase
from odoo.tests.common import new_test_user

from odoo.addons.approval_account_telegram.models.telegram_payment_report_log import (
    TelegramPaymentReportLog,
)


class TestFormatPaymentDetailsHtml(TransactionCase):
    def test_full_paya_dict_renders_all_known_bullets(self):
        data = {
            "partner_fx_name": "Cliente Ejemplo SA",
            "product_category": "AGROQUIMICOS",
            "cfdi_use": "GASTOS EN GENERAL",
            "payment_method": "TRANSFERENCIA",
            "company": "LMMR",
            "partner_cn_name": "Fidel Mendoza Guadian",
            "date": "2026-05-12",
            "amount": 6370.0,
        }
        result = TelegramPaymentReportLog._format_payment_details_html(data)
        self.assertTrue(result.startswith("<ul>"))
        self.assertTrue(result.endswith("</ul>"))
        self.assertIn(
            "<li><strong>Invoice To:</strong> Cliente Ejemplo SA</li>", result
        )
        self.assertIn(
            "<li><strong>Product Category:</strong> AGROQUIMICOS</li>", result
        )
        self.assertIn("<li><strong>CFDI Use:</strong> GASTOS EN GENERAL</li>", result)
        self.assertIn("<li><strong>Payment Method:</strong> TRANSFERENCIA</li>", result)
        self.assertIn("<li><strong>Company:</strong> LMMR</li>", result)
        self.assertIn(
            "<li><strong>Apply Payment To:</strong> Fidel Mendoza Guadian</li>", result
        )
        self.assertIn("<li><strong>Payment Date:</strong> 2026-05-12</li>", result)
        self.assertIn("<li><strong>Amount:</strong> $6,370.00</li>", result)

    def test_especie_dict_includes_product_reference(self):
        data = {
            "partner_fx_name": "Cliente Especie",
            "product_category": "VEHICULOS",
            "partner_cn_name": "Recibe Bien",
            "product_reference": "174",
            "date": "2024-06-15",
            "amount": 1500.50,
        }
        result = TelegramPaymentReportLog._format_payment_details_html(data)
        self.assertIn("<li><strong>Product Reference:</strong> 174</li>", result)
        self.assertNotIn("CFDI Use", result)
        self.assertNotIn("Payment Method", result)
        self.assertNotIn("Company", result)

    def test_missing_keys_are_silently_skipped(self):
        result = TelegramPaymentReportLog._format_payment_details_html({})
        self.assertEqual(result, "<ul></ul>")

    def test_amount_formats_with_thousands_separator(self):
        result = TelegramPaymentReportLog._format_payment_details_html(
            {"amount": 1234567.8}
        )
        self.assertIn("<li><strong>Amount:</strong> $1,234,567.80</li>", result)

    def test_untrusted_value_is_html_escaped(self):
        payload = "<img src=x onerror=alert(1)>"
        result = TelegramPaymentReportLog._format_payment_details_html(
            {"partner_fx_name": payload}
        )
        self.assertNotIn(payload, result)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", result)

    def test_helper_matches_compute_output(self):
        data = {
            "partner_fx_name": "ACME",
            "product_category": "AGROQUIMICOS",
            "amount": 100.0,
        }
        log = self.env["telegram.payment.report.log"].create(
            {
                "payment_details": json_dumps(data),
            }
        )
        expected = TelegramPaymentReportLog._format_payment_details_html(data)
        self.assertEqual(log.payment_details_display, expected)


class TestPaymentReportLogAccess(TransactionCase):
    def _make_log(self):
        return self.env["telegram.payment.report.log"].create(
            {"amount": 100.0, "payment_details": json_dumps({"amount": 100.0})}
        )

    def test_plain_employee_cannot_read_payment_log(self):
        log = self._make_log()
        employee = new_test_user(
            self.env, login="taaa2_employee", groups="base.group_user"
        )
        with self.assertRaises(AccessError):
            log.with_user(employee).read(["payment_details", "amount"])

    def test_system_user_can_read_payment_log(self):
        log = self._make_log()
        admin = self.env.ref("base.user_admin")
        data = log.with_user(admin).read(["amount"])
        self.assertEqual(data[0]["amount"], 100.0)
