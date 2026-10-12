from odoo.tests.common import TransactionCase

from odoo.addons.asset_ledger.tests.common import create_test_product


class ProductAssetRemoteCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        cls.km_uom = cls.env.ref("base.product_uom_km", raise_if_not_found=False)
        if not cls.km_uom:
            cls.km_uom = cls.env["uom.uom"].create(
                {
                    "name": "km",
                    "relative_factor": 1000,
                    "relative_uom_id": cls.env.ref("base.product_uom_meter").id,
                }
            )

        cls.product = create_test_product(
            cls.env,
            name="Test Vehicle Product",
            type="consu",
            tracking="serial",
            asset_kind="vehicle",
        )

        cls.config = cls.env["device.profile"].create(
            {
                "name": "Asset Test Config",
                "auth_type": "bearer",
                "auth_token": "test_token_asset",
            }
        )
