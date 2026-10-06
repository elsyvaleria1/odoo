from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTreeTriggers(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        kind = cls.env.ref("resource_asset.kind_vehicle")
        cls.brand_a, cls.brand_b = cls.env["res.partner"].create(
            [
                {"name": "Tree Motors A", "is_manufacturer": True, "is_company": True},
                {"name": "Tree Motors B", "is_manufacturer": True, "is_company": True},
            ]
        )
        cls.model_a, cls.model_b = cls.env["product.product"].create(
            [
                {
                    "name": "Tree A",
                    "type": "consu",
                    "asset_kind_id": kind.id,
                    "manufacturer_id": cls.brand_a.id,
                    "vehicle_model_year": "2020",
                },
                {
                    "name": "Tree B",
                    "type": "consu",
                    "asset_kind_id": kind.id,
                    "manufacturer_id": cls.brand_b.id,
                    "vehicle_model_year": "2022",
                },
            ]
        )
        cls.asset = cls.env["resource.asset"].create(
            {"name": "Tree vehicle", "kind_id": kind.id}
        )
        cls.vehicle = cls.env["resource.asset.vehicle"].browse(cls.asset.id)

    def test_a_write_through_the_root_reaches_the_vehicle_dependents(self):
        self.assertEqual(self.vehicle._get_concrete()._name, "resource.asset.vehicle")
        self.assertFalse(self.vehicle.model_year)
        self.assertFalse(self.vehicle.manufacturer_id)

        self.asset._write_concrete({"product_id": self.model_a.id})
        self.assertEqual(self.vehicle.manufacturer_id, self.brand_a)
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(self.vehicle.model_year, 2020)

        self.asset._write_concrete({"product_id": self.model_b.id})
        self.assertEqual(self.vehicle.manufacturer_id, self.brand_b)
