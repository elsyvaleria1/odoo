from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDecimalPrecisionAudit(TransactionCase):
    def test_negative_digits_rejected_on_create(self):
        with self.assertRaises(ValidationError):
            self.env["decimal.precision"].create(
                {"name": "audit_dp_negative_create", "digits": -1}
            )

    def test_negative_digits_rejected_on_write(self):
        precision = self.env["decimal.precision"].create(
            {"name": "audit_dp_negative_write", "digits": 2}
        )
        with self.assertRaises(ValidationError):
            precision.write({"digits": -1})

    def test_get_precision_unknown_application_warns(self):
        Precision = self.env["decimal.precision"]
        name = "audit_dp_unknown_application"
        self.env.registry.clear_cache("stable")
        with self.assertLogs(
            "odoo.addons.base.models.decimal_precision", "WARNING"
        ) as capture:
            self.assertEqual(Precision.get_precision(name), 2)
        self.assertIn(name, capture.output[0])

    def test_get_precision_reflects_write(self):
        Precision = self.env["decimal.precision"]
        name = "audit_dp_cache"
        precision = Precision.create({"name": name, "digits": 2})
        self.assertEqual(Precision.get_precision(name), 2)
        precision.write({"digits": 5})
        self.assertEqual(Precision.get_precision(name), 5)

    def test_uom_rounding_follows_precision_create_and_unlink(self):
        Precision = self.env["decimal.precision"]
        uom = self.env["uom.uom"].search([], limit=1)
        Precision.search([("name", "=", "Product Unit")]).unlink()
        self.assertEqual(uom.rounding, 0.01)

        created = Precision.create({"name": "Product Unit", "digits": 4})
        self.assertEqual(uom.rounding, 0.0001)

        created.unlink()
        self.assertEqual(uom.rounding, 0.01)
