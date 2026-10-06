from odoo.tests import Form, TransactionCase


class TestProductTrace(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ProductTrace = cls.env["product.trace"]
        cls.StockLocation = cls.env["stock.location"]
        cls.ProductProduct = cls.env["product.product"]

        cls.product = cls.ProductProduct.create(
            {
                "name": "Test Equipment",
                "is_storable": True,
                "tracking": "serial",
                "maintenance_ok": True,
            }
        )

        cls.storage_location = cls.StockLocation.create(
            {
                "name": "Storage Location",
                "usage": "internal",
                "deployed_location": False,
                "maintenance_location": False,
            }
        )

        cls.deployed_location = cls.StockLocation.create(
            {
                "name": "Deployed Location",
                "usage": "internal",
                "deployed_location": True,
                "maintenance_location": False,
            }
        )

        cls.maintenance_location = cls.StockLocation.create(
            {
                "name": "Maintenance Workshop",
                "usage": "internal",
                "deployed_location": False,
                "maintenance_location": True,
            }
        )

    def test_equipment_in_storage(self):
        lot = self.ProductTrace.create(
            {
                "name": "SERIAL001",
                "product_id": self.product.id,
                "location_id": self.storage_location.id,
            }
        )

        self.assertTrue(lot.is_in_storage)
        self.assertFalse(lot.is_deployed)
        self.assertFalse(lot.is_in_maintenance)

    def test_equipment_deployed(self):
        lot = self.ProductTrace.create(
            {
                "name": "SERIAL002",
                "product_id": self.product.id,
                "location_id": self.deployed_location.id,
            }
        )

        self.assertTrue(lot.is_deployed)
        self.assertFalse(lot.is_in_storage)
        self.assertFalse(lot.is_in_maintenance)

    def test_equipment_in_maintenance(self):
        lot = self.ProductTrace.create(
            {
                "name": "SERIAL003",
                "product_id": self.product.id,
                "location_id": self.maintenance_location.id,
            }
        )

        self.assertTrue(lot.is_in_maintenance)
        self.assertFalse(lot.is_deployed)
        self.assertFalse(lot.is_in_storage)

    def test_location_change_updates_state(self):
        lot = self.ProductTrace.create(
            {
                "name": "SERIAL004",
                "product_id": self.product.id,
                "location_id": self.storage_location.id,
            }
        )

        self.assertTrue(lot.is_in_storage)

        lot.location_id = self.deployed_location

        self.assertTrue(lot.is_deployed)
        self.assertFalse(lot.is_in_storage)

        lot.location_id = self.maintenance_location

        self.assertTrue(lot.is_in_maintenance)
        self.assertFalse(lot.is_deployed)

    def test_maintenance_state_none_for_non_maintenance_products(self):
        regular_product = self.ProductProduct.create(
            {
                "name": "Regular Product",
                "is_storable": True,
                "tracking": "serial",
                "maintenance_ok": False,
            }
        )

        lot = self.ProductTrace.create(
            {
                "name": "SERIAL005",
                "product_id": regular_product.id,
                "location_id": self.storage_location.id,
            }
        )

        self.assertEqual(lot.maintenance_state, "none")
        self.assertFalse(lot.maintenance_ok)

    def test_maintenance_state_good_for_new_equipment(self):
        lot = self.ProductTrace.create(
            {
                "name": "SERIAL006",
                "product_id": self.product.id,
                "location_id": self.storage_location.id,
            }
        )

        self.assertEqual(lot.maintenance_state, "good")
        self.assertTrue(lot.maintenance_ok)

    def test_maintenance_state_no_crash_on_new_record(self):
        form = Form(self.ProductTrace)
        form.product_id = self.product
        form.name = "SERIAL-NEWID"
        lot = form.save()
        self.assertEqual(lot.maintenance_state, "good")

    def test_maintenance_count_fields(self):
        lot = self.ProductTrace.create(
            {
                "name": "SERIAL007",
                "product_id": self.product.id,
                "location_id": self.storage_location.id,
            }
        )

        self.assertEqual(lot.asset_id.maintenance_count, 0)
        self.assertEqual(lot.asset_id.maintenance_plan_count, 0)
