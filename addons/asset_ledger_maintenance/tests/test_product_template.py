from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestProductTemplate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ProductTemplate = cls.env["product.template"]

    def test_maintenance_ok_requires_serial_tracking(self):
        with self.assertRaises(ValidationError) as cm:
            self.ProductTemplate.create(
                {
                    "name": "Test Equipment",
                    "maintenance_ok": True,
                    "is_storable": True,
                    "tracking": "lot",
                }
            )

        self.assertIn("By Unique Serial Number", str(cm.exception))

    def test_create_maintenance_product_with_serial_tracking(self):
        product = self.ProductTemplate.create(
            {
                "name": "Test Equipment",
                "maintenance_ok": True,
                "is_storable": True,
                "tracking": "serial",
            }
        )

        self.assertTrue(product.maintenance_ok)
        self.assertEqual(product.tracking, "serial")

    def test_create_non_maintenance_product_without_serial(self):
        product = self.ProductTemplate.create(
            {
                "name": "Regular Product",
                "maintenance_ok": False,
                "is_storable": True,
                "tracking": "lot",
            }
        )

        self.assertFalse(product.maintenance_ok)
        self.assertEqual(product.tracking, "lot")

    def test_update_maintenance_ok_validates_tracking(self):
        product = self.ProductTemplate.create(
            {
                "name": "Test Product",
                "maintenance_ok": False,
                "is_storable": True,
                "tracking": "lot",
            }
        )

        with self.assertRaises(ValidationError):
            product.maintenance_ok = True
