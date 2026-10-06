from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import create_test_template


@tagged("post_install", "-at_install")
class TestAssetAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.asset_user = cls.env["res.users"].create(
            {
                "name": "Fleet clerk",
                "login": "asset_access_probe",
                "group_ids": [
                    (4, cls.env.ref("asset_ledger.group_asset_user").id),
                    (4, cls.env.ref("asset_ledger.group_enable_fleet_assets").id),
                ],
            }
        )
        cls.template = create_test_template(
            cls.env,
            name="Unrelated consumable",
            list_price=100.0,
        )

    def test_an_asset_user_may_read_product_templates(self):
        as_user = self.template.with_user(self.asset_user)
        self.assertEqual(as_user.name, "Unrelated consumable")

    def test_an_asset_user_may_not_rewrite_product_templates(self):
        as_user = self.template.with_user(self.asset_user)
        with self.assertRaises(AccessError):
            as_user.write({"list_price": 1.0})

    def test_an_asset_manager_may_configure_asset_models(self):
        manager = self.env["res.users"].create(
            {
                "name": "Fleet administrator",
                "login": "asset_access_manager_probe",
                "group_ids": [
                    (4, self.env.ref("asset_ledger.group_asset_manager").id),
                ],
            }
        )
        self.template.with_user(manager).write({"fuel_tank_capacity": 80.0})
        self.assertEqual(self.template.fuel_tank_capacity, 80.0)


@tagged("post_install", "-at_install")
class TestLedgerWritesThroughTheLot(TransactionCase):
    """The ledger fields live on resource.asset; a stock user who may edit the
    serial but holds no right on the asset still writes them through the lot."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stock_user = cls.env["res.users"].create(
            {
                "name": "Warehouse only",
                "login": "warehouse_only",
                "group_ids": [
                    (4, cls.env.ref("base.group_user").id),
                    (4, cls.env.ref("stock.group_stock_user").id),
                ],
            }
        )
        template = create_test_template(
            cls.env, name="Ledger truck", asset_kind="vehicle", tracking="serial"
        )
        cls.lot = cls.env["product.trace"].create(
            {
                "name": "LEDGER-ACCESS-1",
                "product_id": template.product_variant_id.id,
                "company_id": cls.env.company.id,
            }
        )

    def test_a_stock_user_writes_the_ledger_fields_through_the_lot(self):
        with self.assertRaises(AccessError):
            self.lot.asset_id.with_user(self.stock_user).write({"location": "Bay 1"})
        lot = self.lot.with_user(self.stock_user)
        lot.write({"location": "Bay 1", "value_original": 42000.0})
        self.assertEqual(self.lot.asset_id.location, "Bay 1")
        self.assertEqual(self.lot.asset_id.value_original, 42000.0)
        self.assertEqual(lot.value_original, 42000.0)
